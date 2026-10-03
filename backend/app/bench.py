"""Measure how long the operations overview takes, before and after each optimization.

Usage:
    python -m app.bench              # 30 runs per strategy against the current database

Strategies, from slowest to fastest:
  1. Live aggregation    every request scans the raw tables (the original approach)
  2. Materialized view   finished days precomputed, only today computed live
  3. Redis cache hit     the finished response served from memory

The first two call the service directly; the cache measurement goes through the full HTTP
stack (routing, validation, JSON) so it reflects what the dashboard actually experiences.
"""

import argparse
import statistics
import time
import warnings
from collections.abc import Callable

warnings.filterwarnings("ignore", message="Using `httpx` with `starlette.testclient`")

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.core.cache import get_cache  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Order  # noqa: E402
from app.services.stats import (  # noqa: E402
    OVERVIEW_CACHE_KEY,
    overview,
    overview_live,
    refresh_daily_operations,
)


def measure(fn: Callable[[], object], runs: int) -> list[float]:
    fn()  # warm-up: connection pool, query plans, caches
    timings = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        timings.append((time.perf_counter() - start) * 1000)
    return timings


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, round(0.95 * (len(ordered) - 1)))]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--runs", type=int, default=30)
    args = parser.parse_args()

    with SessionLocal() as db:
        order_count = db.scalar(select(func.count()).select_from(Order))
        refresh_daily_operations(db, concurrently=False)
        live = measure(lambda: overview_live(db), args.runs)
        fast = measure(lambda: overview(db), args.runs)

    client = TestClient(app)
    cache = get_cache()
    if not cache.ping():
        raise SystemExit("Redis isn't reachable. Start it with `make up` and try again.")

    def miss():
        cache.delete(OVERVIEW_CACHE_KEY)
        client.get("/api/v1/stats/overview")

    http_miss = measure(miss, args.runs)
    client.get("/api/v1/stats/overview")
    http_hit = measure(lambda: client.get("/api/v1/stats/overview"), args.runs)

    rows = [
        ("Live aggregation (no precomputation)", live),
        ("Materialized view + live today", fast),
        ("Full request, cache miss", http_miss),
        ("Full request, Redis cache hit", http_hit),
    ]
    baseline = statistics.median(live)
    print(f"\nOverview latency with {order_count:,} orders ({args.runs} runs each)\n")
    print(f"| {'Strategy':<38} | {'Median':>9} | {'p95':>9} | {'vs live':>8} |")
    print(f"|{'-' * 40}|{'-' * 11}|{'-' * 11}|{'-' * 10}|")
    for name, timings in rows:
        median = statistics.median(timings)
        print(
            f"| {name:<38} | {median:>6.1f} ms | {p95(timings):>6.1f} ms | "
            f"{baseline / median:>7.0f}x |"
        )
    print()


if __name__ == "__main__":
    main()
