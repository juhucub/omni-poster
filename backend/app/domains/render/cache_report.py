from __future__ import annotations

import time
from pathlib import Path
from typing import Any


def _cache_transfer_metadata(
    transfer_metadata: dict[str, Any] | None,
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {**dict(transfer_metadata or {}), **dict(extra_metadata or {})}


def build_final_render_cache_transfer_metadata(transfer_metadata: dict[str, Any] | None) -> dict[str, Any]:
    return _cache_transfer_metadata(transfer_metadata)


def build_normalized_audio_cache_transfer_metadata(
    transfer_metadata: dict[str, Any] | None,
    *,
    duration_seconds: float | None,
    normalization_skipped: bool,
) -> dict[str, Any]:
    return _cache_transfer_metadata(
        transfer_metadata,
        {
            "duration_seconds": duration_seconds,
            "normalization_skipped": normalization_skipped,
        },
    )


def build_composite_audio_cache_transfer_metadata(transfer_metadata: dict[str, Any] | None) -> dict[str, Any]:
    return _cache_transfer_metadata(transfer_metadata)


def build_background_cache_transfer_metadata(
    transfer_metadata: dict[str, Any] | None,
    *,
    cache_duration_seconds: float,
) -> dict[str, Any]:
    return _cache_transfer_metadata(
        transfer_metadata,
        {"cache_duration_seconds": cache_duration_seconds},
    )


def build_overlay_cache_transfer_metadata(transfer_metadata: dict[str, Any] | None) -> dict[str, Any]:
    return _cache_transfer_metadata(transfer_metadata)


def build_tts_segment_cache_transfer_metadata(
    transfer_metadata: dict[str, Any] | None,
    *,
    speaker: str,
    provider_used: Any,
) -> dict[str, Any]:
    return _cache_transfer_metadata(
        transfer_metadata,
        {
            "speaker": speaker,
            "provider_used": provider_used,
        },
    )


def build_tts_segment_cache_miss_metadata(*, speaker: str) -> dict[str, Any]:
    return {"speaker": speaker}


class RenderCacheReport:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def record(
        self,
        *,
        artifact_type: str,
        cache_key: str,
        status: str,
        cache_path: Path | None = None,
        job_path: Path | None = None,
        duration_seconds: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.events.append(
            {
                "artifact_type": artifact_type,
                "cache_key": cache_key,
                "cache_key_prefix": cache_key[:16],
                "status": status,
                "cache_path": str(cache_path) if cache_path else None,
                "job_path": str(job_path) if job_path else None,
                "duration_seconds": duration_seconds,
                "metadata": dict(metadata or {}),
            }
        )

    def timed(self):
        start = time.perf_counter()

        def elapsed() -> float:
            return max(time.perf_counter() - start, 0.0)

        return elapsed

    def summary(self) -> dict[str, Any]:
        by_type: dict[str, dict[str, int]] = {}
        transfer_methods: dict[str, int] = {}
        for event in self.events:
            artifact_type = str(event["artifact_type"])
            status = str(event["status"])
            bucket = by_type.setdefault(artifact_type, {})
            bucket[status] = bucket.get(status, 0) + 1
            method = (event.get("metadata") or {}).get("method")
            if method:
                transfer_methods[str(method)] = transfer_methods.get(str(method), 0) + 1
        hits = sum(1 for event in self.events if event["status"] in {"hit", "materialized_from_cache"})
        misses = sum(1 for event in self.events if event["status"] in {"miss", "regenerated"})
        return {
            "events": self.events,
            "by_type": by_type,
            "transfer_methods": transfer_methods,
            "hits": hits,
            "misses": misses,
            "total_events": len(self.events),
        }
