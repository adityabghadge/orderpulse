"""Return prioritization: estimate how likely each open return is to escalate.

An XGBoost model (gradient-boosted decision trees) scores every new return with the
probability that the customer escalates (files a complaint or a chargeback). The review
queue can then be sorted so the riskiest returns are handled first.

Trees suit this problem: the inputs are a mix of amounts, counts, and categories, the
interactions matter ("expensive AND angry"), and the model trains in a second.
"""

import json
import math
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import xgboost as xgb

from app.domain.returns import ReturnReason
from app.ml import ML_THREADS

REASONS = [r.value for r in ReturnReason]
UPSET_PHRASES = (
    "not happy",
    "disappointed",
    "money back",
    "unacceptable",
    "angry",
    "worst",
    "furious",
)

FEATURE_NAMES = [
    "log_refund_amount",
    "log_order_total",
    "plus_member",
    "customer_other_returns",
    "upset_phrases",
    "days_since_delivery",
    "text_length",
    *[f"reason_{r}" for r in REASONS],
]


@dataclass(frozen=True)
class PriorityInput:
    """Everything known about a return at the moment it is requested."""

    refund_amount_cents: int
    order_total_cents: int
    plus_member: bool
    customer_other_returns: int
    days_since_delivery: float
    reason_code: str
    reason_text: str


def features(row: PriorityInput) -> list[float]:
    text = row.reason_text.lower()
    return [
        math.log1p(row.refund_amount_cents / 100),
        math.log1p(row.order_total_cents / 100),
        float(row.plus_member),
        float(row.customer_other_returns),
        float(sum(phrase in text for phrase in UPSET_PHRASES)),
        row.days_since_delivery,
        float(len(text.split())),
        *[float(row.reason_code == r) for r in REASONS],
    ]


class PriorityModel:
    def __init__(self, booster: xgb.Booster, metadata: dict | None = None) -> None:
        booster.set_param({"nthread": ML_THREADS})
        self.booster = booster
        self.metadata = metadata or {}

    def predict_many(self, rows: list[PriorityInput]) -> list[float]:
        if not rows:
            return []
        matrix = xgb.DMatrix(np.array([features(r) for r in rows]), feature_names=FEATURE_NAMES)
        return [round(float(p), 4) for p in self.booster.predict(matrix)]

    def predict(self, row: PriorityInput) -> float:
        return self.predict_many([row])[0]

    def feature_importance(self) -> dict[str, float]:
        gains = self.booster.get_score(importance_type="gain")
        total = sum(gains.values()) or 1
        return {name: round(gains.get(name, 0) / total, 3) for name in FEATURE_NAMES}

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.booster.save_model(path)
        path.with_suffix(".meta.json").write_text(json.dumps(self.metadata, indent=2))

    @classmethod
    def load(cls, path: Path) -> "PriorityModel":
        booster = xgb.Booster()
        booster.load_model(path)
        meta_path = path.with_suffix(".meta.json")
        metadata = json.loads(meta_path.read_text()) if meta_path.exists() else {}
        return cls(booster, metadata)


def train_priority(
    rows: list[PriorityInput], escalated: list[bool], seed: int = 7
) -> PriorityModel:
    # Hold out the most recent 15% of the training rows to decide when to stop adding trees.
    cut = int(len(rows) * 0.85)
    train = xgb.DMatrix(
        np.array([features(r) for r in rows[:cut]]),
        label=np.array(escalated[:cut], dtype=float),
        feature_names=FEATURE_NAMES,
    )
    valid = xgb.DMatrix(
        np.array([features(r) for r in rows[cut:]]),
        label=np.array(escalated[cut:], dtype=float),
        feature_names=FEATURE_NAMES,
    )
    params = {
        "objective": "binary:logistic",  # outputs a probability between 0 and 1
        "eval_metric": "logloss",
        "max_depth": 3,
        "eta": 0.05,
        "subsample": 0.9,
        "colsample_bytree": 0.9,
        "min_child_weight": 5,
        "seed": seed,
        "nthread": ML_THREADS,
    }
    booster = xgb.train(
        params,
        train,
        num_boost_round=600,
        evals=[(valid, "valid")],
        early_stopping_rounds=40,
        verbose_eval=False,
    )
    return PriorityModel(
        booster,
        {"trained_at": datetime.now(UTC).isoformat(), "trees": booster.best_iteration + 1},
    )


def precision_at_k(scores: list[float], labels: list[bool], k: int) -> float:
    """Of the k highest-scored returns, the share that actually escalated."""
    ranked = sorted(zip(scores, labels, strict=True), key=lambda pair: pair[0], reverse=True)
    top = ranked[:k]
    return sum(label for _, label in top) / len(top) if top else 0.0


def auc(scores: list[float], labels: list[bool]) -> float:
    """Chance a random escalated return is scored above a random non-escalated one."""
    positives = [s for s, y in zip(scores, labels, strict=True) if y]
    negatives = [s for s, y in zip(scores, labels, strict=True) if not y]
    if not positives or not negatives:
        return 0.5
    # Rank all scores (tied scores share their average rank), then use the rank-sum formula.
    ordered = sorted(scores)
    ranks: dict[float, float] = {}
    i = 0
    while i < len(ordered):
        j = i
        while j < len(ordered) and ordered[j] == ordered[i]:
            j += 1
        ranks[ordered[i]] = (i + 1 + j) / 2
        i = j
    rank_sum = sum(ranks[s] for s in positives)
    n_pos, n_neg = len(positives), len(negatives)
    return (rank_sum - n_pos * (n_pos + 1) / 2) / (n_pos * n_neg)
