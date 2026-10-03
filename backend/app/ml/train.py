"""Train both models, evaluate them honestly, save them, and apply them to open returns.

Usage:
    python -m app.ml.train

Evaluation uses a time-based split: models learn from the oldest 80% of closed returns and
are tested on the newest 20%, the same way they'd be used in production (trained on the
past, predicting the future). A random split would quietly leak future patterns into training.
"""

import argparse
import json
import time
from collections import Counter

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.domain.returns import ReturnReason, route_by_reason
from app.ml import registry
from app.ml.dataset import ReturnExample, closed_returns, open_returns
from app.ml.priority import auc, precision_at_k, train_priority
from app.ml.routing import TEAMS, train_router
from app.models import Return
from app.services.stats import invalidate_overview

TEST_SHARE = 0.2
TOP_K = 20
MIN_EXAMPLES = 200


def _misroute_rate(predicted: list[str], actual: list[str]) -> float:
    return sum(p != a for p, a in zip(predicted, actual, strict=True)) / len(actual)


def evaluate_routing(router, test: list[ReturnExample]) -> dict:
    actual = [e.team for e in test]
    dropdown = [route_by_reason(ReturnReason(e.reason)).value for e in test]
    predictions = router.predict_many([e.text for e in test], [e.reason for e in test])
    model = [p.team for p in predictions]

    threshold = get_settings().routing_min_confidence
    deployed = [
        p.team if p.confidence >= threshold else rule
        for p, rule in zip(predictions, dropdown, strict=True)
    ]
    per_team = {}
    for team in TEAMS:
        rows = [i for i, a in enumerate(actual) if a == team]
        if rows:
            per_team[team] = round(sum(model[i] == team for i in rows) / len(rows), 3)

    return {
        "test_size": len(test),
        "dropdown_misroute_rate": round(_misroute_rate(dropdown, actual), 4),
        "model_misroute_rate": round(_misroute_rate(model, actual), 4),
        "deployed_misroute_rate": round(_misroute_rate(deployed, actual), 4),
        "model_used_share": round(
            sum(p.confidence >= threshold for p in predictions) / len(test), 4
        ),
        "recall_by_team": per_team,
    }


def evaluate_priority(model, test: list[ReturnExample]) -> dict:
    labels = [bool(e.escalated) for e in test]
    scores = model.predict_many([e.priority_input for e in test])
    by_amount = [float(e.priority_input.refund_amount_cents) for e in test]
    return {
        "test_size": len(test),
        "escalation_rate": round(sum(labels) / len(labels), 4),
        f"precision_at_{TOP_K}": round(precision_at_k(scores, labels, TOP_K), 3),
        f"precision_at_{TOP_K}_by_refund_amount": round(
            precision_at_k(by_amount, labels, TOP_K), 3
        ),
        "auc": round(auc(scores, labels), 3),
        "auc_by_refund_amount": round(auc(by_amount, labels), 3),
        "feature_importance": dict(
            sorted(model.feature_importance().items(), key=lambda kv: -kv[1])[:6]
        ),
    }


def apply_to_open_returns(db: Session) -> int:
    """Re-route and re-score open returns that no agent has corrected by hand."""
    examples = [e for e in open_returns(db) if e.team is not None]
    sources = dict(
        db.query(Return.id, Return.routing_source).filter(Return.id.in_([e.id for e in examples]))
    )
    examples = [e for e in examples if sources.get(e.id) != "agent"]
    decisions = registry.route_many([e.text for e in examples], [e.reason for e in examples])
    scores = registry.score_many([e.priority_input for e in examples])
    for example, decision, score in zip(examples, decisions, scores, strict=True):
        db.execute(
            update(Return)
            .where(Return.id == example.id)
            .values(
                assigned_team=decision.team,
                routing_source=decision.source,
                routing_confidence=decision.confidence,
                priority_score=score,
            )
        )
    db.commit()
    invalidate_overview()
    return len(examples)


def main() -> None:
    argparse.ArgumentParser(
        description="Train the return routing and priority models."
    ).parse_args()
    settings = get_settings()
    started = time.perf_counter()

    with SessionLocal() as db:
        examples = closed_returns(db)
        if len(examples) < MIN_EXAMPLES:
            raise SystemExit(
                f"Only {len(examples)} closed returns found; need {MIN_EXAMPLES}. "
                "Run `make seed` first."
            )
        cut = int(len(examples) * (1 - TEST_SHARE))
        train, test = examples[:cut], examples[cut:]

        router = train_router(
            [e.text for e in train], [e.reason for e in train], [e.team for e in train]
        )
        routing_metrics = evaluate_routing(router, test)
        router.metadata.update(
            {
                "train_size": len(train),
                "team_distribution": dict(Counter(e.team for e in train)),
                "metrics": routing_metrics,
            }
        )
        router.save(settings.model_dir / registry.ROUTER_FILE)

        priority = train_priority(
            [e.priority_input for e in train], [bool(e.escalated) for e in train]
        )
        priority_metrics = evaluate_priority(priority, test)
        priority.metadata.update({"train_size": len(train), "metrics": priority_metrics})
        priority.save(settings.model_dir / registry.PRIORITY_FILE)

        registry.reload_models()
        updated = apply_to_open_returns(db)

    r, p = routing_metrics, priority_metrics
    print(f"\nTrained on {len(train):,} closed returns, tested on the newest {len(test):,}.\n")
    print("Return routing (which team should handle it)")
    print(f"  Dropdown rule misroutes      {r['dropdown_misroute_rate']:6.1%}")
    print(f"  Model misroutes              {r['model_misroute_rate']:6.1%}")
    print(
        f"  As deployed (model if >={settings.routing_min_confidence:.0%} confident) "
        f"{r['deployed_misroute_rate']:6.1%}   model decides {r['model_used_share']:.0%}"
    )
    print("\nPriority (will this return escalate?)")
    print(f"  Escalation rate              {p['escalation_rate']:6.1%}")
    print(f"  Precision@{TOP_K}, model          {p[f'precision_at_{TOP_K}']:6.2f}")
    print(f"  Precision@{TOP_K}, by refund size {p[f'precision_at_{TOP_K}_by_refund_amount']:6.2f}")
    print(f"  Precision@{TOP_K}, random pick    {p['escalation_rate']:6.2f}  (= escalation rate)")
    print(f"  AUC model / by refund size    {p['auc']:.3f} / {p['auc_by_refund_amount']:.3f}")
    print(f"  Most important features      {', '.join(list(p['feature_importance'])[:4])}")
    print(f"\nRe-routed and scored {updated:,} open returns. Models saved to {settings.model_dir}")
    print(f"Done in {time.perf_counter() - started:.1f}s\n")
    (settings.model_dir / "metrics.json").write_text(
        json.dumps({"routing": r, "priority": p}, indent=2)
    )


if __name__ == "__main__":
    main()
