"""Business logic for orders.

Routes stay thin (parse the request, call a function here, return the result). Everything
that encodes a business rule lives in this module, so it can be tested without HTTP and
reused later by background jobs.
"""

from datetime import UTC, datetime

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import ConflictError, NotFoundError
from app.domain.order_status import OrderStatus, can_transition
from app.models import Customer, Order, OrderItem, OrderStatusEvent
from app.schemas.order import OrderCreate


def create_order(db: Session, data: OrderCreate) -> Order:
    if db.get(Customer, data.customer_id) is None:
        raise NotFoundError(f"Customer {data.customer_id} not found")

    items = [OrderItem(**item.model_dump()) for item in data.items]
    order = Order(
        customer_id=data.customer_id,
        status=OrderStatus.PLACED.value,
        payment_method=data.payment_method,
        shipping_city=data.shipping_city,
        # The total is always computed on the server. Clients never send it.
        total_cents=sum(i.quantity * i.unit_price_cents for i in items),
        items=items,
        events=[
            OrderStatusEvent(
                from_status=None,
                to_status=OrderStatus.PLACED.value,
                actor="checkout",
                note="Order placed",
            )
        ],
    )
    db.add(order)
    db.commit()
    return get_order(db, order.order_number)


def list_orders(
    db: Session,
    *,
    status: OrderStatus | None = None,
    customer_id: int | None = None,
    search: str | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[Order], int]:
    filters = []
    if status is not None:
        filters.append(Order.status == status.value)
    if customer_id is not None:
        filters.append(Order.customer_id == customer_id)
    if search:
        term = f"%{search.strip()}%"
        filters.append(or_(Order.order_number.ilike(term), Order.shipping_city.ilike(term)))

    total = db.scalar(select(func.count()).select_from(Order).where(*filters)) or 0
    rows = db.scalars(
        select(Order)
        .where(*filters)
        .order_by(Order.placed_at.desc(), Order.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return list(rows), total


def get_order(db: Session, order_number: str) -> Order:
    order = db.scalar(
        select(Order).where(Order.order_number == order_number).options(selectinload(Order.events))
    )
    if order is None:
        raise NotFoundError(f"Order {order_number} not found")
    return order


def change_status(
    db: Session,
    order_number: str,
    target: OrderStatus,
    *,
    actor: str,
    note: str | None = None,
) -> Order:
    # SELECT ... FOR UPDATE locks this order's row until we commit. If two operators click
    # "ship" at the same moment, the second waits, then sees the new status and is rejected,
    # instead of both succeeding and writing two conflicting events.
    order = db.scalar(
        select(Order).where(Order.order_number == order_number).with_for_update(of=Order)
    )
    if order is None:
        raise NotFoundError(f"Order {order_number} not found")

    current = OrderStatus(order.status)
    if not can_transition(current, target):
        raise ConflictError(f"Cannot move order {order_number} from '{current}' to '{target}'")

    order.status = target.value
    if target is OrderStatus.DELIVERED:
        order.delivered_at = datetime.now(UTC)
    order.events.append(
        OrderStatusEvent(from_status=current.value, to_status=target.value, actor=actor, note=note)
    )
    db.commit()
    return get_order(db, order_number)
