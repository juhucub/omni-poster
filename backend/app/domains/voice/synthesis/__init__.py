"""Voice synthesis orchestration helpers."""

from app.domains.voice.synthesis.audio import audio_stats
from app.domains.voice.synthesis.cache_keys import (
    voice_cache_key,
    voice_cache_settings,
    voice_reference_hash,
    voice_style_hash,
)
from app.domains.voice.synthesis.overrides import apply_voice_lab_overrides
from app.domains.voice.synthesis.results import (
    cached_synthesis_result,
    fallback_reason,
    provider_error_failure,
    provider_synthesis_result,
    unavailable_provider_failure,
    unknown_provider_failure,
    voice_label_for_result,
)
from app.domains.voice.synthesis.service import TTSOrchestrator

__all__ = [
    "apply_voice_lab_overrides",
    "audio_stats",
    "cached_synthesis_result",
    "fallback_reason",
    "provider_error_failure",
    "provider_synthesis_result",
    "TTSOrchestrator",
    "unavailable_provider_failure",
    "unknown_provider_failure",
    "voice_cache_key",
    "voice_cache_settings",
    "voice_label_for_result",
    "voice_reference_hash",
    "voice_style_hash",
]
