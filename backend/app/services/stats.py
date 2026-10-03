"""Numbers for the operations overview.

Two ways to compute the same result:

* `overview_live` aggregates the raw tables on every call. Simple and always exact, but its
  cost grows with the number of orders.
* `overview` (used by the API) reads finished days from the `daily_operations` materialized
  view and computes only *today* live, using indexed queries. Its cost stays flat as history
  grows. The view is refreshed in the background, and since today is always computed live,
  a refresh delay only affects activity on past days that happened after the last refresh.

A test checks that both functions return identical results.

All "last N days" windows are UTC calendar days that include today.
"""

from datetime import date, datetime, timedelta

from sqlalchemy import Date, cast, extract, func, select, text
from sqlalchemy.orm import Session

from app.core.cache import get_cache
from app.core.config import get_settings
from app.domain.order_status import OrderStatus
from app.domain.returns import ReturnStatus, Team
from app.models import Order, OrderStatusEvent, Refund, Return
from app.schemas.stats import DailyOrders, OverviewStats, PipelineStage, TeamLoad

ACTIVE_STAGES = [
    OrderStatus.PLACED,
    OrderStatus.PACKED,
    OrderStatus.SHIPPED,
    OrderStatus.OUT_FOR_DELIVERY,
]
OPEN_RETURN_STATUSES = [ReturnStatus.REQUESTED, ReturnStatus.APPROVED, ReturnStatus.RECEIVED]
HISTORY_DAYS = 30
WEEK_DAYS = 7
OVERVIEW_CACHE_KEY = "stats:overview:v1"
DAY_FIELDS = [
    "orders",
    "revenue_cents",
    "delivered",
    "delivery_seconds",
    "cancelled",
    "refunds",
    "refunded_cents",
]


# --- shared pieces ------------------------------------------------------------------------


def _utc_today(db: Session) -> tuple[date, datetime]:
    """Today's UTC date and the timestamp of its midnight, according to the database clock."""
    day, midnight = db.execute(
        text(
            "SELECT (now() AT TIME ZONE 'UTC')::date, "
            "date_trunc('day', now() AT TIME ZONE 'UTC') AT TIME ZONE 'UTC'"
        )
    ).one()
    return day, midnight


def _pipeline(db: Session) -> list[PipelineStage]:
    counts = dict(
        db.execute(
            select(Order.status, func.count())
            .where(Order.status.in_([s.value for s in ACTIVE_STAGES]))
            .group_by(Order.status)
        ).all()
    )
    return [PipelineStage(status=s.value, count=counts.get(s.value, 0)) for s in ACTIVE_STAGES]


def _returns(db: Session) -> tuple[dict[str, int], list[TeamLoad]]:
    by_status = dict(db.execute(select(Return.status, func.count()).group_by(Return.status)).all())
    by_team = dict(
        db.execute(
            select(Return.assigned_team, func.count())
            .where(Return.status.in_([s.value for s in OPEN_RETURN_STATUSES]))
            .group_by(Return.assigned_team)
        ).all()
    )
    return (
        {s.value: by_status.get(s.value, 0) for s in ReturnStatus},
        [TeamLoad(team=t.value, open_returns=by_team.get(t.value, 0)) for t in Team],
    )


def _assemble(db: Session, today: date, days: dict[date, dict[str, float]]) -> OverviewStats:
    """Build the response from per-day totals covering the last HISTORY_DAYS days."""

    def window(field: str, length: int) -> float:
        start = today - timedelta(days=length - 1)
        return sum(row[field] for day, row in days.items() if day >= start)

    empty = {"orders": 0, "revenue_cents": 0}
    series = [today - timedelta(days=offset) for offset in range(HISTORY_DAYS - 1, -1, -1)]
    delivered_30d = window("delivered", HISTORY_DAYS)
    returns_by_status, team_load = _returns(db)
    today_row = days.get(today, empty)

    return OverviewStats(
        pipeline=_pipeline(db),
        delivered_last_7d=int(window("delivered", WEEK_DAYS)),
        cancelled_last_7d=int(window("cancelled", WEEK_DAYS)),
        orders_today=int(today_row["orders"]),
        revenue_today_cents=int(today_row["revenue_cents"]),
        open_returns=sum(returns_by_status[s.value] for s in OPEN_RETURN_STATUSES),
        returns_by_status=returns_by_status,
        refunded_30d_cents=int(window("refunded_cents", HISTORY_DAYS)),
        refunds_30d=int(window("refunds", HISTORY_DAYS)),
        avg_delivery_hours_30d=(
            round(window("delivery_seconds", HISTORY_DAYS) / delivered_30d / 3600, 1)
            if delivered_30d
            else None
        ),
        orders_per_day=[
            DailyOrders(
                day=day,
                orders=int(days.get(day, empty)["orders"]),
                revenue_cents=int(days.get(day, empty)["revenue_cents"]),
            )
            for day in series
        ],
        open_returns_by_team=team_load,
    )


