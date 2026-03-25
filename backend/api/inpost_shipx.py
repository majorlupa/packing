"""
InPost ShipX API client — fetch shipping labels.
Docs: https://dokumentacja-inpost.atlassian.net/wiki/spaces/PL/pages/
"""
import os
import httpx

SHIPX_TOKEN = os.getenv("INPOST_SHIPX_TOKEN", "")
BASE_URL = "https://api-shipx-pl.easypack24.net/v1"


def _headers() -> dict:
    return {"Authorization": f"Bearer {SHIPX_TOKEN}"}


async def get_label(shipment_id: str) -> bytes:
    """Fetch Zebra-ready ZPL label (or PDF) for a shipment."""
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/shipments/{shipment_id}/label",
            headers=_headers(),
            params={"format": "Zpl"},
        )
        r.raise_for_status()
        return r.content


async def get_shipment_for_order(allegro_order_id: str) -> str | None:
    """
    Look up the InPost shipment ID linked to an Allegro order.
    Returns shipment_id or None if not found.
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/shipments",
            headers=_headers(),
            params={"reference": allegro_order_id},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        items = data.get("items", [])
        return items[0]["id"] if items else None
