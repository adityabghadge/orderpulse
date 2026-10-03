from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import BigInteger, CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.returns import Return


class Refund(Base):
    __tablename__ = "refunds"
    __table_args__ = (CheckConstraint("amount_cents > 0", name="amount_positive"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    # UNIQUE: the database itself guarantees a return can be refunded at most once,
    # no matter which code path or idempotency key tries to do it.
    return_id: Mapped[int] = mapped_column(ForeignKey("returns.id"), unique=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id"), index=True)
    amount_cents: Mapped[int] = mapped_column(BigInteger)
    currency: Mapped[str] = mapped_column(String(3))
    status: Mapped[str] = mapped_column(String(16), default="succeeded")
    provider_reference: Mapped[str] = mapped_column(String(64), unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    return_: Mapped["Return"] = relationship(back_populates="refund")

    @property
    def return_number(self) -> str:
        return self.return_.return_number


class IdempotencyKey(Base):
    """Remembers the outcome of every request sent with an Idempotency-Key header.

    If a client retries (network timeout, double click, mobile app resending), the stored
    response is replayed instead of running the operation a second time.
    """

    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(255), primary_key=True)
    # Hash of the original request, so a key can't be reused for a different request.
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    response_status: Mapped[int | None] = mapped_column(Integer)
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
