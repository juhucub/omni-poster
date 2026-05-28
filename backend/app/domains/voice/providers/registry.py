from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any

from app.domains.voice.providers.base import BaseTTSProvider, ProviderCapability

logger = logging.getLogger(__name__)


class ProviderRegistry:
    def __init__(self, providers: Mapping[str, BaseTTSProvider] | None = None) -> None:
        self.providers: dict[str, BaseTTSProvider] = dict(providers or {})

    def capabilities(self) -> list[ProviderCapability]:
        capabilities = [provider.supported_controls() for provider in self.providers.values()]
        logger.info(
            "tts.registry discovered providers %s",
            " ".join(
                f"{cap.provider}={'available' if cap.available else f'unavailable(reason={cap.reason})'}"
                for cap in capabilities
            ),
        )
        return capabilities

    def healthcheck(self) -> dict[str, Any]:
        return {name: provider.healthcheck() for name, provider in self.providers.items()}

    def get(self, provider_name: str) -> BaseTTSProvider | None:
        return self.providers.get(provider_name)


def provider_selection_order(
    voice_profile: dict[str, Any],
    requested_provider: str | None,
    fallback_allowed: bool,
) -> list[str]:
    attempts: list[str] = []
    if requested_provider and requested_provider not in {"", "auto"}:
        attempts.append(requested_provider)
    primary = str(voice_profile.get("provider") or "espeak").lower()
    if primary not in attempts:
        attempts.append(primary)
    fallback = str(voice_profile.get("fallback_provider") or "").lower()
    if fallback_allowed and fallback and fallback not in attempts:
        attempts.append(fallback)
    if fallback_allowed and "espeak" not in attempts:
        attempts.append("espeak")
    return attempts


def resolve_provider_selection(
    voice_profile: dict[str, Any],
    provider_state: dict[str, Any],
    requested_provider: str | None = None,
    fallback_allowed: bool = True,
) -> dict[str, Any]:
    selection_order = provider_selection_order(voice_profile, requested_provider, fallback_allowed)
    selected_provider = next(
        (provider_name for provider_name in selection_order if (provider_state.get(provider_name) or {}).get("available")),
        selection_order[0] if selection_order else None,
    )
    return {
        "selection_order": selection_order,
        "selected_provider": selected_provider,
        "provider_state": provider_state,
        "fallback_allowed": fallback_allowed,
    }
