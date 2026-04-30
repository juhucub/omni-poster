from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import uuid
import wave
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from fastapi import HTTPException, UploadFile, status
from sqlalchemy.orm import Session, joinedload

from app.core.config import settings
from app.db import SessionLocal
from app.models import CharacterPreset, Project, ProjectSpeakerBinding, VoiceProfile, VoiceReferenceAudio

logger = logging.getLogger(__name__)

DEFAULT_SAMPLE_TEXT = "Hey, welcome back. Today we're testing a new character voice."
REFERENCE_AUDIO_SAMPLE_RATE = 16000
REFERENCE_AUDIO_MIN_DURATION_MS = 1200
REFERENCE_AUDIO_SILENCE_FILTER = (
    "silenceremove="
    "start_periods=1:start_silence=0.25:start_threshold=-45dB"
)
REFERENCE_AUDIO_NORMALIZATION_FILTER = f"{REFERENCE_AUDIO_SILENCE_FILTER},loudnorm=I=-18:TP=-3:LRA=11"


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


def _bundled_presets_path() -> Path:
    return Path(settings.BUNDLED_MEDIA_DIR) / "character_presets.json"


def _runtime_presets_path() -> Path:
    return _runtime_lab_dir() / "character_presets.json"


@contextmanager
def _session_scope(db: Session | None = None) -> Iterator[tuple[Session, bool]]:
    if db is not None:
        yield db, False
        return
    session = SessionLocal()
    try:
        yield session, True
    finally:
        session.close()


def _load_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        logger.warning("Voice preset bootstrap file is invalid JSON: %s", path)
        return []
    if not isinstance(payload, list):
        logger.warning("Voice preset bootstrap file is not a list: %s", path)
        return []
    return [item for item in payload if isinstance(item, dict)]


def _normalize_controls(payload: dict[str, Any]) -> dict[str, Any]:
    controls = dict(payload.get("controls") or {})
    rate = payload.get("rate")
    pitch = payload.get("pitch")
    word_gap = payload.get("word_gap")
    amplitude = payload.get("amplitude")
    if controls.get("speaking_rate") is None and rate is not None:
        controls["speaking_rate"] = float(rate) / float(settings.TTS_ESPEAK_RATE or 1)
    if controls.get("pitch") is None and pitch is not None:
        controls["pitch"] = float(pitch)
    if controls.get("pause_length") is None and word_gap is not None:
        controls["pause_length"] = float(word_gap)
    if controls.get("energy") is None and amplitude is not None:
        controls["energy"] = float(amplitude)
    return {key: value for key, value in controls.items() if value is not None}


def _fallback_voice_settings(payload: dict[str, Any]) -> dict[str, Any]:
    settings_payload = dict(payload.get("fallback_voice_settings") or {})
    legacy = {
        "voice": payload.get("voice"),
        "rate": payload.get("rate"),
        "pitch": payload.get("pitch"),
        "word_gap": payload.get("word_gap"),
        "amplitude": payload.get("amplitude"),
    }
    for key, value in legacy.items():
        if settings_payload.get(key) is None and value is not None:
            settings_payload[key] = value
    return {key: value for key, value in settings_payload.items() if value is not None}


def _voice_profile_id(payload: dict[str, Any], preset_id: str | None = None) -> str:
    candidate = str(payload.get("voice_profile_id") or "").strip()
    if candidate:
        return candidate
    if preset_id:
        return f"vp_{preset_id}"
    return f"vp_{uuid.uuid4().hex[:16]}"


def _default_profile_payload(payload: dict[str, Any], preset_id: str | None = None) -> dict[str, Any]:
    display_name = str(payload.get("display_name") or "Speaker").strip()
    provider = str(payload.get("tts_provider") or payload.get("provider") or "espeak").strip().lower()
    voice_profile_id = _voice_profile_id(payload, preset_id)
    controls = _normalize_controls(payload)
    return {
        "id": voice_profile_id,
        "display_name": display_name,
        "provider": provider,
        "model_id": payload.get("model_id") or settings.OPENVOICE_DEFAULT_MODEL_ID if provider == "openvoice" else payload.get("model_id"),
        "language": payload.get("language") or "en",
        "embedding_path": payload.get("embedding_path"),
        "fallback_provider": payload.get("fallback_provider") or "espeak",
        "fallback_voice_settings_json": _fallback_voice_settings(payload),
        "style_json": dict(payload.get("style") or {}),
        "controls_json": controls,
        "provider_metadata_json": dict(payload.get("provider_metadata") or {}),
        "espeak_voice": payload.get("voice") or settings.TTS_ESPEAK_VOICE_SLOT_1,
        "espeak_rate": int(payload.get("rate") if payload.get("rate") is not None else settings.TTS_ESPEAK_RATE),
        "espeak_pitch": int(payload.get("pitch") if payload.get("pitch") is not None else settings.TTS_ESPEAK_PITCH),
        "espeak_word_gap": int(payload.get("word_gap") if payload.get("word_gap") is not None else settings.TTS_ESPEAK_WORD_GAP),
        "espeak_amplitude": int(payload.get("amplitude") if payload.get("amplitude") is not None else settings.TTS_ESPEAK_AMPLITUDE),
    }


def _default_preset_payload(payload: dict[str, Any], source: str, created_by_user_id: int | None = None) -> dict[str, Any]:
    preset_id = str(payload.get("id") or uuid.uuid4().hex[:12]).strip()
    profile_payload = _default_profile_payload(payload, preset_id)
    speaker_names = payload.get("speaker_names") or [payload.get("display_name") or "Speaker"]
    return {
        "id": preset_id,
        "display_name": payload.get("display_name") or "Speaker",
        "speaker_names": list(speaker_names),
        "portrait_filename": payload.get("portrait_filename"),
        "voice_profile": profile_payload,
        "sample_text": payload.get("sample_text") or DEFAULT_SAMPLE_TEXT,
        "notes": payload.get("notes") or "",
        "source": source,
        "is_seeded": source == "bundled",
        "created_by_user_id": created_by_user_id,
    }


