from __future__ import annotations

from typing import Any

from app.domains.voice.providers import SynthesisResult, TTSProviderError


def unknown_provider_failure(provider_name: str) -> dict[str, Any]:
    return {
        "code": "unknown_provider",
        "message": f"Unknown TTS provider requested: {provider_name}",
    }


def unavailable_provider_failure(provider_name: str, provider_health: dict[str, Any]) -> dict[str, Any]:
    return {
        "code": provider_health.get("reason") or "not_available",
        "message": f"Provider {provider_name} is not available in this environment.",
        "provider_state": provider_health,
    }


def provider_error_failure(exc: TTSProviderError) -> dict[str, Any]:
    return {
        "code": exc.code,
        "message": exc.message,
        "provider_state": exc.provider_state,
        "fallback_attempted": exc.fallback_attempted,
        "suggested_action": exc.suggested_action,
    }


def fallback_reason(provider_failures: dict[str, Any], fallback_used: bool) -> str | None:
    if fallback_used and provider_failures:
        return next(iter(provider_failures.values()), {}).get("code")
    return None


def voice_label_for_result(voice_profile: dict[str, Any], provider_name: str) -> str:
    return str(voice_profile.get("voice") or voice_profile.get("espeak_voice") or voice_profile.get("display_name") or provider_name)


def cached_synthesis_result(
    *,
    audio_path: str,
    duration_seconds: float,
    provider_name: str,
    voice_profile: dict[str, Any],
    state: dict[str, Any],
    controls_applied: dict[str, Any],
    provider_failures: dict[str, Any],
    fallback_used: bool,
) -> SynthesisResult:
    return SynthesisResult(
        audio_path=audio_path,
        voice=voice_label_for_result(voice_profile, provider_name),
        duration_seconds=max(duration_seconds, 0.6),
        provider_used=provider_name,
        fallback_used=fallback_used,
        controls_applied=controls_applied,
        reference_audio_count=len(voice_profile.get("reference_audios") or []),
        provider_state=state,
        cache_hit=True,
        voice_profile_id=str(voice_profile.get("id") or ""),
        provider_failures=dict(provider_failures),
        fallback_reason=fallback_reason(provider_failures, fallback_used),
        recipe_used=dict(voice_profile.get("selected_recipe") or {}),
        golden_preview_wav=None,
    )


def provider_synthesis_result(
    *,
    result: dict[str, Any],
    voice_profile: dict[str, Any],
    state: dict[str, Any],
    provider_failures: dict[str, Any],
    fallback_used: bool,
) -> SynthesisResult:
    return SynthesisResult(
        audio_path=result["audio_path"],
        voice=result["voice"],
        duration_seconds=result["duration_seconds"],
        provider_used=result["provider_used"],
        fallback_used=fallback_used,
        controls_applied=result.get("controls_applied") or {},
        reference_audio_count=int(result.get("reference_audio_count") or 0),
        provider_state=state,
        cache_hit=False,
        voice_profile_id=str(voice_profile.get("id") or ""),
        provider_failures=dict(provider_failures),
        fallback_reason=fallback_reason(provider_failures, fallback_used),
        recipe_used=dict(result.get("recipe_used") or voice_profile.get("selected_recipe") or {}),
        golden_preview_wav=result.get("golden_preview_wav"),
    )
