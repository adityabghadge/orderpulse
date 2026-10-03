"""Request and response shapes for the Orders API.

These are the API's public contract. Keeping them separate from the database models means
the database can change shape without breaking clients, and clients can never set fields
they shouldn't (like an order's total, which the server always calculates).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.order_status import OrderStatus

PaymentMethod = Literal["card", "wallet", "cod"]


class OrderItemIn(BaseModel):
    sku: str = Field(min_length=1, max_length=32)
    product_name: str = Field(min_length=1, max_length=200)
    category: str = Field(min_length=1, max_length=40)
    quantity: int = Field(ge=1, le=100)
    unit_price_cents: int = Field(ge=0, le=10_000_000)


class OrderCreate(BaseModel):
    customer_id: int
    payment_method: PaymentMethod
    shipping_city: str = Field(min_length=1, max_length=80)
    items: list[OrderItemIn] = Field(min_length=1, max_length=50)


class StatusUpdate(BaseModel):
    status: OrderStatus
    note: str | None = Field(default=None, max_length=500)
    actor: str = Field(default="ops-console", min_length=1, max_length=80)


class CustomerRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_name: str
    email: str
    tier: str


class OrderItemOut(OrderItemIn):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_total_cents: int


class OrderEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: OrderStatus | None
    to_status: OrderStatus
    note: str | None
    actor: str
    created_at: datetime


class OrderSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    order_number: str
    customer_id: int
    status: OrderStatus
    total_cents: int
    currency: str
    payment_method: PaymentMethod
    shipping_city: str
    placed_at: datetime
    delivered_at: datetime | None
    item_count: int


class OrderDetail(OrderSummary):
    customer: CustomerRef
    items: list[OrderItemOut]
    events: list[OrderEventOut]


class OrderPage(BaseModel):
    items: list[OrderSummary]
    total: int
    limit: int
    offset: int