def _serialize_reference_audio(item: VoiceReferenceAudio) -> dict[str, Any]:
    return {
        "id": item.id,
        "voice_profile_id": item.voice_profile_id,
        "storage_path": item.storage_path,
        "mime_type": item.mime_type,
        "duration_ms": item.duration_ms,
        "sha256": item.sha256,
        "authorization_confirmed": item.authorization_confirmed,
        "authorization_note": item.authorization_note,
        "created_at": item.created_at,
    }


def _reference_audio_mode(reference_count: int) -> str:
    if reference_count > 1:
        return "average_all_clips"
    if reference_count == 1:
        return "single_clip"
    return "none"


def _active_processed_reference_payload(metadata: dict[str, Any], reference_audios: list[VoiceReferenceAudio]) -> dict[str, Any]:
    processed_by_id = dict(metadata.get("processed_reference_audio") or {})
    chunks: list[dict[str, Any]] = []
    paths: list[str] = []
    processed_reference_ids: set[int] = set()
    for item in reference_audios:
        payload = processed_by_id.get(str(item.id))
        if not isinstance(payload, dict):
            continue
        for chunk in payload.get("chunks") or []:
            if not isinstance(chunk, dict) or not chunk.get("path"):
                continue
            path = Path(str(chunk["path"]))
            if not path.exists():
                continue
            chunk_payload = dict(chunk)
            chunk_payload["reference_audio_id"] = item.id
            chunks.append(chunk_payload)
            paths.append(str(path))
            processed_reference_ids.add(item.id)
    return {
        "processed_reference_paths": paths,
        "processed_reference_chunks": chunks,
        "processed_reference_audio_ids": sorted(processed_reference_ids),
        "selected_chunk_durations": [float(chunk.get("duration_seconds") or 0) for chunk in chunks],
        "processed_reference_duration_seconds": round(sum(float(chunk.get("duration_seconds") or 0) for chunk in chunks), 3),
    }


def _voice_profile_provider_metadata(profile: VoiceProfile) -> dict[str, Any]:
    metadata = dict(profile.provider_metadata_json or {})
    reference_audios = list(profile.reference_audios or [])
    active_reference_ids = [item.id for item in reference_audios]
    reference_paths = [Path(item.storage_path) for item in reference_audios if item.storage_path]
    processed_payload = _active_processed_reference_payload(metadata, reference_audios)
    processed_paths = [Path(path) for path in processed_payload["processed_reference_paths"]]
    processed_ids = set(processed_payload["processed_reference_audio_ids"])
    unprocessed_reference_paths = [Path(item.storage_path) for item in reference_audios if item.storage_path and item.id not in processed_ids]
    hash_paths = processed_paths + unprocessed_reference_paths
    reference_files_exist = bool(hash_paths) and all(path.exists() for path in hash_paths)
    active_reference_hash = reference_audio_content_hash_from_paths(hash_paths) if reference_files_exist else None
    stored_reference_hash = str(metadata.get("reference_audio_sha256") or "")
    expected_artifact_path = voice_embedding_artifact_path_for_reference(profile.id, active_reference_hash) if active_reference_hash else None
    explicit_embedding_path = Path(profile.embedding_path) if profile.embedding_path else None
    embedding_path_candidates = [path for path in [explicit_embedding_path, expected_artifact_path] if path is not None]
    embedding_artifact_path = None
    for candidate in embedding_path_candidates:
        if not candidate.exists() or not active_reference_hash:
            continue
        filename_matches_reference = active_reference_hash[:16] in candidate.stem
        metadata_matches_reference = stored_reference_hash == active_reference_hash
        if filename_matches_reference or metadata_matches_reference:
            embedding_artifact_path = str(candidate)
            break
    embedding_ready = bool(embedding_artifact_path)
    stored_status = str(metadata.get("embedding_status") or "")
    if embedding_ready:
        embedding_status = "ready"
    elif stored_status == "failed":
        embedding_status = "failed"
    elif not reference_audios:
        embedding_status = "pending_reference_audio"
    else:
        embedding_status = stored_status if stored_status in {"building", "not_prepared"} else "not_prepared"
    performance_controls_supported = ["speaking_rate"] if profile.provider == "openvoice" else ["speaking_rate", "pitch", "energy", "pause_length"]
    metadata.update(
        {
            "voice_identity_provider": profile.provider,
            "embedding_status": embedding_status,
            "embedding_ready": embedding_ready,
            "embedding_artifact_path": embedding_artifact_path,
            "active_reference_count": len(reference_audios),
            "active_reference_audio_ids": active_reference_ids,
            "reference_audio_sha256": active_reference_hash,
            "reference_audio_mode": _reference_audio_mode(len(reference_audios)),
            "performance_controls_supported": performance_controls_supported,
            **processed_payload,
        }
    )
    if profile.provider == "openvoice":
        metadata["unsupported_controls"] = [
            "accent",
            "emotion",
            "energy",
            "expressiveness",
            "intonation",
            "pause_length",
            "pitch",
            "rhythm",
        ]
    return metadata


