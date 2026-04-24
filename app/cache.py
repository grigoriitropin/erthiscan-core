import json
import logging
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.config import get_settings

logger = logging.getLogger(__name__)

_redis: redis.Redis | None = None


async def get_redis() -> redis.Redis | None:
    global _redis
    if _redis is not None:
        return _redis
    url = get_settings().redis_url
    if url is None:
        return None
    _redis = redis.from_url(
        url,
        decode_responses=True,
        socket_timeout=2,
        socket_connect_timeout=2,
        health_check_interval=30,
    )
    return _redis


async def cache_get(key: str) -> Any | None:
    r = await get_redis()
    if r is None:
        return None
    try:
        data = await r.get(key)
    except RedisError:
        logger.warning("redis get failed for key=%s", key, exc_info=True)
        return None
    if data is None:
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        logger.warning("corrupt cache entry for key=%s", key)
        return None


async def cache_set(key: str, value: Any, ttl: int = 120) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        await r.set(key, json.dumps(value, default=str), ex=ttl)
    except RedisError:
        logger.warning("redis set failed for key=%s", key, exc_info=True)


async def cache_delete_pattern(pattern: str) -> None:
    r = await get_redis()
    if r is None:
        return
    try:
        batch: list[str] = []
        async for key in r.scan_iter(match=pattern, count=500):
            batch.append(key)
            if len(batch) >= 500:
                await r.unlink(*batch)
                batch.clear()
        if batch:
            await r.unlink(*batch)
    except RedisError:
        logger.warning("redis delete_pattern failed for pattern=%s", pattern, exc_info=True)


async def blacklist_token(jti: str, ttl: int) -> None:
    r = await get_redis()
    if r is None:
        raise RuntimeError("Redis not configured, cannot blacklist token")
    try:
        await r.set(f"bl:{jti}", "1", ex=ttl)
    except RedisError:
        logger.error("redis blacklist_token failed for jti=%s", jti, exc_info=True)
        raise


async def is_token_blacklisted(jti: str) -> bool:
    r = await get_redis()
    if r is None:
        return True  # fail closed
    try:
        return await r.exists(f"bl:{jti}") > 0
    except RedisError:
        logger.error("redis blacklist check failed for jti=%s", jti, exc_info=True)
        return True  # fail closed
