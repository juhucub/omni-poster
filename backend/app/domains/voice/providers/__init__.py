"""Voice provider contracts and adapters."""

from app.domains.voice.providers.base import (
    BaseTTSProvider,
    ProviderCapability,
    SpeechSegment,
    SynthesisResult,
    TTSProviderError,
    TextToSpeechError,
)
from app.domains.voice.providers.espeak import EspeakProvider
from app.domains.voice.providers.metadata import (
    available_provider_names,
    provider_capabilities_payload,
    provider_capability_payload,
)
from app.domains.voice.providers.registry import ProviderRegistry, provider_selection_order, resolve_provider_selection

__all__ = [
    "BaseTTSProvider",
    "EspeakProvider",
    "ProviderCapability",
    "ProviderRegistry",
    "SpeechSegment",
    "SynthesisResult",
    "TTSProviderError",
    "TextToSpeechError",
    "available_provider_names",
    "provider_capabilities_payload",
    "provider_capability_payload",
    "provider_selection_order",
    "resolve_provider_selection",
]
