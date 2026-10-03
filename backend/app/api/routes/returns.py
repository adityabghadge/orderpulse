from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Header, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.domain.returns import ReturnReason, ReturnStatus
from app.integrations.payments import PaymentGateway, get_payment_gateway
from app.schemas.returns import (
    RefundOut,
    RefundRequest,
    ReturnCreate,
    ReturnOut,
    ReturnPage,
    ReturnStatusUpdate,
)
from app.services import returns as return_service

DbSession = Annotated[Session, Depends(get_db)]

order_returns_router = APIRouter(prefix="/orders", tags=["returns"])
router = APIRouter(prefix="/returns", tags=["returns"])


@order_returns_router.post(
    "/{order_number}/returns", response_model=ReturnOut, status_code=status.HTTP_201_CREATED
)
def create_return(order_number: str, payload: ReturnCreate, db: DbSession) -> ReturnOut:
    """Request a return for one line item of a delivered order (within the return window)."""
    return return_service.create_return(db, order_number, payload)


@router.get("", response_model=ReturnPage)
def list_returns(
    db: DbSession,
    status_filter: Annotated[ReturnStatus | None, Query(alias="status")] = None,
    reason: ReturnReason | None = None,
    order_number: Annotated[str | None, Query(max_length=20)] = None,
    sort: Literal["newest", "oldest"] = "newest",
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReturnPage:
    rows, total = return_service.list_returns(
        db,
        status=status_filter,
        reason=reason,
        order_number=order_number,
        oldest_first=sort == "oldest",
        limit=limit,
        offset=offset,
    )
    return ReturnPage(
        items=[ReturnOut.model_validate(r) for r in rows], total=total, limit=limit, offset=offset
    )


@router.get("/{return_number}", response_model=ReturnOut)
def get_return(return_number: str, db: DbSession) -> ReturnOut:
    return return_service.get_return(db, return_number)


@router.post("/{return_number}/status", response_model=ReturnOut)
def update_return_status(
    return_number: str, payload: ReturnStatusUpdate, db: DbSession
) -> ReturnOut:
    """Approve, reject, or mark a return as received at the warehouse."""
    return return_service.change_return_status(
        db, return_number, ReturnStatus(payload.status), payload.note
    )


@router.post(
    "/{return_number}/refund",
    response_model=RefundOut,
    status_code=status.HTTP_201_CREATED,
    responses={
        409: {"description": "Return not received yet, or already refunded"},
        422: {"description": "Idempotency-Key reused with a different request"},
        502: {"description": "Payment provider failed; safe to retry with the same key"},
    },
)
def issue_refund(
    return_number: str,
    response: Response,
    db: DbSession,
    gateway: Annotated[PaymentGateway, Depends(get_payment_gateway)],
    idempotency_key: Annotated[
        str,
        Header(
            alias="Idempotency-Key",
            min_length=8,
            max_length=255,
            description="Unique per refund attempt (e.g. a UUID). Retries must reuse it.",
        ),
    ],
    payload: RefundRequest | None = None,
) -> dict:
    """Refund a received return. Safe to retry: the same key never refunds twice."""
    result = return_service.issue_refund(
        db,
        return_number,
        idempotency_key=idempotency_key,
        note=payload.note if payload else None,
        gateway=gateway,
    )
    response.status_code = result.status_code
    if result.replayed:
        response.headers["Idempotent-Replayed"] = "true"
    return result.body
