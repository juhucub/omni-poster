from __future__ import annotations

import os
import resource
import sys
from logging import Logger
from typing import Any


def _current_rss_bytes() -> int | None:
    try:
        page_size = os.sysconf("SC_PAGE_SIZE")
        with open("/proc/self/statm", "r", encoding="utf-8") as handle:
            resident_pages = int(handle.read().split()[1])
        return resident_pages * page_size
    except Exception:
        return None


def _peak_rss_bytes() -> int | None:
    try:
        value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except Exception:
        return None
    return value if sys.platform == "darwin" else value * 1024


def log_memory_event(logger: Logger, event: str, **metadata: Any) -> None:
    logger.info(
        "%s memory=%s",
        event,
        {
            "container_role": os.getenv("OMNI_CONTAINER_ROLE") or os.getenv("CONTAINER_ROLE") or "unknown",
            "rss_bytes": _current_rss_bytes(),
            "peak_rss_bytes": _peak_rss_bytes(),
            **metadata,
        },
    )
