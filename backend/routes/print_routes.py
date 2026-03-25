"""
Print routes — return PDF/ZPL content for the browser to trigger printing.
Zebra label: ZPL sent directly, or PDF for browsers that support it.
A4 invoice: simple HTML rendered to PDF via the browser print dialog.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import store
import api.allegro as allegro

router = APIRouter(prefix="/print", tags=["print"])


class InvoiceSettings(BaseModel):
    show_buyer_name: bool = True
    show_buyer_address: bool = True
    show_items: bool = True
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


@router.get("/orders/{order_id}/label")
async def print_label(order_id: str):
    """Fetch courier label PDF from Allegro shipment management."""
    orders = store.get_orders()
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    order = orders[order_id]

    try:
        label_bytes = await allegro.get_label_for_order(order.allegro_id)
    except RuntimeError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return Response(content=label_bytes, media_type="application/pdf")


@router.get("/orders/{order_id}/invoice")
async def print_invoice(order_id: str):
    """Return a sales document HTML — browser opens it and auto-prints."""
    orders = store.get_orders()
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    order = orders[order_id]
    s = store.get_invoice_settings()

    rows = []
    if s.get("show_buyer_name") and order.buyer_name:
        rows.append(("<strong>Kupujący</strong>", order.buyer_name))
    if s.get("show_buyer_address") and order.buyer_address:
        rows.append(("Adres", order.buyer_address.replace("\n", "<br>")))
    if s.get("show_courier") and order.courier:
        rows.append(("Kurier", order.courier))
    if s.get("show_pickup_point") and order.pickup_point:
        rows.append(("Punkt odbioru", f"<strong>{order.pickup_point}</strong>"))
    if s.get("show_allegro_id"):
        rows.append(("Nr zamówienia", order.allegro_id))

    info_html = "".join(
        f"<tr><td class='label'>{label}</td><td>{value}</td></tr>"
        for label, value in rows
    )

    items_html = ""
    if s.get("show_items"):
        items_html = "<table class='items'><thead><tr><th>Produkt</th><th>Ilość</th></tr></thead><tbody>" + "".join(
            f"<tr><td>{item.name}</td><td>{item.quantity}</td></tr>"
            for item in order.items
        ) + "</tbody></table>"

    free_text_html = f'<p class="free-text">{s["free_text"]}</p>' if s.get("free_text") else ""

    html = f"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<title>Dokument sprzedażowy</title>
<style>
  body {{ font-family: Arial, sans-serif; margin: 40px; font-size: 14px; color: #111; }}
  h1 {{ font-size: 18px; margin-bottom: 20px; }}
  table.info {{ border-collapse: collapse; margin-bottom: 24px; }}
  table.info td {{ padding: 6px 12px 6px 0; vertical-align: top; }}
  table.info td.label {{ color: #666; font-size: 12px; text-transform: uppercase; white-space: nowrap; padding-right: 20px; }}
  table.items {{ width: 100%; border-collapse: collapse; }}
  table.items th, table.items td {{ border: 1px solid #ccc; padding: 8px 10px; text-align: left; }}
  table.items th {{ background: #f5f5f5; font-size: 12px; text-transform: uppercase; }}
  .free-text {{ margin-top: 24px; font-size: 13px; color: #444; border-top: 1px solid #eee; padding-top: 12px; }}
  @media print {{ body {{ margin: 20px; }} }}
</style>
</head>
<body>
<h1>Dokument sprzedażowy</h1>
<table class="info">{info_html}</table>
{items_html}
{free_text_html}
<script>window.onload = () => window.print();</script>
</body>
</html>"""

    return Response(content=html, media_type="text/html")
