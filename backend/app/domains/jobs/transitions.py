from __future__ import annotations

from app.domains.jobs.statuses import (
    ACTIVE_GENERATION_STATUSES,
    CANCELABLE_GENERATION_STATUSES,
    TERMINAL_GENERATION_STATUSES,
)


def is_active_status(status: str) -> bool:
    return status in ACTIVE_GENERATION_STATUSES


def is_terminal_status(status: str) -> bool:
    return status in TERMINAL_GENERATION_STATUSES


def can_cancel(status: str) -> bool:
    return status in CANCELABLE_GENERATION_STATUSES