def serialize_voice_profile(profile: VoiceProfile) -> dict[str, Any]:
    provider_metadata = _voice_profile_provider_metadata(profile)
    return {
        "id": profile.id,
        "display_name": profile.display_name,
        "provider": profile.provider,
        "model_id": profile.model_id,
        "language": profile.language,
        "embedding_path": provider_metadata.get("embedding_artifact_path"),
        "fallback_provider": profile.fallback_provider,
        "fallback_voice_settings": dict(profile.fallback_voice_settings_json or {}),
        "style": dict(profile.style_json or {}),
        "controls": dict(profile.controls_json or {}),
        "provider_metadata": provider_metadata,
        "voice": profile.espeak_voice,
        "espeak_rate": profile.espeak_rate,
        "espeak_pitch": profile.espeak_pitch,
        "espeak_word_gap": profile.espeak_word_gap,
        "espeak_amplitude": profile.espeak_amplitude,
        "reference_audio_count": len(profile.reference_audios),
        "reference_audios": [_serialize_reference_audio(item) for item in profile.reference_audios],
        "created_at": profile.created_at,
        "updated_at": profile.updated_at,
    }


def runtime_voice_profile_payload(profile: VoiceProfile, display_name: str) -> dict[str, Any]:
    provider_metadata = _voice_profile_provider_metadata(profile)
    return {
        "id": profile.id,
        "display_name": display_name,
        "provider": profile.provider,
        "fallback_provider": profile.fallback_provider,
        "voice": profile.espeak_voice,
        "espeak_voice": profile.espeak_voice,
        "espeak_rate": profile.espeak_rate,
        "espeak_pitch": profile.espeak_pitch,
        "espeak_word_gap": profile.espeak_word_gap,
        "espeak_amplitude": profile.espeak_amplitude,
        "controls": dict(profile.controls_json or {}),
        "style": dict(profile.style_json or {}),
        "fallback_voice_settings": dict(profile.fallback_voice_settings_json or {}),
        "reference_audios": [
            {
                "id": item.id,
                "storage_path": item.storage_path,
                "sha256": item.sha256,
                "mime_type": item.mime_type,
            }
            for item in profile.reference_audios
        ],
        "language": profile.language,
        "model_id": profile.model_id,
        "embedding_path": provider_metadata.get("embedding_artifact_path"),
        "provider_metadata": provider_metadata,
    }


def serialize_character_preset(preset: CharacterPreset) -> dict[str, Any]:
    profile = preset.voice_profile
    controls = dict(profile.controls_json or {})
    fallback_voice_settings = dict(profile.fallback_voice_settings_json or {})
    return {
        "id": preset.id,
        "display_name": preset.display_name,
        "speaker_names": list(preset.speaker_names_json or []),
        "portrait_filename": preset.portrait_filename,
        "voice_profile_id": profile.id,
        "tts_provider": profile.provider,
        "provider_preference": "auto",
        "fallback_provider": profile.fallback_provider,
        "voice": profile.espeak_voice or settings.TTS_ESPEAK_VOICE_SLOT_1,
        "rate": int(profile.espeak_rate or settings.TTS_ESPEAK_RATE),
        "pitch": int(profile.espeak_pitch or settings.TTS_ESPEAK_PITCH),
        "word_gap": int(profile.espeak_word_gap if profile.espeak_word_gap is not None else settings.TTS_ESPEAK_WORD_GAP),
        "amplitude": int(profile.espeak_amplitude or settings.TTS_ESPEAK_AMPLITUDE),
        "language": profile.language,
        "model_id": profile.model_id,
        "controls": controls,
        "fallback_voice_settings": fallback_voice_settings,
        "reference_audio_count": len(profile.reference_audios),
        "notes": preset.notes or "",
        "sample_text": preset.sample_text or DEFAULT_SAMPLE_TEXT,
        "source": preset.source,
        "is_seeded": preset.is_seeded,
    }


def _can_mutate_preset(preset: CharacterPreset, current_user_id: int) -> bool:
    return preset.is_seeded or preset.created_by_user_id in {None, current_user_id}


def _can_mutate_voice_profile(profile: VoiceProfile, current_user_id: int) -> bool:
    if profile.created_by_user_id in {None, current_user_id}:
        return True
    return any(_can_mutate_preset(preset, current_user_id) for preset in profile.presets)


