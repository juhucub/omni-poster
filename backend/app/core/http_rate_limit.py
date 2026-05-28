from __future__ import annotations

import logging

from fastapi import HTTPException, Request, status

from app.core.config import settings
from app.infra.redis.client import get_redis_client
from app.infra.redis.rate_limit import (
    MEMORY_RATE_LIMIT_WINDOWS,
    REDIS_RATE_LIMIT_SCRIPT,
    memory_rate_limit_allowed,
    redis_rate_limit_allowed,
    redis_rate_limit_key,
)

logger = logging.getLogger(__name__)

_WINDOWS = MEMORY_RATE_LIMIT_WINDOWS
_REDIS_RATE_LIMIT_SCRIPT = REDIS_RATE_LIMIT_SCRIPT


def _get_redis_client():
    return get_redis_client()


def _memory_enforce_rate_limit(bucket: str, key: str, *, limit: int, window_seconds: int) -> None:
    if not memory_rate_limit_allowed(bucket, key, limit=limit, window_seconds=window_seconds):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again soon.",
        )


def _redis_rate_limit_key(bucket: str, key: str) -> str:
    return redis_rate_limit_key(bucket, key)


def _redis_enforce_rate_limit(bucket: str, key: str, *, limit: int, window_seconds: int) -> bool:
    allowed = redis_rate_limit_allowed(bucket, key, limit=limit, window_seconds=window_seconds)
    if allowed is None:
        return False
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again soon.",
        )
    return True


def enforce_rate_limit(bucket: str, key: str, *, limit: int, window_seconds: int) -> None:
    if limit <= 0 or window_seconds <= 0:
        return
    backend = settings.RATE_LIMIT_BACKEND.lower().strip()
    if backend == "redis":
        try:
            if _redis_enforce_rate_limit(bucket, key, limit=limit, window_seconds=window_seconds):
                return
        except HTTPException:
            raise
        except Exception as exc:
            if not settings.is_dev:
                logger.exception("Redis rate limiting failed outside dev")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Rate limiting is temporarily unavailable.",
                ) from exc
            logger.warning("Redis rate limiting unavailable; using process-local dev fallback: %s", exc)
    elif backend != "memory" and not settings.is_dev:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Rate limiting backend is misconfigured.",
        )

    _memory_enforce_rate_limit(bucket, key, limit=limit, window_seconds=window_seconds)


def request_identity(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for") if settings.TRUST_PROXY_HEADERS else None
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
