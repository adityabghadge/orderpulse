"""A small Redis cache that never takes the API down with it.

Caching is an optimization, not a dependency: if Redis is slow or unreachable, every call
here quietly falls back to "cache miss" and the API keeps answering from the database.
After a failure, Redis is skipped for a short cool-down period (a simple circuit breaker),
so a dead cache doesn't add a timeout to every request.
"""

import json
import logging
import time
from functools import lru_cache
from typing import Any

import redis
from redis.exceptions import RedisError

from app.core.config import get_settings

log = logging.getLogger(__name__)

COOL_DOWN_SECONDS = 15


class Cache:
    def __init__(self, url: str) -> None:
        self._client = redis.Redis.from_url(
            url, socket_connect_timeout=0.25, socket_timeout=0.25, decode_responses=True
        )
        self._skip_until = 0.0

    @property
    def available(self) -> bool:
        return time.monotonic() >= self._skip_until

    def _failed(self, operation: str, error: Exception) -> None:
        log.warning(
            "Cache %s failed, bypassing Redis for %ss: %s", operation, COOL_DOWN_SECONDS, error
        )
        self._skip_until = time.monotonic() + COOL_DOWN_SECONDS

    def get_json(self, key: str) -> Any | None:
        if not self.available:
            return None
        try:
            raw = self._client.get(key)
        except RedisError as error:
            self._failed("read", error)
            return None
        return json.loads(raw) if raw is not None else None

    def set_json(self, key: str, value: Any, ttl_seconds: int) -> None:
        if not self.available:
            return
        try:
            self._client.set(key, json.dumps(value, separators=(",", ":")), ex=ttl_seconds)
        except RedisError as error:
            self._failed("write", error)

    def delete(self, *keys: str) -> None:
        if not self.available:
            return
        try:
            self._client.delete(*keys)
        except RedisError as error:
            self._failed("delete", error)

    def ping(self) -> bool:
        try:
            return bool(self._client.ping())
        except RedisError:
            return False


@lru_cache
def get_cache() -> Cache:
    return Cache(get_settings().redis_url)
