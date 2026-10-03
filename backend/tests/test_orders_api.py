from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient


def create(client: TestClient, payload: dict) -> dict:
    response = client.post("/api/v1/orders", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def advance(client: TestClient, order_number: str, status: str):
    return client.post(f"/api/v1/orders/{order_number}/status", json={"status": status})


# --- health -------------------------------------------------------------------------------


def test_health_reports_database(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}
    assert "X-Response-Time-Ms" in response.headers


# --- creating orders ----------------------------------------------------------------------


def test_create_order_computes_total_on_the_server(client, order_payload):
    order = create(client, order_payload)

    assert order["order_number"].startswith("OP-")
    assert order["status"] == "placed"
    assert order["total_cents"] == 2 * 5900 + 1800
    assert order["item_count"] == 3
    assert [line["line_total_cents"] for line in order["items"]] == [11800, 1800]
    assert order["customer"]["full_name"] == "Priya Shah"
    assert [(e["from_status"], e["to_status"]) for e in order["events"]] == [(None, "placed")]


def test_client_cannot_override_total(client, order_payload):
    order = create(client, {**order_payload, "total_cents": 1})
    assert order["total_cents"] == 13600


def test_order_numbers_are_unique_and_sequential(client, order_payload):
    numbers = [create(client, order_payload)["order_number"] for _ in range(3)]
    assert len(set(numbers)) == 3
    assert numbers == sorted(numbers)


def test_unknown_customer_returns_404(client, order_payload):
    response = client.post("/api/v1/orders", json={**order_payload, "customer_id": 999})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_invalid_payload_returns_consistent_validation_error(client, order_payload):
    response = client.post("/api/v1/orders", json={**order_payload, "items": []})
    assert response.status_code == 422
    body = response.json()["error"]
    assert body["code"] == "validation_error"
    assert body["details"][0]["loc"] == ["body", "items"]


def test_negative_quantity_is_rejected(client, order_payload):
    bad_item = {**order_payload["items"][0], "quantity": -1}
    response = client.post("/api/v1/orders", json={**order_payload, "items": [bad_item]})
    assert response.status_code == 422


# --- reading orders -----------------------------------------------------------------------


def test_get_unknown_order_returns_404(client):
    response = client.get("/api/v1/orders/OP-1")
    assert response.status_code == 404
    assert response.json() == {"error": {"code": "not_found", "message": "Order OP-1 not found"}}


def test_list_filters_paginates_and_returns_newest_first(client, order_payload):
    created = [create(client, order_payload)["order_number"] for _ in range(5)]
    advance(client, created[0], "packed")

    page = client.get("/api/v1/orders", params={"limit": 2, "offset": 0}).json()
    assert page["total"] == 5
    assert [o["order_number"] for o in page["items"]] == [created[4], created[3]]

    packed = client.get("/api/v1/orders", params={"status": "packed"}).json()
    assert packed["total"] == 1
    assert packed["items"][0]["order_number"] == created[0]

    searched = client.get("/api/v1/orders", params={"q": created[2]}).json()
    assert [o["order_number"] for o in searched["items"]] == [created[2]]


def test_list_rejects_unknown_status(client):
    assert client.get("/api/v1/orders", params={"status": "lost"}).status_code == 422


# --- lifecycle ----------------------------------------------------------------------------


def test_full_lifecycle_records_history_and_delivery_time(client, order_payload):
    number = create(client, order_payload)["order_number"]

    for status in ["packed", "shipped", "out_for_delivery", "delivered"]:
        response = advance(client, number, status)
        assert response.status_code == 200, response.text

    order = response.json()
    assert order["status"] == "delivered"
    assert order["delivered_at"] is not None
    assert [e["to_status"] for e in order["events"]] == [
        "placed",
        "packed",
        "shipped",
        "out_for_delivery",
        "delivered",
    ]


def test_skipping_a_step_returns_409(client, order_payload):
    number = create(client, order_payload)["order_number"]

    response = advance(client, number, "delivered")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"
    assert client.get(f"/api/v1/orders/{number}").json()["status"] == "placed"


def test_cancelled_orders_cannot_move(client, order_payload):
    number = create(client, order_payload)["order_number"]
    assert advance(client, number, "cancelled").status_code == 200
    assert advance(client, number, "packed").status_code == 409


def test_shipped_orders_cannot_be_cancelled(client, order_payload):
    number = create(client, order_payload)["order_number"]
    advance(client, number, "packed")
    advance(client, number, "shipped")
    assert advance(client, number, "cancelled").status_code == 409


def test_concurrent_updates_apply_exactly_once(client, order_payload):
    """Ten operators click "pack" at the same time: exactly one wins, the rest get 409."""
    number = create(client, order_payload)["order_number"]

    with ThreadPoolExecutor(max_workers=10) as pool:
        codes = list(pool.map(lambda _: advance(client, number, "packed").status_code, range(10)))

    assert sorted(codes) == [200] + [409] * 9
    events = client.get(f"/api/v1/orders/{number}").json()["events"]
    assert [e["to_status"] for e in events] == ["placed", "packed"]


# --- customers ----------------------------------------------------------------------------


def test_customer_search_and_lookup(client, customer):
    found = client.get("/api/v1/customers", params={"q": "priya"}).json()
    assert [c["id"] for c in found] == [customer.id]
    assert client.get(f"/api/v1/customers/{customer.id}").json()["tier"] == "plus"
    assert client.get("/api/v1/customers/999").status_code == 404
