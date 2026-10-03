"""Shared test setup.

Tests always run against a separate `orderpulse_test` database, never the development one,
so running the suite can't wipe the data you're working with.
"""

import os

os.environ["ORDERPULSE_DATABASE_URL"] = os.environ.get(
    "ORDERPULSE_TEST_DATABASE_URL",
    "postgresql+psycopg://orderpulse:orderpulse@localhost:5433/orderpulse_test",
)

from collections.abc import Iterator  # noqa: E402
from pathlib import Path  # noqa: E402

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Customer  # noqa: E402

BACKEND_DIR = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session", autouse=True)
def migrated_database() -> None:
    """Build the schema with the real migrations, so the migrations themselves are tested."""
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")


@pytest.fixture(autouse=True)
def clean_tables() -> Iterator[None]:
    yield
    with SessionLocal() as db:
        db.execute(
            text(
                "TRUNCATE idempotency_keys, refunds, returns, order_status_events, "
                "order_items, orders, customers RESTART IDENTITY CASCADE"
            )
        )
        db.commit()


@pytest.fixture
def db() -> Iterator[Session]:
    with SessionLocal() as session:
        yield session


@pytest.fixture
def client() -> Iterator[TestClient]:
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def customer(db: Session) -> Customer:
    record = Customer(full_name="Priya Shah", email="priya@example.com", city="Austin", tier="plus")
    db.add(record)
    db.commit()
    return record


@pytest.fixture
def order_payload(customer: Customer) -> dict:
    return {
        "customer_id": customer.id,
        "payment_method": "card",
        "shipping_city": "Austin",
        "items": [
            {
                "sku": "EL-1002",
                "product_name": "Bluetooth Speaker",
                "category": "electronics",
                "quantity": 2,
                "unit_price_cents": 5900,
            },
            {
                "sku": "BK-6003",
                "product_name": "Atomic Habits",
                "category": "books",
                "quantity": 1,
                "unit_price_cents": 1800,
            },
        ],
    }


@pytest.fixture
def delivered_order(client: TestClient, order_payload: dict) -> dict:
    order = client.post("/api/v1/orders", json=order_payload).json()
    for status in ["packed", "shipped", "out_for_delivery", "delivered"]:
        order = client.post(
            f"/api/v1/orders/{order['order_number']}/status", json={"status": status}
        ).json()
    return order
