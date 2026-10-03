"""Importing this package registers every table with SQLAlchemy (needed by Alembic)."""

from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatusEvent, order_number_seq
from app.models.refund import IdempotencyKey, Refund
from app.models.returns import Return, return_number_seq

__all__ = [
    "Customer",
    "IdempotencyKey",
    "Order",
    "OrderItem",
    "OrderStatusEvent",
    "Refund",
    "Return",
    "order_number_seq",
    "return_number_seq",
]
