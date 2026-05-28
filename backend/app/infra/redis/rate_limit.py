from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict, deque

from app.infra.redis.client import get_redis_client

MEMORY_RATE_LIMIT_WINDOWS: dict[str, deque[float]] = defaultdict(deque)

REDIS_RATE_LIMIT_SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]
redis.call('ZREMRANGEBYSCORE', key, 0, now - window)
local count = redis.call('ZCARD', key)
if count >= limit then
  redis.call('EXPIRE', key, window)
  return 0
end
redis.call('ZADD', key, now, member)
redis.call('EXPIRE', key, window)
return 1
"""


def memory_rate_limit_allowed(bucket: str, key: str, *, limit: int, window_seconds: int) -> bool:
    now = time.time()
    window = MEMORY_RATE_LIMIT_WINDOWS[f"{bucket}:{key}"]
    while window and window[0] <= now - window_seconds:
        window.popleft()
    if len(window) >= limit:
        return False
    window.append(now)
    return True


def redis_rate_limit_key(bucket: str, key: str) -> str:
    digest = hashlib.sha256(f"{bucket}:{key}".encode("utf-8")).hexdigest()
    return f"omniposter:rate-limit:{bucket}:{digest}"


def redis_rate_limit_allowed(bucket: str, key: str, *, limit: int, window_seconds: int) -> bool | None:
    client = get_redis_client()
    if client is None:
        return None
    now = time.time()
    redis_key = redis_rate_limit_key(bucket, key)
    member = f"{now:.6f}:{uuid.uuid4().hex}"
    allowed = client.eval(
        REDIS_RATE_LIMIT_SCRIPT,
        1,
        redis_key,
        now,
        max(int(window_seconds), 1),
        int(limit),
        member,
    )
    return bool(int(allowed))
