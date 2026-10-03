from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import update

from app.domain.returns import ReturnReason, ReturnStatus, Team, can_transition_return
from app.models import Order


def request_return(client, order: dict, *, item_index: int = 0, quantity: int = 1, **overrides):
    payload = {
        "order_item_id": order["items"][item_index]["id"],
        "quantity": quantity,
        "reason_code": "damaged",
        "reason_text": "The box arrived crushed and the speaker grille is dented.",
        **overrides,
    }
    return client.post(f"/api/v1/orders/{order['order_number']}/returns", json=payload)


def set_return_status(client, return_number: str, status: str):
    return client.post(f"/api/v1/returns/{return_number}/status", json={"status": status})


# --- requesting a return ------------------------------------------------------------------


def test_request_return_for_delivered_order(client, delivered_order):
    response = request_return(client, delivered_order, quantity=2)
    assert response.status_code == 201, response.text

    body = response.json()
    assert body["return_number"].startswith("RT-")
    assert body["order_number"] == delivered_order["order_number"]
    assert body["status"] == "requested"
    assert body["assigned_team"] == "logistics"
    assert body["refund_amount_cents"] == 2 * 5900
    assert body["refund"] is None


def test_cannot_return_an_undelivered_order(client, order_payload):
    order = client.post("/api/v1/orders", json=order_payload).json()
    response = request_return(client, order)
    assert response.status_code == 409
    assert "delivered" in response.json()["error"]["message"]


def test_cannot_return_after_the_window_closes(client, db, delivered_order):
    db.execute(
        update(Order)
        .where(Order.order_number == delivered_order["order_number"])
        .values(delivered_at=datetime.now(UTC) - timedelta(days=31))
    )
    db.commit()
    response = request_return(client, delivered_order)
    assert response.status_code == 409
    assert "window" in response.json()["error"]["message"]


def test_cannot_return_more_units_than_were_bought(client, delivered_order):
    assert request_return(client, delivered_order, quantity=1).status_code == 201
    assert request_return(client, delivered_order, quantity=1).status_code == 201
    response = request_return(client, delivered_order, quantity=1)
    assert response.status_code == 409
    assert "Only 0 unit(s)" in response.json()["error"]["message"]


def test_rejected_returns_free_up_quantity(client, delivered_order):
    first = request_return(client, delivered_order, quantity=2).json()
    set_return_status(client, first["return_number"], "rejected")
    assert request_return(client, delivered_order, quantity=2).status_code == 201


def test_item_must_belong_to_the_order(client, delivered_order):
    response = request_return(client, delivered_order, order_item_id=999_999)
    assert response.status_code == 404


def test_reason_text_is_required(client, delivered_order):
    assert request_return(client, delivered_order, reason_text="bad").status_code == 422


@pytest.mark.parametrize(
    ("reason", "team"),
    [
        ("damaged", "logistics"),
        ("late_delivery", "logistics"),
        ("defective", "quality"),
        ("not_as_described", "quality"),
        ("wrong_item", "fulfillment"),
        ("missing_parts", "fulfillment"),
        ("size_fit", "customer_care"),
        ("changed_mind", "customer_care"),
    ],
)
def test_baseline_routing_by_reason(client, delivered_order, reason, team):
    body = request_return(client, delivered_order, reason_code=reason).json()
    assert body["assigned_team"] == team


def test_every_reason_routes_to_a_team():
    from app.domain.returns import REASON_TO_TEAM

    assert set(REASON_TO_TEAM) == set(ReturnReason)
    assert set(REASON_TO_TEAM.values()) == set(Team)


# --- lifecycle ----------------------------------------------------------------------------


def test_return_lifecycle_rules():
    assert can_transition_return(ReturnStatus.REQUESTED, ReturnStatus.APPROVED)
    assert can_transition_return(ReturnStatus.APPROVED, ReturnStatus.RECEIVED)
    assert not can_transition_return(ReturnStatus.REQUESTED, ReturnStatus.RECEIVED)
    assert not can_transition_return(ReturnStatus.REJECTED, ReturnStatus.APPROVED)


def test_approve_then_receive(client, delivered_order):
    number = request_return(client, delivered_order).json()["return_number"]
    assert set_return_status(client, number, "approved").status_code == 200
    body = set_return_status(client, number, "received").json()
    assert body["status"] == "received"


def test_cannot_skip_approval(client, delivered_order):
    number = request_return(client, delivered_order).json()["return_number"]
    assert set_return_status(client, number, "received").status_code == 409


def test_refunded_cannot_be_set_manually(client, delivered_order):
    number = request_return(client, delivered_order).json()["return_number"]
    assert set_return_status(client, number, "refunded").status_code == 422


def test_rejection_records_note_and_resolution_time(client, delivered_order):
    number = request_return(client, delivered_order).json()["return_number"]
    body = client.post(
        f"/api/v1/returns/{number}/status",
        json={"status": "rejected", "note": "Photos show the item was used."},
    ).json()
    assert body["status"] == "rejected"
    assert body["decision_note"] == "Photos show the item was used."
    assert body["resolved_at"] is not None


# --- listing ------------------------------------------------------------------------------


def test_list_returns_with_filters(client, delivered_order):
    first = request_return(client, delivered_order).json()
    request_return(client, delivered_order, item_index=1, reason_code="changed_mind")
    set_return_status(client, first["return_number"], "approved")

    everything = client.get("/api/v1/returns").json()
    assert everything["total"] == 2

    approved = client.get("/api/v1/returns", params={"status": "approved"}).json()
    assert [r["return_number"] for r in approved["items"]] == [first["return_number"]]

    by_reason = client.get("/api/v1/returns", params={"reason": "changed_mind"}).json()
    assert by_reason["total"] == 1

    by_order = client.get(
        "/api/v1/returns", params={"order_number": delivered_order["order_number"]}
    ).json()
    assert by_order["total"] == 2

    assert client.get("/api/v1/returns/RT-1").status_code == 404
