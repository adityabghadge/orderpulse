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
from sqlalchemy import insert, select, text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.domain.order_status import OrderStatus
from app.domain.returns import REASON_TO_TEAM, RETURN_WINDOW_DAYS, ReturnStatus
from app.models import Customer, Order, OrderItem, OrderStatusEvent, Refund, Return
from app.return_reasons import sample_return_reason

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
BATCH_SIZE = 2000


def _reset(db: Session) -> None:
    db.execute(
        text(
            "TRUNCATE idempotency_keys, refunds, returns, order_status_events, order_items, "
            "orders, customers RESTART IDENTITY CASCADE"
        )
    )
    db.execute(text("ALTER SEQUENCE order_number_seq RESTART WITH 100000"))
    db.execute(text("ALTER SEQUENCE return_number_seq RESTART WITH 500000"))


def _make_customers(fake: Faker, rng: random.Random, count: int) -> list[dict]:
    customers = []
    for i in range(count):
        first, last = fake.first_name(), fake.last_name()
        customers.append(
            {
                "full_name": f"{first} {last}",
                # The index guarantees uniqueness even when Faker repeats a name.
                "email": f"{first}.{last}.{i}@example.com".lower(),
                "city": rng.choice(CITIES),
                "tier": "plus" if rng.random() < 0.18 else "standard",
            }
        )
    return customers


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


def _chunks(rows: list[dict], size: int):
    for start in range(0, len(rows), size):
        yield rows[start : start + size]


def seed(customer_count: int, order_count: int, random_seed: int = 42) -> None:
    rng = random.Random(random_seed)
    fake = Faker("en_US")
    Faker.seed(random_seed)
    now = datetime.now(UTC)
    started = time.perf_counter()

    with SessionLocal() as db:
        _reset(db)

        customer_rows = _make_customers(fake, rng, customer_count)
        customer_ids = list(
            db.scalars(
                insert(Customer).returning(Customer.id, sort_by_parameter_order=True),
                customer_rows,
            )
        )
        customer_city = {
            cid: row["city"] for cid, row in zip(customer_ids, customer_rows, strict=True)
        }
        # A minority of customers place most orders, as in real stores.
        weights = [rng.paretovariate(1.5) for _ in customer_ids]

        order_rows, order_items, order_events = [], [], []
        for _ in range(order_count):
            customer_id = rng.choices(customer_ids, weights=weights)[0]
            placed_at = now - timedelta(days=rng.betavariate(1.2, 2.5) * 120)
            lines = rng.sample(CATALOG, k=rng.choices([1, 2, 3, 4], weights=[55, 28, 12, 5])[0])
            items = [
                {
                    "sku": sku,
                    "product_name": name,
                    "category": category,
                    "quantity": rng.choices([1, 2, 3], weights=[80, 15, 5])[0],
                    # Small price variation simulates discounts and promotions.
                    "unit_price_cents": int(round(price * rng.uniform(0.85, 1.0), 2) * 100),
                }
                for sku, name, category, price in lines
            ]
            history = _lifecycle(rng, placed_at, now)
            final_status, last_change = history[-1][1], history[-1][2]

            order_rows.append(
                {
                    "customer_id": customer_id,
                    "status": final_status.value,
                    "total_cents": sum(i["quantity"] * i["unit_price_cents"] for i in items),
                    "payment_method": rng.choices(["card", "wallet", "cod"], [70, 20, 10])[0],
                    "shipping_city": (
                        customer_city[customer_id] if rng.random() < 0.9 else rng.choice(CITIES)
                    ),
                    "placed_at": placed_at,
                    "delivered_at": last_change if final_status is OrderStatus.DELIVERED else None,
                    "created_at": placed_at,
                    "updated_at": last_change,
                }
            )
            order_items.append(items)
            order_events.append(history)

        for batch_start, batch in enumerate(_chunks(order_rows, BATCH_SIZE)):
            order_ids = list(
                db.scalars(insert(Order).returning(Order.id, sort_by_parameter_order=True), batch)
            )
            offset = batch_start * BATCH_SIZE
            item_rows, event_rows = [], []
            for idx, order_id in enumerate(order_ids):
                item_rows += [{**item, "order_id": order_id} for item in order_items[offset + idx]]
                event_rows += [
                    {
                        "order_id": order_id,
                        "from_status": from_s.value if from_s else None,
                        "to_status": to_s.value,
                        "actor": "checkout" if from_s is None else "fulfillment-bot",
                        "note": None,
                        "created_at": at,
                    }
                    for from_s, to_s, at in order_events[offset + idx]
                ]
            db.execute(insert(OrderItem), item_rows)
            db.execute(insert(OrderStatusEvent), event_rows)

        return_count = _seed_returns(db, rng, now)
        db.commit()

    elapsed = time.perf_counter() - started
    print(
        f"Seeded {customer_count:,} customers, {order_count:,} orders "
        f"and {return_count:,} returns in {elapsed:.1f}s"
    )


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


