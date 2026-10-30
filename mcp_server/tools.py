"""MCP tool implementations.

Each method is a tool: the docstring is what the model sees, the name is what it
calls. Every method maps onto an existing HTTP route of the app — the route is
named in the docstring and in docs/mcp-server.md.

Tools never invent an endpoint and never touch the state file directly.
"""
import asyncio
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from .client import PackingClient, PackingError
from .config import Settings
from .printing import print_pdf, validate_print_request

DocumentKind = Literal["auto", "custom", "sales", "combined"]
OrderStatus = Literal["pending", "picking", "packing", "done"]
ParcelSize = Literal["A", "B", "C"]
PageSize = Literal["A6", "A4"]

MAX_CUSTOM_DOC_BYTES = 20 * 1024 * 1024


def _slug(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "-" for char in value)
    return safe.strip("-")[:60] or "document"


def _write_pdf(content: bytes, directory: str, stem: str) -> Path:
    target_dir = Path(directory).expanduser() if directory else Path(tempfile.mkdtemp(prefix="packing-labels-"))
    target_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    fd, filename = tempfile.mkstemp(prefix=f"{_slug(stem)}-{stamp}-", suffix=".pdf", dir=target_dir)
    path = Path(filename)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def _summarize(order: dict) -> dict:
    return {
        "id": order.get("id"),
        "allegro_id": order.get("allegro_id"),
        "buyer_name": order.get("buyer_name"),
        "status": order.get("status"),
        "courier": order.get("courier"),
        "delivery_type": order.get("delivery_type"),
        "parcel_size": order.get("parcel_size"),
        "shipment_id": order.get("shipment_id"),
        "tracking_number": order.get("tracking_number"),
    }


