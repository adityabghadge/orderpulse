"""Loads trained models once per process and decides how each return is routed and scored.

Models are optional. If no trained model exists (or loading fails), the API falls back to the
dropdown rule for routing and leaves the priority empty, so the app always works.
"""

import logging
from dataclasses import dataclass
from functools import lru_cache

from app.core.config import get_settings
from app.domain.returns import ReturnReason, route_by_reason
from app.ml.priority import PriorityInput, PriorityModel
from app.ml.routing import ReturnRouter

log = logging.getLogger(__name__)

ROUTER_FILE = "return_router.pt"
PRIORITY_FILE = "return_priority.json"


@dataclass(frozen=True)
class Models:
    router: ReturnRouter | None
    priority: PriorityModel | None


@lru_cache
def get_models() -> Models:
    model_dir = get_settings().model_dir
    router = priority = None
    try:
        if (model_dir / ROUTER_FILE).exists():
            router = ReturnRouter.load(model_dir / ROUTER_FILE)
        if (model_dir / PRIORITY_FILE).exists():
            priority = PriorityModel.load(model_dir / PRIORITY_FILE)
    except Exception:  # a broken model file must never take the API down
        log.exception("Could not load models from %s; using rule-based routing", model_dir)
    return Models(router, priority)


def reload_models() -> Models:
    get_models.cache_clear()
    return get_models()


@dataclass(frozen=True)
class RoutingDecision:
    team: str
    source: str  # "model" or "rule"
    confidence: float | None


def route_many(texts: list[str], reasons: list[str]) -> list[RoutingDecision]:
    """Use the model where it's confident enough; otherwise trust the customer's dropdown."""
    router = get_models().router
    rule = [route_by_reason(ReturnReason(r)).value for r in reasons]
    if router is None:
        return [RoutingDecision(team, "rule", None) for team in rule]

    threshold = get_settings().routing_min_confidence
    decisions = []
    for prediction, fallback in zip(router.predict_many(texts, reasons), rule, strict=True):
        if prediction.confidence >= threshold:
            decisions.append(RoutingDecision(prediction.team, "model", prediction.confidence))
        else:
            decisions.append(RoutingDecision(fallback, "rule", prediction.confidence))
    return decisions


def route(text: str, reason: str) -> RoutingDecision:
    return route_many([text], [reason])[0]


def score_many(rows: list[PriorityInput]) -> list[float | None]:
    model = get_models().priority
    return model.predict_many(rows) if model else [None] * len(rows)


def model_summary() -> dict:
    models = get_models()
    return {
        "routing": models.router.metadata if models.router else None,
        "priority": models.priority.metadata if models.priority else None,
    }
