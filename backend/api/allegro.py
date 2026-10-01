"""
Allegro API client — authorization-code OAuth + order fetching.
Sandbox: allegro.pl.allegrosandbox.pl
Production: allegro.pl
"""
import os
import asyncio
import logging
import httpx
from typing import List
from models.order import Order, OrderItem
import uuid

logger = logging.getLogger("packing.allegro")

SANDBOX = os.getenv("ALLEGRO_SANDBOX", "true").lower() == "true"
BASE_URL = "https://allegro.pl.allegrosandbox.pl" if SANDBOX else "https://allegro.pl"
API_URL = "https://api.allegro.pl.allegrosandbox.pl" if SANDBOX else "https://api.allegro.pl"

CLIENT_ID = os.getenv("ALLEGRO_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("ALLEGRO_CLIENT_SECRET", "")

REQUEST_TIMEOUT = float(os.getenv("ALLEGRO_TIMEOUT", "30"))

# Simple in-memory token cache
REDIRECT_URI = os.getenv("ALLEGRO_REDIRECT_URI", "http://localhost:3001/api/orders/auth/callback")

_token: str | None = None


class AllegroError(RuntimeError):
    """Allegro answered, but not with what we asked for (or did not answer at all)."""


class AllegroNotAuthorized(AllegroError):
    """No usable access token — the operator has to authorize first."""


def _get_token() -> str:
    if _token is None:
        raise AllegroNotAuthorized("Allegro nie jest autoryzowane. Kliknij 'Autoryzuj Allegro'.")
    return _token


def to_http_exception(exc: AllegroError):
    """Map an Allegro failure onto the right HTTP status for the browser."""
    from fastapi import HTTPException

    if isinstance(exc, AllegroNotAuthorized):
        return HTTPException(status_code=401, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Allegro: {exc}")



def auth_url() -> str:
    return (
        f"{BASE_URL}/auth/oauth/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
    )


async def exchange_code(code: str):
    global _token
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.post(
            f"{BASE_URL}/auth/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": REDIRECT_URI,
            },
            auth=(CLIENT_ID, CLIENT_SECRET),
        )
        if not r.is_success:
            raise AllegroError(f"Allegro token exchange {r.status_code}: {r.text[:300]}")
        _token = r.json()["access_token"]


async def create_shipment(order, sender: dict, package: dict) -> str:
    """Create a shipment via Allegro shipment management. Returns shipment UUID."""
    token = _get_token()

    delivery_method_id = order.delivery_method_id
    if not delivery_method_id:
        # Fetch directly from Allegro if not stored
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as _c:
            _r = await _c.get(
                f"{API_URL}/order/checkout-forms/{order.allegro_id}",
                headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"},
            )
            if _r.is_success:
                form = _r.json()
                delivery_method_id = form.get("delivery", {}).get("method", {}).get("id")
                print(f"[shipment] checkout-form method id={delivery_method_id}", flush=True)
            else:
                print(f"[shipment] checkout-form fetch failed {_r.status_code}", flush=True)
    if not delivery_method_id:
        raise AllegroError("Brak delivery_method_id — kurier nieznany. Sprawdź czy zamówienie ma wybraną metodę dostawy.")
    if not sender.get("street"):
        raise AllegroError("Brak adresu nadawcy. Uzupełnij dane w Ustawienia → Wysyłka.")

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

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
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
            raise AllegroError(f"Allegro create shipment {r.status_code}: {r.text[:300]}")
        command_id = r.json().get("commandId")
        if not command_id:
            raise AllegroError("Brak commandId w odpowiedzi Allegro.")

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
                raise AllegroError(f"Allegro shipment status {r.status_code}: {r.text[:300]}")
            data = r.json()
            status = data.get("status")
            if status == "SUCCESS":
                return data["shipmentId"]
            if status == "ERROR":
                errors = data.get("errors", [])
                msg = errors[0].get("message", "unknown") if errors else "unknown"
                raise AllegroError(f"Allegro shipment creation failed: {msg}")

    raise AllegroError("Przekroczono czas oczekiwania na utworzenie przesyłki.")


async def download_label(shipment_id: str, page_size: str = "A6") -> bytes:
    """Download label PDF for a shipment management UUID."""
    token = _get_token()
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.post(
            f"{API_URL}/shipment-management/label",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/vnd.allegro.public.v1+json",
                "Accept": "application/octet-stream, application/vnd.allegro.public.v1+json",
            },
            json={"shipmentIds": [shipment_id], "pageSize": page_size},
        )
        if r.status_code == 204:
            raise AllegroError("Allegro nie ma jeszcze etykiety dla tej przesyłki.")
        if not r.is_success:
            raise AllegroError(f"Allegro label API {r.status_code}: {r.text[:300]}")
        return r.content


# Some forms can be paginated forever only in theory; a day's packing fits in one page.
MAX_SYNC_PAGES = 10


async def fetch_orders(limit: int = 100) -> List[Order]:
    """Fetch recent READY_FOR_PROCESSING orders from Allegro, page by page."""
    token = _get_token()
    orders: List[Order] = []
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"}
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        for page in range(MAX_SYNC_PAGES):
            r = await client.get(
                f"{API_URL}/order/checkout-forms",
                headers=headers,
                params={"status": "READY_FOR_PROCESSING", "limit": limit, "offset": page * limit},
            )
            if not r.is_success:
                raise AllegroError(f"Allegro checkout-forms {r.status_code}: {r.text[:300]}")
            forms = r.json().get("checkoutForms") or []
            for form in forms:
                try:
                    orders.append(_order_from_form(form))
                except (AttributeError, KeyError, TypeError, ValueError) as exc:
                    # One malformed order must not fail the whole sync.
                    logger.warning("pomijam zamówienie z Allegro: %s", exc)
            if len(forms) < limit:
                break
    return orders


def _order_from_form(form: dict) -> Order:
    buyer = form.get("buyer") or {}
    delivery_root = form.get("delivery") or {}
    delivery = delivery_root.get("address") or {}
    items = [
        OrderItem(
            name=li["offer"]["name"],
            quantity=li["quantity"],
            unit_price=float(li["price"]["amount"]) if li.get("price") else None,
        )
        for li in form.get("lineItems") or []
    ]
    return Order(
        id=str(uuid.uuid4()),
        allegro_id=form["id"],
        buyer_name=f"{buyer.get('firstName', '')} {buyer.get('lastName', '')}".strip(),
        buyer_address=f"{delivery.get('street', '')} {delivery.get('zipCode', '')} {delivery.get('city', '')}".strip(),
        items=items,
        courier=(delivery_root.get("method") or {}).get("name"),
        pickup_point=(delivery_root.get("pickupPoint") or {}).get("id"),
        delivery_method_id=(delivery_root.get("method") or {}).get("id"),
        buyer_email=buyer.get("email"),
        buyer_phone=buyer.get("phoneNumber"),
        buyer_street=delivery.get("street"),
        buyer_postal_code=delivery.get("zipCode"),
        buyer_city=delivery.get("city"),
        buyer_country=delivery.get("countryCode", "PL"),
    )
