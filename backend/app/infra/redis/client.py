from __future__ import annotations

from app.core.config import settings

try:
    import redis as redis_lib
except Exception:  # pragma: no cover - import availability is environment-specific
    redis_lib = None

_CLIENT_CACHE: dict[tuple[str, float, float], object] = {}


def redis_package_available() -> bool:
    return redis_lib is not None


def safe_redis_url(url: str) -> str:
    if "@" not in url:
        return url
    scheme, rest = url.split("://", 1) if "://" in url else ("", url)
    host = rest.split("@", 1)[1]
    return f"{scheme}://***@{host}" if scheme else f"***@{host}"


def get_redis_url() -> str:
    return settings.REDIS_URL


def get_redis_client(
    url: str | None = None,
    *,
    socket_connect_timeout: float = 1,
    socket_timeout: float = 1,
):
    if redis_lib is None:
        return None
    redis_url = url or get_redis_url()
    cache_key = (redis_url, float(socket_connect_timeout), float(socket_timeout))
    if cache_key not in _CLIENT_CACHE:
        _CLIENT_CACHE[cache_key] = redis_lib.Redis.from_url(
            redis_url,
            socket_connect_timeout=socket_connect_timeout,
            socket_timeout=socket_timeout,
        )
    return _CLIENT_CACHE[cache_key]


def redis_ping(
    url: str | None = None,
    *,
    socket_connect_timeout: float = 1,
    socket_timeout: float = 1,
) -> bool:
    client = get_redis_client(
        url,
        socket_connect_timeout=socket_connect_timeout,
        socket_timeout=socket_timeout,
    )
    if client is None:
        return False
    return bool(client.ping())
