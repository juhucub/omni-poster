from __future__ import annotations

PUBLISH_PROCESSABLE_STATUSES: frozenset[str] = frozenset({"publish_queued", "queued", "retrying"})
PUBLISH_CANCELABLE_STATUSES: frozenset[str] = frozenset({"scheduled"})
PUBLISH_RETRYABLE_STATUSES: frozenset[str] = frozenset({"failed"})
PUBLISH_TERMINAL_STATUSES: frozenset[str] = frozenset({"published", "failed", "canceled"})
PUBLISH_ACTIVE_STATUSES: frozenset[str] = frozenset({"publish_queued", "queued", "retrying", "publishing", "scheduled"})


def is_publish_job_processable(status: str) -> bool:
    return status in PUBLISH_PROCESSABLE_STATUSES


def is_publish_job_cancelable(status: str) -> bool:
    return status in PUBLISH_CANCELABLE_STATUSES


def is_publish_job_retryable(status: str) -> bool:
    return status in PUBLISH_RETRYABLE_STATUSES


def publish_job_public_status(status: str) -> str:
    """Normalize internal "publish_queued" to the API-visible "queued" label."""
    return "queued" if status == "publish_queued" else status
