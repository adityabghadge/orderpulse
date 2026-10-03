"""Business logic for returns and refunds."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import ConflictError, NotFoundError, PaymentProviderError
from app.core.idempotency import IdempotentResult, fingerprint, run_idempotent
from app.domain.order_status import OrderStatus
from app.domain.returns import (
    RETURN_WINDOW_DAYS,
    ReturnReason,
    ReturnStatus,
    can_transition_return,
    route_by_reason,
)
from app.integrations.payments import PaymentGateway, PaymentGatewayError
from app.models import Order, Refund, Return
from app.schemas.returns import RefundOut, ReturnCreate


def create_return(db: Session, order_number: str, data: ReturnCreate) -> Return:
    # Lock the order so two simultaneous return requests for the same item can't both pass
    # the "enough quantity left" check below.
    order = db.scalar(select(Order).where(Order.order_number == order_number).with_for_update())
    if order is None:
        raise NotFoundError(f"Order {order_number} not found")
    if order.status != OrderStatus.DELIVERED.value or order.delivered_at is None:
        raise ConflictError("Only delivered orders can be returned")
    if datetime.now(UTC) - order.delivered_at > timedelta(days=RETURN_WINDOW_DAYS):
        raise ConflictError(f"The {RETURN_WINDOW_DAYS}-day return window has closed")

    item = next((i for i in order.items if i.id == data.order_item_id), None)
    if item is None:
        raise NotFoundError(f"Item {data.order_item_id} is not part of order {order_number}")

    already_returned = db.scalar(
        select(func.coalesce(func.sum(Return.quantity), 0)).where(
            Return.order_item_id == item.id, Return.status != ReturnStatus.REJECTED.value
        )
    )
    remaining = item.quantity - already_returned
    if data.quantity > remaining:
        raise ConflictError(f"Only {remaining} unit(s) of this item can still be returned")

    record = Return(
        order_id=order.id,
        order_item_id=item.id,
        quantity=data.quantity,
        reason_code=data.reason_code.value,
        reason_text=data.reason_text.strip(),
        status=ReturnStatus.REQUESTED.value,
        assigned_team=route_by_reason(data.reason_code).value,
        refund_amount_cents=item.unit_price_cents * data.quantity,
    )
    db.add(record)
    db.commit()
    return get_return(db, record.return_number)


def get_return(db: Session, return_number: str) -> Return:
    record = db.scalar(select(Return).where(Return.return_number == return_number))
    if record is None:
        raise NotFoundError(f"Return {return_number} not found")
    return record


def list_returns(
    db: Session,
    *,
    status: ReturnStatus | None = None,
    order_number: str | None = None,
    reason: ReturnReason | None = None,
    limit: int = 25,
    offset: int = 0,
) -> tuple[list[Return], int]:
    filters = []
    if status is not None:
        filters.append(Return.status == status.value)
    if reason is not None:
        filters.append(Return.reason_code == reason.value)
    if order_number:
        filters.append(Return.order.has(Order.order_number == order_number))

    total = db.scalar(select(func.count()).select_from(Return).where(*filters)) or 0
    rows = db.scalars(
        select(Return)
        .where(*filters)
        .order_by(Return.requested_at.desc(), Return.id.desc())
        .limit(limit)
        .offset(offset)
    ).unique()
    return list(rows), total


def change_return_status(
    db: Session, return_number: str, target: ReturnStatus, note: str | None
) -> Return:
    record = _lock_return(db, return_number)
    current = ReturnStatus(record.status)
    if not can_transition_return(current, target):
        raise ConflictError(f"Cannot move return {return_number} from '{current}' to '{target}'")

    record.status = target.value
    if note:
        record.decision_note = note
    if target is ReturnStatus.REJECTED:
        record.resolved_at = datetime.now(UTC)
    db.commit()
    return get_return(db, return_number)


def issue_refund(
    db: Session,
    return_number: str,
    *,
    idempotency_key: str,
    note: str | None,
    gateway: PaymentGateway,
) -> IdempotentResult:
    """Refund a received return exactly once, no matter how many times it's requested.

    Two independent safeguards:
      * the Idempotency-Key makes retries of the *same* request replay the first result;
      * the return's row lock, status check, and UNIQUE(refunds.return_id) stop *different*
        requests from refunding the same return twice.
    """

    def operation() -> tuple[int, dict]:
        record = _lock_return(db, return_number)
        if record.status == ReturnStatus.REFUNDED.value:
            raise ConflictError(f"Return {return_number} has already been refunded")
        if record.status != ReturnStatus.RECEIVED.value:
            raise ConflictError("Refunds can only be issued after the item has been received")

        try:
            provider_reference = gateway.refund(
                order_number=record.order.order_number,
                amount_cents=record.refund_amount_cents,
                currency=record.order.currency,
                idempotency_key=idempotency_key,
            )
        except PaymentGatewayError as exc:
            raise PaymentProviderError(f"Payment provider error: {exc}") from exc

        refund = Refund(
            return_=record,
            order_id=record.order_id,
            amount_cents=record.refund_amount_cents,
            currency=record.order.currency,
            status="succeeded",
            provider_reference=provider_reference,
            idempotency_key=idempotency_key,
        )
        record.status = ReturnStatus.REFUNDED.value
        record.resolved_at = datetime.now(UTC)
        if note:
            record.decision_note = note
        db.add(refund)
        db.flush()
        return 201, RefundOut.model_validate(refund).model_dump(mode="json")

    return run_idempotent(
        db,
        key=idempotency_key,
        request_fingerprint=fingerprint("refund", return_number, note),
        operation=operation,
    )


def _lock_return(db: Session, return_number: str) -> Return:
    record = db.scalar(
        select(Return)
        .where(Return.return_number == return_number)
        .with_for_update(of=Return)
        .execution_options(populate_existing=True)
    )
    if record is None:
        raise NotFoundError(f"Return {return_number} not found")
    return record
