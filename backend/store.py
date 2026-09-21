"""
Simple JSON file store. Data lives in /app/data/state.json (mounted as a volume).
Override the location with PACKING_DATA_DIR so the app can also run outside the container.

Durability rules:
  * every write goes to a temp file, is fsynced, then os.replace()d into place;
  * the previous good file is kept as state.json.bak, so a crash mid-write can never
    leave a half-written queue behind;
  * a state file that cannot be parsed falls back to the backup, and the broken file is
    preserved as state.json.corrupt-<timestamp> instead of being clobbered;
  * individual records that fail validation are quarantined (kept and reported) instead of
    taking every API call down with a 500.
"""
import json
import os
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List, Optional, TypeVar

from pydantic import ValidationError

from models.order import Order, PickingList

DATA_DIR = Path(os.getenv("PACKING_DATA_DIR", "/app/data"))
DATA_FILE = DATA_DIR / "state.json"
BACKUP_FILE = DATA_DIR / "state.json.bak"

_MAX_QUARANTINE = 50

T = TypeVar("T")

_LOCK = threading.RLock()

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


class StateError(RuntimeError):
    """The state file exists but cannot be used. Surface this, never a bare 500."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _default_state() -> dict:
    return {
        "orders": {},
        "picking_lists": {},
        "picking_list_counter": 0,
        "invoice_settings": deepcopy(DEFAULT_INVOICE_SETTINGS),
        "shipment_settings": deepcopy(DEFAULT_SHIPMENT_SETTINGS),
        "archive": [],
        "quarantine": [],
    }


def _merged(defaults: dict, saved: object) -> dict:
    """Merge saved values over defaults, ignoring unknown keys and wrong shapes."""
    out = deepcopy(defaults)
    if not isinstance(saved, dict):
        return out
    for key, default in defaults.items():
        value = saved.get(key)
        if isinstance(default, dict):
            if isinstance(value, dict):
                for sub_key, _sub_default in default.items():
                    sub_value = value.get(sub_key)
                    if sub_value is not None:
                        out[key][sub_key] = sub_value
        elif value is not None:
            out[key] = value
    return out


def _normalise(raw: object) -> dict:
    """Coerce whatever is on disk into the current schema, quarantining bad records."""
    if not isinstance(raw, dict):
        raise StateError(f"{DATA_FILE} does not contain a JSON object.")

    state = _default_state()
    quarantine: List[dict] = [q for q in (raw.get("quarantine") or []) if isinstance(q, dict)][:_MAX_QUARANTINE]

    raw_orders = raw.get("orders")
    if isinstance(raw_orders, dict):
        for key, value in raw_orders.items():
            try:
                state["orders"][key] = Order(**value).model_dump(mode="json")
            except (ValidationError, TypeError) as exc:
                quarantine.append({"kind": "order", "id": key, "error": str(exc)[:500], "record": value})
    elif raw_orders not in (None, {}):
        quarantine.append({"kind": "orders-collection", "id": "orders", "error": "nie jest obiektem", "record": None})

    counter = raw.get("picking_list_counter")
    state["picking_list_counter"] = counter if isinstance(counter, int) and counter >= 0 else 0

    repaired = 0
    raw_lists = raw.get("picking_lists")
    if isinstance(raw_lists, dict):
        for key, value in raw_lists.items():
            try:
                pl = PickingList(**value)
            except (ValidationError, TypeError) as exc:
                quarantine.append({"kind": "picking-list", "id": key, "error": str(exc)[:500], "record": value})
                continue
            kept = [oid for oid in pl.order_ids if oid in state["orders"]]
            repaired += len(pl.order_ids) - len(kept)
            pl.order_ids = kept
            if pl.order_ids:
                state["picking_lists"][key] = pl.model_dump(mode="json")
            else:
                repaired += 1

    for entry in raw.get("archive") or []:
        if isinstance(entry, str):
            state["archive"].append({"allegro_id": entry, "archived_at": None})
        elif isinstance(entry, dict) and entry.get("allegro_id"):
            state["archive"].append({
                "allegro_id": entry["allegro_id"],
                "archived_at": entry.get("archived_at"),
            })

    state["invoice_settings"] = _merged(DEFAULT_INVOICE_SETTINGS, raw.get("invoice_settings"))
    state["shipment_settings"] = _merged(DEFAULT_SHIPMENT_SETTINGS, raw.get("shipment_settings"))
    state["quarantine"] = quarantine[:_MAX_QUARANTINE]

    state["_status"] = {
        "ok": not quarantine,
        "quarantined": len(quarantine),
        "repaired": repaired,
        "message": (
            f"{len(quarantine)} rekord(ów) pominięto — dane nie przechodzą walidacji."
            if quarantine else ""
        ),
    }
    return state


def _load() -> dict:
    if not DATA_FILE.exists():
        if BACKUP_FILE.exists():
            state = _normalise(json.loads(BACKUP_FILE.read_text(encoding="utf-8")))
            state["_status"].update(ok=False, message="Brak/czytelnego state.json nie było — odtworzono z kopii zapasowej.")
            return state
        state = _default_state()
        state["_status"] = {"ok": True, "quarantined": 0, "repaired": 0, "message": ""}
        return state

    try:
        return _normalise(json.loads(DATA_FILE.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
        if not BACKUP_FILE.exists():
            raise StateError(
                f"Nie można odczytać {DATA_FILE} ({exc}). Plik NIE został nadpisany — "
                "przywróć go ręcznie z kopii zapasowej lub popraw i zrestartuj kontener."
            ) from exc
        broken = DATA_FILE.with_name(f"state.json.corrupt-{datetime.now().strftime('%Y%m%d-%H%M%S')}")
        try:
            os.replace(DATA_FILE, broken)
        except OSError:
            pass
        state = _normalise(json.loads(BACKUP_FILE.read_text(encoding="utf-8")))
        state["_status"].update(
            ok=False,
            message=f"state.json był uszkodzony — odtworzono z kopii zapasowej ({broken.name}).",
        )
        return state


def _save(state: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {k: v for k, v in state.items() if not k.startswith("_")}
    tmp = DATA_FILE.with_name(DATA_FILE.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    if DATA_FILE.exists():
        try:
            os.replace(DATA_FILE, BACKUP_FILE)
        except OSError:
            pass
    os.replace(tmp, DATA_FILE)


def transact(mutator: Callable[[dict], T]) -> T:
    """One write per logical operation: load, mutate, atomically save — under a lock."""
    with _LOCK:
        state = _load()
        result = mutator(state)
        _save(state)
        return result


def state_status() -> dict:
    with _LOCK:
        try:
            status = _load()["_status"]
        except StateError as exc:
            return {"ok": False, "quarantined": 0, "repaired": 0, "message": str(exc)}
        return dict(status)


# ---- Orders ----


def get_orders() -> Dict[str, Order]:
    with _LOCK:
        return {k: Order(**v) for k, v in _load()["orders"].items()}


def get_order(order_id: str) -> Optional[Order]:
    with _LOCK:
        data = _load()["orders"].get(order_id)
        return Order(**data) if data else None


def get_order_by_allegro_id(allegro_id: str) -> Optional[Order]:
    with _LOCK:
        for data in _load()["orders"].values():
            if data.get("allegro_id") == allegro_id:
                return Order(**data)
        return None


def save_order(order: Order) -> None:
    def mutate(state):
        state["orders"][order.id] = order.model_dump(mode="json")

    transact(mutate)


def save_orders(orders: List[Order]) -> None:
    def mutate(state):
        for order in orders:
            state["orders"][order.id] = order.model_dump(mode="json")

    transact(mutate)


# ---- Picking lists ----


def get_picking_lists() -> Dict[str, PickingList]:
    with _LOCK:
        return {k: PickingList(**v) for k, v in _load()["picking_lists"].items()}


def get_picking_list(pl_id: str) -> Optional[PickingList]:
    with _LOCK:
        data = _load()["picking_lists"].get(pl_id)
        return PickingList(**data) if data else None


def save_picking_list(pl: PickingList) -> None:
    def mutate(state):
        state["picking_lists"][pl.id] = pl.model_dump(mode="json")

    transact(mutate)


def delete_picking_list(pl_id: str) -> None:
    def mutate(state):
        state["picking_lists"].pop(pl_id, None)

    transact(mutate)


def next_picking_list_number() -> int:
    def mutate(state):
        state["picking_list_counter"] = int(state.get("picking_list_counter") or 0) + 1
        return state["picking_list_counter"]

    return transact(mutate)


# ---- Archive ----


def get_archive() -> List[dict]:
    with _LOCK:
        return [dict(entry) for entry in _load()["archive"]]


def archived_allegro_ids() -> set:
    return {entry["allegro_id"] for entry in get_archive() if entry.get("allegro_id")}


def archive_done_orders() -> int:
    """Tombstone every done order, drop it from state, and clean up the picking lists."""

    def mutate(state):
        done_ids = {k for k, v in state["orders"].items() if v.get("status") == "done"}
        if not done_ids:
            return 0
        done_allegro_ids = {state["orders"][oid]["allegro_id"] for oid in done_ids}

        known = {entry["allegro_id"] for entry in state["archive"]}
        for allegro_id in done_allegro_ids - known:
            state["archive"].append({"allegro_id": allegro_id, "archived_at": _now()})

        state["orders"] = {k: v for k, v in state["orders"].items() if k not in done_ids}

        cleaned: Dict[str, dict] = {}
        for pl_id, pl in state["picking_lists"].items():
            remaining = [oid for oid in pl["order_ids"] if oid not in done_ids]
            if remaining:
                pl["order_ids"] = remaining
                cleaned[pl_id] = pl
        state["picking_lists"] = cleaned
        return len(done_allegro_ids)

    return transact(mutate)


# ---- Settings ----


def get_invoice_settings() -> dict:
    with _LOCK:
        return _merged(DEFAULT_INVOICE_SETTINGS, _load()["invoice_settings"])


def save_invoice_settings(settings: dict) -> None:
    def mutate(state):
        state["invoice_settings"] = _merged(DEFAULT_INVOICE_SETTINGS, settings)

    transact(mutate)


def get_shipment_settings() -> dict:
    with _LOCK:
        return _merged(DEFAULT_SHIPMENT_SETTINGS, _load()["shipment_settings"])


def save_shipment_settings(settings: dict) -> None:
    def mutate(state):
        state["shipment_settings"] = _merged(DEFAULT_SHIPMENT_SETTINGS, settings)

    transact(mutate)
