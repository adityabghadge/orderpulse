def test_overview_on_empty_database(client):
    body = client.get("/api/v1/stats/overview").json()

    assert [s["status"] for s in body["pipeline"]] == [
        "placed",
        "packed",
        "shipped",
        "out_for_delivery",
    ]
    assert all(s["count"] == 0 for s in body["pipeline"])
    assert body["open_returns"] == 0
    assert body["avg_delivery_hours_30d"] is None
    assert len(body["orders_per_day"]) == 30
    assert {t["team"] for t in body["open_returns_by_team"]} == {
        "logistics",
        "quality",
        "fulfillment",
        "customer_care",
    }


def test_overview_counts_orders_returns_and_refunds(client, order_payload, delivered_order):
    shipped = client.post("/api/v1/orders", json=order_payload).json()["order_number"]
    for status in ["packed", "shipped"]:
        client.post(f"/api/v1/orders/{shipped}/status", json={"status": status})

    item = delivered_order["items"][0]
    created = client.post(
        f"/api/v1/orders/{delivered_order['order_number']}/returns",
        json={
            "order_item_id": item["id"],
            "quantity": 1,
            "reason_code": "wrong_item",
            "reason_text": "Received a different product than ordered.",
        },
    ).json()

    body = client.get("/api/v1/stats/overview").json()
    pipeline = {s["status"]: s["count"] for s in body["pipeline"]}

    assert pipeline["shipped"] == 1
    assert body["delivered_last_7d"] == 1
    assert body["orders_today"] == 2
    assert body["revenue_today_cents"] == 2 * 13600
    assert body["orders_per_day"][-1]["orders"] == 2
    assert body["open_returns"] == 1
    assert body["returns_by_status"]["requested"] == 1
    teams = {t["team"]: t["open_returns"] for t in body["open_returns_by_team"]}
    assert teams["fulfillment"] == 1
    assert body["avg_delivery_hours_30d"] is not None

    number = created["return_number"]
    for status in ["approved", "received"]:
        client.post(f"/api/v1/returns/{number}/status", json={"status": status})
    client.post(f"/api/v1/returns/{number}/refund", headers={"Idempotency-Key": "stats-test-1"})

    after = client.get("/api/v1/stats/overview").json()
    assert after["refunds_30d"] == 1
    assert after["refunded_30d_cents"] == 5900
    assert after["open_returns"] == 0


def test_returns_can_be_listed_oldest_first(client, delivered_order):
    numbers = []
    for item in delivered_order["items"]:
        numbers.append(
            client.post(
                f"/api/v1/orders/{delivered_order['order_number']}/returns",
                json={
                    "order_item_id": item["id"],
                    "quantity": 1,
                    "reason_code": "changed_mind",
                    "reason_text": "No longer need this item.",
                },
            ).json()["return_number"]
        )
    oldest = client.get("/api/v1/returns", params={"sort": "oldest"}).json()["items"]
    assert [r["return_number"] for r in oldest] == numbers
