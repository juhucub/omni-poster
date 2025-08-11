from typing import Optional
from redis import Redis

class ETagCache:
    def __init__(self, r: Redis): self.r = r
    def key(self, platform: str, resource: str) -> str:
        return f"etag:{platform}:{resource}"
    def get(self, platform: str, resource: str) -> Optional[str]:
        return self.r.get(self.key(platform, resource))
    def set(self, platform: str, resource: str, etag: str, ttl=86400):
        self.r.setex(self.key(platform, resource), ttl, etag)
