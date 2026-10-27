"""Async cache-aside with TTL jitter, single-flight, soft/hard TTL (stale-while-revalidate),
negative caching, timeouts and a simple circuit breaker. Errors are never cached as misses.

Requires redis-py >= 5 (redis.asyncio). Keys follow {app}:{env}:v{schema}:[t:{tenant}:]{entity}:{id}.

Usage:
    cache = CacheAside(redis.asyncio.from_url(REDIS_URL), prefix="shop:prod:v3")
    product = await cache.get(f"product:{pid}", lambda: load_product(pid), soft_ttl=60, hard_ttl=600)
    await cache.delete(f"product:{pid}")      # after the DB commit
"""

from __future__ import annotations

import asyncio
import json
import random
import time
from typing import Any, Awaitable, Callable, Optional

NOT_FOUND = object()  # loaders return this (or None) for "doesn't exist"


class CacheAside:
    def __init__(self, redis, prefix: str, cache_timeout: float = 0.05,
                 breaker_threshold: int = 5, breaker_open_seconds: float = 10.0):
        self.redis = redis
        self.prefix = prefix
        self.cache_timeout = cache_timeout
        self.breaker_threshold = breaker_threshold
        self.breaker_open_seconds = breaker_open_seconds
        self._inflight: dict[str, asyncio.Task] = {}
        self._failures = 0
        self._open_until = 0.0

    def _key(self, k: str) -> str:
        return f"{self.prefix}:{k}"

    @staticmethod
    def _jitter(seconds: float) -> int:
        return max(1, int(seconds * 1000 * random.uniform(0.9, 1.1)))  # ms, ±10 %

    async def _read(self, k: str) -> Optional[dict]:
        if time.monotonic() < self._open_until:
            return None
        try:
            raw = await asyncio.wait_for(self.redis.get(k), self.cache_timeout)
            self._failures = 0
            return json.loads(raw) if raw else None
        except Exception:  # cache outage: fail open to the source, trip the breaker
            self._failures += 1
            if self._failures >= self.breaker_threshold:
                self._open_until = time.monotonic() + self.breaker_open_seconds
            return None

    async def _write(self, k: str, envelope: dict, ttl_seconds: float) -> None:
        if time.monotonic() < self._open_until:
            return
        try:
            await asyncio.wait_for(self.redis.set(k, json.dumps(envelope), px=self._jitter(ttl_seconds)), self.cache_timeout)
        except Exception:
            pass  # best effort: never fail the request because the cache write failed

    async def _load(self, k: str, loader: Callable[[], Awaitable[Any]], soft_ttl: float, hard_ttl: float,
                    negative_ttl: float, loader_timeout: float) -> Any:
        try:
            value = await asyncio.wait_for(loader(), loader_timeout)
            if value is None or value is NOT_FOUND:
                if negative_ttl > 0:
                    await self._write(k, {"v": None, "soft": time.time() + negative_ttl, "neg": True}, negative_ttl)
                return None
            await self._write(k, {"v": value, "soft": time.time() + soft_ttl}, hard_ttl)
            return value
        finally:
            self._inflight.pop(k, None)

    def _single_flight(self, k: str, *args) -> asyncio.Task:
        task = self._inflight.get(k)
        if task is None:
            task = asyncio.ensure_future(self._load(k, *args))
            self._inflight[k] = task
        return task

    async def get(self, key: str, loader: Callable[[], Awaitable[Any]], *, soft_ttl: float, hard_ttl: float,
                  negative_ttl: float = 30.0, loader_timeout: float = 5.0) -> Any:
        """Values must be JSON-serializable. Loader exceptions propagate and are not cached."""
        k = self._key(key)
        args = (loader, soft_ttl, hard_ttl, negative_ttl, loader_timeout)
        hit = await self._read(k)
        if hit is not None:
            if time.time() >= hit["soft"] and not hit.get("neg"):
                task = self._single_flight(k, *args)  # refresh in the background; keep serving stale
                task.add_done_callback(lambda t: t.cancelled() or t.exception())  # swallow errors: stale value stays
            return hit["v"]
        return await asyncio.shield(self._single_flight(k, *args))

    async def delete(self, key: str) -> None:
        await self.redis.delete(self._key(key))  # call after the DB transaction commits
