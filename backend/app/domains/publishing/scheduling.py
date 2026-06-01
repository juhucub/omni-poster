from __future__ import annotations

from datetime import datetime


def is_scheduled_job_due(
    status: str,
    scheduled_for: datetime | None,
    now: datetime,
) -> bool:
    return status == "scheduled" and scheduled_for is not None and scheduled_for <= now
