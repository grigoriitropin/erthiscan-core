# CACHE TESTS: Validates Redis integration and serialization logic.
import pytest

from app.cache import cache_get, cache_set


@pytest.mark.asyncio
@pytest.mark.integration
async def test_cache_set_get():
    """
    INTEGRATION TEST: Verifies that data can be serialized to JSON,
    stored in Redis, and retrieved/deserialized correctly.
    Requires a running Redis instance (marked as @integration).
    """
    await cache_set("test_key", {"hello": "world"}, ttl=60)
    result = await cache_get("test_key")
    assert result == {"hello": "world"}


@pytest.mark.asyncio
async def test_cache_miss():
    """Ensures that cache misses return None gracefully."""
    result = await cache_get("nonexistent")
    assert result is None
