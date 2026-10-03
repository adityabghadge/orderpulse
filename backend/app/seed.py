"""Generate realistic demo data: customers, orders, status histories, returns and refunds.

Usage:
    python -m app.seed                      # 500 customers, 5,000 orders
    python -m app.seed --orders 50000       # larger dataset for performance work

Every order walks through the real lifecycle with realistic delays between steps, so recent
orders are still in progress and older ones are delivered (or occasionally cancelled).
The random generator is seeded, so the same command always produces the same data.
"""

import argparse
import random
import time
import uuid
from datetime import UTC, datetime, timedelta

from faker import Faker
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.domain.order_status import OrderStatus
from app.domain.returns import REASON_TO_TEAM, RETURN_WINDOW_DAYS, ReturnStatus, route_by_reason
from app.return_reasons import sample_return_reason
from app.services.stats import invalidate_overview, refresh_daily_operations

# (sku, name, category, typical price in dollars)
CATALOG: list[tuple[str, str, str, float]] = [
    ("EL-1001", "Wireless Noise-Cancelling Headphones", "electronics", 189.00),
    ("EL-1002", "Bluetooth Speaker", "electronics", 59.00),
    ("EL-1003", "USB-C Fast Charger 65W", "electronics", 39.00),
    ("EL-1004", "Smartwatch Series 5", "electronics", 249.00),
    ("EL-1005", '27" 4K Monitor', "electronics", 329.00),
    ("EL-1006", "Mechanical Keyboard", "electronics", 99.00),
    ("EL-1007", "Wireless Mouse", "electronics", 29.00),
    ("EL-1008", "Tablet 11-inch", "electronics", 449.00),
    ("AP-2001", "Men's Running Jacket", "apparel", 79.00),
    ("AP-2002", "Women's Denim Jeans", "apparel", 59.00),
    ("AP-2003", "Cotton Crew T-Shirt (3-pack)", "apparel", 25.00),
    ("AP-2004", "Wool Blend Sweater", "apparel", 69.00),
    ("AP-2005", "Leather Sneakers", "apparel", 110.00),
    ("AP-2006", "Rain Boots", "apparel", 49.00),
    ("HM-3001", "Stainless Steel Cookware Set", "home", 159.00),
    ("HM-3002", "Memory Foam Pillow", "home", 45.00),
    ("HM-3003", "Robot Vacuum", "home", 279.00),
    ("HM-3004", "Ceramic Dinnerware Set", "home", 89.00),
    ("HM-3005", "LED Desk Lamp", "home", 35.00),
    ("HM-3006", "Air Purifier", "home", 149.00),
    ("BT-4001", "Vitamin C Serum", "beauty", 28.00),
    ("BT-4002", "Hair Dryer Pro", "beauty", 89.00),
    ("BT-4003", "Electric Toothbrush", "beauty", 69.00),
    ("BT-4004", "Fragrance Gift Set", "beauty", 75.00),
    ("SP-5001", "Yoga Mat", "sports", 32.00),
    ("SP-5002", "Adjustable Dumbbells", "sports", 199.00),
    ("SP-5003", "Insulated Water Bottle", "sports", 24.00),
    ("SP-5004", "Trail Running Shoes", "sports", 129.00),
    ("SP-5005", "Camping Tent (2-person)", "sports", 139.00),
    ("BK-6001", "Designing Data-Intensive Applications", "books", 42.00),
    ("BK-6002", "The Pragmatic Programmer", "books", 38.00),
    ("BK-6003", "Atomic Habits", "books", 18.00),
    ("BK-6004", "Children's Picture Book Set", "books", 29.00),
]

CITIES = [
    "New York", "Jersey City", "Chicago", "Austin", "Seattle", "San Francisco", "Boston",
    "Denver", "Atlanta", "Miami", "Los Angeles", "Phoenix", "Dallas", "Minneapolis",
    "Portland", "Philadelphia", "San Diego", "Nashville", "Charlotte", "Columbus",
]  # fmt: skip

# How long each lifecycle step typically takes, in hours (min, max).
STEP_DURATIONS: dict[OrderStatus, tuple[float, float]] = {
    OrderStatus.PACKED: (2, 20),
    OrderStatus.SHIPPED: (6, 30),
    OrderStatus.OUT_FOR_DELIVERY: (24, 72),
    OrderStatus.DELIVERED: (3, 12),
}
HAPPY_PATH = [OrderStatus.PACKED, OrderStatus.SHIPPED, OrderStatus.OUT_FOR_DELIVERY]
CANCEL_RATE = 0.04
RETURN_RATE = 0.15
REJECT_RATE = 0.08


