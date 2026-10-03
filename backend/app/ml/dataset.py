"""Loading model inputs from the database.

The same SQL feeds training (closed returns, with known outcomes) and scoring (open returns),
so the features a model learns from are computed exactly the way they are at prediction time.
"""

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.ml.priority import PriorityInput

_RETURNS_WITH_CONTEXT = """
SELECT r.id,
       r.reason_text,
       r.reason_code,
       r.assigned_team,
       r.escalated,
       r.refund_amount_cents,
       o.total_cents,
       c.tier = 'plus' AS plus_member,
       -- returns this customer made before this one (no peeking at the future)
       count(*) OVER (
           PARTITION BY o.customer_id ORDER BY r.requested_at, r.id
           ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
       ) AS customer_other_returns,
       extract(epoch FROM r.requested_at - o.delivered_at) / 86400 AS days_since_delivery,
       r.requested_at
FROM returns r
JOIN orders o ON o.id = r.order_id
JOIN customers c ON c.id = o.customer_id
"""


@dataclass(frozen=True)
class ReturnExample:
    id: int
    text: str
    reason: str
    team: str | None
    escalated: bool | None
    priority_input: PriorityInput


def _to_example(row) -> ReturnExample:
    return ReturnExample(
        id=row.id,
        text=row.reason_text,
        reason=row.reason_code,
        team=row.assigned_team,
        escalated=row.escalated,
        priority_input=PriorityInput(
            refund_amount_cents=row.refund_amount_cents,
            order_total_cents=row.total_cents,
            plus_member=row.plus_member,
            customer_other_returns=row.customer_other_returns,
            days_since_delivery=float(row.days_since_delivery or 0),
            reason_code=row.reason_code,
            reason_text=row.reason_text,
        ),
    )


def closed_returns(db: Session) -> list[ReturnExample]:
    """Resolved returns, oldest first: their team and escalation outcome are known."""
    rows = db.execute(
        text(
            f"SELECT * FROM ({_RETURNS_WITH_CONTEXT}) t "
            "WHERE t.escalated IS NOT NULL ORDER BY t.requested_at, t.id"
        )
    ).all()
    return [_to_example(r) for r in rows]


def open_returns(db: Session, ids: list[int] | None = None) -> list[ReturnExample]:
    """Returns still in progress (optionally only the given ids)."""
    query = (
        f"SELECT * FROM ({_RETURNS_WITH_CONTEXT}) t "
        "WHERE t.id IN (SELECT id FROM returns WHERE status IN "
        "('requested', 'approved', 'received'))"
    )
    params = {}
    if ids is not None:
        query += " AND t.id = ANY(:ids)"
        params["ids"] = ids
    return [_to_example(r) for r in db.execute(text(query), params).all()]
