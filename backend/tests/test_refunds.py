"""Refunds must happen exactly once, even with retries, races, and provider failures."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import func, select

from app.integrations.payments import PaymentGatewayError, get_payment_gateway
from app.main import app
from app.models import IdempotencyKey, Refund


class RecordingGateway:
    """Fake payment provider that counts calls and can be told to fail."""

    def __init__(self, failures: int = 0) -> None:
        self.calls = 0
        self.failures_left = failures
        self._lock = threading.Lock()

    def refund(self, *, order_number, amount_cents, currency, idempotency_key) -> str:
        with self._lock:
            self.calls += 1
            if self.failures_left:
                self.failures_left -= 1
                raise PaymentGatewayError("provider timed out")
            return f"re_test_{self.calls}"


@pytest.fixture
def gateway() -> RecordingGateway:
    fake = RecordingGateway()
    app.dependency_overrides[get_payment_gateway] = lambda: fake
    return fake


@pytest.fixture
def received_return(client, delivered_order) -> dict:
    item = delivered_order["items"][0]
    created = client.post(
        f"/api/v1/orders/{delivered_order['order_number']}/returns",
        json={
            "order_item_id": item["id"],
            "quantity": 2,
            "reason_code": "defective",
            "reason_text": "Speaker stops charging after one day of use.",
        },
    ).json()
    number = created["return_number"]
    for status in ["approved", "received"]:
        client.post(f"/api/v1/returns/{number}/status", json={"status": status})
    return created


def refund(client, return_number: str, key: str | None = None, note: str | None = None):
    headers = {"Idempotency-Key": key} if key else {}
    body = {"note": note} if note is not None else None
    return client.post(f"/api/v1/returns/{return_number}/refund", headers=headers, json=body)


def refund_count(db) -> int:
    return db.scalar(select(func.count()).select_from(Refund))


# --- happy path ---------------------------------------------------------------------------


def test_refund_pays_the_return_amount_and_closes_the_return(client, db, gateway, received_return):
    number = received_return["return_number"]
    response = refund(client, number, key=str(uuid.uuid4()))

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["amount_cents"] == 2 * 5900
    assert body["return_number"] == number
    assert body["provider_reference"] == "re_test_1"
    assert "Idempotent-Replayed" not in response.headers

    ret = client.get(f"/api/v1/returns/{number}").json()
    assert ret["status"] == "refunded"
    assert ret["resolved_at"] is not None
    assert ret["refund"]["id"] == body["id"]


def test_idempotency_key_header_is_required(client, gateway, received_return):
    response = refund(client, received_return["return_number"])
    assert response.status_code == 422
    assert gateway.calls == 0


def test_refund_requires_the_item_to_be_received(client, gateway, delivered_order):
    item = delivered_order["items"][0]
    number = client.post(
        f"/api/v1/orders/{delivered_order['order_number']}/returns",
        json={
            "order_item_id": item["id"],
            "quantity": 1,
            "reason_code": "size_fit",
            "reason_text": "Too small, would like a larger size.",
        },
    ).json()["return_number"]

    response = refund(client, number, key=str(uuid.uuid4()))
    assert response.status_code == 409
    assert gateway.calls == 0


# --- retries ------------------------------------------------------------------------------


def test_retry_with_same_key_replays_without_paying_twice(client, db, gateway, received_return):
    key = str(uuid.uuid4())
    first = refund(client, received_return["return_number"], key=key)
    second = refund(client, received_return["return_number"], key=key)

    assert first.status_code == second.status_code == 201
    assert second.json() == first.json()
    assert second.headers["Idempotent-Replayed"] == "true"
    assert gateway.calls == 1
    assert refund_count(db) == 1


def test_reusing_a_key_for_a_different_request_is_rejected(client, gateway, received_return):
    key = str(uuid.uuid4())
    refund(client, received_return["return_number"], key=key, note="first")
    response = refund(client, received_return["return_number"], key=key, note="different")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "idempotency_key_reused"


def test_a_new_key_cannot_refund_the_same_return_again(client, db, gateway, received_return):
    refund(client, received_return["return_number"], key=str(uuid.uuid4()))
    response = refund(client, received_return["return_number"], key=str(uuid.uuid4()))

    assert response.status_code == 409
    assert "already been refunded" in response.json()["error"]["message"]
    assert gateway.calls == 1
    assert refund_count(db) == 1


def test_provider_failure_is_not_cached_and_the_same_key_can_retry(
    client, db, gateway, received_return
):
    gateway.failures_left = 1
    key = str(uuid.uuid4())
    number = received_return["return_number"]

    failed = refund(client, number, key=key)
    assert failed.status_code == 502
    assert failed.json()["error"]["code"] == "payment_provider_error"
    assert refund_count(db) == 0
    assert db.get(IdempotencyKey, key) is None
    assert client.get(f"/api/v1/returns/{number}").json()["status"] == "received"

    retried = refund(client, number, key=key)
    assert retried.status_code == 201
    assert "Idempotent-Replayed" not in retried.headers
    assert refund_count(db) == 1


# --- races --------------------------------------------------------------------------------


def test_concurrent_duplicates_with_one_key_pay_once(client, db, gateway, received_return):
    """A client fires the same request 10 times at once (e.g. aggressive retries)."""
    key = str(uuid.uuid4())
    number = received_return["return_number"]

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(pool.map(lambda _: refund(client, number, key=key), range(10)))

    assert {r.status_code for r in responses} == {201}
    assert len({r.json()["id"] for r in responses}) == 1
    assert sum(r.headers.get("Idempotent-Replayed") == "true" for r in responses) == 9
    assert gateway.calls == 1
    assert refund_count(db) == 1


def test_concurrent_requests_with_different_keys_pay_once(client, db, gateway, received_return):
    """Ten operators click "Refund" at the same moment, each with their own key."""
    number = received_return["return_number"]

    with ThreadPoolExecutor(max_workers=10) as pool:
        responses = list(
            pool.map(lambda _: refund(client, number, key=str(uuid.uuid4())), range(10))
        )

    assert sorted(r.status_code for r in responses) == [201] + [409] * 9
    assert gateway.calls == 1
    assert refund_count(db) == 1
