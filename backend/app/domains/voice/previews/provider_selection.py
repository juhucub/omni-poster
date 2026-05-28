from __future__ import annotations

from typing import Any


def preview_requested_provider(voice_profile: dict[str, Any]) -> str:
    return str(voice_profile.get("tts_provider") or voice_profile.get("provider") or "espeak").strip().lower()


def preview_fallback_provider(voice_profile: dict[str, Any]) -> str:
    return str(voice_profile.get("fallback_provider") or "").strip().lower()


def select_preview_provider(voice_profile: dict[str, Any], available_providers: set[str]) -> str | None:
    requested_provider = preview_requested_provider(voice_profile)
    if requested_provider in available_providers:
        return requested_provider
    fallback = preview_fallback_provider(voice_profile)
    if fallback and fallback in available_providers:
        return fallback
    if "espeak" in available_providers:
        return "espeak"
    return None
