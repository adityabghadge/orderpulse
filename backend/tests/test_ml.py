import random

import pytest

from app.core.config import get_settings
from app.ml import registry
from app.ml.priority import PriorityInput, PriorityModel, auc, precision_at_k, train_priority
from app.ml.routing import ReturnRouter, train_router
from app.ml.text import Vocabulary, tokenize

# A tiny, clearly separable training set: text decides the team, the dropdown is often wrong.
PHRASES = {
    "logistics": ["box arrived crushed", "package soaked and torn", "courier dropped it"],
    "quality": ["stopped working after a day", "won't turn on", "battery drains fast"],
    "fulfillment": ["wrong item in the box", "missing the charger", "received someone else's"],
    "customer_care": ["changed my mind", "too small need bigger size", "ordered by mistake"],
}
REASONS = ["damaged", "defective", "wrong_item", "size_fit", "changed_mind", "not_as_described"]


def synthetic_routing_data(n: int, seed: int = 1):
    rng = random.Random(seed)
    texts, reasons, teams = [], [], []
    for _ in range(n):
        team = rng.choice(list(PHRASES))
        texts.append(f"Hello, {rng.choice(PHRASES[team])}. Please help.")
        reasons.append(rng.choice(REASONS))  # deliberately uninformative dropdown
        teams.append(team)
    return texts, reasons, teams


def synthetic_priority_data(n: int, seed: int = 2):
    rng = random.Random(seed)
    rows, labels = [], []
    for _ in range(n):
        amount = rng.randint(1_000, 50_000)
        upset = rng.random() < 0.3
        text = "Very disappointed, want my money back." if upset else "Please process this."
        rows.append(
            PriorityInput(
                refund_amount_cents=amount,
                order_total_cents=amount + 2_000,
                plus_member=rng.random() < 0.2,
                customer_other_returns=rng.randint(0, 3),
                days_since_delivery=rng.uniform(0, 20),
                reason_code=rng.choice(REASONS),
                reason_text=text,
            )
        )
        labels.append(rng.random() < (0.6 if upset and amount > 20_000 else 0.05))
    return rows, labels


@pytest.fixture
def trained_models(tmp_path, monkeypatch):
    """Train small models into a temp folder and make the API use them."""
    texts, reasons, teams = synthetic_routing_data(600)
    train_router(texts, reasons, teams, epochs=15).save(tmp_path / registry.ROUTER_FILE)
    rows, labels = synthetic_priority_data(1500)
    train_priority(rows, labels).save(tmp_path / registry.PRIORITY_FILE)

    monkeypatch.setattr(get_settings(), "model_dir", tmp_path)
    registry.reload_models()
    yield tmp_path
    monkeypatch.undo()
    registry.reload_models()


# --- text ---------------------------------------------------------------------------------


def test_tokenize_adds_word_pairs():
    assert tokenize("Box arrived CRUSHED!") == [
        "box",
        "arrived",
        "crushed",
        "box_arrived",
        "arrived_crushed",
    ]


def test_vocabulary_drops_rare_tokens_and_maps_unknowns_to_zero():
    vocab = Vocabulary.build(["broken box", "broken box", "typo"], min_count=2)
    assert "typo" not in vocab.tokens
    assert vocab.encode("never seen") == [0, 0, 0]
    assert vocab.encode("") == [0]


# --- routing model ------------------------------------------------------------------------


def test_router_learns_from_text_not_dropdown():
    texts, reasons, teams = synthetic_routing_data(600)
    router = train_router(texts, reasons, teams, epochs=15)
    test_texts, test_reasons, test_teams = synthetic_routing_data(200, seed=99)
    predictions = router.predict_many(test_texts, test_reasons)
    accuracy = sum(p.team == t for p, t in zip(predictions, test_teams, strict=True)) / 200
    assert accuracy > 0.95
    assert all(0 < p.confidence <= 1 for p in predictions)


def test_router_survives_save_and_load(tmp_path):
    texts, reasons, teams = synthetic_routing_data(300)
    router = train_router(texts, reasons, teams, epochs=5)
    router.save(tmp_path / "router.pt")
    loaded = ReturnRouter.load(tmp_path / "router.pt")
    assert loaded.predict_many(texts[:20], reasons[:20]) == router.predict_many(
        texts[:20], reasons[:20]
    )


