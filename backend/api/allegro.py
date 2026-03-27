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


async def create_shipment(order, sender: dict, package: dict) -> str:
    """Create a shipment via Allegro shipment management. Returns shipment UUID."""
    import asyncio
    token = _get_token()

    delivery_method_id = order.delivery_method_id
    if not delivery_method_id:
        # Fetch directly from Allegro if not stored
        async with httpx.AsyncClient() as _c:
            _r = await _c.get(
                f"{API_URL}/order/checkout-forms/{order.allegro_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"},
            )
            if _r.is_success:
                form = _r.json()
                delivery_method_id = form.get("delivery", {}).get("method", {}).get("id")
                print(f"[shipment] checkout-form delivery={form.get('delivery')}", flush=True)
            else:
                print(f"[shipment] checkout-form fetch failed {_r.status_code}: {_r.text[:200]}", flush=True)
        print(f"[shipment] delivery_method_id={delivery_method_id}", flush=True)
    if not delivery_method_id:
        raise RuntimeError("Brak delivery_method_id — kurier nieznany. Sprawdź czy zamówienie ma wybraną metodę dostawy.")
    if not sender.get("street"):
        raise RuntimeError("Brak adresu nadawcy. Uzupełnij dane w Ustawienia → Wysyłka.")

    payload = {
        "input": {
            "deliveryMethodId": delivery_method_id,
            "sender": {
                "name": sender.get("name") or None,
                "company": sender.get("company") or None,
                "street": sender["street"],
                "postalCode": sender["postal_code"],
                "city": sender["city"],
                "countryCode": sender.get("country_code", "PL"),
                "email": sender["email"],
                "phone": sender["phone"],
            },
            "receiver": {
                "name": order.buyer_name or None,
                "street": order.buyer_street or "",
                "postalCode": order.buyer_postal_code or "",
                "city": order.buyer_city or "",
                "countryCode": order.buyer_country or "PL",
                "email": order.buyer_email or "",
                "phone": order.buyer_phone or "",
            },
            "packages": [{
                "type": package.get("type", "PACKAGE"),
                "length": {"value": package.get("length", 30), "unit": "CENTIMETER"},
                "width":  {"value": package.get("width",  20), "unit": "CENTIMETER"},
                "height": {"value": package.get("height", 15), "unit": "CENTIMETER"},
                "weight": {"value": str(package.get("weight", 1.0)), "unit": "KILOGRAMS"},
            }],
            "labelFormat": package.get("label_format", "PDF"),
        }
    }
    if package.get("label_format", "PDF") == "PDF":
        payload["input"]["pageSize"] = package.get("page_size", "A6")

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API_URL}/shipment-management/shipments/create-commands",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.allegro.public.v1+json",
                "Accept": "application/vnd.allegro.public.v1+json",
            },
            json=payload,
        )
        if not r.is_success:
            raise RuntimeError(f"Allegro create shipment {r.status_code}: {r.text}")
        command_id = r.json().get("commandId")
        if not command_id:
            raise RuntimeError("Brak commandId w odpowiedzi Allegro.")

        # Poll for result
        for _ in range(15):
            await asyncio.sleep(2)
            r = await client.get(
                f"{API_URL}/shipment-management/shipments/create-commands/{command_id}",
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/vnd.allegro.public.v1+json",
                },
            )
            if not r.is_success:
                raise RuntimeError(f"Allegro shipment status {r.status_code}: {r.text}")
            data = r.json()
            status = data.get("status")
            if status == "SUCCESS":
                return data["shipmentId"]
            if status == "ERROR":
                errors = data.get("errors", [])
                msg = errors[0].get("message", "unknown") if errors else "unknown"
                raise RuntimeError(f"Allegro shipment creation failed: {msg}")

    raise RuntimeError("Przekroczono czas oczekiwania na utworzenie przesyłki.")


async def download_label(shipment_id: str) -> bytes:
    """Download label PDF for a shipment management UUID."""
    token = _get_token()
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{API_URL}/shipment-management/label",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.allegro.public.v1+json",
                "Accept": "application/octet-stream, application/vnd.allegro.public.v1+json",
            },
            json={"shipmentIds": [shipment_id], "pageSize": "A6"},
        )
        if r.status_code == 204:
            raise RuntimeError("Allegro nie ma jeszcze etykiety dla tej przesyłki.")
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
            delivery_method_id = delivery_root.get("method", {}).get("id")
            orders.append(Order(
                id=str(uuid.uuid4()),
                allegro_id=form["id"],
                buyer_name=f"{buyer.get('firstName', '')} {buyer.get('lastName', '')}".strip(),
                buyer_address=f"{delivery.get('street', '')} {delivery.get('zipCode', '')} {delivery.get('city', '')}".strip(),
                items=items,
                courier=courier,
                pickup_point=pickup_point,
                delivery_method_id=delivery_method_id,
                buyer_email=buyer.get("email"),
                buyer_phone=buyer.get("phoneNumber"),
                buyer_street=delivery.get("street"),
                buyer_postal_code=delivery.get("zipCode"),
                buyer_city=delivery.get("city"),
                buyer_country=delivery.get("countryCode", "PL"),
            ))
    return orders
