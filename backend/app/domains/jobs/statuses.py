from __future__ import annotations

ACTIVE_GENERATION_STATUSES: frozenset[str] = frozenset({"queued", "processing", "retrying"})
TERMINAL_GENERATION_STATUSES: frozenset[str] = frozenset({"completed", "failed", "canceled"})
CANCELABLE_GENERATION_STATUSES: frozenset[str] = frozenset({"queued"})

STALE_GENERATION_MINUTES: int = 15
STALE_GENERATION_ERROR: str = "worker lost during render"
