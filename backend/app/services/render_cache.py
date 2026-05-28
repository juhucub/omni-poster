from __future__ import annotations

import hashlib
import json
import os
import shutil
import time
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.domains.render.cache_report import RenderCacheReport


RENDER_CACHE_SCHEMA_VERSION = 2


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


def _file_stat_identity(path: Path) -> dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path.resolve()),
        "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "inode": getattr(stat, "st_ino", None),
        "device": getattr(stat, "st_dev", None),
    }


def render_cache_root() -> Path:
    root = Path(settings.MEDIA_DIR) / "render_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def cached_file_sha256(path: Path) -> tuple[str, dict[str, Any]]:
    """Return a content hash, avoiding full reads when stable file identity is cached."""
    identity = _file_stat_identity(path)
    fingerprint_dir = render_cache_root() / "file_fingerprints"
    fingerprint_dir.mkdir(parents=True, exist_ok=True)
    fingerprint_path = fingerprint_dir / f"{stable_hash({'path': identity['path']})}.json"
    metadata = {
        "identity": identity,
        "fingerprint_cache_hit": False,
        "fingerprint_path": str(fingerprint_path),
    }
    if fingerprint_path.exists():
        try:
            cached = json.loads(fingerprint_path.read_text(encoding="utf-8"))
            if cached.get("identity") == identity and cached.get("sha256"):
                metadata["fingerprint_cache_hit"] = True
                metadata["sha256"] = cached["sha256"]
                return str(cached["sha256"]), metadata
        except (OSError, json.JSONDecodeError):
            pass
    sha256 = file_sha256(path)
    payload = {"identity": identity, "sha256": sha256, "updated_at": time.time()}
    fingerprint_path.write_text(json.dumps(payload, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    metadata["sha256"] = sha256
    return sha256, metadata


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
        self._last_transfer: dict[str, Any] = {}

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

    @property
    def last_transfer(self) -> dict[str, Any]:
        return dict(self._last_transfer)

    def _link_or_copy(self, source: Path, destination: Path, *, operation: str) -> dict[str, Any]:
        transfer = {"operation": operation, "method": "none", "error": None}
        source_resolved = source.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)
        try:
            if destination.exists() and destination.resolve() == source_resolved:
                transfer["method"] = "same_path"
                return transfer
        except FileNotFoundError:
            pass
        try:
            if destination.exists() or destination.is_symlink():
                destination.unlink()
            os.link(source, destination)
            transfer["method"] = "hardlink"
            return transfer
        except OSError as exc:
            transfer["error"] = str(exc)
            shutil.copy2(source, destination)
            transfer["method"] = "copy"
            return transfer

    def materialize(self, cache_path: Path, destination: Path) -> bool:
        self._last_transfer = {"operation": "materialize", "method": "missing", "error": None}
        if not cache_path.exists():
            return False
        self._last_transfer = self._link_or_copy(cache_path, destination, operation="materialize")
        return True

    def store(self, source: Path, cache_path: Path, metadata: dict[str, Any] | None = None) -> None:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._last_transfer = self._link_or_copy(source, cache_path, operation="store")
        if metadata is not None:
            self.write_metadata(cache_path, {**metadata, "transfer": self.last_transfer})

