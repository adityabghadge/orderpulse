from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.order import Order


class Customer(TimestampMixin, Base):
    __tablename__ = "customers"
    __table_args__ = (CheckConstraint("tier IN ('standard', 'plus')", name="tier_valid"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(255), unique=True)
    city: Mapped[str] = mapped_column(String(80))
    tier: Mapped[str] = mapped_column(String(20), default="standard", server_default="standard")

    orders: Mapped[list["Order"]] = relationship(back_populates="customer")