def ensure_voice_profile_editable(profile: VoiceProfile, current_user_id: int) -> None:
    if not _can_mutate_voice_profile(profile, current_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Voice profile is not editable by this user")


def voice_embedding_artifact_path(profile_id: str) -> Path:
    return voice_embedding_dir() / f"{profile_id}.pth"


def voice_embedding_artifact_path_for_reference(profile_id: str, reference_audio_sha256: str) -> Path:
    return voice_embedding_dir() / f"{profile_id}_{reference_audio_sha256[:16]}.pth"


def reference_audio_content_hash_from_paths(reference_paths: list[Path]) -> str:
    digests = sorted(_sha256_path(path) for path in reference_paths)
    return hashlib.sha256("||".join(digests).encode("utf-8")).hexdigest()


def update_voice_profile_preparation_metadata(
    profile: VoiceProfile,
    *,
    embedding_path: str | None,
    provider_metadata: dict[str, Any] | None,
    db: Session,
) -> VoiceProfile:
    if embedding_path:
        profile.embedding_path = embedding_path
    next_metadata = dict(profile.provider_metadata_json or {})
    next_metadata.update(provider_metadata or {})
    profile.provider_metadata_json = next_metadata
    db.commit()
    db.refresh(profile)
    return profile


def invalidate_voice_profile_embedding(profile: VoiceProfile, db: Session) -> None:
    paths_to_remove: set[Path] = set()
    if profile.embedding_path:
        paths_to_remove.add(Path(profile.embedding_path))
    paths_to_remove.add(voice_embedding_artifact_path(profile.id))
    paths_to_remove.update(path for path in voice_embedding_dir().glob("*.pth") if path.name.startswith(f"{profile.id}_"))
    for path in paths_to_remove:
        path.unlink(missing_ok=True)
    shutil.rmtree(voice_reference_chunk_dir(profile.id), ignore_errors=True)
    profile.embedding_path = None
    next_metadata = dict(profile.provider_metadata_json or {})
    next_metadata.update(
        {
            "embedding_status": "not_prepared",
            "embedding_ready": False,
            "embedding_artifact_path": None,
            "reference_audio_sha256": None,
            "target_embedding_hash": None,
        }
    )
    profile.provider_metadata_json = next_metadata
    db.flush()


def _ffmpeg_binary() -> str | None:
    return shutil.which("ffmpeg")


def _normalize_reference_audio_upload(content: bytes, filename: str) -> tuple[Path, int]:
    ffmpeg_binary = _ffmpeg_binary()
    if not ffmpeg_binary:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reference audio normalization is unavailable because ffmpeg is not installed.",
        )

    source_suffix = Path(filename).suffix or ".bin"
    source_path = voice_reference_audio_dir() / f"{uuid.uuid4().hex}_raw{source_suffix}"
    output_path = voice_reference_audio_dir() / f"{uuid.uuid4().hex}.wav"
    source_path.write_bytes(content)
    source_size_bytes = source_path.stat().st_size
    source_sha256 = _sha256_path(source_path)
    source_duration_ms = _audio_duration_ms(source_path)
    command = [
        ffmpeg_binary,
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-vn",
        "-map_metadata",
        "-1",
        "-ac",
        "1",
        "-ar",
        str(REFERENCE_AUDIO_SAMPLE_RATE),
        "-sample_fmt",
        "s16",
        "-af",
        REFERENCE_AUDIO_NORMALIZATION_FILTER,
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        output_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reference audio could not be decoded or normalized: {exc.stderr.strip() or 'unknown ffmpeg error'}",
        ) from exc
    finally:
        source_path.unlink(missing_ok=True)

    duration_ms = _audio_duration_ms(output_path)
    if duration_ms is None:
        output_path.unlink(missing_ok=True)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reference audio could not be decoded after normalization")
    if duration_ms < REFERENCE_AUDIO_MIN_DURATION_MS:
        output_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Reference audio must contain at least {REFERENCE_AUDIO_MIN_DURATION_MS / 1000:.1f} seconds of usable speech after trimming silence.",
        )
    logger.info(
        "voice.reference_audio.normalized metadata=%s",
        {
            "reference_audio_path": str(source_path),
            "normalized_reference_path": str(output_path),
            "reference_audio_sha256": source_sha256,
            "normalized_reference_sha256": _sha256_path(output_path),
            "duration_before_seconds": round(source_duration_ms / 1000, 3) if source_duration_ms is not None else None,
            "normalized_audio_duration_seconds": round(duration_ms / 1000, 3),
            "input_file_size_bytes": source_size_bytes,
            "normalized_file_size_bytes": output_path.stat().st_size,
            "ffmpeg_filter": REFERENCE_AUDIO_NORMALIZATION_FILTER,
        },
    )
    return output_path, duration_ms


def _parse_silencedetect_windows(stderr: str, duration_seconds: float) -> list[dict[str, float]]:
    silence_events: list[tuple[str, float]] = []
    for line in stderr.splitlines():
        start_match = re.search(r"silence_start:\s*([0-9.]+)", line)
        if start_match:
            silence_events.append(("start", float(start_match.group(1))))
            continue
        end_match = re.search(r"silence_end:\s*([0-9.]+)", line)
        if end_match:
            silence_events.append(("end", float(end_match.group(1))))

    windows: list[dict[str, float]] = []
    speech_start = 0.0
    in_silence = False
    for event, timestamp in silence_events:
        timestamp = max(0.0, min(float(timestamp), duration_seconds))
        if event == "start" and not in_silence:
            if timestamp > speech_start:
                windows.append({"start_seconds": speech_start, "end_seconds": timestamp, "duration_seconds": timestamp - speech_start})
            in_silence = True
        elif event == "end" and in_silence:
            speech_start = timestamp
            in_silence = False
    if not in_silence and speech_start < duration_seconds:
        windows.append({"start_seconds": speech_start, "end_seconds": duration_seconds, "duration_seconds": duration_seconds - speech_start})
    if not windows and duration_seconds > 0:
        windows.append({"start_seconds": 0.0, "end_seconds": duration_seconds, "duration_seconds": duration_seconds})
    return windows


def _detect_reference_speech_windows(path: Path, duration_ms: int) -> list[dict[str, float]]:
    ffmpeg_binary = _ffmpeg_binary()
    duration_seconds = max(duration_ms / 1000, 0.0)
    if not ffmpeg_binary or duration_seconds <= 0:
        return []
    command = [
        ffmpeg_binary,
        "-hide_banner",
        "-nostats",
        "-i",
        str(path),
        "-af",
        f"silencedetect=n={settings.VOICE_LAB_REFERENCE_SILENCE_THRESHOLD_DB}:d={settings.VOICE_LAB_REFERENCE_SILENCE_MIN_SECONDS}",
        "-f",
        "null",
        "-",
    ]
    try:
        result = subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        logger.warning(
            "voice.reference_audio.silencedetect_failed metadata=%s",
            {"normalized_reference_path": str(path), "error": exc.stderr.strip() if exc.stderr else str(exc)},
        )
        return [{"start_seconds": 0.0, "end_seconds": duration_seconds, "duration_seconds": duration_seconds}]
    return _parse_silencedetect_windows(getattr(result, "stderr", "") or "", duration_seconds)


