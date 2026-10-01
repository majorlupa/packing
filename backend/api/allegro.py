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
import io
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
    except (OSError, UnicodeError, json.JSONDecodeError):
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


def _error_messages(errors: object) -> str:
    """Join Allegro error entries, tolerating nulls, missing fields and odd shapes."""
    if not isinstance(errors, list):
        return ""
    messages = [
        entry.get("userMessage") or entry.get("message") or entry.get("code")
        for entry in errors
        if isinstance(entry, dict)
    ]
    return "; ".join(message for message in messages if isinstance(message, str))[:1000]


def _shipment_error(response: httpx.Response) -> str:
    """Prefer actionable Allegro errors without dumping a response containing addresses."""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    detail = _error_messages(payload.get("errors")) if isinstance(payload, dict) else ""
    return detail or "Sprawdź ustawienia Wysyłam z Allegro i uprawnienia aplikacji do przesyłek."


def _json_object(response: httpx.Response, what: str) -> dict:
    """Parse an Allegro body; a gateway HTML page must become a 502, not a 500."""
    try:
        payload = response.json()
    except ValueError as exc:
        raise AllegroError(f"Allegro zwróciło nieprawidłowe dane ({what}).") from exc
    if not isinstance(payload, dict):
        raise AllegroError(f"Allegro zwróciło nieprawidłowe dane ({what}).")
    return payload


DRY_RUN_PREFIX = "dry-run-"


def _dry_run_enabled() -> bool:
    """PACKING_SHIPMENT_DRY_RUN=1 exercises the label flow without buying shipments."""
    return os.getenv("PACKING_SHIPMENT_DRY_RUN", "").lower() in ("1", "true", "yes")


def _dry_run_label(page_size: str) -> bytes:
    """A real, blank PDF so the browser print flow behaves exactly as with a carrier label."""
    from pypdf import PdfWriter

    width, height = {"A4": (595, 842), "A6": (298, 420)}.get(page_size.upper(), (298, 420))
    writer = PdfWriter()
    writer.add_blank_page(width=width, height=height)
    writer.add_metadata({"/Title": "DRY RUN — testowa etykieta", "/Producer": "Weles"})
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


async def create_shipment(order, sender: dict, package: dict) -> str:
    """Create a shipment via Allegro shipment management. Returns shipment UUID."""
    if _dry_run_enabled():
        logger.warning("PACKING_SHIPMENT_DRY_RUN=1: pomijam tworzenie przesyłki w Allegro (%s)", order.allegro_id)
        return f"{DRY_RUN_PREFIX}{uuid.uuid4()}"
    token = await _access_token()

    # The legacy sender argument is retained for callers/settings compatibility.
    # Allegro owns sender/recipient addresses, pickup points, COD and carrier settings.
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.allegro.public.v1+json",
    }
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        proposal = await client.get(
            f"{API_URL}/shipment-management/delivery-proposals/{order.allegro_id}",
            headers=headers,
        )
        if proposal.status_code == 401:
            raise AllegroNotAuthorized("Sesja Allegro wygasła. Kliknij 'Autoryzuj Allegro'.")
        if not proposal.is_success:
            raise AllegroError(
                f"Nie udało się pobrać danych wysyłki z Allegro ({proposal.status_code}). "
                f"{_shipment_error(proposal)}"
            )
        suggested = _json_object(proposal, "propozycje wysyłki").get("suggestedInput")
        if not isinstance(suggested, dict):
            raise AllegroError("Allegro nie zwróciło proponowanych danych wysyłki.")
        if not isinstance(suggested.get("sender"), dict) or not suggested["sender"]:
            raise AllegroError(
                "Brak danych nadawcy w Allegro. Dodaj domyślny adres w książce adresowej "
                "Wysyłam z Allegro, a następnie spróbuj ponownie."
            )
        receiver = suggested.get("receiver")
        if not isinstance(receiver, dict) or not receiver.get("email"):
            raise AllegroError("Allegro nie zwróciło danych odbiorcy z adresem e-mail zamówienia.")

        shipment_input = dict(suggested)
        shipment_input["packages"] = [{
            "type": package.get("type", "PACKAGE"),
            "length": {"value": package.get("length", 30), "unit": "CENTIMETER"},
            "width": {"value": package.get("width", 20), "unit": "CENTIMETER"},
            "height": {"value": package.get("height", 15), "unit": "CENTIMETER"},
            "weight": {"value": package.get("weight", 1.0), "unit": "KILOGRAMS"},
        }]
        # The browser prints PDFs. Page size belongs to the label-download request.
        shipment_input["labelFormat"] = "PDF"
        payload = {"input": shipment_input}
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
            raise AllegroError(f"Allegro create shipment {r.status_code}: {_shipment_error(r)}")
        command_id = _json_object(r, "utworzenie przesyłki").get("commandId")
        if not isinstance(command_id, str) or not command_id:
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
            data = _json_object(r, "status przesyłki")
            status = data.get("status")
            if status == "SUCCESS":
                shipment_id = data.get("shipmentId")
                if not isinstance(shipment_id, str) or not shipment_id:
                    raise AllegroError("Allegro nie zwróciło identyfikatora utworzonej przesyłki.")
                return shipment_id
            if status == "ERROR":
                msg = _error_messages(data.get("errors")) or "unknown"
                raise AllegroError(f"Allegro shipment creation failed: {msg}")

    raise AllegroError("Przekroczono czas oczekiwania na utworzenie przesyłki.")


async def download_label(shipment_id: str, page_size: str = "A6") -> bytes:
    """Download label PDF for a shipment management UUID."""
    if shipment_id.startswith(DRY_RUN_PREFIX):
        logger.warning("PACKING_SHIPMENT_DRY_RUN: zwracam atrapę etykiety dla %s", shipment_id)
        return _dry_run_label(page_size)
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
        if not r.content.startswith(b"%PDF-"):
            raise AllegroError(
                "Allegro zwróciło etykietę w formacie innym niż PDF. "
                "Istniejącą etykietę ZPL pobierz w Wysyłam z Allegro; nowe etykiety w aplikacji są PDF."
            )
        return r.content


# Bound API work; reaching the cap requires an overflow probe before reporting success.
MAX_SYNC_PAGES = 10


async def fetch_orders(limit: int = 100) -> List[Order]:
    """Fetch recent READY_FOR_PROCESSING orders from Allegro, page by page."""
    token = await _access_token()
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
        else:
            # A full last page can mean exactly the cap or more orders. Probe one more item.
            r = await client.get(
                f"{API_URL}/order/checkout-forms",
                headers=headers,
                params={"status": "READY_FOR_PROCESSING", "limit": 1, "offset": MAX_SYNC_PAGES * limit},
            )
            if not r.is_success:
                raise AllegroError(f"Allegro checkout-forms {r.status_code}: {r.text[:300]}")
            if r.json().get("checkoutForms"):
                raise AllegroError(
                    f"Niepełna synchronizacja: przekroczono limit {MAX_SYNC_PAGES * limit} zamówień. "
                    "Nie zapisano wyników tej synchronizacji."
                )
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
