from __future__ import annotations

import hashlib
from pathlib import Path

from app.domains.voice.profiles.paths import voice_embedding_dir


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reference_audio_content_hash_from_paths(reference_paths: list[Path]) -> str:
    digests = sorted(sha256_path(path) for path in reference_paths)
    return hashlib.sha256("||".join(digests).encode("utf-8")).hexdigest()


def voice_embedding_artifact_path(profile_id: str) -> Path:
    return voice_embedding_dir() / f"{profile_id}.pth"


def voice_embedding_artifact_path_for_reference(profile_id: str, reference_audio_sha256: str) -> Path:
    return voice_embedding_dir() / f"{profile_id}_{reference_audio_sha256[:16]}.pth"
