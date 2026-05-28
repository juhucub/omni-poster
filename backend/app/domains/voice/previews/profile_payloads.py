from __future__ import annotations

from typing import Any

from app.domains.voice.providers.base import _slugify

_CLONE_PROVIDERS = {"openvoice", "xtts", "rvc"}


def reference_audio_profile_payload(reference_audio: Any) -> dict[str, Any]:
    return {
        "id": reference_audio.id,
        "storage_path": reference_audio.storage_path,
        "original_storage_path": reference_audio.original_storage_path,
        "processed_storage_path": reference_audio.processed_storage_path or reference_audio.storage_path,
        "sha256": reference_audio.sha256,
        "processed_sha256": reference_audio.processed_sha256,
        "mime_type": reference_audio.mime_type,
        "validation_status": reference_audio.validation_status,
        "validation": dict(reference_audio.validation_json or {}),
    }


def voice_profile_model_payload(preset_model: Any) -> dict[str, Any]:
    profile = preset_model.voice_profile
    return {
        "id": profile.id,
        "display_name": preset_model.display_name,
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
            reference_audio_profile_payload(item)
            for item in profile.reference_audios
        ],
        "language": profile.language,
        "model_id": profile.model_id,
        "model_checkpoint_path": profile.model_checkpoint_path,
        "selected_recipe": dict(profile.selected_recipe_json or {}),
        "reference_dataset_id": profile.reference_dataset_id,
        "character_slug": profile.character_slug,
        "calibration_score": profile.calibration_score,
        "last_verified_render_job_id": profile.last_verified_render_job_id,
        "embedding_path": profile.embedding_path,
        "provider_metadata": dict(profile.provider_metadata_json or {}),
        "fallback_allowed": str(profile.provider or "").lower() not in _CLONE_PROVIDERS,
    }


def build_ephemeral_voice_profile(
    speaker: str,
    payload: dict[str, Any],
    *,
    default_voice: str,
    default_rate: int,
    default_pitch: int,
    default_word_gap: int,
    default_amplitude: int,
) -> dict[str, Any]:
    provider = str(payload.get("tts_provider") or payload.get("provider") or "espeak").lower()
    return {
        "id": f"ephemeral_{_slugify(speaker)}",
        "display_name": speaker,
        "provider": provider,
        "fallback_provider": str(payload.get("fallback_provider") or "espeak").lower(),
        "voice": payload.get("voice") or default_voice,
        "espeak_voice": payload.get("voice") or default_voice,
        "espeak_rate": payload.get("rate") if payload.get("rate") is not None else default_rate,
        "espeak_pitch": payload.get("pitch") if payload.get("pitch") is not None else default_pitch,
        "espeak_word_gap": payload.get("word_gap") if payload.get("word_gap") is not None else default_word_gap,
        "espeak_amplitude": payload.get("amplitude") if payload.get("amplitude") is not None else default_amplitude,
        "controls": dict(payload.get("controls") or {}),
        "style": dict(payload.get("style") or {}),
        "fallback_voice_settings": {
            "voice": payload.get("voice"),
            "rate": payload.get("rate"),
            "pitch": payload.get("pitch"),
            "word_gap": payload.get("word_gap"),
            "amplitude": payload.get("amplitude"),
        },
        "reference_audios": list(payload.get("reference_audios") or []),
        "language": payload.get("language") or "en",
        "model_id": payload.get("model_id"),
        "embedding_path": payload.get("embedding_path"),
        "fallback_allowed": provider not in {"openvoice", "xtts", "rvc"},
    }


def normalize_manifest_voice_profile(manifest_entry: dict[str, Any]) -> dict[str, Any] | None:
    voice_profile = dict(manifest_entry.get("voice_profile") or {})
    if not voice_profile:
        return None
    provider = str(manifest_entry.get("requested_provider") or voice_profile.get("provider") or "espeak").lower()
    default_fallback_allowed = provider not in {"openvoice", "xtts", "rvc"}
    fallback_allowed = bool(manifest_entry.get("fallback_allowed", voice_profile.get("fallback_allowed", default_fallback_allowed)))
    return {
        **voice_profile,
        "requested_provider": provider,
        "fallback_allowed": fallback_allowed,
    }
