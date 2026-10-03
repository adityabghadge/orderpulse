from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
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
from app.domain.returns import ReturnReason, ReturnStatus, Team

if TYPE_CHECKING:
    from app.models.order import Order, OrderItem
    from app.models.refund import Refund

return_number_seq = Sequence("return_number_seq", start=500000, metadata=Base.metadata)


def _in(values) -> str:
    return ", ".join(f"'{v.value}'" for v in values)


class Return(TimestampMixin, Base):
    __tablename__ = "returns"
    __table_args__ = (
        CheckConstraint(f"status IN ({_in(ReturnStatus)})", name="status_valid"),
        CheckConstraint(f"reason_code IN ({_in(ReturnReason)})", name="reason_code_valid"),
        CheckConstraint(
            f"assigned_team IS NULL OR assigned_team IN ({_in(Team)})", name="team_valid"
        ),
        CheckConstraint("quantity > 0", name="quantity_positive"),
        CheckConstraint(
            "routing_source IS NULL OR routing_source IN ('rule', 'model', 'agent')",
            name="routing_source_valid",
        ),
        Index("ix_returns_status_requested_at", "status", "requested_at"),
        Index("ix_returns_status_priority_score", "status", "priority_score"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    return_number: Mapped[str] = mapped_column(
        String(20), unique=True, server_default=text("'RT-' || nextval('return_number_seq')")
    )
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    order_item_id: Mapped[int] = mapped_column(ForeignKey("order_items.id"), index=True)
    quantity: Mapped[int] = mapped_column(Integer)
    reason_code: Mapped[str] = mapped_column(String(32))
    reason_text: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default=ReturnStatus.REQUESTED.value)
    assigned_team: Mapped[str | None] = mapped_column(String(24))
    # How the team was chosen: the dropdown rule, the routing model, or an agent's correction.
    routing_source: Mapped[str | None] = mapped_column(String(8))
    routing_confidence: Mapped[float | None] = mapped_column(Float)
    # Model-estimated probability that this return escalates (complaint or chargeback).
    priority_score: Mapped[float | None] = mapped_column(Float)
    # Known only after a return is closed: did the customer escalate? (training label)
    escalated: Mapped[bool | None] = mapped_column(Boolean)
    decision_note: Mapped[str | None] = mapped_column(Text)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    refund_amount_cents: Mapped[int] = mapped_column(BigInteger)

    order: Mapped["Order"] = relationship(lazy="joined")
    item: Mapped["OrderItem"] = relationship(lazy="joined")
    refund: Mapped["Refund | None"] = relationship(back_populates="return_", lazy="joined")

    @property
    def order_number(self) -> str:
        return self.order.order_number