def _reset(db: Session) -> None:
    db.execute(
        text(
            "TRUNCATE idempotency_keys, refunds, returns, order_status_events, order_items, "
            "orders, customers RESTART IDENTITY CASCADE"
        )
    )
    db.execute(text("ALTER SEQUENCE order_number_seq RESTART WITH 100000"))
    db.execute(text("ALTER SEQUENCE return_number_seq RESTART WITH 500000"))


def _copy(db: Session, table: str, columns: list[str], rows: list[tuple]) -> None:
    """Bulk-load rows with PostgreSQL COPY: one streamed command instead of one INSERT per row."""
    cursor = db.connection().connection.driver_connection.cursor()
    with cursor.copy(f"COPY {table} ({', '.join(columns)}) FROM STDIN") as copy:
        for row in rows:
            copy.write_row(row)


def _sync_id_sequences(db: Session, tables: list[str]) -> None:
    """IDs were assigned here, so move each table's ID counter past the highest one used."""
    for table in tables:
        db.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 0) + 1, false)"
            )
        )


def _lifecycle(
    rng: random.Random, placed_at: datetime, now: datetime
) -> list[tuple[OrderStatus | None, OrderStatus, datetime]]:
    """Return the (from, to, at) transitions this order has gone through by `now`."""
    events: list[tuple[OrderStatus | None, OrderStatus, datetime]] = [
        (None, OrderStatus.PLACED, placed_at)
    ]
    current, at = OrderStatus.PLACED, placed_at
    cancel_at_step = rng.choice([0, 1]) if rng.random() < CANCEL_RATE else None

    for step, target in enumerate([*HAPPY_PATH, OrderStatus.DELIVERED]):
        if cancel_at_step == step:
            cancel_time = at + timedelta(hours=rng.uniform(0.5, 12))
            if cancel_time <= now:
                events.append((current, OrderStatus.CANCELLED, cancel_time))
            return events
        at = at + timedelta(hours=rng.uniform(*STEP_DURATIONS[target]))
        if at > now:
            break
        events.append((current, target, at))
        current = target
    return events


def _return_status(rng: random.Random, age_days: float) -> ReturnStatus:
    """Where a return would be in its lifecycle, given how long ago it was requested."""
    if age_days < 1:
        return ReturnStatus.REQUESTED
    if rng.random() < REJECT_RATE:
        return ReturnStatus.REJECTED
    if age_days < 3:
        return ReturnStatus.APPROVED
    if age_days < 7:
        return ReturnStatus.RECEIVED
    return ReturnStatus.REFUNDED


