"""The order lifecycle, expressed as a state machine.

An order can only move along the arrows below. Anything else (for example jumping from
`placed` straight to `delivered`) is rejected, which keeps the data trustworthy for the
dashboards and models built on top of it.

    placed -> packed -> shipped -> out_for_delivery -> delivered
       |         |
       +---------+--> cancelled
"""

from enum import StrEnum


class OrderStatus(StrEnum):
    PLACED = "placed"
    PACKED = "packed"
    SHIPPED = "shipped"
    OUT_FOR_DELIVERY = "out_for_delivery"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


ALLOWED_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.PLACED: frozenset({OrderStatus.PACKED, OrderStatus.CANCELLED}),
    OrderStatus.PACKED: frozenset({OrderStatus.SHIPPED, OrderStatus.CANCELLED}),
    OrderStatus.SHIPPED: frozenset({OrderStatus.OUT_FOR_DELIVERY}),
    OrderStatus.OUT_FOR_DELIVERY: frozenset({OrderStatus.DELIVERED}),
    OrderStatus.DELIVERED: frozenset(),
    OrderStatus.CANCELLED: frozenset(),
}

TERMINAL_STATUSES = frozenset(s for s, nxt in ALLOWED_TRANSITIONS.items() if not nxt)


def can_transition(current: OrderStatus, target: OrderStatus) -> bool:
    return target in ALLOWED_TRANSITIONS[current]