def _select_reference_chunks(speech_windows: list[dict[str, float]], duration_ms: int) -> list[dict[str, float]]:
    duration_seconds = max(duration_ms / 1000, 0.0)
    max_total = max(float(settings.VOICE_LAB_MAX_REFERENCE_EMBEDDING_SECONDS), 1.0)
    max_chunk = max(float(settings.VOICE_LAB_REFERENCE_CHUNK_SECONDS), 1.0)
    min_chunk = max(float(settings.VOICE_LAB_MIN_REFERENCE_CHUNK_SECONDS), 0.25)
    candidates: list[dict[str, float]] = []
    for window in speech_windows or [{"start_seconds": 0.0, "end_seconds": duration_seconds, "duration_seconds": duration_seconds}]:
        start = float(window["start_seconds"])
        end = float(window["end_seconds"])
        cursor = start
        while cursor < end:
            chunk_end = min(cursor + max_chunk, end)
            chunk_duration = chunk_end - cursor
            if chunk_duration >= min_chunk:
                candidates.append(
                    {
                        "start_seconds": round(cursor, 3),
                        "end_seconds": round(chunk_end, 3),
                        "duration_seconds": round(chunk_duration, 3),
                    }
                )
            cursor = chunk_end
    if not candidates and duration_seconds > 0:
        chunk_duration = min(duration_seconds, max_total, max_chunk)
        candidates.append({"start_seconds": 0.0, "end_seconds": round(chunk_duration, 3), "duration_seconds": round(chunk_duration, 3)})

    selected: list[dict[str, float]] = []
    total = 0.0
    for candidate in sorted(candidates, key=lambda item: (-item["duration_seconds"], item["start_seconds"])):
        if total >= max_total:
            break
        remaining = max_total - total
        if candidate["duration_seconds"] > remaining:
            if remaining < min_chunk:
                continue
            candidate = {
                "start_seconds": candidate["start_seconds"],
                "end_seconds": round(candidate["start_seconds"] + remaining, 3),
                "duration_seconds": round(remaining, 3),
            }
        selected.append(candidate)
        total += candidate["duration_seconds"]
    return sorted(selected, key=lambda item: item["start_seconds"])


def _extract_reference_chunks(path: Path, voice_profile_id: str, reference_audio_id: int, selected_chunks: list[dict[str, float]]) -> list[dict[str, Any]]:
    ffmpeg_binary = _ffmpeg_binary()
    if not ffmpeg_binary:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Reference audio chunking is unavailable because ffmpeg is not installed.",
        )
    chunk_dir = voice_reference_chunk_dir(voice_profile_id)
    chunks: list[dict[str, Any]] = []
    for index, chunk in enumerate(selected_chunks):
        output_path = chunk_dir / f"ref_{reference_audio_id}_{index:03d}_{uuid.uuid4().hex[:8]}.wav"
        command = [
            ffmpeg_binary,
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{chunk['start_seconds']:.3f}",
            "-t",
            f"{chunk['duration_seconds']:.3f}",
            "-i",
            str(path),
            "-vn",
            "-map_metadata",
            "-1",
            "-ac",
            "1",
            "-ar",
            str(REFERENCE_AUDIO_SAMPLE_RATE),
            "-sample_fmt",
            "s16",
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            output_path.unlink(missing_ok=True)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Reference audio chunk could not be extracted: {exc.stderr.strip() or 'unknown ffmpeg error'}",
            ) from exc
        duration_ms = _audio_duration_ms(output_path)
        if not duration_ms:
            output_path.unlink(missing_ok=True)
            continue
        chunks.append(
            {
                "path": str(output_path),
                "sha256": _sha256_path(output_path),
                "start_seconds": chunk["start_seconds"],
                "end_seconds": chunk["end_seconds"],
                "duration_seconds": round(duration_ms / 1000, 3),
                "file_size_bytes": output_path.stat().st_size,
            }
        )
    return chunks


def _process_reference_audio_for_embedding(path: Path, *, voice_profile_id: str, reference_audio_id: int, duration_ms: int) -> dict[str, Any]:
    speech_windows = _detect_reference_speech_windows(path, duration_ms)
    selected_windows = _select_reference_chunks(speech_windows, duration_ms)
    chunks = _extract_reference_chunks(path, voice_profile_id, reference_audio_id, selected_windows)
    if not chunks:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Reference audio did not contain usable speech chunks after processing.")
    payload = {
        "status": "ready",
        "normalized_reference_path": str(path),
        "normalized_reference_sha256": _sha256_path(path),
        "normalized_duration_seconds": round(duration_ms / 1000, 3),
        "speech_windows": speech_windows,
        "chunks": chunks,
        "selected_duration_seconds": round(sum(float(chunk["duration_seconds"]) for chunk in chunks), 3),
        "max_reference_embedding_seconds": float(settings.VOICE_LAB_MAX_REFERENCE_EMBEDDING_SECONDS),
    }
    logger.info(
        "voice.reference_audio.chunks_selected metadata=%s",
        {
            "voice_profile_id": voice_profile_id,
            "reference_audio_id": reference_audio_id,
            "normalized_reference_path": str(path),
            "normalized_reference_sha256": payload["normalized_reference_sha256"],
            "selected_duration_seconds": payload["selected_duration_seconds"],
            "chunks": [
                {
                    "path": chunk["path"],
                    "start_seconds": chunk["start_seconds"],
                    "end_seconds": chunk["end_seconds"],
                    "duration_seconds": chunk["duration_seconds"],
                }
                for chunk in chunks
            ],
        },
    )
    return payload


