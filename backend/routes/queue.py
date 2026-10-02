from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Literal
import uuid
import store
from models.order import Order, OrderStatus, PickingList

router = APIRouter(tags=["queue"])


class CreatePickingListRequest(BaseModel):
    name: str = ""
    order_ids: List[str] = Field(min_length=1)


class RenamePickingListRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


def _detach_from_lists(state: dict, order_id: str) -> None:
    """Remove an order from every picking list; drop lists left empty.

    Status changes and list membership must never disagree, otherwise
    'start packing' on an old list resurrects an order the operator reverted.
    """
    empty = []
    for pl_id, picking_list in state["picking_lists"].items():
        picking_list["order_ids"] = [oid for oid in picking_list["order_ids"] if oid != order_id]
        if not picking_list["order_ids"]:
            empty.append(pl_id)
    for pl_id in empty:
        state["picking_lists"].pop(pl_id, None)


@router.patch("/picking-lists/{pl_id}")
async def rename_picking_list(pl_id: str, req: RenamePickingListRequest):
    """Rename a picking list. Only the name is needed — the orders are not touched."""

    def mutate(state):
        pl = state["picking_lists"].get(pl_id)
        if pl is None:
            raise HTTPException(status_code=404, detail="Picking list not found.")
        pl["name"] = req.name
        return pl

    return store.transact(mutate)


@router.post("/picking-lists")
async def create_picking_list(req: CreatePickingListRequest):
    """Group selected pending orders into a picking list."""
    order_ids = list(dict.fromkeys(req.order_ids))

    def mutate(state):
        for oid in order_ids:
            if oid not in state["orders"]:
                raise HTTPException(status_code=404, detail=f"Order {oid} not found.")
        # Selecting an order that sits in another list moves it instead of leaving a dangling id.
        for oid in order_ids:
            _detach_from_lists(state, oid)

        state["picking_list_counter"] = int(state.get("picking_list_counter") or 0) + 1
        pl = PickingList(
            id=str(uuid.uuid4()),
            name=req.name or f"Lista #{state['picking_list_counter']}",
            order_ids=order_ids,
        )
        state["picking_lists"][pl.id] = pl.model_dump(mode="json")
        for oid in pl.order_ids:
            state["orders"][oid]["status"] = OrderStatus.picking.value
            state["orders"][oid]["picking_list_id"] = pl.id
        return pl.model_dump(mode="json")

    return store.transact(mutate)


@router.get("/picking-lists")
async def list_picking_lists():
    return [pl.model_dump() for pl in store.get_picking_lists().values()]


@router.post("/picking-lists/{pl_id}/revert")
async def revert_to_pending(pl_id: str):
    def mutate(state):
        pl = state["picking_lists"].get(pl_id)
        if pl is None:
            raise HTTPException(status_code=404, detail="Picking list not found.")
        for oid in pl["order_ids"]:
            order = state["orders"].get(oid)
            if order is None:
                continue
            order["picking_list_id"] = None
            # A finished order is already packed, shipped and archived-eligible;
            # reverting the list must not pull it back into Oczekujące.
            if order["status"] != OrderStatus.done.value:
                order["status"] = OrderStatus.pending.value
        state["picking_lists"].pop(pl_id, None)
        return {"status": "ok"}

    return store.transact(mutate)


@router.post("/picking-lists/{pl_id}/start-packing")
async def start_packing(pl_id: str):
    """Move the picking list's orders to packing status.

    A finished order stays in Gotowe: the packing view keeps the list for
    reprinting, so a stale list must not pull done orders back into the queue.
    """

    def mutate(state):
        pl = state["picking_lists"].get(pl_id)
        if pl is None:
            raise HTTPException(status_code=404, detail="Picking list not found.")
        moved = []
        for oid in pl["order_ids"]:
            order = state["orders"].get(oid)
            if order is not None and order["status"] != OrderStatus.done.value:
                order["status"] = OrderStatus.packing.value
                moved.append(oid)
        return {"status": "ok", "order_ids": moved}

    return store.transact(mutate)


def _set_status(order_id: str, status: OrderStatus, clear_list: bool = False):
    def mutate(state):
        order = state["orders"].get(order_id)
        if order is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        order["status"] = status.value
        if clear_list:
            order["picking_list_id"] = None
            _detach_from_lists(state, order_id)
        return {"status": status.value}

    return store.transact(mutate)


@router.post("/orders/{order_id}/done")
async def mark_done(order_id: str):
    return _set_status(order_id, OrderStatus.done)


@router.post("/orders/{order_id}/revert-pending")
async def revert_to_pending_single(order_id: str):
    return _set_status(order_id, OrderStatus.pending, clear_list=True)


@router.post("/orders/{order_id}/undo-done")
async def undo_done(order_id: str):
    return _set_status(order_id, OrderStatus.packing)


class ParcelSizeRequest(BaseModel):
    parcel_size: Literal["A", "B", "C"]


@router.patch("/orders/{order_id}/parcel-size")
async def set_parcel_size(order_id: str, req: ParcelSizeRequest) -> dict[str, str]:
    """Persist a locker size locally; carrier integration is deferred."""
    def mutate(state: dict) -> dict[str, str]:
        data = state["orders"].get(order_id)
        if data is None:
            raise HTTPException(status_code=404, detail="Order not found.")
        order = Order.model_validate(data)
        if not order.is_inpost_locker:
            raise HTTPException(status_code=400, detail="Gabaryt A/B/C dotyczy tylko Paczkomat InPost.")
        if order.shipment_id or order.tracking_number:
            raise HTTPException(status_code=409, detail="Przesyłka już istnieje — nie można zmienić gabarytu.")
        data["parcel_size"] = req.parcel_size
        return {"parcel_size": req.parcel_size}

    return store.transact(mutate)
