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
    for order in new_orders:
        if order.allegro_id not in existing_allegro_ids and order.allegro_id not in archived_allegro_ids:
            store.save_order(order)
            added += 1

    return {"added": added, "total": len(store.get_orders())}


@router.post("/zakoncz-dzien")
async def zakoncz_dzien():
    """Archive all done orders (tombstone their allegro_ids) and remove them from state."""
    archived = store.archive_done_orders()
    return {"archived": archived}


@router.get("/archive")
async def get_archive():
    return store.get_archive()


# --- Allegro OAuth2 authorization code flow ---

@router.post("/dev/seed")
async def seed_test_orders():
    """Add fake orders for testing the workflow."""
    import uuid
    from models.order import OrderItem
    test_orders = [
        {"buyer_name": "Jan Kowalski", "buyer_address": "ul. Piotrkowska 1, 90-001 Łódź",
         "items": [{"name": "Klocki Lego City 60388", "quantity": 1, "unit_price": 129.99}]},
        {"buyer_name": "Anna Nowak", "buyer_address": "ul. Brzezińska 12, 92-103 Łódź",
         "items": [{"name": "Klocki Lego City 60388", "quantity": 1, "unit_price": 129.99}]},
        {"buyer_name": "Piotr Wiśniewski", "buyer_address": "ul. Zgierska 45, 91-001 Łódź",
         "items": [{"name": "Lalka Baby Born 43cm", "quantity": 1, "unit_price": 219.00}, {"name": "Ubranko Baby Born", "quantity": 2, "unit_price": 49.99}]},
        {"buyer_name": "Maria Wójcik", "buyer_address": "ul. Kilińskiego 8, 90-002 Łódź",
         "items": [{"name": "Lalka Baby Born 43cm", "quantity": 1, "unit_price": 219.00}]},
        {"buyer_name": "Tomasz Kamiński", "buyer_address": "ul. Narutowicza 22, 90-135 Łódź",
         "items": [{"name": "Puzzle 1000 el. Krajobraz", "quantity": 1, "unit_price": 64.90}]},
    ]
    from models.order import Order, OrderStatus
    added = 0
    for o in test_orders:
        order = Order(
            id=str(uuid.uuid4()),
            allegro_id=f"TEST-{uuid.uuid4().hex[:8].upper()}",
            buyer_name=o["buyer_name"],
            buyer_address=o["buyer_address"],
            items=[OrderItem(**i) for i in o["items"]],
            status=OrderStatus.pending,
        )
        store.save_order(order)
        added += 1
    return {"added": added}


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
