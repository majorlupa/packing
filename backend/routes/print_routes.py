"""
Print routes — return PDF/HTML content for the browser to trigger printing.
Carrier label: PDF fetched from Allegro shipment management API.
Sales document: HTML rendered via Jinja2 template, browser prints.
Custom doc: user-uploaded static PDF, served as-is.
Combined: invoice rendered to PDF via weasyprint, merged with custom doc via pypdf.
"""
import asyncio
import io
import os
import shutil
import threading
from datetime import date
from pathlib import Path

import httpx
from fastapi import APIRouter, HTTPException, UploadFile, File, Query
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel, Field

import store
import api.allegro as allegro
from api.allegro import to_http_exception
from localization import current_language, date_format, t

router = APIRouter(prefix="/print", tags=["print"])

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
_jinja = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)

CUSTOM_DOC_PATH: Path = store.DATA_DIR / "custom_doc.pdf"
MAX_CUSTOM_DOC_BYTES = 20 * 1024 * 1024

# One lock per (event loop, order): two "print label" requests for the same order must not
# each create a shipment at Allegro (a shipment costs money and can only be created once).
_ORDER_LOCKS: dict = {}
_ORDER_LOCKS_GUARD = threading.Lock()


def _order_lock(order_id: str) -> asyncio.Lock:
    loop = asyncio.get_running_loop()
    key = (loop, order_id)
    with _ORDER_LOCKS_GUARD:
        lock = _ORDER_LOCKS.get(key)
        if lock is None:
            lock = asyncio.Lock()
            _ORDER_LOCKS[key] = lock
        return lock


def _build_invoice_html(order_id: str) -> str:
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=t("error.order_not_found"))
    s = store.get_invoice_settings()

    rows = []
    if s.get("show_buyer_name") and order.buyer_name:
        rows.append((t("doc.buyer"), order.buyer_name, True))
    if s.get("show_buyer_address") and order.buyer_address:
        rows.append((t("doc.address"), order.buyer_address.replace("\n", "<br>"), False))
    if s.get("show_courier") and order.courier:
        rows.append((t("doc.courier"), order.courier, False))
    if s.get("show_pickup_point") and order.pickup_point:
        rows.append((t("doc.pickup_point"), order.pickup_point, True))
    if s.get("show_allegro_id"):
        rows.append((t("doc.order_number"), order.allegro_id, False))

    show_price = s.get("show_price") and s.get("show_items")
    items = order.items if s.get("show_items") else []
    total = None
    if show_price and items and all(i.unit_price is not None for i in items):
        total = sum(i.unit_price * i.quantity for i in items)

    labels = {
        name: t(f"doc.{name}")
        for name in ("title", "products", "product", "quantity", "unit_price", "value", "total")
    }
    # The language is read from the request scope set by the middleware, so the
    # rendered document matches the Accept-Language of this very request.
    language = current_language.get()
    template = _jinja.get_template("invoice.html")
    return template.render(
        lang=language,
        labels=labels,
        date=date.today().strftime(date_format(language)),
        rows=rows,
        items=items,
        show_price=show_price,
        total=total,
        free_text=s.get("free_text", ""),
    )


class InvoiceSettings(BaseModel):
    show_buyer_name: bool = True
    show_buyer_address: bool = True
    show_items: bool = True
    show_price: bool = True
    show_courier: bool = True
    show_pickup_point: bool = True
    show_allegro_id: bool = True
    free_text: str = Field("", max_length=160)


class SenderSettings(BaseModel):
    name: str = ""
    company: str = ""
    street: str = ""
    postal_code: str = ""
    city: str = ""
    country_code: str = "PL"
    email: str = ""
    phone: str = ""


class PackageSettings(BaseModel):
    type: str = "PACKAGE"
    length: float = Field(30, gt=0, le=500)
    width: float = Field(20, gt=0, le=500)
    height: float = Field(15, gt=0, le=500)
    weight: float = Field(1.0, gt=0, le=100)
    label_format: str = "PDF"
    page_size: str = "A6"


