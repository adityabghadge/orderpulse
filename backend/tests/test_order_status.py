from itertools import product

import pytest

from app.domain.order_status import (
    ALLOWED_TRANSITIONS,
    TERMINAL_STATUSES,
    OrderStatus,
    can_transition,
)

VALID = {
    (OrderStatus.PLACED, OrderStatus.PACKED),
    (OrderStatus.PLACED, OrderStatus.CANCELLED),
    (OrderStatus.PACKED, OrderStatus.SHIPPED),
    (OrderStatus.PACKED, OrderStatus.CANCELLED),
    (OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY),
    (OrderStatus.OUT_FOR_DELIVERY, OrderStatus.DELIVERED),
}


@pytest.mark.parametrize(("current", "target"), list(product(OrderStatus, OrderStatus)))
def test_every_transition_matches_the_lifecycle(current, target):
    assert can_transition(current, target) == ((current, target) in VALID)


def test_every_status_has_rules():
    assert set(ALLOWED_TRANSITIONS) == set(OrderStatus)


def test_terminal_statuses():
    assert TERMINAL_STATUSES == {OrderStatus.DELIVERED, OrderStatus.CANCELLED}
