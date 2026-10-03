# OrderPulse

Operations platform for e-commerce support teams: track orders through fulfillment, handle returns and refunds, and prioritize the issues that matter most.

![CI](https://github.com/adityabghadge/orderpulse/actions/workflows/ci.yml/badge.svg)

## Features

- **Order lifecycle API**: orders move through `placed → packed → shipped → out_for_delivery → delivered` (or `cancelled`), enforced by an explicit state machine. Invalid moves are rejected with `409 Conflict`.
- **Full audit trail**: every status change is recorded with who made it, when, and why.
- **Safe under concurrency**: status changes lock the order row (`SELECT … FOR UPDATE`), so simultaneous updates apply exactly once.
- **Server-side money math**: totals are computed from line items in integer cents. Clients can't set them.
- **Consistent errors**: every failure returns `{"error": {"code", "message"}}`.
- **Response timing**: every response carries an `X-Response-Time-Ms` header for latency tracking.
- **Realistic demo data**: a seeded generator simulates thousands of orders with true-to-life fulfillment timelines.

## Tech stack

| Layer | Tools |
|---|---|
| API | Python 3.13, FastAPI, Pydantic |
| Database | PostgreSQL 16, SQLAlchemy 2, Alembic migrations |
| Testing & quality | pytest, Ruff |
| Infrastructure | Docker Compose, GitHub Actions |

## Getting started

Requirements: Docker Desktop, Python 3.11+, and `make`.

```bash
make setup   # start Postgres, install dependencies, run migrations, load demo data
make api     # http://localhost:8000
```

Interactive API docs are at **http://localhost:8000/docs**.

Run `make` to see all commands, including `make test` and `make lint`.

## API

| Method | Path | Description |
|---|---|---|
| `GET` | `/health` | Service and database health |
| `GET` | `/api/v1/orders` | List orders. Filters: `status`, `customer_id`, `q`; paging: `limit`, `offset` |
| `POST` | `/api/v1/orders` | Place an order |
| `GET` | `/api/v1/orders/{order_number}` | Order details with line items and status history |
| `POST` | `/api/v1/orders/{order_number}/status` | Move an order to its next status |
| `GET` | `/api/v1/customers` | Search customers by name or email |
| `GET` | `/api/v1/customers/{id}` | Customer details |

## Project structure

```
backend/
  app/
    api/        HTTP routes (thin: validate input, call a service, return output)
    services/   Business logic
    domain/     Core rules, e.g. the order state machine
    models/     Database tables (SQLAlchemy)
    schemas/    Request and response contracts (Pydantic)
    core/       Settings and error handling
    db/         Database engine and sessions
    seed.py     Demo data generator
  alembic/      Database migrations
  tests/        API, concurrency, and state-machine tests
infra/          Database initialization
```

## Testing

```bash
make test
```

Tests run against a dedicated `orderpulse_test` database built from the real migrations, and cover the full order lifecycle, validation, error formats, and concurrent updates.