def _seed_returns(db: Session, rng: random.Random, now: datetime) -> int:
    delivered_items = db.execute(
        select(
            OrderItem.id,
            OrderItem.order_id,
            OrderItem.quantity,
            OrderItem.unit_price_cents,
            OrderItem.product_name,
            OrderItem.category,
            Order.delivered_at,
            Order.currency,
        )
        .join(Order, Order.id == OrderItem.order_id)
        .where(Order.status == OrderStatus.DELIVERED.value)
        .order_by(OrderItem.order_id, OrderItem.id)
    ).all()

    items_by_order: dict[int, list] = {}
    for row in delivered_items:
        items_by_order.setdefault(row.order_id, []).append(row)

    return_rows, outcomes = [], []
    for order_id, items in items_by_order.items():
        if rng.random() >= RETURN_RATE:
            continue
        item = rng.choice(items)
        requested_at = item.delivered_at + timedelta(
            days=rng.uniform(0.2, RETURN_WINDOW_DAYS * 0.6)
        )
        if requested_at > now:
            continue
        true_cause, picked, reason_text = sample_return_reason(
            rng, item.product_name, item.category
        )
        status = _return_status(rng, (now - requested_at).total_seconds() / 86400)
        quantity = rng.randint(1, item.quantity)
        resolved_at = None
        if status in (ReturnStatus.REJECTED, ReturnStatus.REFUNDED):
            resolved_at = min(now, requested_at + timedelta(days=rng.uniform(1, 9)))
        return_rows.append(
            {
                "order_id": order_id,
                "order_item_id": item.id,
                "quantity": quantity,
                "reason_code": picked.value,
                "reason_text": reason_text,
                "status": status.value,
                # Historical returns carry the team that actually resolved them
                # (after human triage), not the team the dropdown pointed to.
                "assigned_team": REASON_TO_TEAM[true_cause].value,
                "refund_amount_cents": item.unit_price_cents * quantity,
                "requested_at": requested_at,
                "resolved_at": resolved_at,
                "created_at": requested_at,
                "updated_at": resolved_at or requested_at,
            }
        )
        outcomes.append((status, item.currency, resolved_at))

    if not return_rows:
        return 0
    return_ids = list(
        db.scalars(insert(Return).returning(Return.id, sort_by_parameter_order=True), return_rows)
    )
    refund_rows = [
        {
            "return_id": return_id,
            "order_id": row["order_id"],
            "amount_cents": row["refund_amount_cents"],
            "currency": currency,
            "status": "succeeded",
            "provider_reference": f"re_{uuid.UUID(int=rng.getrandbits(128)).hex[:20]}",
            "idempotency_key": str(uuid.UUID(int=rng.getrandbits(128))),
            "created_at": resolved_at,
        }
        for return_id, row, (status, currency, resolved_at) in zip(
            return_ids, return_rows, outcomes, strict=True
        )
        if status is ReturnStatus.REFUNDED
    ]
    if refund_rows:
        db.execute(insert(Refund), refund_rows)
    return len(return_rows)


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
