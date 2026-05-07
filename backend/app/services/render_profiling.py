from __future__ import annotations

import json
import os
import platform
import socket
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

from app.core.config import settings


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    return str(value)


def current_rss_bytes() -> int | None:
    try:
        import psutil  # type: ignore

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        pass

    statm = Path("/proc/self/statm")
    try:
        pages = int(statm.read_text(encoding="utf-8").split()[1])
        return pages * int(os.sysconf("SC_PAGE_SIZE"))
    except Exception:
        pass

    try:
        import resource

        usage = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if platform.system().lower() == "darwin":
            return int(usage)
        return int(usage) * 1024
    except Exception:
        return None


def _detect_docker() -> bool:
    if Path("/.dockerenv").exists():
        return True
    try:
        cgroup = Path("/proc/1/cgroup").read_text(encoding="utf-8")
    except Exception:
        return False
    lowered = cgroup.lower()
    return "docker" in lowered or "containerd" in lowered or "kubepods" in lowered


class RenderProfiler:
    def __init__(
        self,
        *,
        enabled: bool = True,
        job_id: int | None = None,
        project_id: int | None = None,
        output_kind: str | None = None,
        rss_reader: Callable[[], int | None] | None = None,
    ) -> None:
        self.enabled = enabled
        self.job_id = job_id
        self.project_id = project_id
        self.output_kind = output_kind
        self._rss_reader = rss_reader or current_rss_bytes
        self._started = time.perf_counter()
        self._created_at = datetime.now(timezone.utc)
        self._stages: list[dict[str, Any]] = []
        self._context: dict[str, Any] = {}
        self._peak_rss_bytes: int | None = None
        self._read_rss()

    def _read_rss(self) -> int | None:
        if not self.enabled:
            return None
        rss = self._rss_reader()
        if rss is not None:
            self._peak_rss_bytes = max(self._peak_rss_bytes or rss, rss)
        return rss

    def add_context(self, **metadata: Any) -> None:
        if not self.enabled:
            return
        self._context.update(_json_safe(metadata))

    @contextmanager
    def stage(self, name: str, **metadata: Any) -> Iterator[None]:
        if not self.enabled:
            yield
            return

        start = time.perf_counter()
        rss_before = self._read_rss()
        stage_peak = rss_before
        try:
            yield
        finally:
            rss_after = self._read_rss()
            if rss_after is not None:
                stage_peak = max(stage_peak or rss_after, rss_after)
            self._stages.append(
                {
                    "name": name,
                    "duration_seconds": round(time.perf_counter() - start, 6),
                    "rss_before_bytes": rss_before,
                    "rss_after_bytes": rss_after,
                    "observed_peak_rss_bytes": stage_peak,
                    "metadata": _json_safe(metadata),
                }
            )

    def sample_memory(self) -> int | None:
        return self._read_rss()

    def summary(self, *, top_n: int = 5) -> dict[str, Any]:
        if not self.enabled:
            return {"enabled": False}
        total = max(time.perf_counter() - self._started, 0.0)
        top_stages = sorted(self._stages, key=lambda item: item["duration_seconds"], reverse=True)[:top_n]
        return {
            "enabled": True,
            "total_duration_seconds": round(total, 6),
            "stage_count": len(self._stages),
            "peak_observed_rss_bytes": self._peak_rss_bytes,
            "top_stages": [
                {
                    "name": item["name"],
                    "duration_seconds": item["duration_seconds"],
                    "observed_peak_rss_bytes": item.get("observed_peak_rss_bytes"),
                }
                for item in top_stages
            ],
        }

    def to_dict(self) -> dict[str, Any]:
        if not self.enabled:
            return {"schema_version": 1, "enabled": False}
        payload = {
            "schema_version": 1,
            "enabled": True,
            "job_id": self.job_id,
            "project_id": self.project_id,
            "output_kind": self.output_kind,
            "created_at": self._created_at.isoformat(),
            "total_duration_seconds": round(time.perf_counter() - self._started, 6),
            "peak_observed_rss_bytes": self._peak_rss_bytes,
            "runtime": {
                "pid": os.getpid(),
                "hostname": socket.gethostname(),
                "platform": platform.platform(),
                "python": platform.python_version(),
                "cpu_count": os.cpu_count(),
                "environment": settings.ENVIRONMENT,
                "in_docker": _detect_docker(),
                "xtts_device": settings.XTTS_DEVICE,
                "openvoice_device": settings.OPENVOICE_DEVICE,
            },
            "context": _json_safe(self._context),
            "stages": list(self._stages),
            "summary": self.summary(),
        }
        return _json_safe(payload)

    def write_json(self, path: Path) -> Path | None:
        if not self.enabled:
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return path
