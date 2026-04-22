from __future__ import annotations

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request, status


_WINDOWS: dict[str, deque[float]] = defaultdict(deque)


def enforce_rate_limit(bucket: str, key: str, *, limit: int, window_seconds: int) -> None:
    now = time.time()
    window = _WINDOWS[f"{bucket}:{key}"]
    while window and window[0] <= now - window_seconds:
        window.popleft()
    if len(window) >= limit:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Please try again soon.",
        )
    window.append(now)


def request_identity(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"
