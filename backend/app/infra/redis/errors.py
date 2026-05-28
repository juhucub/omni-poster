from __future__ import annotations


class RedisInfraError(RuntimeError):
    """Base error for low-level Redis infrastructure failures."""


class RedisUnavailableError(RedisInfraError):
    """Raised when Redis is required but not available."""
