"""
Print routes — return PDF/HTML content for the browser to trigger printing.
Zebra label: PDF fetched from Allegro shipment management API.
Sales document: HTML rendered via Jinja2 template, browser prints.
Custom doc: user-uploaded static PDF, served as-is.
Combined: invoice rendered to PDF via weasyprint, merged with custom doc via pypdf.
"""
import io
import os
import shutil
from datetime import date

from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import Response
from jinja2 import Environment, FileSystemLoader
from pydantic import BaseModel

import store
import api.allegro as allegro

router = APIRouter(prefix="/print", tags=["print"])

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), "..", "templates")
_jinja = Environment(loader=FileSystemLoader(TEMPLATES_DIR), autoescape=True)

CUSTOM_DOC_PATH = "/app/data/custom_doc.pdf"


def _build_invoice_html(order_id: str) -> str:
    orders = store.get_orders()
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    order = orders[order_id]
    s = store.get_invoice_settings()

    rows = []
    if s.get("show_buyer_name") and order.buyer_name:
        rows.append(("Kupujący", order.buyer_name, True))
    if s.get("show_buyer_address") and order.buyer_address:
        rows.append(("Adres", order.buyer_address.replace("\n", "<br>"), False))
    if s.get("show_courier") and order.courier:
        rows.append(("Kurier", order.courier, False))
    if s.get("show_pickup_point") and order.pickup_point:
        rows.append(("Punkt odbioru", order.pickup_point, True))
    if s.get("show_allegro_id"):
        rows.append(("Nr zamówienia", order.allegro_id, False))

    show_price = s.get("show_price") and s.get("show_items")
    items = order.items if s.get("show_items") else []
    total = None
    if show_price and items and all(i.unit_price is not None for i in items):
        total = sum(i.unit_price * i.quantity for i in items)

    template = _jinja.get_template("invoice.html")
    return template.render(
        date=date.today().strftime("%-d.%-m.%Y"),
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
    free_text: str = ""


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
def save_shipment_settings(body: dict):
    store.save_shipment_settings(body)
    return {"status": "saved"}


@router.get("/orders/{order_id}/label")
async def print_label(
    order_id: str,
    length: float = 30, width: float = 20, height: float = 40, weight: float = 1.0,
):
    """Create shipment (if needed) and return label PDF."""
    orders = store.get_orders()
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    order = orders[order_id]

    try:
        if not order.shipment_id:
            settings = store.get_shipment_settings()
            package = {**settings["package"], "length": length, "width": width, "height": height, "weight": weight}
            shipment_id = await allegro.create_shipment(order, settings["sender"], package)
            order.shipment_id = shipment_id
            store.save_order(order)
        label_bytes = await allegro.download_label(order.shipment_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response(content=label_bytes, media_type="application/pdf")


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
    for page in PdfReader(CUSTOM_DOC_PATH).pages:
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
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Wymagany plik PDF.")
    os.makedirs(os.path.dirname(CUSTOM_DOC_PATH), exist_ok=True)
    with open(CUSTOM_DOC_PATH, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"status": "uploaded"}


@router.get("/custom-doc")
def serve_custom_doc():
    if not os.path.exists(CUSTOM_DOC_PATH):
        raise HTTPException(status_code=404, detail="Brak wgranego dokumentu.")
    with open(CUSTOM_DOC_PATH, "rb") as f:
        content = f.read()
    return Response(content=content, media_type="application/pdf")


@router.delete("/custom-doc")
def delete_custom_doc():
    if os.path.exists(CUSTOM_DOC_PATH):
        os.remove(CUSTOM_DOC_PATH)
    return {"status": "deleted"}
