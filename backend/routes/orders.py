import os

from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from typing import List
import httpx

import store
import api.allegro as allegro
from api.allegro import to_http_exception

router = APIRouter(prefix="/orders", tags=["orders"])

# Fields added to Order after the first releases; older records are backfilled on sync.
BACKFILL_FIELDS = (
    "delivery_method_id",
    "buyer_email",
    "buyer_phone",
    "buyer_street",
    "buyer_postal_code",
    "buyer_city",
    "buyer_country",
)

UI_BASE_URL = os.getenv("PACKING_BASE_URL", "http://localhost:3001")


@router.get("/", response_model=List[dict])
async def list_orders():
    orders = store.get_orders()
    return [o.model_dump() for o in orders.values()]


@router.get("/status")
async def state_status():
    """Health of the state file: whether records had to be skipped or repaired."""
    return store.state_status()


@router.get("/debug/allegro-orders")
async def debug_allegro_orders():
    """Dump raw order statuses from Allegro for debugging. Contains buyer PII — local use only."""
    token = allegro._token
    if not token:
        raise HTTPException(status_code=401, detail="Not authorized")
    async with httpx.AsyncClient(timeout=allegro.REQUEST_TIMEOUT) as client:
        r = await client.get(
            f"{allegro.API_URL}/order/checkout-forms",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"},
            params={"limit": 20},
        )
        if not r.is_success:
            raise HTTPException(status_code=502, detail=f"Allegro {r.status_code}: {r.text[:300]}")
        return r.json()


@router.post("/sync")
async def sync_from_allegro():
    """Pull new READY_FOR_PROCESSING orders from Allegro and add any not already stored."""
    try:
        new_orders = await allegro.fetch_orders()
    except allegro.AllegroError as exc:
        raise to_http_exception(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Brak łączności z Allegro: {exc}")

    archived_allegro_ids = store.archived_allegro_ids()

    def mutate(state):
        index = {v["allegro_id"]: k for k, v in state["orders"].items()}
        added = 0
        updated = 0
        for order in new_orders:
            if order.allegro_id in archived_allegro_ids:
                continue
            payload = order.model_dump(mode="json")
            key = index.get(order.allegro_id)
            if key is None:
                state["orders"][order.id] = payload
                index[order.allegro_id] = order.id
                added += 1
                continue
            stored = state["orders"][key]
            dirty = False
            for field in BACKFILL_FIELDS:
                if stored.get(field) is None and payload.get(field) is not None:
                    stored[field] = payload[field]
                    dirty = True
            if dirty:
                updated += 1
        return added, updated

    added, updated = store.transact(mutate)
    return {"added": added, "updated": updated, "total": len(store.get_orders())}


@router.post("/zakoncz-dzien")
async def zakoncz_dzien():
    """Archive all done orders (tombstone their allegro_ids) and remove them from state."""
    archived = store.archive_done_orders()
    return {"archived": archived}


@router.get("/archive")
async def get_archive():
    """Archived orders as [{allegro_id, archived_at}, ...]."""
    return store.get_archive()


# --- Allegro OAuth2 authorization code flow ---


@router.get("/auth/status")
async def auth_status():
    return {"authorized": allegro._token is not None}


@router.get("/auth/token")
async def auth_token():
    return {"token": allegro._token}


@router.get("/auth/url")
async def auth_url():
    return {"url": allegro.auth_url()}


@router.get("/auth/callback")
async def auth_callback(code: str | None = None, error: str | None = None):
    if error:
        raise HTTPException(status_code=400, detail=f"Allegro odrzuciło autoryzację: {error}")
    if not code:
        raise HTTPException(status_code=400, detail="Brak parametru 'code' w callbacku Allegro.")
    try:
        await allegro.exchange_code(code)
    except allegro.AllegroError as exc:
        raise to_http_exception(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Brak łączności z Allegro: {exc}")
    return RedirectResponse(f"{UI_BASE_URL}/")
