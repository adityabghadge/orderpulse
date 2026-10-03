from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field

from app.domain.returns import ReturnReason, ReturnStatus, Team, priority_level


class ReturnCreate(BaseModel):
    order_item_id: int
    quantity: int = Field(ge=1, le=100)
    reason_code: ReturnReason
    reason_text: str = Field(min_length=10, max_length=1000)


class ReturnStatusUpdate(BaseModel):
    status: Literal["approved", "rejected", "received"]
    note: str | None = Field(default=None, max_length=500)


class TeamUpdate(BaseModel):
    team: Team


class RefundRequest(BaseModel):
    note: str | None = Field(default=None, max_length=500)


class RefundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    return_number: str
    amount_cents: int
    currency: str
    status: str
    provider_reference: str
    created_at: datetime


class ReturnOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    return_number: str
    order_number: str
    order_item_id: int
    quantity: int
    reason_code: ReturnReason
    reason_text: str
    status: ReturnStatus
    assigned_team: Team | None
    routing_source: Literal["rule", "model", "agent"] | None
    routing_confidence: float | None
    priority_score: float | None
    decision_note: str | None
    refund_amount_cents: int
    requested_at: datetime
    resolved_at: datetime | None
    refund: RefundOut | None

    @computed_field
    @property
    def priority(self) -> Literal["high", "medium", "low"] | None:
        return priority_level(self.priority_score)


class ReturnPage(BaseModel):
    items: list[ReturnOut]
    total: int
    limit: int
    offset: int
