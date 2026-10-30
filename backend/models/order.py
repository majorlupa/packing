from enum import Enum
from typing import Literal

from pydantic import BaseModel


# StrEnum changes str()/format() output; preserve the existing enum behavior.
class OrderStatus(str, Enum):  # noqa: UP042
    pending = "pending"
    picking = "picking"
    packing = "packing"
    done = "done"


class OrderItem(BaseModel):
    name: str
    quantity: int
    unit_price: float | None = None
    sku: str | None = None
    offer_id: str | None = None


class Order(BaseModel):
    id: str
    allegro_id: str
    buyer_name: str
    buyer_address: str
    items: list[OrderItem]
    status: OrderStatus = OrderStatus.pending
    picking_list_id: str | None = None
    courier: str | None = None
    pickup_point: str | None = None
    tracking_number: str | None = None
    # Structured buyer address for shipment creation
    buyer_email: str | None = None
    buyer_phone: str | None = None
    buyer_street: str | None = None
    buyer_postal_code: str | None = None
    buyer_city: str | None = None
    buyer_country: str | None = "PL"
    # Allegro delivery method UUID (from order)
    delivery_method_id: str | None = None
    # Shipment management UUID (set after creating shipment via API)
    shipment_id: str | None = None
    # Durable creation intent; retained after uncertain carrier/network failures.
    shipment_command_id: str | None = None
    parcel_size: Literal["A", "B", "C"] | None = None

    @property
    def is_inpost_locker(self) -> bool:
        name = (self.courier or "").casefold()
        return "inpost" in name and "paczkomat" in name



class PickingList(BaseModel):
    id: str
    name: str
    order_ids: list[str]