class ShipmentSettings(BaseModel):
    sender: SenderSettings = Field(default_factory=lambda: SenderSettings())
    package: PackageSettings = Field(default_factory=lambda: PackageSettings())


@router.get("/invoice-settings")
def get_invoice_settings():
    return store.get_invoice_settings()


@router.post("/invoice-settings")
def save_invoice_settings(body: InvoiceSettings):
    store.save_invoice_settings(body.model_dump())
    return {"status": "saved"}


@router.get("/shipment-settings")
def get_shipment_settings():
    return store.get_shipment_settings()


@router.post("/shipment-settings")
def save_shipment_settings(body: ShipmentSettings):
    store.save_shipment_settings(body.model_dump())
    return {"status": "saved"}


INPOST_LOCKER_SIZES = {
    "A": {"length": 64.0, "width": 38.0, "height": 8.0},
    "B": {"length": 64.0, "width": 38.0, "height": 19.0},
    "C": {"length": 64.0, "width": 38.0, "height": 41.0},
}


@router.get("/orders/{order_id}/label")
async def print_label(
    order_id: str,
    length: float | None = Query(None, gt=0, le=500),
    width: float | None = Query(None, gt=0, le=500),
    height: float | None = Query(None, gt=0, le=500),
    weight: float | None = Query(None, gt=0, le=100),
):
    """Create the shipment once (if needed) and return the label PDF.

    Dimensions come from the shipping settings unless this request overrides them.
    For InPost lockers, dimensions are derived from the order's parcel_size (A/B/C).
    Serialised per order so a double click cannot create two shipments.
    """
    async with _order_lock(order_id):
        order = store.get_order(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail=t("error.order_not_found"))

        settings = store.get_shipment_settings()
        package = dict(settings["package"])
        for key, value in (("length", length), ("width", width), ("height", height), ("weight", weight)):
            if value is not None:
                package[key] = value

        if order.is_inpost_locker and not order.shipment_id:
            if not order.parcel_size and not (length and width and height):
                raise HTTPException(
                    status_code=400,
                    detail=t("label.select_size"),
                )
            if order.parcel_size in INPOST_LOCKER_SIZES:
                dims = INPOST_LOCKER_SIZES[order.parcel_size]
                if length is None:
                    package["length"] = dims["length"]
                if width is None:
                    package["width"] = dims["width"]
                if height is None:
                    package["height"] = dims["height"]

        try:
            shipment_id = order.shipment_id
            tracking_number = order.tracking_number
            created_now = False
            if not shipment_id:
                shipment_id = await allegro.create_shipment(order, settings["sender"], package)
                created_now = True
                tracking_number = await allegro.get_shipment_tracking(shipment_id)
            elif not tracking_number:
                # The shipment exists but the waybill was never stored — either
                # Allegro had not issued it yet at creation time, or this order
                # predates tracking. Allegro assigns the carrier number shortly
                # after creation, so re-reading it on a later print recovers it.
                tracking_number = await allegro.get_shipment_tracking(shipment_id)

            # The new id must be saved even when no tracking number came back:
            # the shipment has already been paid for, and losing the id would let
            # a second click buy another one. Only the two fields are written —
            # while Allegro was creating the shipment the order may have moved on
            # (marked done, reverted, archived), and saving the whole stale record
            # back would undo that change.
            if created_now or (tracking_number and tracking_number != order.tracking_number):
                def remember_shipment(state):
                    stored = state["orders"].get(order_id)
                    if stored is not None:
                        if not stored.get("shipment_id"):
                            stored["shipment_id"] = shipment_id
                        if tracking_number:
                            stored["tracking_number"] = tracking_number

                store.transact(remember_shipment)

            label_bytes = await allegro.download_label(shipment_id, package.get("page_size", "A6"))
        except allegro.AllegroError as exc:
            raise to_http_exception(exc)
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=t("common.allegro_unreachable", error=exc))

    return Response(content=label_bytes, media_type="application/pdf")