# --- priority model -----------------------------------------------------------------------


def test_metrics():
    assert precision_at_k([0.9, 0.8, 0.1, 0.7], [True, False, False, True], k=2) == 0.5
    assert auc([0.9, 0.8, 0.2, 0.1], [True, True, False, False]) == 1.0
    assert auc([0.1, 0.2, 0.8, 0.9], [True, True, False, False]) == 0.0
    assert auc([0.5, 0.5], [True, False]) == 0.5  # ties count as half


def test_priority_model_ranks_risky_returns_first(tmp_path):
    rows, labels = synthetic_priority_data(1500)
    model = train_priority(rows, labels)
    test_rows, test_labels = synthetic_priority_data(600, seed=3)
    scores = model.predict_many(test_rows)
    assert auc(scores, test_labels) > 0.8
    assert precision_at_k(scores, test_labels, 20) > sum(test_labels) / len(test_labels)

    model.save(tmp_path / "priority.json")
    assert PriorityModel.load(tmp_path / "priority.json").predict_many(test_rows[:5]) == scores[:5]


# --- in the API ---------------------------------------------------------------------------


def create_return(client, order, text: str, reason: str) -> dict:
    response = client.post(
        f"/api/v1/orders/{order['order_number']}/returns",
        json={
            "order_item_id": order["items"][0]["id"],
            "quantity": 1,
            "reason_code": reason,
            "reason_text": text,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_without_models_the_dropdown_decides(client, delivered_order):
    body = create_return(client, delivered_order, "The box arrived crushed.", "changed_mind")
    assert body["assigned_team"] == "customer_care"
    assert body["routing_source"] == "rule"
    assert body["priority_score"] is None
    assert body["priority"] is None


def test_model_overrides_a_wrong_dropdown(client, delivered_order, trained_models):
    body = create_return(
        client, delivered_order, "Hello, box arrived crushed. Please help.", "changed_mind"
    )
    assert body["assigned_team"] == "logistics"
    assert body["routing_source"] == "model"
    assert body["routing_confidence"] >= 0.6
    assert 0 <= body["priority_score"] <= 1
    assert body["priority"] in {"high", "medium", "low"}


def test_unsure_model_defers_to_dropdown(client, delivered_order, trained_models, monkeypatch):
    monkeypatch.setattr(get_settings(), "routing_min_confidence", 0.999)
    body = create_return(client, delivered_order, "Something about my order.", "size_fit")
    assert body["assigned_team"] == "customer_care"
    assert body["routing_source"] == "rule"
    assert body["routing_confidence"] is not None  # recorded for later analysis


def test_queue_can_be_sorted_by_priority(client, delivered_order, trained_models):
    create_return(client, delivered_order, "Please process this.", "changed_mind")
    create_return(client, delivered_order, "Very disappointed, want my money back.", "damaged")
    items = client.get("/api/v1/returns", params={"sort": "priority"}).json()["items"]
    scores = [r["priority_score"] for r in items]
    assert scores == sorted(scores, reverse=True)


def test_agent_can_reassign_team(client, delivered_order):
    number = create_return(client, delivered_order, "The box arrived crushed.", "defective")[
        "return_number"
    ]
    body = client.post(f"/api/v1/returns/{number}/team", json={"team": "logistics"}).json()
    assert body["assigned_team"] == "logistics"
    assert body["routing_source"] == "agent"

    client.post(f"/api/v1/returns/{number}/status", json={"status": "rejected", "note": "x"})
    closed = client.post(f"/api/v1/returns/{number}/team", json={"team": "quality"})
    assert closed.status_code == 409


def test_models_endpoint(client, trained_models):
    body = client.get("/api/v1/ml/models").json()
    assert body["routing"]["vocab_size"] > 10
    assert body["priority"]["trees"] >= 1


def test_broken_model_file_falls_back_to_rules(tmp_path, monkeypatch):
    (tmp_path / registry.ROUTER_FILE).write_bytes(b"not a model")
    monkeypatch.setattr(get_settings(), "model_dir", tmp_path)
    models = registry.reload_models()
    assert models.router is None
    assert registry.route("Box arrived crushed.", "defective").source == "rule"
    monkeypatch.undo()
    registry.reload_models()
