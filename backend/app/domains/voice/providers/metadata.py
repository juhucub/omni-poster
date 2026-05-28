from __future__ import annotations

from typing import Any, Iterable

from app.domains.voice.providers.base import ProviderCapability


def provider_capability_payload(capability: ProviderCapability) -> dict[str, Any]:
    return {
        "provider": capability.provider,
        "available": capability.available,
        "reason": capability.reason,
        "supports_voice_cloning": capability.supports_voice_cloning,
        "supports_prepare": capability.supports_prepare,
        "supported_controls": capability.supported_controls,
        "metadata": capability.metadata,
    }


def provider_capabilities_payload(capabilities: Iterable[ProviderCapability]) -> list[dict[str, Any]]:
    return [provider_capability_payload(capability) for capability in capabilities]


def available_provider_names(provider_state: dict[str, Any]) -> set[str]:
    return {name for name, state in provider_state.items() if state.get("available")}
