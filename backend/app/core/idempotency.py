"""Idempotent request handling: run an operation at most once per Idempotency-Key.

How it works, inside a single database transaction:

1. Try to INSERT the key. The primary key on `idempotency_keys.key` makes this atomic.
2. If the insert succeeds, this is the first request: run the operation, store its response
   next to the key, and commit everything together.
3. If the key already exists, the operation already ran: replay the stored response.
   (If the first request is still running, Postgres makes this insert wait until it
   commits, so a concurrent duplicate replays the result instead of running twice.)
4. If the operation fails, the transaction rolls back, including the key, so the client
   can safely retry with the same key once the problem is fixed.

The request fingerprint stops a client from reusing a key for a *different* request.
"""

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.errors import IdempotencyKeyReusedError
from app.models import IdempotencyKey


@dataclass(frozen=True)
class IdempotentResult:
    status_code: int
    body: dict[str, Any]
    replayed: bool


def fingerprint(*parts: Any) -> str:
    canonical = json.dumps(parts, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


def run_idempotent(
    db: Session,
    *,
    key: str,
    request_fingerprint: str,
    operation: Callable[[], tuple[int, dict[str, Any]]],
) -> IdempotentResult:
    """Run `operation` once per key. `operation` must not commit; this function does."""
    claimed = db.scalar(
        insert(IdempotencyKey)
        .values(key=key, request_fingerprint=request_fingerprint)
        .on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
        .returning(IdempotencyKey.key)
    )

    if claimed is None:
        existing = db.get(IdempotencyKey, key)
        db.rollback()
        if existing is None or existing.response_status is None:  # pragma: no cover
            raise RuntimeError("Idempotency record vanished; retry the request")
        if existing.request_fingerprint != request_fingerprint:
            raise IdempotencyKeyReusedError(
                "This Idempotency-Key was already used for a different request."
            )
        return IdempotentResult(existing.response_status, existing.response_body or {}, True)

    try:
        status_code, body = operation()
        record = db.get(IdempotencyKey, key)
        record.response_status = status_code
        record.response_body = body
        db.commit()
    except Exception:
        db.rollback()
        raise
    return IdempotentResult(status_code, body, False)