def seed(customer_count: int, order_count: int, random_seed: int = 42) -> dict[str, int]:
    rng = random.Random(random_seed)
    fake = Faker("en_US")
    Faker.seed(random_seed)
    now = datetime.now(UTC)
    started = time.perf_counter()

    customers, orders, items, events, returns, refunds = [], [], [], [], [], []
    customer_city: dict[int, str] = {}
    for customer_id in range(1, customer_count + 1):
        first, last = fake.first_name(), fake.last_name()
        city = rng.choice(CITIES)
        customer_city[customer_id] = city
        customers.append(
            (
                customer_id,
                f"{first} {last}",
                f"{first}.{last}.{customer_id}@example.com".lower(),
                city,
                "plus" if rng.random() < 0.18 else "standard",
                now,
                now,
            )
        )

    customer_ids = list(customer_city)
    # A minority of customers place most orders, as in real stores.
    weights = [rng.lognormvariate(0, 0.8) for _ in customer_ids]
    order_customers = rng.choices(customer_ids, weights=weights, k=order_count)

    item_id = event_id = return_id = 0
    for order_id, customer_id in enumerate(order_customers, start=1):
        placed_at = now - timedelta(days=rng.betavariate(1.2, 2.5) * 120)
        lines = rng.sample(CATALOG, k=rng.choices([1, 2, 3, 4], weights=[55, 28, 12, 5])[0])
        order_items = []
        for sku, name, category, price in lines:
            item_id += 1
            quantity = rng.choices([1, 2, 3], weights=[80, 15, 5])[0]
            # Small price variation simulates discounts and promotions.
            unit_price = int(round(price * rng.uniform(0.85, 1.0), 2) * 100)
            order_items.append((item_id, order_id, sku, name, category, quantity, unit_price))
        items.extend(order_items)

        history = _lifecycle(rng, placed_at, now)
        final_status, last_change = history[-1][1], history[-1][2]
        delivered_at = last_change if final_status is OrderStatus.DELIVERED else None
        for from_status, to_status, at in history:
            event_id += 1
            events.append(
                (
                    event_id,
                    order_id,
                    from_status.value if from_status else None,
                    to_status.value,
                    None,
                    "checkout" if from_status is None else "fulfillment-bot",
                    at,
                )
            )

        orders.append(
            (
                order_id,
                customer_id,
                final_status.value,
                sum(i[5] * i[6] for i in order_items),
                "USD",
                rng.choices(["card", "wallet", "cod"], [70, 20, 10])[0],
                customer_city[customer_id] if rng.random() < 0.9 else rng.choice(CITIES),
                placed_at,
                delivered_at,
                placed_at,
                last_change,
            )
        )

        if delivered_at is None or rng.random() >= RETURN_RATE:
            continue
        requested_at = delivered_at + timedelta(days=rng.uniform(0.2, RETURN_WINDOW_DAYS * 0.6))
        if requested_at > now:
            continue
        product_name, category, item_quantity, unit_price, line_id = _pick_item(rng, order_items)
        true_cause, picked, reason_text = sample_return_reason(rng, product_name, category)
        status = _return_status(rng, (now - requested_at).total_seconds() / 86400)
        quantity = rng.randint(1, item_quantity)
        resolved_at = None
        if status in (ReturnStatus.REJECTED, ReturnStatus.REFUNDED):
            resolved_at = min(now, requested_at + timedelta(days=rng.uniform(1, 9)))
        return_id += 1
        returns.append(
            (
                return_id,
                order_id,
                line_id,
                quantity,
                picked.value,
                reason_text,
                status.value,
                # Open returns are routed by the dropdown, exactly like the live API.
                # Closed returns carry the team that actually resolved them after human
                # triage: the labels a routing model learns from.
                REASON_TO_TEAM[true_cause].value if resolved_at else route_by_reason(picked).value,
                None,
                requested_at,
                resolved_at,
                unit_price * quantity,
                requested_at,
                resolved_at or requested_at,
            )
        )
        if status is ReturnStatus.REFUNDED:
            refunds.append(
                (
                    return_id,
                    order_id,
                    unit_price * quantity,
                    "USD",
                    "succeeded",
                    f"re_{uuid.UUID(int=rng.getrandbits(128)).hex[:20]}",
                    str(uuid.UUID(int=rng.getrandbits(128))),
                    resolved_at,
                )
            )

    with SessionLocal() as db:
        _reset(db)
        _copy(
            db,
            "customers",
            ["id", "full_name", "email", "city", "tier", "created_at", "updated_at"],
            customers,
        )
        _copy(
            db,
            "orders",
            [
                "id", "customer_id", "status", "total_cents", "currency", "payment_method",
                "shipping_city", "placed_at", "delivered_at", "created_at", "updated_at",
            ],
            orders,
        )  # fmt: skip
        _copy(
            db,
            "order_items",
            ["id", "order_id", "sku", "product_name", "category", "quantity", "unit_price_cents"],
            items,
        )
        _copy(
            db,
            "order_status_events",
            ["id", "order_id", "from_status", "to_status", "note", "actor", "created_at"],
            events,
        )
        _copy(
            db,
            "returns",
            [
                "id", "order_id", "order_item_id", "quantity", "reason_code", "reason_text",
                "status", "assigned_team", "decision_note", "requested_at", "resolved_at",
                "refund_amount_cents", "created_at", "updated_at",
            ],
            returns,
        )  # fmt: skip
        _copy(
            db,
            "refunds",
            [
                "return_id", "order_id", "amount_cents", "currency", "status",
                "provider_reference", "idempotency_key", "created_at",
            ],
            refunds,
        )  # fmt: skip
        _sync_id_sequences(
            db, ["customers", "orders", "order_items", "order_status_events", "returns"]
        )
        db.commit()
        db.execute(text("ANALYZE"))  # refresh the query planner's statistics after a bulk load
        refresh_daily_operations(db, concurrently=False)
    invalidate_overview()

    elapsed = time.perf_counter() - started
    print(
        f"Seeded {customer_count:,} customers, {order_count:,} orders "
        f"and {len(returns):,} returns in {elapsed:.1f}s"
    )
    return {"customers": customer_count, "orders": order_count, "returns": len(returns)}


def _pick_item(rng: random.Random, order_items: list[tuple]) -> tuple:
    """Pick the line item being returned: (product, category, quantity, price, item id)."""
    item_id, _, _, name, category, quantity, unit_price = rng.choice(order_items)
    return name, category, quantity, unit_price, item_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Load demo data into the OrderPulse database.")
    parser.add_argument("--customers", type=int, default=500)
    parser.add_argument("--orders", type=int, default=5000)
    parser.add_argument("--seed", type=int, default=42, help="Random seed for repeatable data")
    args = parser.parse_args()

    if get_settings().environment == "production":
        raise SystemExit("Refusing to seed: this wipes all data and is for local use only.")
    seed(args.customers, args.orders, args.seed)


if __name__ == "__main__":
    main()
