"""The fast overview must match the slow one exactly, and caching must never serve stale
numbers after a change or break the API when Redis is down."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text, update

from app.core import cache as cache_module
from app.core.cache import Cache
from app.models import Order, OrderStatusEvent, Refund
from app.services.stats import overview, overview_live, refresh_daily_operations


def place_order(client, payload) -> str:
    return client.post("/api/v1/orders", json=payload).json()["order_number"]


def advance(client, number, *statuses):
    for status in statuses:
        client.post(f"/api/v1/orders/{number}/status", json={"status": status})


def backdate(db, number: str, days: int) -> None:
    """Move an order and its history `days` into the past."""
    shift = timedelta(days=days)
    order = db.query(Order).filter_by(order_number=number).one()
    db.execute(
        update(Order)
        .where(Order.id == order.id)
        .values(
            placed_at=Order.placed_at - shift,
            delivered_at=Order.delivered_at - shift,
            updated_at=Order.updated_at - shift,
        )
    )
    db.execute(
        update(OrderStatusEvent)
        .where(OrderStatusEvent.order_id == order.id)
        .values(created_at=OrderStatusEvent.created_at - shift)
    )
    db.execute(
        update(Refund)
        .where(Refund.order_id == order.id)
        .values(created_at=Refund.created_at - shift)
    )
    db.commit()


@pytest.fixture
def history(client, db, order_payload):
    """Orders spread over today, 3 days ago, 10 days ago and 45 days ago."""
    for days_ago, statuses in [
        (0, ["packed"]),
        (0, ["packed", "shipped", "out_for_delivery", "delivered"]),
        (3, ["packed", "shipped", "out_for_delivery", "delivered"]),
        (3, ["cancelled"]),
        (10, ["packed", "shipped", "out_for_delivery", "delivered"]),
        (45, ["packed", "shipped", "out_for_delivery", "delivered"]),
    ]:
        number = place_order(client, order_payload)
        advance(client, number, *statuses)
        if days_ago and statuses[-1] == "delivered":
            item = client.get(f"/api/v1/orders/{number}").json()["items"][0]
            ret = client.post(
                f"/api/v1/orders/{number}/returns",
                json={
                    "order_item_id": item["id"],
                    "quantity": 1,
                    "reason_code": "defective",
                    "reason_text": "Stopped working after a day.",
                },
            ).json()["return_number"]
            for status in ["approved", "received"]:
                client.post(f"/api/v1/returns/{ret}/status", json={"status": status})
            client.post(
                f"/api/v1/returns/{ret}/refund", headers={"Idempotency-Key": f"hist-{number}"}
            )
        if days_ago:
            backdate(db, number, days_ago)


def test_fast_overview_matches_live_aggregation(db, history):
    refresh_daily_operations(db, concurrently=False)
    fast, live = overview(db), overview_live(db)

    assert fast == live
    assert fast.orders_today == 2
    assert sum(d.orders for d in fast.orders_per_day) == 5  # the 45-day-old order is outside
    assert fast.delivered_last_7d == 2
    assert fast.cancelled_last_7d == 1
    assert fast.refunds_30d == 2
    assert fast.avg_delivery_hours_30d is not None


def test_today_is_live_even_before_the_view_refreshes(client, db, order_payload, history):
    refresh_daily_operations(db, concurrently=False)
    place_order(client, order_payload)  # not in the view yet
    assert overview(db).orders_today == 3
    assert overview(db) == overview_live(db)


def test_concurrent_refresh_keeps_working(db, history):
    assert refresh_daily_operations(db) is True
    count = db.scalar(text("SELECT count(*) FROM daily_operations"))
    assert count == 4  # today, 3, 10 and 45 days ago


def test_overview_is_cached_and_writes_clear_the_cache(client, order_payload):
    first = client.get("/api/v1/stats/overview")
    second = client.get("/api/v1/stats/overview")
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert second.json() == first.json()

    number = place_order(client, order_payload)
    after_write = client.get("/api/v1/stats/overview")
    assert after_write.headers["X-Cache"] == "MISS"
    assert after_write.json()["orders_today"] == first.json()["orders_today"] + 1

    advance(client, number, "packed")
    assert client.get("/api/v1/stats/overview").headers["X-Cache"] == "MISS"


def test_api_keeps_working_when_redis_is_down(client, monkeypatch):
    dead = Cache("redis://localhost:1/0")
    monkeypatch.setattr(cache_module, "get_cache", lambda: dead)
    monkeypatch.setattr("app.services.stats.get_cache", lambda: dead)
    monkeypatch.setattr("app.api.routes.health.get_cache", lambda: dead)

    response = client.get("/api/v1/stats/overview")
    assert response.status_code == 200
    assert response.headers["X-Cache"] == "MISS"
    assert not dead.available  # circuit open: later calls skip Redis entirely
    assert client.get("/api/v1/stats/overview").status_code == 200
    assert client.get("/health").json() == {
        "status": "ok",
        "database": "ok",
        "cache": "unavailable",
    }


def test_cache_stays_closed_only_for_the_cool_down(monkeypatch):
    dead = Cache("redis://localhost:1/0")
    clock = [1000.0]
    monkeypatch.setattr(cache_module.time, "monotonic", lambda: clock[0])
    assert dead.get_json("k") is None
    assert not dead.available
    clock[0] += cache_module.COOL_DOWN_SECONDS + 1
    assert dead.available


def test_utc_windows_use_the_database_clock(db):
    db_now = db.scalar(text("SELECT now()"))
    assert abs((db_now - datetime.now(UTC)).total_seconds()) < 60