def _merge(days: dict[date, dict[str, float]], rows, field_names: list[str]) -> None:
    zero = dict.fromkeys(DAY_FIELDS, 0)
    for day, *values in rows:
        target = days.setdefault(day, dict(zero))
        for name, value in zip(field_names, values, strict=True):
            target[name] += float(value or 0)


# --- live: aggregate raw tables on every call ---------------------------------------------


def overview_live(db: Session) -> OverviewStats:
    today, midnight = _utc_today(db)
    since = midnight - timedelta(days=HISTORY_DAYS - 1)
    days: dict[date, dict[str, float]] = {}

    def daily(timestamp, *aggregates, where):
        day = cast(func.timezone("UTC", timestamp), Date)
        return db.execute(select(day, *aggregates).where(*where).group_by(day)).all()

    _merge(
        days,
        daily(
            Order.placed_at,
            func.count(),
            func.sum(Order.total_cents),
            where=[Order.placed_at >= since],
        ),
        ["orders", "revenue_cents"],
    )
    _merge(
        days,
        daily(
            Order.delivered_at,
            func.count(),
            func.sum(extract("epoch", Order.delivered_at - Order.placed_at)),
            where=[Order.delivered_at >= since],
        ),
        ["delivered", "delivery_seconds"],
    )
    _merge(
        days,
        daily(
            OrderStatusEvent.created_at,
            func.count(),
            where=[
                OrderStatusEvent.to_status == OrderStatus.CANCELLED.value,
                OrderStatusEvent.created_at >= since,
            ],
        ),
        ["cancelled"],
    )
    _merge(
        days,
        daily(
            Refund.created_at,
            func.count(),
            func.sum(Refund.amount_cents),
            where=[Refund.created_at >= since],
        ),
        ["refunds", "refunded_cents"],
    )
    return _assemble(db, today, days)


# --- fast: precomputed history + live "today" ---------------------------------------------


def overview(db: Session) -> OverviewStats:
    today, midnight = _utc_today(db)
    days: dict[date, dict[str, float]] = {}

    history = db.execute(
        text(
            "SELECT day, orders, revenue_cents, delivered, delivery_seconds, cancelled, "
            "refunds, refunded_cents FROM daily_operations "
            "WHERE day >= :start AND day < :today"
        ),
        {"start": today - timedelta(days=HISTORY_DAYS - 1), "today": today},
    ).all()
    _merge(days, history, DAY_FIELDS)

    # Today so far, straight from the tables. Each query is an index range scan.
    orders_today = db.execute(
        select(func.count(), func.sum(Order.total_cents)).where(Order.placed_at >= midnight)
    ).one()
    delivered_today = db.execute(
        select(
            func.count(), func.sum(extract("epoch", Order.delivered_at - Order.placed_at))
        ).where(Order.delivered_at >= midnight)
    ).one()
    cancelled_today = db.scalar(
        select(func.count()).where(
            OrderStatusEvent.to_status == OrderStatus.CANCELLED.value,
            OrderStatusEvent.created_at >= midnight,
        )
    )
    refunds_today = db.execute(
        select(func.count(), func.sum(Refund.amount_cents)).where(Refund.created_at >= midnight)
    ).one()
    _merge(
        days,
        [(today, *orders_today, *delivered_today, cancelled_today, *refunds_today)],
        DAY_FIELDS,
    )
    return _assemble(db, today, days)


def cached_overview(db: Session) -> tuple[dict, bool]:
    """The overview as JSON, served from Redis when possible. Returns (payload, cache_hit)."""
    cache = get_cache()
    cached = cache.get_json(OVERVIEW_CACHE_KEY)
    if cached is not None:
        return cached, True
    payload = overview(db).model_dump(mode="json")
    cache.set_json(OVERVIEW_CACHE_KEY, payload, get_settings().overview_cache_seconds)
    return payload, False


def invalidate_overview() -> None:
    """Called after any write that changes the numbers, so operators see their own changes."""
    get_cache().delete(OVERVIEW_CACHE_KEY)


def refresh_daily_operations(db: Session, *, concurrently: bool = True) -> bool:
    """Recompute the materialized view. Returns False if another process is already doing it.

    A Postgres advisory lock makes sure only one API process refreshes at a time, even when
    several are running. CONCURRENTLY lets dashboards keep reading the old data meanwhile.
    """
    if not db.scalar(text("SELECT pg_try_advisory_xact_lock(hashtext('daily_operations'))")):
        db.rollback()
        return False
    mode = "CONCURRENTLY " if concurrently else ""
    db.execute(text(f"REFRESH MATERIALIZED VIEW {mode}daily_operations"))
    db.commit()
    return True
