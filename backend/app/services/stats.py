"""Aggregates for the operations overview.

These queries scan the orders and returns tables on every call. That's fine for thousands
of rows; the next step for larger data is precomputing them (materialized views + cache).
"""

from sqlalchemy import Date, cast, extract, func, select, text
from sqlalchemy.orm import Session

from app.domain.order_status import OrderStatus
from app.domain.returns import ReturnStatus, Team
from app.models import Order, Refund, Return
from app.schemas.stats import DailyOrders, OverviewStats, PipelineStage, TeamLoad

ACTIVE_STAGES = [
    OrderStatus.PLACED,
    OrderStatus.PACKED,
    OrderStatus.SHIPPED,
    OrderStatus.OUT_FOR_DELIVERY,
]
OPEN_RETURN_STATUSES = [ReturnStatus.REQUESTED, ReturnStatus.APPROVED, ReturnStatus.RECEIVED]
DAYS_OF_HISTORY = 30


def overview(db: Session) -> OverviewStats:
    now = func.now()
    week_ago = now - text("interval '7 days'")
    month_ago = now - text("interval '30 days'")
    today = func.date_trunc("day", now)

    stage_counts = dict(
        db.execute(
            select(Order.status, func.count())
            .where(Order.status.in_([s.value for s in ACTIVE_STAGES]))
            .group_by(Order.status)
        ).all()
    )

    delivered_7d, cancelled_7d, orders_today, revenue_today, avg_delivery_seconds = db.execute(
        select(
            func.count().filter(Order.delivered_at >= week_ago),
            func.count().filter(
                Order.status == OrderStatus.CANCELLED.value, Order.updated_at >= week_ago
            ),
            func.count().filter(Order.placed_at >= today),
            func.coalesce(func.sum(Order.total_cents).filter(Order.placed_at >= today), 0),
            func.avg(extract("epoch", Order.delivered_at - Order.placed_at)).filter(
                Order.delivered_at >= month_ago
            ),
        )
    ).one()

    return_counts = dict(
        db.execute(select(Return.status, func.count()).group_by(Return.status)).all()
    )
    refunded_30d, refunds_30d = db.execute(
        select(func.coalesce(func.sum(Refund.amount_cents), 0), func.count()).where(
            Refund.created_at >= month_ago
        )
    ).one()

    team_counts = dict(
        db.execute(
            select(Return.assigned_team, func.count())
            .where(Return.status.in_([s.value for s in OPEN_RETURN_STATUSES]))
            .group_by(Return.assigned_team)
        ).all()
    )

    days = (
        select(
            cast(
                func.generate_series(
                    func.date_trunc("day", now) - text(f"interval '{DAYS_OF_HISTORY - 1} days'"),
                    func.date_trunc("day", now),
                    text("interval '1 day'"),
                ),
                Date,
            ).label("day")
        )
    ).subquery()
    order_day = cast(func.date_trunc("day", Order.placed_at), Date)
    daily = db.execute(
        select(
            days.c.day,
            func.count(Order.id),
            func.coalesce(func.sum(Order.total_cents), 0),
        )
        .select_from(days)
        .outerjoin(Order, order_day == days.c.day)
        .group_by(days.c.day)
        .order_by(days.c.day)
    ).all()

    return OverviewStats(
        pipeline=[
            PipelineStage(status=s.value, count=stage_counts.get(s.value, 0)) for s in ACTIVE_STAGES
        ],
        delivered_last_7d=delivered_7d,
        cancelled_last_7d=cancelled_7d,
        orders_today=orders_today,
        revenue_today_cents=int(revenue_today),
        open_returns=sum(return_counts.get(s.value, 0) for s in OPEN_RETURN_STATUSES),
        returns_by_status={s.value: return_counts.get(s.value, 0) for s in ReturnStatus},
        refunded_30d_cents=int(refunded_30d),
        refunds_30d=refunds_30d,
        avg_delivery_hours_30d=(
            round(float(avg_delivery_seconds) / 3600, 1) if avg_delivery_seconds else None
        ),
        orders_per_day=[
            DailyOrders(day=day, orders=count, revenue_cents=int(revenue))
            for day, count, revenue in daily
        ],
        open_returns_by_team=[
            TeamLoad(team=t.value, open_returns=team_counts.get(t.value, 0)) for t in Team
        ],
    )
