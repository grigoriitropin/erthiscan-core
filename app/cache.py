import json
import os
from typing import Any

import redis.asyncio as redis

REDIS_URL = os.environ.get("REDIS_URL", "redis://redis.erthiscan.svc.cluster.local:6379/0")

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    global _redis
    if _redis is None:
        _redis = redis.from_url(REDIS_URL, decode_responses=True)
    return _redis


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    data = await r.get(key)
    if data is None:
        return None
    return json.loads(data)


async def cache_set(key: str, value: Any, ttl: int = 120) -> None:
    r = await get_redis()
    await r.set(key, json.dumps(value, default=str), ex=ttl)


async def cache_delete_pattern(pattern: str) -> None:
    r = await get_redis()
    async for key in r.scan_iter(match=pattern):
        await r.delete(key)


async def blacklist_token(jti: str, ttl: int) -> None:
    r = await get_redis()
    await r.set(f"bl:{jti}", "1", ex=ttl)


async def is_token_blacklisted(jti: str) -> bool:
    r = await get_redis()
    return await r.exists(f"bl:{jti}") > 0
