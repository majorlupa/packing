import logging
import os
import secrets
import time
import threading
from html import escape

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import List
import httpx
from starlette.concurrency import run_in_threadpool

import store
import api.allegro as allegro
from api.allegro import to_http_exception
from localization import negotiate_language, t

router = APIRouter(prefix="/orders", tags=["orders"])
logger = logging.getLogger("packing.orders")

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
# Each pending flow carries its own language and expires after ten minutes.
_oauth_states: dict[str, tuple[str, float]] = {}
_oauth_states_lock = threading.Lock()


def _prune_oauth_states(now: float) -> None:
    """Called with the state lock held."""
    for state, (_, deadline) in list(_oauth_states.items()):
        if now > deadline:
            del _oauth_states[state]

# Browser-facing page for a failed authorization. The message comes from a query
# parameter, so it is HTML-escaped — never injected as markup.
OAUTH_ERROR_PAGE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: system-ui, 'Segoe UI', Arial, sans-serif; background: #f6f7f9;
         color: #1a1a1a; margin: 0; display: grid; place-items: center; min-height: 100vh; }}
  main {{ background: #fff; border: 1px solid #e5e7eb; border-radius: 10px;
          padding: 28px 32px; max-width: 460px; box-shadow: 0 1px 3px rgba(0,0,0,.06); }}
  h1 {{ font-size: 18px; margin: 0 0 12px; }}
  p {{ line-height: 1.55; margin: 0 0 16px; }}
  a {{ color: #1d4ed8; }}
</style>
</head>
<body>
<main>
  <h1>{title}</h1>
  <p>{message}</p>
  <p><a href="{back_url}">{back_label}</a></p>
</main>
</body>
</html>
"""


def _oauth_error_page(language: str, message: str, status_code: int = 400) -> HTMLResponse:
    """Localized HTML page for a failed OAuth callback, in the given language."""
    html = OAUTH_ERROR_PAGE.format(
        lang=escape(language),
        title=escape(t("oauth.callback_title", lang=language)),
        message=escape(message),
        back_url=escape(f"{UI_BASE_URL}/", quote=True),
        back_label=escape(t("oauth.callback_back", lang=language)),
    )
    return HTMLResponse(content=html, status_code=status_code, headers={"Cache-Control": "no-store"})


@router.get("/", response_model=List[dict])
def list_orders():
    orders = store.get_orders()
    return [{**o.model_dump(), "delivery_type": "inpost_locker" if o.is_inpost_locker else "courier"}
            for o in orders.values()]


@router.get("/status")
def state_status():
    """Health of the state file: whether records had to be skipped or repaired.

    ``dry_run`` travels with it so the browser only offers test-only actions
    (seeding sample orders) on an instance that is actually in dry-run mode.
    """
    status = store.state_status()
    return {**status, "dry_run": allegro.dry_run_enabled()}


@router.post("/sync")
async def sync_from_allegro():
    """Pull new READY_FOR_PROCESSING orders from Allegro and add any not already stored."""
    try:
        new_orders = await allegro.fetch_orders()
    except allegro.AllegroNotAuthorized as exc:
        # Only an *absent* authorization falls back to sample orders, and only in
        # dry run. Any other upstream failure must reach the operator: silently
        # substituting three fake orders for a real sync would hide a broken
        # Allegro connection behind a healthy-looking "added: 3".
        if allegro.dry_run_enabled() and not await run_in_threadpool(allegro.is_authorized):
            logger.warning("Brak autoryzacji Allegro w trybie dry run: używam zamówień testowych.")
            new_orders = allegro._generate_mock_orders()
        else:
            raise to_http_exception(exc)
    except (allegro.AllegroError, httpx.HTTPError) as exc:
        if isinstance(exc, allegro.AllegroError):
            raise to_http_exception(exc)
        raise HTTPException(status_code=502, detail=t("common.allegro_unreachable", error=exc))

    def mutate(state):
        # Read the archive inside the transaction: a concurrent "end of day" must not be missed.
        archived_allegro_ids = {entry["allegro_id"] for entry in state["archive"] if entry.get("allegro_id")}
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

    added, updated = await run_in_threadpool(store.transact, mutate)
    orders = await run_in_threadpool(store.get_orders)
    return {"added": added, "updated": updated, "total": len(orders)}


@router.post("/seed-mock")
def seed_mock_orders():
    """Seed sample test orders into the queue.

    Dry-run only. These records carry fabricated Allegro ids, so they cannot be
    shipped and would otherwise sit in the real queue looking like paid orders.
    """
    if not allegro.dry_run_enabled():
        raise HTTPException(
            status_code=409,
            detail=t("orders.seed_mock_disabled"),
        )
    mock_orders = allegro._generate_mock_orders()

    def mutate(state):
        archived_allegro_ids = {entry["allegro_id"] for entry in state["archive"] if entry.get("allegro_id")}
        index = {v["allegro_id"]: k for k, v in state["orders"].items()}
        added = 0
        for order in mock_orders:
            if order.allegro_id in archived_allegro_ids:
                continue
            if order.allegro_id not in index:
                state["orders"][order.id] = order.model_dump(mode="json")
                index[order.allegro_id] = order.id
                added += 1
        return added

    added = store.transact(mutate)
    return {"added": added, "total": len(store.get_orders())}


@router.post("/zakoncz-dzien")
def zakoncz_dzien():
    """Archive all done orders (tombstone their allegro_ids) and remove them from state."""
    archived = store.archive_done_orders()
    return {"archived": archived}


@router.get("/archive")
def get_archive():
    """Archived orders as [{allegro_id, archived_at}, ...]."""
    return store.get_archive()


# --- Allegro OAuth2 authorization code flow ---


@router.get("/auth/status")
def auth_status():
    return {"authorized": allegro.is_authorized()}


@router.get("/auth/url")
def auth_url(request: Request):
    state = secrets.token_urlsafe(32)
    # Remember the language of the request that started the flow: the callback
    # is a browser navigation and may arrive with a different Accept-Language.
    language = negotiate_language(request.headers.get("accept-language"))
    with _oauth_states_lock:
        now = time.monotonic()
        _prune_oauth_states(now)
        _oauth_states[state] = (language, now + 600)
    return {"url": allegro.auth_url(state)}


@router.get("/auth/callback")
async def auth_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
):
    with _oauth_states_lock:
        _prune_oauth_states(time.monotonic())
        flow = _oauth_states.pop(state, None) if state else None
    if flow is None:
        # No valid flow to take a language from: use this request's own header.
        language = negotiate_language(request.headers.get("accept-language"))
        return _oauth_error_page(language, t("oauth.invalid_state", lang=language))

    # From here the flow is genuine: answer in the language it was started with.
    language, _ = flow
    if error:
        return _oauth_error_page(language, t("oauth.rejected", lang=language, error=error))
    if not code:
        return _oauth_error_page(language, t("oauth.missing_code", lang=language))
    try:
        await allegro.exchange_code(code)
    except allegro.AllegroError as exc:
        raise to_http_exception(exc)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=t("common.allegro_unreachable", error=exc))
    return RedirectResponse(f"{UI_BASE_URL}/")
