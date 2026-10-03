"""daily operations view and reporting indexes

Precomputes per-day totals for the operations overview so the dashboard reads ~120 small
rows instead of aggregating every order on each request. Days are UTC calendar days.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-02
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DAILY_OPERATIONS = """
CREATE MATERIALIZED VIEW daily_operations AS
WITH placed AS (
    SELECT (placed_at AT TIME ZONE 'UTC')::date AS day,
           count(*) AS orders,
           sum(total_cents) AS revenue_cents
    FROM orders
    GROUP BY 1
),
delivered AS (
    SELECT (delivered_at AT TIME ZONE 'UTC')::date AS day,
           count(*) AS delivered,
           sum(extract(epoch FROM delivered_at - placed_at)) AS delivery_seconds
    FROM orders
    WHERE delivered_at IS NOT NULL
    GROUP BY 1
),
cancelled AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
           count(*) AS cancelled
    FROM order_status_events
    WHERE to_status = 'cancelled'
    GROUP BY 1
),
refunded AS (
    SELECT (created_at AT TIME ZONE 'UTC')::date AS day,
           count(*) AS refunds,
           sum(amount_cents) AS refunded_cents
    FROM refunds
    GROUP BY 1
),
days AS (
    SELECT day FROM placed
    UNION SELECT day FROM delivered
    UNION SELECT day FROM cancelled
    UNION SELECT day FROM refunded
)
SELECT days.day,
       coalesce(placed.orders, 0)::int AS orders,
       coalesce(placed.revenue_cents, 0)::bigint AS revenue_cents,
       coalesce(delivered.delivered, 0)::int AS delivered,
       coalesce(delivered.delivery_seconds, 0)::double precision AS delivery_seconds,
       coalesce(cancelled.cancelled, 0)::int AS cancelled,
       coalesce(refunded.refunds, 0)::int AS refunds,
       coalesce(refunded.refunded_cents, 0)::bigint AS refunded_cents
FROM days
LEFT JOIN placed USING (day)
LEFT JOIN delivered USING (day)
LEFT JOIN cancelled USING (day)
LEFT JOIN refunded USING (day)
"""


def upgrade() -> None:
    # Indexes that keep the "today so far" queries fast.
    op.create_index(
        "ix_order_status_events_to_status_created_at",
        "order_status_events",
        ["to_status", "created_at"],
    )
    op.create_index("ix_orders_delivered_at", "orders", ["delivered_at"])
    op.create_index("ix_refunds_created_at", "refunds", ["created_at"])

    op.execute(DAILY_OPERATIONS)
    # A unique index lets the view be refreshed CONCURRENTLY (readers are never blocked).
    op.execute("CREATE UNIQUE INDEX ux_daily_operations_day ON daily_operations (day)")


def downgrade() -> None:
    op.execute("DROP MATERIALIZED VIEW daily_operations")
    op.drop_index("ix_refunds_created_at", table_name="refunds")
    op.drop_index("ix_orders_delivered_at", table_name="orders")
    op.drop_index("ix_order_status_events_to_status_created_at", table_name="order_status_events")
