"""HTTP client for the Packing (Weles) API.

Only endpoints that really exist in the app are called; each method names the
route it uses so the mapping stays auditable against backend/routes/*.py.

The access token travels in the ``Authorization`` header only. It is never put
into an exception message, a log line or a tool result.
"""
from typing import Any

import httpx

from .config import Settings

API_PREFIX = "/api"


class PackingError(RuntimeError):
    """A failure the operator (or the calling model) can act on."""

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code


def _error_detail(payload: object) -> tuple[str, str | None]:
    """Extract (message, code) from the app's error shapes.

    The API answers either ``{"detail": "<text>"}``, the structured Allegro
    failure ``{"detail": {"code": ..., "message": ...}}`` or FastAPI's
    validation list. Unknown shapes must not leak a raw JSON dump.
    """
    if not isinstance(payload, dict):
        return "", None
    detail = payload.get("detail", payload.get("message"))
    if isinstance(detail, dict):
        code = detail.get("code")
        message = detail.get("message") or detail.get("code") or ""
        return str(message).strip(), str(code) if code else None
    if isinstance(detail, list):
        parts = []
        for entry in detail[:5]:
            if isinstance(entry, dict):
                location = ".".join(str(part) for part in entry.get("loc", ()) if part != "body")
                text = entry.get("msg") or ""
                parts.append(f"{location}: {text}" if location else str(text))
        return "; ".join(part for part in parts if part), None
    if isinstance(detail, str):
        return detail.strip(), None
    return "", None


def _error_from(response: httpx.Response) -> PackingError:
    """Turn a non-2xx response into an actionable message."""
    try:
        payload = response.json()
    except ValueError:
        payload = None
    message, code = _error_detail(payload)
    status = response.status_code

    if status == 401:
        text = (
            "The Packing API rejected the request (HTTP 401). Set PACKING_ACCESS_TOKEN to the "
            "token stored in the app's .env, then restart the MCP server."
        )
    elif status == 403:
        text = "The Packing API refused the request (HTTP 403)."
    elif status == 404:
        text = "Not found (HTTP 404)."
    elif status == 409:
        text = "The action conflicts with the current state (HTTP 409)."
    elif status == 422:
        text = "The Packing API rejected the request as invalid (HTTP 422)."
    elif status >= 500:
        text = f"The Packing API reported a failure (HTTP {status})."
    else:
        text = f"The Packing API rejected the request (HTTP {status})."

    if message:
        text = f"{text} {message}"
    if code:
        text = f"{text} [{code}]"
    return PackingError(text, status_code=status, code=code)


