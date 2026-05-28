from __future__ import annotations

from typing import Any

from app.core.config import settings


def apply_voice_lab_overrides(
    voice_profile: dict[str, Any],
    *,
    controls: dict[str, Any] | None = None,
    rate: int | None = None,
    pitch: int | None = None,
    word_gap: int | None = None,
    amplitude: int | None = None,
) -> dict[str, Any]:
    payload = dict(voice_profile)
    normalized_controls = dict(payload.get("controls") or {})
    if rate is not None:
        payload["espeak_rate"] = rate
        normalized_controls["speaking_rate"] = round(float(rate) / float(settings.TTS_ESPEAK_RATE or 1), 3)
    if pitch is not None:
        payload["espeak_pitch"] = pitch
        normalized_controls["pitch"] = pitch
    if word_gap is not None:
        payload["espeak_word_gap"] = word_gap
        normalized_controls["pause_length"] = word_gap
    if amplitude is not None:
        payload["espeak_amplitude"] = amplitude
        normalized_controls["energy"] = amplitude
    normalized_controls.update(controls or {})
    payload["controls"] = normalized_controls
    payload["fallback_voice_settings"] = {
        **dict(payload.get("fallback_voice_settings") or {}),
        "voice": payload.get("voice"),
        "rate": payload.get("espeak_rate"),
        "pitch": payload.get("espeak_pitch"),
        "word_gap": payload.get("espeak_word_gap"),
        "amplitude": payload.get("espeak_amplitude"),
    }
    return payload
