from __future__ import annotations

from typing import Any

from app.services.render_cache import RENDER_CACHE_SCHEMA_VERSION, stable_hash


def _preset_payload(preset: Any) -> dict[str, Any]:
    return preset.__dict__


def voice_profile_cache_payload(voice_profile: dict[str, Any]) -> dict[str, Any]:
    references = []
    for item in voice_profile.get("reference_audios") or []:
        if not isinstance(item, dict):
            continue
        references.append(
            {
                "id": item.get("id"),
                "processed_sha256": item.get("processed_sha256"),
                "sha256": item.get("sha256"),
                "processed_storage_path": item.get("processed_storage_path"),
                "storage_path": item.get("storage_path"),
                "validation_status": item.get("validation_status"),
            }
        )
    return {
        "id": voice_profile.get("id"),
        "provider": voice_profile.get("provider"),
        "requested_provider": voice_profile.get("requested_provider"),
        "fallback_allowed": voice_profile.get("fallback_allowed"),
        "fallback_provider": voice_profile.get("fallback_provider"),
        "voice": voice_profile.get("voice") or voice_profile.get("espeak_voice"),
        "language": voice_profile.get("language"),
        "model_id": voice_profile.get("model_id"),
        "model_checkpoint_path": voice_profile.get("model_checkpoint_path"),
        "character_slug": voice_profile.get("character_slug"),
        "reference_dataset_id": voice_profile.get("reference_dataset_id"),
        "selected_recipe": dict(voice_profile.get("selected_recipe") or {}),
        "controls": dict(voice_profile.get("controls") or {}),
        "style": dict(voice_profile.get("style") or {}),
        "fallback_voice_settings": dict(voice_profile.get("fallback_voice_settings") or {}),
        "provider_metadata": dict(voice_profile.get("provider_metadata") or {}),
        "reference_audios": references,
    }


def tts_segment_cache_key(
    *,
    speaker: str,
    text: str,
    voice_profile: dict[str, Any],
    requested_provider: str | None,
    fallback_allowed: bool,
    output_kind: str,
) -> str:
    return stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "tts_segment",
            "speaker": speaker,
            "text": text,
            "voice_profile": voice_profile_cache_payload(voice_profile),
            "requested_provider": requested_provider,
            "fallback_allowed": fallback_allowed,
            "output_kind": output_kind,
        }
    )


def normalized_audio_cache_key(
    source_identity: str,
    sample_rate: int,
    channels: int = 2,
    codec: str = "pcm_s16le",
) -> str:
    return stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "normalized_audio",
            "source_identity": source_identity,
            "format": {"codec": codec, "sample_rate": sample_rate, "channels": channels},
        }
    )


def composite_audio_cache_key(
    normalized_segment_keys: list[str],
    timed_segments: list[dict[str, Any]],
    sample_rate: int,
    channels: int = 2,
    codec: str = "pcm_s16le",
) -> str:
    return stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "composite_audio",
            "segments": [
                {"key": key, "duration_seconds": round(item["duration_seconds"], 3)}
                for key, item in zip(normalized_segment_keys, timed_segments, strict=False)
            ],
            "format": {"codec": codec, "sample_rate": sample_rate, "channels": channels},
        }
    )


def background_cache_key(
    background_hash: str,
    background_mime_type: str,
    style_preset: str,
    preset: Any,
    cache_duration_seconds: float,
    requested_duration_seconds: float,
) -> str:
    return stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "background",
            "source_hash": background_hash,
            "mime_type": background_mime_type,
            "style_preset": style_preset,
            "preset": _preset_payload(preset),
            "duration_seconds": round(cache_duration_seconds, 3),
            "requested_duration_seconds": round(requested_duration_seconds, 3),
        }
    )


def static_overlay_cache_key(
    cast: list[tuple[str, int]],
    portrait_hashes: dict[str, str],
    render_layout: dict[str, Any],
    preset: Any,
) -> str:
    return stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "static_overlay",
            "cast": [
                {"speaker": speaker, "slot": slot, "portrait_hash": portrait_hashes.get(speaker)}
                for speaker, slot in cast
            ],
            "layout": render_layout,
            "preset": _preset_payload(preset),
        }
    )


def dynamic_frame_cache_key(
    segment: Any,
    portrait_hash: str,
    render_layout: dict[str, Any],
    preset: Any,
) -> str:
    return stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "dynamic_frame",
            "speaker": segment.speaker,
            "slot": segment.slot_index,
            "text": segment.text,
            "portrait_hash": portrait_hash,
            "layout": render_layout,
            "preset": _preset_payload(preset),
        }
    )


def dynamic_overlay_cache_key(frame_entries: list[dict[str, Any]], preset: Any) -> str:
    return stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "dynamic_overlay",
            "frames": [{"key": item["key"], "duration_seconds": round(item["duration_seconds"], 3)} for item in frame_entries],
            "preset": _preset_payload(preset),
        }
    )


def final_video_cache_key(
    background_key: str,
    static_overlay_key: str,
    dynamic_overlay_key: str,
    composite_audio_key: str,
    preset: Any,
    duration_seconds: float,
    audio_bitrate: str,
) -> str:
    return stable_hash(
        {
            "version": RENDER_CACHE_SCHEMA_VERSION,
            "type": "final_video",
            "background_key": background_key,
            "static_overlay_key": static_overlay_key,
            "dynamic_overlay_key": dynamic_overlay_key,
            "composite_audio_key": composite_audio_key,
            "preset": _preset_payload(preset),
            "duration_seconds": round(duration_seconds, 3),
            "audio_bitrate": audio_bitrate,
        }
    )
