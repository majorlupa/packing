"""
Allegro API client — device authorization flow + order fetching.
Sandbox: allegro.pl.allegrosandbox.pl
Production: allegro.pl
"""
import os
import httpx
from typing import List
from models.order import Order, OrderItem
import uuid

SANDBOX = os.getenv("ALLEGRO_SANDBOX", "true").lower() == "true"
BASE_URL = "https://allegro.pl.allegrosandbox.pl" if SANDBOX else "https://allegro.pl"
API_URL = "https://api.allegro.pl.allegrosandbox.pl" if SANDBOX else "https://api.allegro.pl"

CLIENT_ID = os.getenv("ALLEGRO_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("ALLEGRO_CLIENT_SECRET", "")

# Simple in-memory token cache
REDIRECT_URI = "http://localhost:3001/api/orders/auth/callback"

_token: str | None = None


def _get_token() -> str:
    if _token is None:
        raise RuntimeError("Allegro not authorized. Click 'Autoryzuj Allegro' first.")
    return _token


def auth_url() -> str:
    return (
        f"{BASE_URL}/auth/oauth/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )


async def exchange_code(code: str):
    global _token
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{BASE_URL}/auth/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            auth=(CLIENT_ID, CLIENT_SECRET),
        )
        r.raise_for_status()
        _token = r.json()["access_token"]


async def get_label_for_order(allegro_order_id: str) -> bytes:
    """Fetch courier label PDF for an order via Allegro shipment management."""
    token = _get_token()
    async with httpx.AsyncClient() as client:
        # Find the shipment linked to this checkout form
        r = await client.get(
            f"{API_URL}/order/checkout-forms/{allegro_order_id}/shipments",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"},
        )
        if not r.is_success:
            raise RuntimeError(f"Allegro shipments API {r.status_code}: {r.text}")
        shipments = r.json().get("shipments", [])
        if not shipments:
            raise RuntimeError(f"No shipment found for order {allegro_order_id}")

        shipment_id = shipments[0]["id"]

        # Download the label via POST
        r = await client.post(
            f"{API_URL}/shipment-management/label",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/vnd.allegro.public.v1+json"},
            json={"shipmentIds": [shipment_id]},
        )
        if not r.is_success:
            raise RuntimeError(f"Allegro label API {r.status_code}: {r.text}")
        return r.content


async def fetch_orders() -> List[Order]:
    """Fetch recent READY_FOR_PROCESSING orders from Allegro."""
    token = _get_token()
    orders = []
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{API_URL}/order/checkout-forms",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"},
            params={"status": "READY_FOR_PROCESSING", "limit": 100},
        )
        r.raise_for_status()
        data = r.json()
        for form in data.get("checkoutForms", []):
            buyer = form.get("buyer", {})
            delivery = form.get("delivery", {}).get("address", {})
            items = [
                OrderItem(
                    name=li["offer"]["name"],
                    quantity=li["quantity"],
                    unit_price=float(li["price"]["amount"]) if li.get("price") else None,
                )
                for li in form.get("lineItems", [])
            ]
            delivery_root = form.get("delivery", {})
            courier = delivery_root.get("method", {}).get("name")
            pickup_point = delivery_root.get("pickupPoint", {}).get("id")
            orders.append(Order(
                id=str(uuid.uuid4()),
                allegro_id=form["id"],
                buyer_name=f"{buyer.get('firstName', '')} {buyer.get('lastName', '')}".strip(),
                buyer_address=f"{delivery.get('street', '')} {delivery.get('zipCode', '')} {delivery.get('city', '')}".strip(),
                items=items,
                courier=courier,
                pickup_point=pickup_point,
            ))
    return orders
