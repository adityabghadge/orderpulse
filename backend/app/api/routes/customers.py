from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.customer import CustomerOut
from app.services import customers as customer_service

router = APIRouter(prefix="/customers", tags=["customers"])

DbSession = Annotated[Session, Depends(get_db)]


@router.get("", response_model=list[CustomerOut])
def list_customers(
    db: DbSession,
    q: Annotated[str | None, Query(max_length=80, description="Name or email")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 25,
) -> list[CustomerOut]:
    return customer_service.list_customers(db, search=q, limit=limit)


@router.get("/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: int, db: DbSession) -> CustomerOut:
    return customer_service.get_customer(db, customer_id)