class PackingTools:
    """The tool surface of the Packing MCP server."""

    def __init__(self, client: PackingClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    # ---- connection and app state ----

    async def get_app_health(self) -> dict:
        """Check that the Packing app is running. Calls GET /health (no access token).

        Returns {"status": "ok"|"degraded", "state": {...}}. Use it first when any
        other tool reports that the API cannot be reached.
        """
        return await self.client.health()

    async def get_state_status(self) -> dict:
        """Read the state-file health and whether the app is in dry-run mode.

        Calls GET /api/orders/status. "ok" false means the app quarantined or
        repaired records; "dry_run" true means sample orders and blank PDF labels
        are in use and no real shipment will be bought.
        """
        return await self.client.state_status()

    # ---- Allegro sync and end of day ----

    async def sync_orders(self) -> dict:
        """Fetch new Allegro orders — the sidebar's "Pobierz zamówienia" button.

        Calls POST /api/orders/sync. Returns {"added", "updated", "total"}; "added"
        is the number of new orders placed in the pending queue. Fails with a 401
        message when the Allegro account is not authorized (use
        get_allegro_auth_url) and with HTTP 502 when Allegro itself fails.
        """
        return await self.client.sync_orders()

    async def get_allegro_auth_status(self) -> dict:
        """Report whether the app holds an Allegro authorization.

        Calls GET /api/orders/auth/status -> {"authorized": bool}.
        """
        return await self.client.auth_status()

    async def get_allegro_auth_url(self) -> dict:
        """Get the Allegro authorization URL for the operator to open in a browser.

        Calls GET /api/orders/auth/url -> {"url": ...}. The tool cannot complete
        OAuth itself: show the URL to the user and ask them to approve access,
        then call get_allegro_auth_status to confirm.
        """
        return await self.client.auth_url()

    async def seed_mock_orders(self) -> dict:
        """Add three sample orders (dry-run instances only).

        Calls POST /api/orders/seed-mock. The API answers 409 outside
        PACKING_SHIPMENT_DRY_RUN=true because those orders carry invented Allegro
        ids and cannot be shipped.
        """
        return await self.client.seed_mock_orders()

    async def finish_day(self) -> dict:
        """Archive every finished order — the sidebar's "Zakończ dzień" button.

        Calls POST /api/orders/zakoncz-dzien. Only orders in the "done" status are
        archived and removed from the queue; returns {"archived": n}.
        """
        return await self.client.finish_day()

    async def list_archive(self) -> dict:
        """List archived Allegro order ids with their archival timestamps.

        Calls GET /api/orders/archive. Archived ids are never synced again.
        """
        entries = await self.client.get_archive()
        return {"count": len(entries), "archive": entries}

    # ---- queues and orders ----

    async def list_orders(
        self,
        status: OrderStatus | None = None,
        courier: str | None = None,
        search: str | None = None,
        product: str | None = None,
    ) -> dict:
        """List the orders in the queues, optionally filtered.

        Calls GET /api/orders/. "status" filters the sidebar queues: pending
        (Oczekujące), picking (Kompletowanie), packing (Pakowanie), done (Gotowe).
        "courier" matches the delivery category or courier name (for example
        "inpost_locker" or "Paczkomat"). "search" matches buyer name, address or
        Allegro order id. "product" is a case-insensitive substring of a line
        item name, SKU or offer id, filtered server-side. Other filters are local.
        Queue counts always describe all orders, regardless of filters.
        """
        orders = await self.client.get_orders()
        selected = await self.client.get_orders(product=product.strip()) if product and product.strip() else orders
        if status is not None:
            selected = [order for order in selected if order.get("status") == status]
        if courier:
            needle = courier.strip().casefold()
            selected = [
                order for order in selected
                if needle in str(order.get("courier") or "").casefold()
                or needle in str(order.get("delivery_type") or "").casefold()
            ]
        if search:
            needle = search.strip().casefold()
            selected = [
                order for order in selected
                if any(
                    needle in str(order.get(field) or "").casefold()
                    for field in ("buyer_name", "buyer_address", "allegro_id", "id")
                )
            ]
        counts: dict[str, int] = {"pending": 0, "picking": 0, "packing": 0, "done": 0}
        for order in orders:
            key = order.get("status")
            if key in counts:
                counts[key] += 1
        return {"count": len(selected), "queue_counts": counts, "orders": selected}

    async def get_order(self, order_id: str) -> dict:
        """Read one order by its local id (the "id" field from list_orders).

        Calls GET /api/orders/ and selects the record; there is no single-order
        route in the API. Fails with a clear message when the id is unknown.
        """
        order = await self._find_order(order_id)
        return order

    async def mark_order_done(self, order_id: str) -> dict:
        """Finish a packed order — the ✓ button in the packing card.

        Calls POST /api/orders/{id}/done. The order moves to the "done" queue and
        is archived by finish_day. Reverting later is possible with undo_order_done.
        """
        return await self.client.order_action(order_id, "done")

    async def undo_order_done(self, order_id: str) -> dict:
        """Move a finished order back to packing — the "cofnij" button in Gotowe.

        Calls POST /api/orders/{id}/undo-done.
        """
        return await self.client.order_action(order_id, "undo-done")

    async def revert_order_to_pending(self, order_id: str) -> dict:
        """Send an order back to the pending queue and detach it from its picking list.

        Calls POST /api/orders/{id}/revert-pending. Use it when an order was
        mis-sorted; it applies to packing and picking orders.
        """
        return await self.client.order_action(order_id, "revert-pending")

    async def set_parcel_size(self, order_id: str, parcel_size: ParcelSize) -> dict:
        """Choose the InPost locker size (A, B or C) for a Paczkomat order.

        Calls PATCH /api/orders/{id}/parcel-size. Only allowed for InPost locker
        orders that have no shipment yet; the chosen size decides the package
        dimensions sent to Allegro when the label is created.
        """
        return await self.client.set_parcel_size(order_id, parcel_size)

    # ---- picking lists ----

    async def list_picking_lists(self) -> dict:
        """List picking lists with their ids, names and member order ids.

        Calls GET /api/picking-lists.
        """
        lists = await self.client.get_picking_lists()
        return {"count": len(lists), "picking_lists": lists}

    async def get_picking_list(self, picking_list_id: str) -> dict:
        """Show one picking list with its orders and a consolidated product list.

        Calls GET /api/picking-lists plus GET /api/orders/ and aggregates the items
        the way the app's printed picking list does.
        """
        lists = await self.client.get_picking_lists()
        selected = next((entry for entry in lists if entry.get("id") == picking_list_id), None)
        if selected is None:
            raise PackingError(f"Picking list {picking_list_id} does not exist. Use list_picking_lists.")
        orders = await self.client.get_orders()
        index = {order.get("id"): order for order in orders}
        members = [index[order_id] for order_id in selected.get("order_ids", []) if order_id in index]
        products: dict[str, int] = {}
        for order in members:
            for item in order.get("items") or []:
                name = str(item.get("name"))
                products[name] = products.get(name, 0) + int(item.get("quantity") or 0)
        return {
            "id": selected.get("id"),
            "name": selected.get("name"),
            "order_count": len(members),
            "items": [{"name": name, "quantity": qty} for name, qty in sorted(products.items())],
            "orders": [_summarize(order) for order in members],
        }

    async def create_picking_list(self, order_ids: list[str], name: str = "") -> dict:
        """Group pending orders into a picking list — "Utwórz listę kompletowania".

        Calls POST /api/picking-lists with the selected order ids. Members move to
        the picking status and are detached from any other list. An empty name gets
        the app's default ("Lista N").
        """
        if not order_ids:
            raise PackingError("order_ids must contain at least one order id.")
        return await self.client.create_picking_list(order_ids, name)

    async def rename_picking_list(self, picking_list_id: str, name: str) -> dict:
        """Rename a picking list — the pencil button in Kompletowanie.

        Calls PATCH /api/picking-lists/{id} with the new name; the member orders
        are not touched.
        """
        if not name.strip():
            raise PackingError("name must not be empty.")
        return await self.client.rename_picking_list(picking_list_id, name.strip())

    async def revert_picking_list(self, picking_list_id: str) -> dict:
        """Undo a picking list and return its orders to pending.

        Calls POST /api/picking-lists/{id}/revert. Orders that were already finished
        keep the "done" status.
        """
        return await self.client.revert_picking_list(picking_list_id)

    async def start_packing(self, picking_list_id: str) -> dict:
        """Move a picking list's orders to the packing queue — "Rozpocznij pakowanie".

        Calls POST /api/picking-lists/{id}/start-packing -> {"status", "order_ids"}.
        """
        return await self.client.start_packing(picking_list_id)

    # ---- shipments, labels and documents ----

    async def get_shipment_info(self, order_id: str) -> dict:
        """Check whether an order already has a shipment and read its tracking number.

        Calls GET /api/print/orders/{id}/shipment -> {"shipment_id", "tracking_number"}.
        Safe to call repeatedly: it never buys a shipment.
        """
        return await self.client.shipment_info(order_id)

    async def create_label(
        self,
        order_id: str,
        length: float | None = None,
        width: float | None = None,
        height: float | None = None,
        weight: float | None = None,
    ) -> dict:
        """Buy (create) the carrier shipment for an order — the first step of printing a label.

        Calls POST /api/print/orders/{id}/label. The app creates a shipment at most
        once per order: an order that already has one returns the existing id and
        no new shipment is bought. Dimensions default to the shipping settings;
        for InPost lockers they come from the order's parcel size (A/B/C). Returns
        {"shipment_id", "tracking_number"}.

        A label only becomes billable when the courier scans the parcel, so this is
        safe to automate — but it is still a real carrier booking, not a test.
        """
        dimensions = {"length": length, "width": width, "height": height, "weight": weight}
        return await self.client.create_label(order_id, dimensions)

    async def download_label(self, order_id: str, output_path: str | None = None) -> dict:
        """Download an existing shipment label PDF without creating or printing anything.

        Calls GET /api/print/orders/{id}/label. Requires a shipment (call
        create_label first); the API answers 409 otherwise. The PDF is written to
        output_path, or to PACKING_LABEL_DIR (default: a private packing-labels-*
        folder in the system temp directory). Returns {"path", "bytes"}.
        """
        order = await self._find_order(order_id)
        content = await self.client.label_pdf(order_id)
        path = self._save(content, order_id, output_path, f"label-{order.get('allegro_id') or order_id}")
        return {"path": str(path), "bytes": len(content), "order_id": order_id}

    async def print_label(
        self,
        order_id: str,
        printer: str | None = None,
        copies: int = 1,
        create_if_missing: bool = True,
        length: float | None = None,
        width: float | None = None,
        height: float | None = None,
        weight: float | None = None,
    ) -> dict:
        """Print a shipment label on the local CUPS printer, creating the shipment if needed.

        Creates the shipment first when the order has none (POST
        /api/print/orders/{id}/label, same at-most-once rule as create_label), then
        downloads the PDF (GET /api/print/orders/{id}/label) and sends it to `lp`.

        The printer argument wins over the PACKING_PRINTER environment variable; with
        neither set, CUPS uses its default queue. Returns the saved PDF path, the
        CUPS job id, the printer, and the shipment id/tracking number.
        With PACKING_PRINT_DIR set, saves a virtual print instead of invoking lp;
        print_path identifies that PDF. This does NOT prevent shipment purchases.
        """
        validate_print_request(copies)
        order = await self._find_order(order_id)
        shipment_created = False
        shipment = await self.client.shipment_info(order_id)
        shipment_id = shipment.get("shipment_id")
        tracking_number = shipment.get("tracking_number")

        if not shipment_id:
            if not create_if_missing:
                raise PackingError(
                    f"Order {order_id} has no shipment yet. Call create_label first or leave "
                    "create_if_missing enabled."
                )
            created = await self.client.create_label(
                order_id,
                {"length": length, "width": width, "height": height, "weight": weight},
            )
            shipment_id = created.get("shipment_id")
            tracking_number = created.get("tracking_number") or tracking_number
            shipment_created = True

        content = await self.client.label_pdf(order_id)
        allegro_id = order.get("allegro_id") or order_id
        path = self._save(content, order_id, None, f"label-{allegro_id}")
        job = await asyncio.to_thread(
            print_pdf, path,
            printer=printer or self.settings.printer or None,
            copies=copies,
            title=f"Label {allegro_id}",
        )
        return {
            "order_id": order_id,
            "allegro_id": order.get("allegro_id"),
            "path": str(path),
            "bytes": len(content),
            "printer": job.printer,
            "job_id": job.job_id,
            "print_path": job.output_path,
            "print_dry_run": job.output_path is not None,
            "shipment_id": shipment_id,
            "tracking_number": tracking_number,
            "shipment_created_now": shipment_created,
            "message": (
                (f"Label saved to {job.output_path}" if job.output_path else f"Label queued on {job.printer}")
                + (f" as job {job.job_id}" if job.job_id else "")
                + (" (new shipment created)" if shipment_created else " (existing shipment reused)")
            ),
        }

    async def download_document(
        self,
        order_id: str,
        document: DocumentKind = "auto",
        output_path: str | None = None,
    ) -> dict:
        """Download the customer document PDF for an order without printing it.

        "auto" mirrors the packing card: GET /api/print/custom-doc when a custom
        document is configured, otherwise GET /api/print/orders/{id}/document
        (sales document). "custom" forces GET /api/print/custom-doc?order_id=...,
        "sales" forces the sales document and "combined" merges both via
        GET /api/print/orders/{id}/combined. Returns {"path", "bytes", "document"}.
        """
        order = await self._find_order(order_id)
        kind = await self._resolve_document(document)
        content = await self.client.document_pdf(order_id, kind)
        path = self._save(content, order_id, output_path, f"{kind}-{order.get('allegro_id') or order_id}")
        return {"path": str(path), "bytes": len(content), "document": kind, "order_id": order_id}

    async def print_document(
        self,
        order_id: str,
        document: DocumentKind = "auto",
        printer: str | None = None,
        copies: int = 1,
    ) -> dict:
        """Print the customer document for an order on the local CUPS printer.

        Same document resolution as download_document: GET /api/print/custom-doc
        when a custom document is configured, otherwise GET
        /api/print/orders/{id}/document, or the explicit kind. The PDF is fetched
        with the matching route and sent to `lp` (PACKING_PRINTER or the CUPS
        default queue). PACKING_PRINT_DIR instead saves a virtual print and
        returns print_path, with print_dry_run=true and no CUPS job id.
        """
        validate_print_request(copies)
        order = await self._find_order(order_id)
        kind = await self._resolve_document(document)
        content = await self.client.document_pdf(order_id, kind)
        allegro_id = order.get("allegro_id") or order_id
        path = self._save(content, order_id, None, f"{kind}-{allegro_id}")
        job = await asyncio.to_thread(
            print_pdf, path,
            printer=printer or self.settings.printer or None,
            copies=copies,
            title=f"{kind.title()} {allegro_id}",
        )
        return {
            "order_id": order_id,
            "document": kind,
            "path": str(path),
            "bytes": len(content),
            "printer": job.printer,
            "job_id": job.job_id,
            "print_path": job.output_path,
            "print_dry_run": job.output_path is not None,
            "message": (
                f"Document saved to {job.output_path}" if job.output_path
                else f"Document queued on {job.printer}" + (f" as job {job.job_id}" if job.job_id else "")
            ),
        }

    # ---- settings ----

    async def get_shipment_settings(self) -> dict:
        """Read the default package dimensions, label page size and legacy sender data.

        Calls GET /api/print/shipment-settings.
        """
        return await self.client.get_shipment_settings()

    async def update_shipment_settings(
        self,
        length: float | None = None,
        width: float | None = None,
        height: float | None = None,
        weight: float | None = None,
        page_size: PageSize | None = None,
    ) -> dict:
        """Change the default package size or label page size (Settings → Wysyłka).

        Calls GET then POST /api/print/shipment-settings, keeping the existing
        sender block. Dimensions in centimetres (0 < length/width/height <= 500),
        weight in kilograms (0 < weight <= 100); page_size is A6 or A4.
        """
        if all(value is None for value in (length, width, height, weight, page_size)):
            raise PackingError("Nothing to change: pass at least one of length, width, height, weight, page_size.")
        current = await self.client.get_shipment_settings()
        package = dict(current.get("package") or {})
        package["type"] = package.get("type") or "PACKAGE"
        package["label_format"] = "PDF"
        for key, value in (("length", length), ("width", width), ("height", height), ("weight", weight)):
            if value is not None:
                package[key] = value
        if page_size is not None:
            package["page_size"] = page_size
        body = {"sender": current.get("sender") or {}, "package": package}
        await self.client.save_shipment_settings(body)
        return {"status": "saved", "shipment_settings": body}

    async def get_invoice_settings(self) -> dict:
        """Read which fields the sales document shows plus its free-text footer.

        Calls GET /api/print/invoice-settings.
        """
        return await self.client.get_invoice_settings()

    async def update_invoice_settings(
        self,
        show_buyer_name: bool | None = None,
        show_buyer_address: bool | None = None,
        show_items: bool | None = None,
        show_price: bool | None = None,
        show_courier: bool | None = None,
        show_pickup_point: bool | None = None,
        show_allegro_id: bool | None = None,
        free_text: str | None = None,
    ) -> dict:
        """Change the sales-document fields (Settings → Dokumenty).

        Calls GET then POST /api/print/invoice-settings; omitted switches keep their
        current value. free_text is the footer, at most 160 characters.
        """
        overrides = {
            "show_buyer_name": show_buyer_name,
            "show_buyer_address": show_buyer_address,
            "show_items": show_items,
            "show_price": show_price,
            "show_courier": show_courier,
            "show_pickup_point": show_pickup_point,
            "show_allegro_id": show_allegro_id,
            "free_text": free_text,
        }
        if all(value is None for value in overrides.values()):
            raise PackingError("Nothing to change: pass at least one setting.")
        body = dict(await self.client.get_invoice_settings())
        body.update({key: value for key, value in overrides.items() if value is not None})
        await self.client.save_invoice_settings(body)
        return {"status": "saved", "invoice_settings": body}

    async def get_document_settings(self) -> dict:
        """Read the custom-document settings: every template and the active selection.

        Calls GET /api/print/document-settings. Templates are the full block lists
        the editor works with; use list_document_templates for a compact view.
        """
        return await self.client.get_document_settings()

    async def list_document_templates(self) -> dict:
        """List the custom-document templates and show which one is active.

        Calls GET /api/print/document-settings and reduces it to id, name, block
        count and the active flag.
        """
        settings = await self.client.get_document_settings()
        active = (settings.get("profiles") or {}).get("default", {}).get("active_template_id")
        templates = [
            {
                "id": template.get("id"),
                "name": template.get("name"),
                "blocks": len(template.get("blocks") or []),
                "active": template.get("id") == active,
            }
            for template in settings.get("templates") or []
        ]
        return {"count": len(templates), "active_template_id": active, "templates": templates}

    async def select_document_template(self, template_id: str) -> dict:
        """Choose which custom-document template is printed while packing.

        Calls POST /api/print/document-templates/{id}/select. The template must
        already exist (see list_document_templates).
        """
        return await self.client.select_document_template(template_id)

    async def get_custom_doc_info(self) -> dict:
        """Check whether a printable custom document is available and where it comes from.

        Calls GET /api/print/custom-doc/info -> {"available", "source"
        ("upload"|"template"), "upload_available", "size"}.
        """
        return await self.client.custom_doc_info()

    async def upload_custom_doc(self, file_path: str) -> dict:
        """Upload or replace the custom document PDF (Settings → Dokumenty).

        Calls POST /api/print/custom-doc with a multipart upload of the file at
        file_path. The app accepts a valid PDF up to 20 MB; an encrypted or broken
        PDF is rejected with HTTP 400.
        """
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise PackingError(f"File not found: {path}")
        content = path.read_bytes()
        if len(content) > MAX_CUSTOM_DOC_BYTES:
            raise PackingError(f"{path.name} is larger than the 20 MB limit.")
        if not content.startswith(b"%PDF-"):
            raise PackingError(f"{path.name} is not a PDF file.")
        result = await self.client.upload_custom_doc(path.name, content)
        return {**result, "file": str(path)}

    async def delete_custom_doc(self) -> dict:
        """Delete the uploaded custom document PDF (Settings → Dokumenty).

        Calls DELETE /api/print/custom-doc. Succeeds even when nothing was uploaded.
        A template-based custom document is not affected; this removes only the
        uploaded file.
        """
        return await self.client.delete_custom_doc()

    # ---- internals ----

    async def _find_order(self, order_id: str) -> dict:
        orders = await self.client.get_orders()
        for order in orders:
            if order.get("id") == order_id:
                return order
        raise PackingError(
            f"Order {order_id} is not in the queue. Use list_orders to get current ids; "
            "finished orders leave the queue when finish_day archives them."
        )

    async def _resolve_document(self, document: DocumentKind) -> str:
        if document not in ("auto", "custom", "sales", "combined"):
            raise PackingError('document must be "auto", "custom", "sales" or "combined".')
        if document != "auto":
            return document
        info = await self.client.custom_doc_info()
        return "custom" if info.get("available") else "sales"

    def _save(self, content: bytes, order_id: str, output_path: str | None, stem: str) -> Path:
        if output_path:
            path = Path(output_path).expanduser()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            return path
        return _write_pdf(content, self.settings.label_dir, stem)
