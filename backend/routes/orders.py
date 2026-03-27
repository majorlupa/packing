from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from typing import List
import store
import api.allegro as allegro

router = APIRouter(prefix="/orders", tags=["orders"])


@router.get("/", response_model=List[dict])
async def list_orders():
    orders = store.get_orders()
    return [o.model_dump() for o in orders.values()]


@router.get("/debug/allegro-orders")
async def debug_allegro_orders():
    """Dump raw order statuses from Allegro for debugging."""
    import httpx
    token = allegro._token
    if not token:
        raise HTTPException(status_code=401, detail="Not authorized")
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{allegro.API_URL}/order/checkout-forms",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"},
            params={"limit": 20},
        )
        return r.json()


@router.post("/sync")
async def sync_from_allegro():
    """Pull new READY_FOR_PROCESSING orders from Allegro and add any not already stored."""
    try:
        new_orders = await allegro.fetch_orders()
    except RuntimeError as e:
        raise HTTPException(status_code=401, detail=str(e))

    existing = store.get_orders()
    existing_allegro_ids = {o.allegro_id for o in existing.values()}
    archived_allegro_ids = set(store.get_archive())

    added = 0
    updated = 0
    allegro_map = {o.allegro_id: o for o in new_orders}
    for order in new_orders:
        if order.allegro_id in archived_allegro_ids:
            continue
        if order.allegro_id not in existing_allegro_ids:
            store.save_order(order)
            added += 1
        else:
            # Backfill fields added after initial sync
            existing_order = next(o for o in existing.values() if o.allegro_id == order.allegro_id)
            dirty = False
            for field in ("delivery_method_id", "buyer_email", "buyer_phone", "buyer_street", "buyer_postal_code", "buyer_city", "buyer_country"):
                if getattr(existing_order, field, None) is None and getattr(order, field, None) is not None:
                    setattr(existing_order, field, getattr(order, field))
                    dirty = True
            if dirty:
                store.save_order(existing_order)
                updated += 1

    return {"added": added, "updated": updated, "total": len(store.get_orders())}


@router.post("/zakoncz-dzien")
async def zakoncz_dzien():
    """Archive all done orders (tombstone their allegro_ids) and remove them from state."""
    archived = store.archive_done_orders()
    return {"archived": archived}


@router.get("/archive")
async def get_archive():
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
async def auth_callback(code: str):
    try:
        await allegro.exchange_code(code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token exchange failed: {e}")
    return RedirectResponse("http://localhost:3001/")