@router.get("/orders/{order_id}/shipment")
async def shipment_info(order_id: str):
    """Whether a shipment already exists for this order (so the UI can warn before printing).

    Also the place the browser reads the tracking number after printing. If the
    shipment exists but the number was never stored, fetch it once and persist
    it, so re-opening the packing card does not have to wait for Allegro again.
    """
    order = store.get_order(order_id)
    if order is None:
        raise HTTPException(status_code=404, detail=t("error.order_not_found"))
    tracking_number = order.tracking_number
    if order.shipment_id and not tracking_number:
        try:
            tracking_number = await allegro.get_shipment_tracking(order.shipment_id)
        except allegro.AllegroError:
            tracking_number = None
        if tracking_number:
            def remember_tracking(state):
                stored = state["orders"].get(order_id)
                if stored is not None and not stored.get("tracking_number"):
                    stored["tracking_number"] = tracking_number

            store.transact(remember_tracking)
    return {"shipment_id": order.shipment_id, "tracking_number": tracking_number}


@router.get("/orders/{order_id}/invoice")
async def print_invoice(order_id: str):
    """Return a sales document HTML — browser opens it and auto-prints."""
    html = _build_invoice_html(order_id)
    return Response(content=html, media_type="text/html")


@router.get("/orders/{order_id}/combined")
async def print_combined(order_id: str):
    """Invoice + custom doc merged into one PDF."""
    import weasyprint
    from pypdf import PdfWriter, PdfReader

    html = _build_invoice_html(order_id)
    invoice_pdf = weasyprint.HTML(string=html).write_pdf()

    if not os.path.exists(CUSTOM_DOC_PATH):
        return Response(content=invoice_pdf, media_type="application/pdf")

    writer = PdfWriter()
    for page in PdfReader(io.BytesIO(invoice_pdf)).pages:
        writer.add_page(page)
    for page in PdfReader(str(CUSTOM_DOC_PATH)).pages:
        writer.add_page(page)

    out = io.BytesIO()
    writer.write(out)
    return Response(content=out.getvalue(), media_type="application/pdf")


# ---- Custom document ----


@router.get("/custom-doc/info")
def custom_doc_info():
    if os.path.exists(CUSTOM_DOC_PATH):
        return {"available": True, "size": os.path.getsize(CUSTOM_DOC_PATH)}
    return {"available": False}


@router.post("/custom-doc")
async def upload_custom_doc(file: UploadFile = File(...)):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail=t("print.pdf_required"))
    payload = await file.read(MAX_CUSTOM_DOC_BYTES + 1)
    if len(payload) > MAX_CUSTOM_DOC_BYTES:
        raise HTTPException(status_code=413, detail=t("print.file_too_large"))
    if not payload.startswith(b"%PDF-"):
        raise HTTPException(status_code=400, detail=t("print.not_a_pdf"))
    CUSTOM_DOC_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CUSTOM_DOC_PATH.with_name(CUSTOM_DOC_PATH.name + ".tmp")
    with open(tmp, "wb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, CUSTOM_DOC_PATH)
    return {"status": "uploaded"}


@router.get("/custom-doc")
def serve_custom_doc():
    if not os.path.exists(CUSTOM_DOC_PATH):
        raise HTTPException(status_code=404, detail=t("print.custom_doc_missing"))
    with open(CUSTOM_DOC_PATH, "rb") as handle:
        content = handle.read()
    return Response(content=content, media_type="application/pdf")


@router.delete("/custom-doc")
def delete_custom_doc():
    if os.path.exists(CUSTOM_DOC_PATH):
        os.remove(CUSTOM_DOC_PATH)
    return {"status": "deleted"}
