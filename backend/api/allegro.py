"""
Allegro API client — authorization-code OAuth + order fetching.
Sandbox: allegro.pl.allegrosandbox.pl
Production: allegro.pl

Tokens are kept in memory and persisted to the data volume (allegro_token.json,
0600) so a container restart does not require re-authorizing. The access token is
refreshed with the refresh token once it is close to expiry.
"""
import json
import logging
import math
import os
import asyncio
import time
import httpx
from typing import List
from models.order import Order, OrderItem
import uuid

import store

logger = logging.getLogger("packing.allegro")

SANDBOX = os.getenv("ALLEGRO_SANDBOX", "true").lower() == "true"
BASE_URL = "https://allegro.pl.allegrosandbox.pl" if SANDBOX else "https://allegro.pl"
API_URL = "https://api.allegro.pl.allegrosandbox.pl" if SANDBOX else "https://api.allegro.pl"

CLIENT_ID = os.getenv("ALLEGRO_CLIENT_ID", "")
CLIENT_SECRET = os.getenv("ALLEGRO_CLIENT_SECRET", "")

REQUEST_TIMEOUT = float(os.getenv("ALLEGRO_TIMEOUT", "30"))
REDIRECT_URI = os.getenv("ALLEGRO_REDIRECT_URI", "http://localhost:3001/api/orders/auth/callback")

# In-memory cache, backed by TOKEN_FILE so restarts keep the authorization.
TOKEN_FILE = store.DATA_DIR / "allegro_token.json"
_token: str | None = None
_refresh_token: str | None = None
_expires_at: float = 0.0
# Refresh must not run twice in parallel for one expiry.
_token_lock = asyncio.Lock()


class AllegroError(RuntimeError):
    """Allegro answered, but not with what we asked for (or did not answer at all)."""


class AllegroNotAuthorized(AllegroError):
    """No usable access token — the operator has to authorize first."""


def _load_stored_token() -> None:
    """Pick up the persisted token once per process (or after a refresh)."""
    global _token, _refresh_token, _expires_at
    if _token or _refresh_token:
        return
    try:
        data = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(data, dict):
        return
    access_token = data.get("access_token")
    refresh_token = data.get("refresh_token")
    if any(value is not None and (not isinstance(value, str) or not value.strip())
           for value in (access_token, refresh_token)):
        return
    try:
        expires_at = float(data.get("expires_at") or 0.0)
    except (TypeError, ValueError, OverflowError):
        return
    if not math.isfinite(expires_at) or expires_at < 0:
        return
    _token = access_token
    _refresh_token = refresh_token
    _expires_at = expires_at


def _store_token(payload: dict) -> None:
    global _token, _refresh_token, _expires_at
    _token = payload.get("access_token")
    if payload.get("refresh_token"):
        _refresh_token = payload["refresh_token"]
    expires_in = payload.get("expires_in")
    # No expires_in means the expiry is unknown; treat the token as non-expiring.
    _expires_at = time.time() + float(expires_in) if expires_in else 0.0

    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_FILE.with_name(TOKEN_FILE.name + ".tmp")
    file_descriptor = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        json.dump(
            {"access_token": _token, "refresh_token": _refresh_token, "expires_at": _expires_at},
            handle,
        )
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, TOKEN_FILE)


def _forget_token() -> None:
    global _token, _refresh_token, _expires_at
    _token = _refresh_token = None
    _expires_at = 0.0
    try:
        TOKEN_FILE.unlink()
    except OSError:
        pass


def is_authorized() -> bool:
    """True when the API can be called now or after a token refresh."""
    _load_stored_token()
    return bool(_token or _refresh_token)


async def _refresh_access_token() -> None:
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        response = await client.post(
            f"{BASE_URL}/auth/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": _refresh_token},
            auth=(CLIENT_ID, CLIENT_SECRET),
        )
    if response.status_code in (400, 401):
        _forget_token()
        raise AllegroNotAuthorized("Sesja Allegro wygasła. Kliknij 'Autoryzuj Allegro'.")
    if not response.is_success:
        raise AllegroError(f"Allegro refresh token {response.status_code}: {response.text[:300]}")
    _store_token(response.json())


async def _access_token() -> str:
    """Return a valid access token, refreshing it when it is about to expire."""
    _load_stored_token()
    if _token and (_expires_at == 0.0 or time.time() < _expires_at - 60):
        return _token
    if not _refresh_token:
        raise AllegroNotAuthorized("Allegro nie jest autoryzowane. Kliknij 'Autoryzuj Allegro'.")
    async with _token_lock:
        # Another request may have refreshed while this one waited for the lock.
        if _token and _expires_at != 0.0 and time.time() < _expires_at - 60:
            return _token
        if not _refresh_token:
            raise AllegroNotAuthorized("Allegro nie jest autoryzowane. Kliknij 'Autoryzuj Allegro'.")
        await _refresh_access_token()
    return _token


def to_http_exception(exc: AllegroError):
    """Map an Allegro failure onto the right HTTP status for the browser."""
    from fastapi import HTTPException

    if isinstance(exc, AllegroNotAuthorized):
        return HTTPException(status_code=401, detail=str(exc))
    return HTTPException(status_code=502, detail=f"Allegro: {exc}")



def auth_url(state: str) -> str:
    return (
        f"{BASE_URL}/auth/oauth/authorize"
        f"?response_type=code"
        f"&client_id={CLIENT_ID}"
        f"&redirect_uri={REDIRECT_URI}"
        f"&state={state}"
    )


async def exchange_code(code: str):
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
        _store_token(r.json())


async def create_shipment(order, sender: dict, package: dict) -> str:
    """Create a shipment via Allegro shipment management. Returns shipment UUID."""
    token = await _access_token()

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
    token = await _access_token()
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


async def fetch_orders(limit: int = 100) -> List[Order]:
    """Fetch recent READY_FOR_PROCESSING orders from Allegro."""
    token = await _access_token()
    orders = []
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        r = await client.get(
            f"{API_URL}/order/checkout-forms",
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.allegro.public.v1+json"},
            params={"status": "READY_FOR_PROCESSING", "limit": limit},
        )
        if not r.is_success:
            raise AllegroError(f"Allegro checkout-forms {r.status_code}: {r.text[:300]}")
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