class PackingClient:
    """Thin async wrapper over the app's JSON and PDF endpoints."""

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None) -> None:
        self.settings = settings
        self._transport = transport

    # ---- transport ----

    def _headers(self, accept: str) -> dict[str, str]:
        headers = {"Accept": accept, "Accept-Language": self.settings.language}
        if self.settings.access_token:
            headers["Authorization"] = f"Bearer {self.settings.access_token}"
        return headers

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        files: dict | None = None,
        expect: str = "json",
        auth: bool = True,
        base: str = API_PREFIX,
    ) -> Any:
        if auth and not self.settings.access_token:
            raise PackingError(
                "PACKING_ACCESS_TOKEN is not set. Copy the token from the app's .env into the "
                "MCP server environment (see docs/mcp-server.md)."
            )
        accept = "application/pdf" if expect == "pdf" else "application/json"
        url = f"{self.settings.api_url}{base}{path}"
        try:
            async with httpx.AsyncClient(
                timeout=self.settings.timeout,
                transport=self._transport,
                follow_redirects=False,
            ) as client:
                response = await client.request(
                    method,
                    url,
                    params={key: value for key, value in (params or {}).items() if value is not None},
                    json=json,
                    files=files,
                    headers=self._headers(accept),
                )
        except httpx.HTTPError as exc:
            raise PackingError(
                f"Cannot reach the Packing API at {self.settings.api_url} "
                f"({type(exc).__name__}). Is the app running and is PACKING_API_URL correct?"
            ) from None

        if response.status_code >= 400:
            raise _error_from(response)

        if expect == "pdf":
            content = response.content
            if not content.startswith(b"%PDF-"):
                raise PackingError(
                    "The Packing API returned a response that is not a PDF "
                    f"(HTTP {response.status_code}, {len(content)} bytes)."
                )
            return content
        if expect == "none" or not response.content:
            return None
        try:
            return response.json()
        except ValueError as exc:
            raise PackingError(
                f"The Packing API returned a body that is not JSON (HTTP {response.status_code})."
            ) from exc

    # ---- status ----

    async def health(self) -> dict:
        """GET /health (public, no access token)."""
        return await self._request("GET", "/health", expect="json", auth=False, base="")

    async def state_status(self) -> dict:
        """GET /api/orders/status"""
        return await self._request("GET", "/orders/status")

    async def sync_orders(self) -> dict:
        """POST /api/orders/sync"""
        return await self._request("POST", "/orders/sync")

    async def seed_mock_orders(self) -> dict:
        """POST /api/orders/seed-mock"""
        return await self._request("POST", "/orders/seed-mock")

    async def finish_day(self) -> dict:
        """POST /api/orders/zakoncz-dzien"""
        return await self._request("POST", "/orders/zakoncz-dzien")

    async def get_archive(self) -> list:
        """GET /api/orders/archive"""
        return await self._request("GET", "/orders/archive")

    async def auth_status(self) -> dict:
        """GET /api/orders/auth/status"""
        return await self._request("GET", "/orders/auth/status")

    async def auth_url(self) -> dict:
        """GET /api/orders/auth/url"""
        return await self._request("GET", "/orders/auth/url")

    # ---- orders and queues ----

    async def get_orders(self, product: str | None = None) -> list:
        """GET /api/orders/, optionally filtering line items server-side."""
        params = {"product": product} if product else None
        return await self._request("GET", "/orders/", params=params)

    async def order_action(self, order_id: str, action: str) -> dict:
        """POST /api/orders/{id}/done | undo-done | revert-pending"""
        return await self._request("POST", f"/orders/{order_id}/{action}")

    async def set_parcel_size(self, order_id: str, parcel_size: str) -> dict:
        """PATCH /api/orders/{id}/parcel-size"""
        return await self._request(
            "PATCH", f"/orders/{order_id}/parcel-size", json={"parcel_size": parcel_size},
        )

    async def get_picking_lists(self) -> list:
        """GET /api/picking-lists"""
        return await self._request("GET", "/picking-lists")

    async def create_picking_list(self, order_ids: list[str], name: str = "") -> dict:
        """POST /api/picking-lists"""
        return await self._request("POST", "/picking-lists", json={"name": name, "order_ids": order_ids})

    async def rename_picking_list(self, picking_list_id: str, name: str) -> dict:
        """PATCH /api/picking-lists/{id}"""
        return await self._request("PATCH", f"/picking-lists/{picking_list_id}", json={"name": name})

    async def revert_picking_list(self, picking_list_id: str) -> dict:
        """POST /api/picking-lists/{id}/revert"""
        return await self._request("POST", f"/picking-lists/{picking_list_id}/revert")

    async def start_packing(self, picking_list_id: str) -> dict:
        """POST /api/picking-lists/{id}/start-packing"""
        return await self._request("POST", f"/picking-lists/{picking_list_id}/start-packing")

    # ---- shipments, labels, documents ----

    async def shipment_info(self, order_id: str) -> dict:
        """GET /api/print/orders/{id}/shipment"""
        return await self._request("GET", f"/print/orders/{order_id}/shipment")

    async def create_label(self, order_id: str, dimensions: dict | None = None) -> dict:
        """POST /api/print/orders/{id}/label"""
        return await self._request("POST", f"/print/orders/{order_id}/label", params=dimensions)

    async def label_pdf(self, order_id: str) -> bytes:
        """GET /api/print/orders/{id}/label"""
        return await self._request("GET", f"/print/orders/{order_id}/label", expect="pdf")

    async def document_pdf(self, order_id: str, kind: str) -> bytes:
        """GET /api/print/orders/{id}/document | /combined | /api/print/custom-doc"""
        if kind == "custom":
            return await self._request(
                "GET", "/print/custom-doc", params={"order_id": order_id}, expect="pdf",
            )
        route = "document" if kind == "sales" else kind
        return await self._request("GET", f"/print/orders/{order_id}/{route}", expect="pdf")

    # ---- settings ----

    async def get_shipment_settings(self) -> dict:
        """GET /api/print/shipment-settings"""
        return await self._request("GET", "/print/shipment-settings")

    async def save_shipment_settings(self, body: dict) -> dict:
        """POST /api/print/shipment-settings"""
        return await self._request("POST", "/print/shipment-settings", json=body)

    async def get_invoice_settings(self) -> dict:
        """GET /api/print/invoice-settings"""
        return await self._request("GET", "/print/invoice-settings")

    async def save_invoice_settings(self, body: dict) -> dict:
        """POST /api/print/invoice-settings"""
        return await self._request("POST", "/print/invoice-settings", json=body)

    async def get_document_settings(self) -> dict:
        """GET /api/print/document-settings"""
        return await self._request("GET", "/print/document-settings")

    async def select_document_template(self, template_id: str) -> dict:
        """POST /api/print/document-templates/{id}/select"""
        return await self._request("POST", f"/print/document-templates/{template_id}/select")

    async def custom_doc_info(self) -> dict:
        """GET /api/print/custom-doc/info"""
        return await self._request("GET", "/print/custom-doc/info")

    async def upload_custom_doc(self, filename: str, content: bytes) -> dict:
        """POST /api/print/custom-doc (multipart)"""
        return await self._request(
            "POST",
            "/print/custom-doc",
            files={"file": (filename, content, "application/pdf")},
        )

    async def delete_custom_doc(self) -> dict:
        """DELETE /api/print/custom-doc"""
        return await self._request("DELETE", "/print/custom-doc")
