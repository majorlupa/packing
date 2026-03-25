from enum import Enum
from pydantic import BaseModel
from typing import List, Optional


class OrderStatus(str, Enum):
    pending = "pending"
    picking = "picking"
    packing = "packing"
    done = "done"


class OrderItem(BaseModel):
    name: str
    quantity: int


class Order(BaseModel):
    id: str
    allegro_id: str
    buyer_name: str
    buyer_address: str
    items: List[OrderItem]
    status: OrderStatus = OrderStatus.pending
    picking_list_id: Optional[str] = None
    courier: Optional[str] = None
    pickup_point: Optional[str] = None


class PickingList(BaseModel):
    id: str
    name: str
    order_ids: List[str]
