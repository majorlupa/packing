"""
Simple JSON file store. Data lives in /app/data/state.json (mounted as a volume).
Resets only if you delete the file or the volume.
"""
import json
import os
from typing import Dict
from models.order import Order, PickingList

DATA_FILE = "/app/data/state.json"


DEFAULT_SHIPMENT_SETTINGS = {
    "sender": {
        "name": "",
        "company": "",
        "street": "",
        "postal_code": "",
        "city": "",
        "country_code": "PL",
        "email": "",
        "phone": "",
    },
    "package": {
        "type": "PACKAGE",
        "length": 30,
        "width": 20,
        "height": 15,
        "weight": 1.0,
        "label_format": "PDF",
        "page_size": "A6",
    },
}

DEFAULT_INVOICE_SETTINGS = {
    "show_buyer_name": True,
    "show_buyer_address": True,
    "show_items": True,
    "show_price": True,
    "show_courier": True,
    "show_pickup_point": True,
    "show_allegro_id": True,
    "free_text": "",
}


def _load() -> dict:
    if not os.path.exists(DATA_FILE):
        return {"orders": {}, "picking_lists": {}, "picking_list_counter": 0, "invoice_settings": DEFAULT_INVOICE_SETTINGS.copy(), "shipment_settings": DEFAULT_SHIPMENT_SETTINGS.copy(), "archive": []}
    state = json.load(open(DATA_FILE))
    if "picking_list_counter" not in state:
        state["picking_list_counter"] = 0
    if "invoice_settings" not in state:
        state["invoice_settings"] = DEFAULT_INVOICE_SETTINGS.copy()
    if "shipment_settings" not in state:
        state["shipment_settings"] = DEFAULT_SHIPMENT_SETTINGS.copy()
    if "archive" not in state:
        state["archive"] = []
    return state


def _save(state: dict):
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    with open(DATA_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_orders() -> Dict[str, Order]:
    state = _load()
    return {k: Order(**v) for k, v in state["orders"].items()}


def save_order(order: Order):
    state = _load()
    state["orders"][order.id] = order.model_dump()
    _save(state)


def get_picking_lists() -> Dict[str, PickingList]:
    state = _load()
    return {k: PickingList(**v) for k, v in state["picking_lists"].items()}


def save_picking_list(pl: PickingList):
    state = _load()
    state["picking_lists"][pl.id] = pl.model_dump()
    _save(state)


def next_picking_list_number() -> int:
    state = _load()
    state["picking_list_counter"] += 1
    _save(state)
    return state["picking_list_counter"]


def delete_picking_list(pl_id: str):
    state = _load()
    state["picking_lists"].pop(pl_id, None)
    _save(state)


def get_archive() -> list:
    return _load()["archive"]


def archive_done_orders() -> int:
    """Move all done orders to archive tombstones. Returns count archived."""
    state = _load()
    done_ids = [
        data["allegro_id"]
        for data in state["orders"].values()
        if data.get("status") == "done"
    ]
    if not done_ids:
        return 0
    existing = set(state["archive"])
    state["archive"].extend(aid for aid in done_ids if aid not in existing)
    state["orders"] = {k: v for k, v in state["orders"].items() if v.get("status") != "done"}
    _save(state)
    return len(done_ids)


def get_invoice_settings() -> dict:
    return {**DEFAULT_INVOICE_SETTINGS, **_load()["invoice_settings"]}


def save_invoice_settings(settings: dict):
    state = _load()
    state["invoice_settings"] = settings
    _save(state)


def get_shipment_settings() -> dict:
    saved = _load().get("shipment_settings", {})
    return {
        "sender": {**DEFAULT_SHIPMENT_SETTINGS["sender"], **saved.get("sender", {})},
        "package": {**DEFAULT_SHIPMENT_SETTINGS["package"], **saved.get("package", {})},
    }


def save_shipment_settings(settings: dict):
    state = _load()
    state["shipment_settings"] = settings
    _save(state)