def ensure_seeded_voice_presets(db: Session) -> None:
    has_presets = db.query(CharacterPreset.id).limit(1).first()
    if has_presets:
        return

    loaded_count = 0
    seeded_ids: set[str] = set()
    for source, path in (("bundled", _bundled_presets_path()), ("runtime", _runtime_presets_path())):
        for payload in _load_json_list(path):
            normalized = _default_preset_payload(payload, source)
            if normalized["id"] in seeded_ids:
                continue
            profile_payload = normalized["voice_profile"]
            profile = VoiceProfile(
                id=profile_payload["id"],
                display_name=profile_payload["display_name"],
                provider=profile_payload["provider"],
                model_id=profile_payload["model_id"],
                language=profile_payload["language"],
                embedding_path=profile_payload["embedding_path"],
                fallback_provider=profile_payload["fallback_provider"],
                fallback_voice_settings_json=profile_payload["fallback_voice_settings_json"],
                style_json=profile_payload["style_json"],
                controls_json=profile_payload["controls_json"],
                provider_metadata_json=profile_payload["provider_metadata_json"],
                espeak_voice=profile_payload["espeak_voice"],
                espeak_rate=profile_payload["espeak_rate"],
                espeak_pitch=profile_payload["espeak_pitch"],
                espeak_word_gap=profile_payload["espeak_word_gap"],
                espeak_amplitude=profile_payload["espeak_amplitude"],
                created_by_user_id=None,
            )
            preset = CharacterPreset(
                id=normalized["id"],
                display_name=normalized["display_name"],
                speaker_names_json=normalized["speaker_names"],
                portrait_filename=normalized["portrait_filename"],
                voice_profile_id=profile.id,
                sample_text=normalized["sample_text"],
                notes=normalized["notes"],
                source=normalized["source"],
                is_seeded=normalized["is_seeded"],
                created_by_user_id=normalized["created_by_user_id"],
            )
            db.add(profile)
            db.add(preset)
            loaded_count += 1
            seeded_ids.add(normalized["id"])

    if loaded_count:
        db.commit()
        logger.info("Seeded %s voice presets into the database", loaded_count)


def list_voice_profiles(db: Session | None = None) -> list[dict[str, Any]]:
    with _session_scope(db) as (session, _):
        ensure_seeded_voice_presets(session)
        profiles = (
            session.query(VoiceProfile)
            .options(joinedload(VoiceProfile.reference_audios), joinedload(VoiceProfile.presets))
            .order_by(VoiceProfile.display_name.asc(), VoiceProfile.id.asc())
            .all()
        )
        return [serialize_voice_profile(profile) for profile in profiles]


def get_voice_profile(profile_id: str, db: Session | None = None) -> dict[str, Any] | None:
    with _session_scope(db) as (session, _):
        ensure_seeded_voice_presets(session)
        profile = (
            session.query(VoiceProfile)
            .options(joinedload(VoiceProfile.reference_audios), joinedload(VoiceProfile.presets))
            .filter(VoiceProfile.id == profile_id)
            .one_or_none()
        )
        return serialize_voice_profile(profile) if profile else None


def get_voice_profile_model(profile_id: str, db: Session | None) -> VoiceProfile | None:
    with _session_scope(db) as (session, _):
        ensure_seeded_voice_presets(session)
        return (
            session.query(VoiceProfile)
            .options(joinedload(VoiceProfile.reference_audios), joinedload(VoiceProfile.presets))
            .filter(VoiceProfile.id == profile_id)
            .one_or_none()
        )


def upsert_voice_profile(payload: dict[str, Any], current_user_id: int, db: Session, profile_id: str | None = None) -> dict[str, Any]:
    ensure_seeded_voice_presets(db)
    normalized = _default_profile_payload(payload, preset_id=profile_id)
    target_id = profile_id or normalized["id"]
    profile = get_voice_profile_model(target_id, db)
    if profile and profile.created_by_user_id not in {None, current_user_id}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Voice profile is not editable by this user")

    if not profile:
        profile = VoiceProfile(id=target_id, created_by_user_id=current_user_id)
        db.add(profile)

    profile.display_name = payload.get("display_name") or normalized["display_name"]
    profile.provider = str(payload.get("provider") or normalized["provider"]).lower()
    profile.model_id = payload.get("model_id") or normalized["model_id"]
    profile.language = payload.get("language") or normalized["language"]
    if "embedding_path" in payload:
        profile.embedding_path = payload.get("embedding_path")
    elif not profile.embedding_path and normalized["embedding_path"]:
        profile.embedding_path = normalized["embedding_path"]
    profile.fallback_provider = payload.get("fallback_provider") or normalized["fallback_provider"]
    profile.fallback_voice_settings_json = _fallback_voice_settings(payload or normalized)
    profile.style_json = dict(payload.get("style") or {})
    profile.controls_json = _normalize_controls(payload or normalized)
    if "provider_metadata" in payload:
        profile.provider_metadata_json = dict(payload.get("provider_metadata") or {})
    elif profile.provider_metadata_json is None:
        profile.provider_metadata_json = dict(normalized["provider_metadata_json"] or {})
    profile.espeak_voice = payload.get("voice") or normalized["espeak_voice"]
    profile.espeak_rate = payload.get("espeak_rate") if payload.get("espeak_rate") is not None else normalized["espeak_rate"]
    profile.espeak_pitch = payload.get("espeak_pitch") if payload.get("espeak_pitch") is not None else normalized["espeak_pitch"]
    profile.espeak_word_gap = payload.get("espeak_word_gap") if payload.get("espeak_word_gap") is not None else normalized["espeak_word_gap"]
    profile.espeak_amplitude = payload.get("espeak_amplitude") if payload.get("espeak_amplitude") is not None else normalized["espeak_amplitude"]
    db.commit()
    db.refresh(profile)
    return serialize_voice_profile(get_voice_profile_model(profile.id, db))


def list_character_presets(db: Session | None = None) -> list[dict[str, Any]]:
    with _session_scope(db) as (session, _):
        ensure_seeded_voice_presets(session)
        presets = (
            session.query(CharacterPreset)
            .options(joinedload(CharacterPreset.voice_profile).joinedload(VoiceProfile.reference_audios))
            .order_by(CharacterPreset.display_name.asc(), CharacterPreset.id.asc())
            .all()
        )
        return [serialize_character_preset(preset) for preset in presets]


