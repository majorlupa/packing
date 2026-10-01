from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List
import uuid
import store
from models.order import OrderStatus, PickingList

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
        if order_id in picking_list["order_ids"]:
            picking_list["order_ids"].remove(order_id)
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

    def mutate(state):
        for oid in req.order_ids:
            if oid not in state["orders"]:
                raise HTTPException(status_code=404, detail=f"Order {oid} not found.")
        # Selecting an order that sits in another list moves it instead of leaving a dangling id.
        for oid in req.order_ids:
            _detach_from_lists(state, oid)

        state["picking_list_counter"] = int(state.get("picking_list_counter") or 0) + 1
        pl = PickingList(
            id=str(uuid.uuid4()),
            name=req.name or f"Lista #{state['picking_list_counter']}",
            order_ids=list(req.order_ids),
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
            if order is not None:
                order["status"] = OrderStatus.pending.value
                order["picking_list_id"] = None
        state["picking_lists"].pop(pl_id, None)
        return {"status": "ok"}

    return store.transact(mutate)


@router.post("/picking-lists/{pl_id}/start-packing")
async def start_packing(pl_id: str):
    """Move all orders in a picking list to packing status."""

    def mutate(state):
        pl = state["picking_lists"].get(pl_id)
        if pl is None:
            raise HTTPException(status_code=404, detail="Picking list not found.")
        for oid in pl["order_ids"]:
            order = state["orders"].get(oid)
            if order is not None:
                order["status"] = OrderStatus.packing.value
        return {"status": "ok", "order_ids": pl["order_ids"]}

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
