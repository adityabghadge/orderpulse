from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Customer


def list_customers(db: Session, *, search: str | None = None, limit: int = 25) -> list[Customer]:
    query = select(Customer).order_by(Customer.full_name).limit(limit)
    if search:
        term = f"%{search.strip()}%"
        query = query.where(or_(Customer.full_name.ilike(term), Customer.email.ilike(term)))
    return list(db.scalars(query).all())


def get_customer(db: Session, customer_id: int) -> Customer:
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise NotFoundError(f"Customer {customer_id} not found")
    return customer