def get_character_preset(preset_id: str, db: Session | None = None) -> dict[str, Any] | None:
    with _session_scope(db) as (session, _):
        ensure_seeded_voice_presets(session)
        preset = (
            session.query(CharacterPreset)
            .options(joinedload(CharacterPreset.voice_profile).joinedload(VoiceProfile.reference_audios))
            .filter(CharacterPreset.id == preset_id)
            .one_or_none()
        )
        return serialize_character_preset(preset) if preset else None


def get_character_preset_model(preset_id: str, db: Session | None) -> CharacterPreset | None:
    with _session_scope(db) as (session, _):
        ensure_seeded_voice_presets(session)
        return (
            session.query(CharacterPreset)
            .options(joinedload(CharacterPreset.voice_profile).joinedload(VoiceProfile.reference_audios))
            .filter(CharacterPreset.id == preset_id)
            .one_or_none()
        )


def resolve_character_preset_for_speaker(speaker: str, db: Session | None = None) -> dict[str, Any] | None:
    target = " ".join(speaker.lower().strip().split())
    with _session_scope(db) as (session, _):
        ensure_seeded_voice_presets(session)
        presets = (
            session.query(CharacterPreset)
            .options(joinedload(CharacterPreset.voice_profile).joinedload(VoiceProfile.reference_audios))
            .order_by(CharacterPreset.display_name.asc())
            .all()
        )
        for preset in presets:
            aliases = [" ".join(value.lower().strip().split()) for value in preset.speaker_names_json]
            aliases.append(" ".join(preset.display_name.lower().strip().split()))
            if target in aliases:
                return serialize_character_preset(preset)
    return None


