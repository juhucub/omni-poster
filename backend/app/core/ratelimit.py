import time
import redis

class TokenBucket:
    def __init__(self, r: redis.Redis, key: str, capacity: int, refill_per_sec: float):
        self.r = r
        self.key = key
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec

    def acquire(self, tokens: int = 1, block: bool = True, timeout: float = 30.0) -> bool:
        start = time.time()
        while True:
            with self.r.pipeline() as p:
                p.hmget(self.key, "tokens", "ts")
                tokens_ts = p.execute()[0]
                now = time.time()
                if tokens_ts[0] is None:
                    cur = self.capacity
                    last = now
                else:
                    cur = float(tokens_ts[0])
                    last = float(tokens_ts[1])
                # refill
                cur = min(self.capacity, cur + (now - last) * self.refill_per_sec)
                if cur >= tokens:
                    cur -= tokens
                    p.hset(self.key, mapping={"tokens": cur, "ts": now})
                    p.expire(self.key, 3600)
                    p.execute()
                    return True
                else:
                    p.hset(self.key, mapping={"tokens": cur, "ts": now})
                    p.expire(self.key, 3600)
                    p.execute()
            if not block or (time.time() - start) > timeout:
                return False
            time.sleep(0.2)
