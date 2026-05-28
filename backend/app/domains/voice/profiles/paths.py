from __future__ import annotations

import re
from pathlib import Path

from app.core.config import settings


def _runtime_lab_dir() -> Path:
    path = Path(settings.MEDIA_DIR) / "voice_lab"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_lab_preview_dir() -> Path:
    path = _runtime_lab_dir() / "previews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_reference_audio_dir() -> Path:
    path = _runtime_lab_dir() / "reference_audio"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_reference_audio_profile_dir(voice_profile_id: str) -> Path:
    # Profile ids can come from runtime presets, so sanitize before creating artifact directories.
    safe_id = re.sub(r"[^a-zA-Z0-9_.-]+", "_", voice_profile_id).strip("._") or "profile"
    path = voice_reference_audio_dir() / safe_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_reference_chunk_dir(voice_profile_id: str) -> Path:
    path = _runtime_lab_dir() / "reference_chunks" / voice_profile_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_cache_dir() -> Path:
    path = Path(settings.MEDIA_DIR) / "voice_cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_embedding_dir() -> Path:
    path = _runtime_lab_dir() / "embeddings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def voice_models_dir() -> Path:
    path = Path(settings.VOICE_MODELS_DIR)
    path.mkdir(parents=True, exist_ok=True)
    return path


def character_portrait_dir() -> Path:
    path = Path(settings.MEDIA_DIR) / "characters"
    path.mkdir(parents=True, exist_ok=True)
    return path
