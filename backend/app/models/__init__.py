"""Importing this package registers every table with SQLAlchemy (needed by Alembic)."""

from app.models.customer import Customer
from app.models.order import Order, OrderItem, OrderStatusEvent, order_number_seq

__all__ = ["Customer", "Order", "OrderItem", "OrderStatusEvent", "order_number_seq"]
