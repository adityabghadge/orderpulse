"""Return lifecycle, reasons, and routing rules.

    requested -> approved -> received -> refunded
        |
        +-> rejected

`refunded` is only reachable through the refund endpoint, never by a plain status change,
so a return can't be marked refunded without money actually moving.
"""

from enum import StrEnum

RETURN_WINDOW_DAYS = 30


class ReturnStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    RECEIVED = "received"
    REFUNDED = "refunded"


ALLOWED_RETURN_TRANSITIONS: dict[ReturnStatus, frozenset[ReturnStatus]] = {
    ReturnStatus.REQUESTED: frozenset({ReturnStatus.APPROVED, ReturnStatus.REJECTED}),
    ReturnStatus.APPROVED: frozenset({ReturnStatus.RECEIVED}),
    ReturnStatus.RECEIVED: frozenset({ReturnStatus.REFUNDED}),
    ReturnStatus.REJECTED: frozenset(),
    ReturnStatus.REFUNDED: frozenset(),
}

# Statuses an operator may set directly. REFUNDED requires issuing a refund.
MANUAL_RETURN_STATUSES = frozenset(
    {ReturnStatus.APPROVED, ReturnStatus.REJECTED, ReturnStatus.RECEIVED}
)


def can_transition_return(current: ReturnStatus, target: ReturnStatus) -> bool:
    return target in ALLOWED_RETURN_TRANSITIONS[current]


class ReturnReason(StrEnum):
    """The reason the customer picks from a dropdown when requesting a return."""

    DAMAGED = "damaged"
    DEFECTIVE = "defective"
    WRONG_ITEM = "wrong_item"
    MISSING_PARTS = "missing_parts"
    NOT_AS_DESCRIBED = "not_as_described"
    SIZE_FIT = "size_fit"
    LATE_DELIVERY = "late_delivery"
    CHANGED_MIND = "changed_mind"


class Team(StrEnum):
    """Operations teams that handle returns."""

    LOGISTICS = "logistics"  # carrier damage, delivery delays
    QUALITY = "quality"  # manufacturing defects, listing accuracy
    FULFILLMENT = "fulfillment"  # warehouse picking and packing mistakes
    CUSTOMER_CARE = "customer_care"  # fit, preference, goodwill cases


REASON_TO_TEAM: dict[ReturnReason, Team] = {
    ReturnReason.DAMAGED: Team.LOGISTICS,
    ReturnReason.LATE_DELIVERY: Team.LOGISTICS,
    ReturnReason.DEFECTIVE: Team.QUALITY,
    ReturnReason.NOT_AS_DESCRIBED: Team.QUALITY,
    ReturnReason.WRONG_ITEM: Team.FULFILLMENT,
    ReturnReason.MISSING_PARTS: Team.FULFILLMENT,
    ReturnReason.SIZE_FIT: Team.CUSTOMER_CARE,
    ReturnReason.CHANGED_MIND: Team.CUSTOMER_CARE,
}


def route_by_reason(reason: ReturnReason) -> Team:
    """Baseline router: trusts the dropdown the customer picked.

    Customers often pick the wrong dropdown option (a box crushed in transit gets reported
    as "defective"), so this rule misroutes a meaningful share of returns. It's the baseline
    a text-based model has to beat.
    """
    return REASON_TO_TEAM[reason]
