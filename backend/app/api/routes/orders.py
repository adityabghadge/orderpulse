from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.order_status import OrderStatus
from app.schemas.order import OrderCreate, OrderDetail, OrderPage, OrderSummary, StatusUpdate
from app.services import orders as order_service

router = APIRouter(prefix="/orders", tags=["orders"])

DbSession = Annotated[Session, Depends(get_db)]


@router.post("", response_model=OrderDetail, status_code=status.HTTP_201_CREATED)
def create_order(payload: OrderCreate, db: DbSession) -> OrderDetail:
    """Place a new order. The total is calculated by the server from the line items."""
    return order_service.create_order(db, payload)


@router.get("", response_model=OrderPage)
def list_orders(
    db: DbSession,
    status_filter: Annotated[OrderStatus | None, Query(alias="status")] = None,
    customer_id: int | None = None,
    q: Annotated[str | None, Query(max_length=80, description="Order number or city")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> OrderPage:
    """List orders, newest first, with optional filters and pagination."""
    rows, total = order_service.list_orders(
        db, status=status_filter, customer_id=customer_id, search=q, limit=limit, offset=offset
    )
    return OrderPage(
        items=[OrderSummary.model_validate(o) for o in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{order_number}", response_model=OrderDetail)
def get_order(order_number: str, db: DbSession) -> OrderDetail:
    """Full order details, including line items and the status history."""
    return order_service.get_order(db, order_number)


@router.post("/{order_number}/status", response_model=OrderDetail)
def update_status(order_number: str, payload: StatusUpdate, db: DbSession) -> OrderDetail:
    """Move an order to its next lifecycle status. Invalid moves return 409 Conflict."""
    return order_service.change_status(
        db, order_number, payload.status, actor=payload.actor, note=payload.note
    )
