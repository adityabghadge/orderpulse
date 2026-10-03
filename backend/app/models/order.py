from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Sequence,
    String,
    Text,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.domain.order_status import OrderStatus

if TYPE_CHECKING:
    from app.models.customer import Customer

# Human-friendly order numbers (OP-100000, OP-100001, ...) come from a database sequence,
# so two requests can never be handed the same number, even under heavy concurrency.
order_number_seq = Sequence("order_number_seq", start=100000, metadata=Base.metadata)

_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in OrderStatus)
PAYMENT_METHODS = ("card", "wallet", "cod")


class Order(TimestampMixin, Base):
    __tablename__ = "orders"
    __table_args__ = (
        CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status_valid"),
        CheckConstraint("total_cents >= 0", name="total_non_negative"),
        CheckConstraint(
            "payment_method IN (" + ", ".join(f"'{m}'" for m in PAYMENT_METHODS) + ")",
            name="payment_method_valid",
        ),
        # Supports the most common dashboard query: "orders in status X, newest first".
        Index("ix_orders_status_placed_at", "status", "placed_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_number: Mapped[str] = mapped_column(
        String(20),
        unique=True,
        server_default=text("'OP-' || nextval('order_number_seq')"),
    )
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    status: Mapped[str] = mapped_column(String(24), default=OrderStatus.PLACED.value)
    total_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    payment_method: Mapped[str] = mapped_column(String(16))
    shipping_city: Mapped[str] = mapped_column(String(80))
    placed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    customer: Mapped["Customer"] = relationship(back_populates="orders", lazy="joined")
    items: Mapped[list["OrderItem"]] = relationship(
        back_populates="order", cascade="all, delete-orphan", lazy="selectin"
    )
    events: Mapped[list["OrderStatusEvent"]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderStatusEvent.id",
    )

    @property
    def customer_name(self) -> str:
        return self.customer.full_name

    @property
    def item_count(self) -> int:
        """Total number of units in the order."""
        return sum(item.quantity for item in self.items)


class OrderItem(Base):
    __tablename__ = "order_items"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint("unit_price_cents >= 0", name="unit_price_non_negative"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    sku: Mapped[str] = mapped_column(String(32))
    product_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(40))
    quantity: Mapped[int] = mapped_column(Integer)
    unit_price_cents: Mapped[int] = mapped_column(BigInteger)

    order: Mapped[Order] = relationship(back_populates="items")

    @property
    def line_total_cents(self) -> int:
        return self.quantity * self.unit_price_cents


class OrderStatusEvent(Base):
    """Append-only audit trail: one row every time an order changes status."""

    __tablename__ = "order_status_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    from_status: Mapped[str | None] = mapped_column(String(24))
    to_status: Mapped[str] = mapped_column(String(24))
    note: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(80), default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    order: Mapped[Order] = relationship(back_populates="events")
