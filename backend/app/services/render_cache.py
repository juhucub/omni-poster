from __future__ import annotations

import hashlib
import json
import shutil
import time
from pathlib import Path
from typing import Any

from app.core.config import settings


RENDER_CACHE_SCHEMA_VERSION = 1


def canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def stable_hash(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def render_cache_root() -> Path:
    root = Path(settings.MEDIA_DIR) / "render_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


class RenderCache:
    namespaces = {
        "tts_segments",
        "normalized_audio",
        "composite_audio",
        "backgrounds",
        "overlays",
        "final_videos",
    }

    def __init__(self) -> None:
        self.root = render_cache_root()
        for namespace in self.namespaces:
            (self.root / namespace).mkdir(parents=True, exist_ok=True)

    def path(self, namespace: str, cache_key: str, suffix: str) -> Path:
        if namespace not in self.namespaces:
            raise ValueError(f"Unknown render cache namespace: {namespace}")
        safe_suffix = suffix if suffix.startswith(".") else f".{suffix}"
        return self.root / namespace / f"{cache_key}{safe_suffix}"

    def metadata_path(self, artifact_path: Path) -> Path:
        return artifact_path.with_suffix(f"{artifact_path.suffix}.json")

    def read_metadata(self, artifact_path: Path) -> dict[str, Any]:
        path = self.metadata_path(artifact_path)
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    def write_metadata(self, artifact_path: Path, payload: dict[str, Any]) -> None:
        path = self.metadata_path(artifact_path)
        path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")

    def materialize(self, cache_path: Path, destination: Path) -> bool:
        if not cache_path.exists():
            return False
        destination.parent.mkdir(parents=True, exist_ok=True)
        if cache_path.resolve() != destination.resolve():
            shutil.copy2(cache_path, destination)
        return True

    def store(self, source: Path, cache_path: Path, metadata: dict[str, Any] | None = None) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        if source.resolve() != cache_path.resolve():
            shutil.copy2(source, cache_path)
        if metadata is not None:
            self.write_metadata(cache_path, metadata)


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
        for event in self.events:
            artifact_type = str(event["artifact_type"])
            status = str(event["status"])
            bucket = by_type.setdefault(artifact_type, {})
            bucket[status] = bucket.get(status, 0) + 1
        hits = sum(1 for event in self.events if event["status"] in {"hit", "materialized_from_cache"})
        misses = sum(1 for event in self.events if event["status"] in {"miss", "regenerated"})
        return {
            "events": self.events,
            "by_type": by_type,
            "hits": hits,
            "misses": misses,
            "total_events": len(self.events),
        }
