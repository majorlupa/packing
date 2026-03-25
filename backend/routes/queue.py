from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
import uuid
import store
from models.order import OrderStatus, PickingList

router = APIRouter(tags=["queue"])


class CreatePickingListRequest(BaseModel):
    name: str
    order_ids: List[str]


@router.patch("/picking-lists/{pl_id}")
async def rename_picking_list(pl_id: str, req: CreatePickingListRequest):
    pls = store.get_picking_lists()
    if pl_id not in pls:
        raise HTTPException(status_code=404, detail="Picking list not found.")
    pls[pl_id].name = req.name
    store.save_picking_list(pls[pl_id])
    return pls[pl_id].model_dump()


@router.post("/picking-lists")
async def create_picking_list(req: CreatePickingListRequest):
    """Group selected pending orders into a picking list."""
    orders = store.get_orders()
    for oid in req.order_ids:
        if oid not in orders:
            raise HTTPException(status_code=404, detail=f"Order {oid} not found.")

    num = store.next_picking_list_number()
    pl = PickingList(id=str(uuid.uuid4()), name=f"Lista #{num}", order_ids=req.order_ids)
    store.save_picking_list(pl)

    for oid in req.order_ids:
        order = orders[oid]
        order.status = OrderStatus.picking
        order.picking_list_id = pl.id
        store.save_order(order)

    return pl.model_dump()


@router.get("/picking-lists")
async def list_picking_lists():
    return [pl.model_dump() for pl in store.get_picking_lists().values()]


@router.post("/picking-lists/{pl_id}/revert")
async def revert_to_pending(pl_id: str):
    pls = store.get_picking_lists()
    if pl_id not in pls:
        raise HTTPException(status_code=404, detail="Picking list not found.")
    orders = store.get_orders()
    for oid in pls[pl_id].order_ids:
        if oid in orders:
            orders[oid].status = OrderStatus.pending
            orders[oid].picking_list_id = None
            store.save_order(orders[oid])
    store.delete_picking_list(pl_id)
    return {"status": "ok"}


@router.post("/picking-lists/{pl_id}/start-packing")
async def start_packing(pl_id: str):
    """Move all orders in a picking list to packing status."""
    pls = store.get_picking_lists()
    if pl_id not in pls:
        raise HTTPException(status_code=404, detail="Picking list not found.")

    orders = store.get_orders()
    pl = pls[pl_id]
    for oid in pl.order_ids:
        if oid in orders:
            orders[oid].status = OrderStatus.packing
            store.save_order(orders[oid])

    return {"status": "ok", "order_ids": pl.order_ids}


@router.post("/orders/{order_id}/done")
async def mark_done(order_id: str):
    orders = store.get_orders()
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    orders[order_id].status = OrderStatus.done
    store.save_order(orders[order_id])
    return {"status": "done"}


@router.post("/orders/{order_id}/revert-pending")
async def revert_to_pending_single(order_id: str):
    orders = store.get_orders()
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    orders[order_id].status = OrderStatus.pending
    orders[order_id].picking_list_id = None
    store.save_order(orders[order_id])
    return {"status": "pending"}


@router.post("/orders/{order_id}/undo-done")
async def undo_done(order_id: str):
    orders = store.get_orders()
    if order_id not in orders:
        raise HTTPException(status_code=404, detail="Order not found.")
    orders[order_id].status = OrderStatus.packing
    store.save_order(orders[order_id])
    return {"status": "packing"}