def upsert_character_preset(payload: dict[str, Any], current_user_id: int, db: Session, preset_id: str | None = None) -> dict[str, Any]:
    ensure_seeded_voice_presets(db)
    target_id = preset_id or str(payload.get("id") or uuid.uuid4().hex[:12]).strip()
    preset = get_character_preset_model(target_id, db)
    if preset and not _can_mutate_preset(preset, current_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Character preset is not editable by this user")

    profile_payload = {
        "voice_profile_id": payload.get("voice_profile_id") or (preset.voice_profile_id if preset else None),
        "display_name": payload.get("display_name"),
        "provider": payload.get("tts_provider") or payload.get("provider"),
        "model_id": payload.get("model_id"),
        "language": payload.get("language"),
        "fallback_provider": payload.get("fallback_provider"),
        "fallback_voice_settings": payload.get("fallback_voice_settings") or {},
        "controls": payload.get("controls") or {},
        "voice": payload.get("voice"),
        "rate": payload.get("rate"),
        "pitch": payload.get("pitch"),
        "word_gap": payload.get("word_gap"),
        "amplitude": payload.get("amplitude"),
    }
    voice_profile = upsert_voice_profile(
        profile_payload,
        current_user_id=current_user_id,
        db=db,
        profile_id=profile_payload["voice_profile_id"],
    )

    if not preset:
        preset = CharacterPreset(id=target_id, created_by_user_id=current_user_id, source="runtime", is_seeded=False)
        db.add(preset)

    preset.display_name = str(payload.get("display_name") or preset.display_name or "Speaker").strip()
    preset.speaker_names_json = list(payload.get("speaker_names") or [preset.display_name])
    preset.portrait_filename = payload.get("portrait_filename")
    preset.voice_profile_id = voice_profile["id"]
    preset.sample_text = payload.get("sample_text") or DEFAULT_SAMPLE_TEXT
    preset.notes = payload.get("notes") or ""
    if preset.source == "bundled" and current_user_id:
        preset.source = "bundled"
    db.commit()
    db.refresh(preset)
    return serialize_character_preset(get_character_preset_model(preset.id, db))


def delete_character_preset(preset_id: str, current_user_id: int, db: Session) -> bool:
    preset = get_character_preset_model(preset_id, db)
    if not preset:
        return False
    if preset.is_seeded:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Seeded presets cannot be deleted")
    if not _can_mutate_preset(preset, current_user_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Character preset is not editable by this user")
    voice_profile = preset.voice_profile
    db.delete(preset)
    if voice_profile and len(voice_profile.presets) <= 1:
        db.delete(voice_profile)
    db.commit()
    return True


def resolve_character_portrait_path(preset: dict[str, Any] | None) -> Path | None:
    if not preset or not preset.get("portrait_filename"):
        return None
    filename = Path(str(preset["portrait_filename"])).name
    candidates = [
        Path(settings.BUNDLED_MEDIA_DIR) / "characters" / filename,
        Path(settings.MEDIA_DIR) / "characters" / filename,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _audio_duration_ms(path: Path) -> int | None:
    try:
        with wave.open(str(path), "rb") as handle:
            frame_rate = handle.getframerate()
            frame_count = handle.getnframes()
        return int((frame_count / frame_rate) * 1000) if frame_rate else None
    except wave.Error:
        return None


def save_reference_audio_upload(
    *,
    file: UploadFile,
    voice_profile_id: str,
    current_user_id: int,
    authorization_confirmed: bool,
    authorization_note: str | None,
    db: Session,
) -> tuple[dict[str, Any], dict[str, Any]]:
    ensure_seeded_voice_presets(db)
    if not authorization_confirmed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You must confirm that the reference audio is original or explicitly authorized.",
        )
    profile = get_voice_profile_model(voice_profile_id, db)
    if not profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Voice profile not found")
    ensure_voice_profile_editable(profile, current_user_id)
    allowed_types = {item.strip() for item in settings.VOICE_LAB_ALLOWED_AUDIO_TYPES.split(",") if item.strip()}
    if file.content_type not in allowed_types:
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="Unsupported reference audio type")
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Filename is required")

    content = file.file.read()
    if len(content) > settings.VOICE_LAB_MAX_REFERENCE_AUDIO_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Reference audio exceeds max size")
    sha256 = _sha256_bytes(content)
    destination, duration_ms = _normalize_reference_audio_upload(content, file.filename)

    reference = VoiceReferenceAudio(
        voice_profile_id=voice_profile_id,
        storage_path=str(destination),
        mime_type="audio/wav",
        duration_ms=duration_ms,
        sha256=sha256,
        authorization_confirmed=True,
        authorization_note=authorization_note,
        created_by_user_id=current_user_id,
    )
    db.add(reference)
    db.flush()
    invalidate_voice_profile_embedding(profile, db)
    processed_reference = _process_reference_audio_for_embedding(
        destination,
        voice_profile_id=voice_profile_id,
        reference_audio_id=reference.id,
        duration_ms=duration_ms,
    )
    next_metadata = dict(profile.provider_metadata_json or {})
    processed_by_id = dict(next_metadata.get("processed_reference_audio") or {})
    processed_by_id[str(reference.id)] = {
        **processed_reference,
        "original_filename": file.filename,
        "uploaded_file_size_bytes": len(content),
        "uploaded_file_sha256": sha256,
    }
    next_metadata.update(
        {
            "reference_processing_status": "ready",
            "processed_reference_audio": processed_by_id,
            "last_reference_audio_id": reference.id,
            "last_reference_original_filename": file.filename,
            "last_reference_audio_path": str(destination),
            "last_reference_audio_sha256": sha256,
            "last_reference_normalized_sha256": processed_reference["normalized_reference_sha256"],
            "last_reference_duration_seconds": round(duration_ms / 1000, 3),
            "last_reference_selected_duration_seconds": processed_reference["selected_duration_seconds"],
            "last_error": None,
        }
    )
    profile.provider_metadata_json = next_metadata
    logger.info(
        "voice.reference_audio.uploaded metadata=%s",
        {
            "voice_profile_id": voice_profile_id,
            "original_uploaded_filename": file.filename,
            "stored_reference_path": str(destination),
            "file_size_bytes": len(content),
            "reference_audio_sha256": sha256,
            "normalized_reference_sha256": processed_reference["normalized_reference_sha256"],
            "detected_duration_seconds": round(duration_ms / 1000, 3),
            "selected_chunk_count": len(processed_reference["chunks"]),
            "selected_duration_seconds": processed_reference["selected_duration_seconds"],
        },
    )
    db.commit()
    db.refresh(reference)
    profile = get_voice_profile_model(voice_profile_id, db)
    return serialize_voice_profile(profile), _serialize_reference_audio(reference)


def list_project_speaker_bindings(project_id: int, db: Session) -> list[dict[str, Any]]:
    ensure_seeded_voice_presets(db)
    items = (
        db.query(ProjectSpeakerBinding)
        .options(joinedload(ProjectSpeakerBinding.character_preset).joinedload(CharacterPreset.voice_profile))
        .filter(ProjectSpeakerBinding.project_id == project_id)
        .order_by(ProjectSpeakerBinding.speaker_name.asc())
        .all()
    )
    return [
        {
            "id": item.id,
            "speaker_name": item.speaker_name,
            "character_preset_id": item.character_preset_id,
            "character_display_name": item.character_preset.display_name,
            "voice_profile_id": item.character_preset.voice_profile_id,
            "provider": item.character_preset.voice_profile.provider,
        }
        for item in items
    ]


def suggest_project_speaker_bindings(project: Project, db: Session) -> list[dict[str, Any]]:
    suggestions: list[dict[str, Any]] = []
    seen: set[str] = set()
    for line in project.current_script_revision.parsed_lines_json if project.current_script_revision else []:
        speaker = str(line.get("speaker") or "").strip()
        if not speaker or speaker in seen:
            continue
        preset = resolve_character_preset_for_speaker(speaker, db)
        if preset:
            suggestions.append(
                {
                    "speaker_name": speaker,
                    "character_preset_id": preset["id"],
                }
            )
            seen.add(speaker)
    return suggestions


def upsert_project_speaker_bindings(project_id: int, items: list[dict[str, str]], db: Session) -> list[dict[str, Any]]:
    ensure_seeded_voice_presets(db)
    existing = {
        binding.speaker_name: binding
        for binding in db.query(ProjectSpeakerBinding).filter(ProjectSpeakerBinding.project_id == project_id).all()
    }
    incoming_names = {item["speaker_name"].strip() for item in items}
    for speaker_name, binding in existing.items():
        if speaker_name not in incoming_names:
            db.delete(binding)
    for item in items:
        speaker_name = item["speaker_name"].strip()
        preset_id = item["character_preset_id"].strip()
        preset = get_character_preset_model(preset_id, db)
        if not preset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Character preset not found: {preset_id}")
        binding = existing.get(speaker_name)
        if not binding:
            binding = ProjectSpeakerBinding(project_id=project_id, speaker_name=speaker_name, character_preset_id=preset_id)
            db.add(binding)
        else:
            binding.character_preset_id = preset_id
    db.commit()
    return list_project_speaker_bindings(project_id, db)


def resolve_preset_for_project_speaker(project_id: int, speaker: str, db: Session) -> dict[str, Any] | None:
    ensure_seeded_voice_presets(db)
    binding = (
        db.query(ProjectSpeakerBinding)
        .options(joinedload(ProjectSpeakerBinding.character_preset).joinedload(CharacterPreset.voice_profile).joinedload(VoiceProfile.reference_audios))
        .filter(ProjectSpeakerBinding.project_id == project_id, ProjectSpeakerBinding.speaker_name == speaker)
        .one_or_none()
    )
    if binding:
        return serialize_character_preset(binding.character_preset)
    return resolve_character_preset_for_speaker(speaker, db)
