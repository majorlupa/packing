from enum import Enum
from pydantic import BaseModel
from typing import List, Optional, Literal


class OrderStatus(str, Enum):
    pending = "pending"
    picking = "picking"
    packing = "packing"
    done = "done"


class OrderItem(BaseModel):
    name: str
    quantity: int
    unit_price: Optional[float] = None


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
    tracking_number: Optional[str] = None
    # Structured buyer address for shipment creation
    buyer_email: Optional[str] = None
    buyer_phone: Optional[str] = None
    buyer_street: Optional[str] = None
    buyer_postal_code: Optional[str] = None
    buyer_city: Optional[str] = None
    buyer_country: Optional[str] = "PL"
    # Allegro delivery method UUID (from order)
    delivery_method_id: Optional[str] = None
    # Shipment management UUID (set after creating shipment via API)
    shipment_id: Optional[str] = None
    parcel_size: Optional[Literal["A", "B", "C"]] = None

    @property
    def is_inpost_locker(self) -> bool:
        name = (self.courier or "").casefold()
        return "inpost" in name and "paczkomat" in name



class PickingList(BaseModel):
    id: str
    name: str
    order_ids: List[str]
