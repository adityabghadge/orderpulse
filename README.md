# OrderPulse

Operations platform for e-commerce support teams: track orders through fulfillment, handle returns and refunds, and prioritize the issues that matter most.

![CI](https://github.com/adityabghadge/orderpulse/actions/workflows/ci.yml/badge.svg)

![Operations overview](docs/screenshots/overview.png)

## Features

- **Order lifecycle API**: orders move through `placed → packed → shipped → out_for_delivery → delivered` (or `cancelled`), enforced by an explicit state machine. Invalid moves are rejected with `409 Conflict`.
- **Returns with eligibility rules**: returns are accepted only for delivered orders, inside a 30-day window, and never for more units than were bought. Each return is routed to the team that handles it (logistics, quality, fulfillment, or customer care).
- **Exactly-once refunds**: refunds require an `Idempotency-Key` header. Retries replay the original response instead of paying again, concurrent duplicates are serialized, and a database constraint guarantees one refund per return. Payment-provider failures roll back cleanly so the same key can be retried.
- **Full audit trail**: every status change is recorded with who made it, when, and why.
- **Safe under concurrency**: status changes lock the order row (`SELECT … FOR UPDATE`), so simultaneous updates apply exactly once.
- **Server-side money math**: totals are computed from line items in integer cents. Clients can't set them.
- **Consistent errors**: every failure returns `{"error": {"code", "message"}}`.
- **Response timing**: every response carries an `X-Response-Time-Ms` header for latency tracking.
- **Operations dashboard**: a React console with a live order pipeline, key metrics, a first-in-first-out returns queue, and order detail pages where operators move orders forward, start returns, and issue refunds. Refunds retry network failures with the same idempotency key.
- **Realistic demo data**: a seeded generator simulates thousands of orders with true-to-life fulfillment timelines.

## Tech stack

| Layer | Tools |
|---|---|
| Dashboard | React 19, TypeScript, Vite, React Router, TanStack Query, Recharts |
| API | Python 3.13, FastAPI, Pydantic |
| Database | PostgreSQL 16, SQLAlchemy 2, Alembic migrations |
| Testing & quality | pytest, Vitest, Testing Library, Ruff |
| Infrastructure | Docker Compose, GitHub Actions |

## Getting started

Requirements: Docker Desktop, Python 3.11+, Node.js 20+, and `make`.

```bash
make setup   # start Postgres, install dependencies, run migrations, load demo data
make api     # API at http://localhost:8000 (interactive docs at /docs)
make web     # dashboard at http://localhost:5173 (in a second terminal)
```

Run `make` to see all commands, including `make test` and `make lint`.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service and database health |
| `GET` | `/api/v1/orders` | List orders. Filters: `status`, `customer_id`, `q`; paging: `limit`, `offset` |
| `POST` | `/api/v1/orders` | Place an order |
| `GET` | `/api/v1/orders/{order_number}` | Order details with line items and status history |
| `POST` | `/api/v1/orders/{order_number}/status` | Move an order to its next status |
| `POST` | `/api/v1/orders/{order_number}/returns` | Request a return for a delivered item |
| `GET` | `/api/v1/returns` | List returns. Filters: `status`, `reason`, `order_number` |
| `GET` | `/api/v1/returns/{return_number}` | Return details, including any refund |
| `POST` | `/api/v1/returns/{return_number}/status` | Approve, reject, or mark as received |
| `POST` | `/api/v1/returns/{return_number}/refund` | Issue the refund (requires `Idempotency-Key`) |
| `GET` | `/api/v1/customers` | Search customers by name or email |
| `GET` | `/api/v1/customers/{id}` | Customer details |
| `GET` | `/api/v1/stats/overview` | Pipeline, metrics, and trends for the dashboard |

## Screenshots

| Returns queue | Order detail |
|---|---|
| ![Returns queue](docs/screenshots/returns.png) | ![Order detail](docs/screenshots/order.png) |

## Project structure

```
frontend/
  src/
    pages/      Overview, orders, order detail, returns queue
    components/ Pipeline, status pills, chart, layout, shared states
    api/        Typed API client and data-fetching hooks
    lib/        Formatting and the refund retry logic
backend/
  app/
    api/        HTTP routes (thin: validate input, call a service, return output)
    services/   Business logic
    domain/     Core rules: order and return lifecycles, return routing
    models/     Database tables (SQLAlchemy)
    schemas/    Request and response contracts (Pydantic)
    core/       Settings, error handling, idempotency
    integrations/  External services (payment provider)
    db/         Database engine and sessions
    seed.py     Demo data generator
  alembic/      Database migrations
  tests/        API, concurrency, and state-machine tests
infra/          Database initialization
```

## Testing

```bash
make test      # backend
make web-test  # frontend type-check and tests
```

Backend tests run against a dedicated `orderpulse_test` database built from the real migrations, and cover order and return lifecycles, validation, error formats, idempotent retries, payment-provider failures, and concurrent updates.

## Design notes

**Why refunds can't be paid twice.** Two independent safeguards:

1. *Idempotency keys* handle retries of the same request. The key is claimed with an atomic `INSERT … ON CONFLICT DO NOTHING`, and the operation and its stored response commit in the same transaction. A concurrent duplicate blocks on the key until the first request commits, then replays its response. A request fingerprint rejects a key reused for a different request.
2. *Row locks and a unique constraint* handle different requests for the same return: the return row is locked (`SELECT … FOR UPDATE`), its status is checked, and `UNIQUE(refunds.return_id)` makes a second refund impossible at the database level.

The idempotency key is also forwarded to the payment provider, so the provider can de-duplicate on its side too.
