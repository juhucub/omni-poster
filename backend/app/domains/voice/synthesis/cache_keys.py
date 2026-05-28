from __future__ import annotations

import hashlib
from typing import Any, Iterable


def voice_reference_hash(voice_profile: dict[str, Any]) -> str:
    provider_metadata = dict(voice_profile.get("provider_metadata") or {})
    reference_hash = hashlib.sha256(
        "|".join(
            sorted(
                str(
                    item.get("processed_sha256")
                    or item.get("sha256")
                    or item.get("processed_storage_path")
                    or item.get("storage_path")
                    or ""
                )
                for item in voice_profile.get("reference_audios") or []
            )
        ).encode("utf-8")
    ).hexdigest()
    return str(provider_metadata.get("reference_audio_sha256") or reference_hash)


def voice_cache_settings(
    provider_name: str,
    voice_profile: dict[str, Any],
    supported_control_names: Iterable[str] = (),
) -> dict[str, Any]:
    provider_metadata = dict(voice_profile.get("provider_metadata") or {})
    controls = dict(voice_profile.get("controls") or {})
    style = dict(voice_profile.get("style") or {})
    fallback_settings = dict(voice_profile.get("fallback_voice_settings") or {})
    selected_recipe = dict(voice_profile.get("selected_recipe") or {})
    supported_controls = tuple(supported_control_names or ())
    if provider_name == "openvoice":
        return {
            "controls": {key: controls.get(key) for key in supported_controls if controls.get(key) is not None},
            "language": voice_profile.get("language"),
            "model_id": voice_profile.get("model_id"),
            "base_speaker": voice_profile.get("base_speaker") or style.get("base_speaker"),
            "style_preset": style.get("style_preset"),
            "embedding_path": voice_profile.get("embedding_path") or provider_metadata.get("embedding_artifact_path"),
            "target_embedding_hash": provider_metadata.get("target_embedding_hash"),
        }
    if provider_name in {"xtts", "rvc"}:
        return {
            "controls": {key: controls.get(key) for key in supported_controls if controls.get(key) is not None},
            "language": voice_profile.get("language"),
            "model_id": voice_profile.get("model_id"),
            "model_checkpoint_path": voice_profile.get("model_checkpoint_path"),
            "selected_recipe": selected_recipe,
            "base_speaker": voice_profile.get("base_speaker") or style.get("base_speaker"),
            "style_preset": style.get("style_preset"),
        }
    return {
        "controls": {key: controls.get(key) for key in supported_controls if controls.get(key) is not None},
        "fallback": {
            "voice": fallback_settings.get("voice") or voice_profile.get("voice") or voice_profile.get("espeak_voice"),
            "rate": fallback_settings.get("rate") or voice_profile.get("espeak_rate"),
            "pitch": fallback_settings.get("pitch") or voice_profile.get("espeak_pitch"),
            "word_gap": fallback_settings.get("word_gap")
            if fallback_settings.get("word_gap") is not None
            else voice_profile.get("espeak_word_gap"),
            "amplitude": fallback_settings.get("amplitude") or voice_profile.get("espeak_amplitude"),
        },
    }


def voice_style_hash(
    provider_name: str,
    voice_profile: dict[str, Any],
    supported_control_names: Iterable[str] = (),
) -> str:
    cache_settings = voice_cache_settings(provider_name, voice_profile, supported_control_names)
    return hashlib.sha256(repr(cache_settings).encode("utf-8")).hexdigest()


def voice_cache_key(
    provider_name: str,
    text: str,
    voice_profile: dict[str, Any],
    supported_control_names: Iterable[str] = (),
) -> str:
    style_hash = voice_style_hash(provider_name, voice_profile, supported_control_names)
    payload = "|".join(
        [
            provider_name,
            text,
            str(voice_profile.get("id") or ""),
            voice_reference_hash(voice_profile),
            style_hash,
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
