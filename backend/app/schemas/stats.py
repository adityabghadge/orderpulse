from datetime import date

from pydantic import BaseModel


class PipelineStage(BaseModel):
    status: str
    count: int


class DailyOrders(BaseModel):
    day: date
    orders: int
    revenue_cents: int


class TeamLoad(BaseModel):
    team: str
    open_returns: int


class OverviewStats(BaseModel):
    pipeline: list[PipelineStage]
    delivered_last_7d: int
    cancelled_last_7d: int
    orders_today: int
    revenue_today_cents: int
    open_returns: int
    returns_by_status: dict[str, int]
    refunded_30d_cents: int
    refunds_30d: int
    avg_delivery_hours_30d: float | None
    orders_per_day: list[DailyOrders]
    open_returns_by_team: list[TeamLoad]
