import pytest

from app.cache import cache_get, cache_set


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_set_get():
    await cache_set("test_key", {"hello": "world"}, ttl=60)
    result = await cache_get("test_key")
    assert result == {"hello": "world"}


@pytest.mark.asyncio
async def test_cache_miss():
    result = await cache_get("nonexistent")
    assert result is None
