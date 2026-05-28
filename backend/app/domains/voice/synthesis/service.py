from __future__ import annotations

import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from app.domains.voice.profiles import voice_cache_dir
from app.domains.voice.providers import (
    BaseTTSProvider,
    ProviderRegistry,
    SpeechSegment,
    SynthesisResult,
    TTSProviderError,
    provider_capabilities_payload,
    provider_selection_order,
    resolve_provider_selection as resolve_provider_selection_payload,
)
from app.domains.voice.providers.base import _slugify
from app.domains.voice.synthesis.audio import audio_stats
from app.domains.voice.synthesis.cache_keys import voice_cache_key
from app.domains.voice.synthesis.results import (
    cached_synthesis_result,
    provider_error_failure,
    provider_synthesis_result,
    unavailable_provider_failure,
    unknown_provider_failure,
)

logger = logging.getLogger(__name__)


class TTSOrchestrator:
    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or ProviderRegistry()

    def provider_capabilities(self) -> list[dict[str, Any]]:
        return provider_capabilities_payload(self.registry.capabilities())

    def provider_state(self) -> dict[str, Any]:
        return self.registry.healthcheck()

    def prepare_voice_profile(self, voice_profile: dict[str, Any], requested_provider: str | None = None) -> dict[str, Any]:
        provider_name = str(requested_provider or voice_profile.get("provider") or "espeak").lower()
        provider = self.registry.get(provider_name)
        if not provider:
            raise TTSProviderError(
                code="no_provider_available",
                message=f"Unknown TTS provider requested: {provider_name}",
                provider_state=self.provider_state(),
                suggested_action="Choose a supported provider.",
            )
        result = provider.prepare_voice_profile(voice_profile)
        return {
            "provider_used": provider_name,
            "provider_state": self.provider_state(),
            **result,
        }

    def resolve_provider_selection(
        self,
        voice_profile: dict[str, Any],
        requested_provider: str | None = None,
        fallback_allowed: bool = True,
    ) -> dict[str, Any]:
        state = self.provider_state()
        return resolve_provider_selection_payload(voice_profile, state, requested_provider, fallback_allowed)

    def _selection_order(self, voice_profile: dict[str, Any], requested_provider: str | None, fallback_allowed: bool) -> list[str]:
        return provider_selection_order(voice_profile, requested_provider, fallback_allowed)

    def _voice_cache_key(self, provider_name: str, text: str, voice_profile: dict[str, Any], provider: BaseTTSProvider) -> str:
        return voice_cache_key(
            provider_name,
            text,
            voice_profile,
            tuple(getattr(provider, "supported_control_names", ()) or ()),
        )

    def _copy_cache_if_present(self, key: str, output_path: Path) -> bool:
        cache_path = voice_cache_dir() / f"{key}.wav"
        if cache_path.exists():
            output_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(cache_path, output_path)
            return True
        return False

    def _save_to_cache(self, key: str, output_path: Path) -> None:
        cache_path = voice_cache_dir() / f"{key}.wav"
        if not cache_path.exists() and output_path.exists():
            shutil.copy2(output_path, cache_path)

    def synthesize_line(
        self,
        *,
        text: str,
        voice_profile: dict[str, Any],
        output_path: Path,
        requested_provider: str | None = None,
        fallback_allowed: bool = True,
        options: dict[str, Any] | None = None,
    ) -> SynthesisResult:
        options = dict(options or {})
        profiler = options.get("profiler")
        state = options.get("provider_state")
        if isinstance(state, dict):
            state = dict(state)
        elif profiler is not None and hasattr(profiler, "stage"):
            with profiler.stage("tts.provider_health_check"):
                state = self.provider_state()
        else:
            state = self.provider_state()
        selection_order = self._selection_order(voice_profile, requested_provider, fallback_allowed)
        attempted_providers: list[str] = []
        provider_failures: dict[str, Any] = {}
        fallback_attempted = False
        last_error: TTSProviderError | None = None
        for index, provider_name in enumerate(selection_order):
            attempted_providers.append(provider_name)
            provider = self.registry.get(provider_name)
            provider_health = state.get(provider_name) or {}
            if not provider:
                provider_failures[provider_name] = unknown_provider_failure(provider_name)
                logger.warning("tts.select skipped_provider=%s reason=unknown_provider", provider_name)
                continue
            if not provider_health.get("available"):
                provider_failures[provider_name] = unavailable_provider_failure(provider_name, provider_health)
                logger.warning(
                    "tts.select preset=%s profile=%s skipped_provider=%s reason=%s fallback=%s",
                    voice_profile.get("display_name"),
                    voice_profile.get("id"),
                    provider_name,
                    provider_health.get("reason") or "not_available",
                    selection_order[index + 1] if index + 1 < len(selection_order) else None,
                )
                continue
            recipe_requires_validation = provider_name == "xtts" and str(voice_profile.get("character_slug") or "").strip().lower() == "stewie_griffin"
            cache_enabled = provider_name != "xtts" and not recipe_requires_validation
            cache_key = self._voice_cache_key(provider_name, text, voice_profile, provider) if cache_enabled else None
            cache_hit = self._copy_cache_if_present(cache_key, output_path) if cache_key else False
            if cache_hit:
                duration_seconds = audio_stats(output_path)["duration_seconds"]
                if provider_name == "openvoice" and hasattr(provider, "_applied_controls"):
                    controls_applied = provider._applied_controls(voice_profile)  # type: ignore[attr-defined]
                else:
                    supported_control_names = tuple(getattr(provider, "supported_control_names", ()) or ())
                    fallback_settings = dict(voice_profile.get("fallback_voice_settings") or {})
                    controls_applied = {
                        "speaking_rate": (voice_profile.get("controls") or {}).get("speaking_rate"),
                        "pitch": fallback_settings.get("pitch") or voice_profile.get("espeak_pitch"),
                        "pause_length": (
                            fallback_settings.get("word_gap")
                            if fallback_settings.get("word_gap") is not None
                            else voice_profile.get("espeak_word_gap")
                        ),
                        "energy": fallback_settings.get("amplitude") or voice_profile.get("espeak_amplitude"),
                    }
                    if not supported_control_names:
                        controls_applied = {}
                    controls_applied = {key: value for key, value in controls_applied.items() if value is not None}
                logger.info(
                    "tts.select preset=%s profile=%s requested=%s selected=%s fallback_allowed=%s cache_hit=true",
                    voice_profile.get("display_name"),
                    voice_profile.get("id"),
                    requested_provider or "auto",
                    provider_name,
                    fallback_allowed,
                )
                return cached_synthesis_result(
                    audio_path=str(output_path),
                    duration_seconds=max(duration_seconds, 0.6),
                    provider_name=provider_name,
                    voice_profile=voice_profile,
                    state=state,
                    controls_applied=controls_applied,
                    provider_failures=provider_failures,
                    fallback_used=index > 0,
                )
            try:
                logger.info(
                    "tts.select preset=%s profile=%s requested=%s selected=%s fallback_allowed=%s",
                    voice_profile.get("display_name"),
                    voice_profile.get("id"),
                    requested_provider or "auto",
                    provider_name,
                    fallback_allowed,
                )
                if profiler is not None and hasattr(profiler, "stage"):
                    with profiler.stage(
                        "tts.segment_synthesis",
                        provider=provider_name,
                        voice_profile_id=voice_profile.get("id"),
                        output_path=output_path,
                        text_length=len(text),
                    ):
                        result = provider.synthesize_line(text=text, voice_profile=voice_profile, output_path=output_path, options=options)
                    with profiler.stage(
                        "tts.segment_wav_persistence",
                        provider=provider_name,
                        output_path=output_path,
                    ):
                        if output_path.exists():
                            output_path.stat()
                else:
                    result = provider.synthesize_line(text=text, voice_profile=voice_profile, output_path=output_path, options=options)
                if cache_key:
                    self._save_to_cache(cache_key, output_path)
                return provider_synthesis_result(
                    result=result,
                    voice_profile=voice_profile,
                    state=state,
                    provider_failures=provider_failures,
                    fallback_used=index > 0,
                )
            except TTSProviderError as exc:
                last_error = exc
                fallback_attempted = fallback_attempted or index > 0 or index + 1 < len(selection_order)
                provider_failures[provider_name] = provider_error_failure(exc)
                logger.warning(
                    "tts.select preset=%s profile=%s skipped_provider=%s reason=%s fallback=%s",
                    voice_profile.get("display_name"),
                    voice_profile.get("id"),
                    provider_name,
                    exc.code,
                    selection_order[index + 1] if index + 1 < len(selection_order) else None,
                )
                continue

        if last_error:
            raise TTSProviderError(
                code=last_error.code if len(selection_order) == 1 else "no_provider_available",
                message=last_error.message if len(selection_order) == 1 else "No configured TTS provider is currently usable.",
                provider_state=state,
                fallback_attempted=fallback_attempted,
                attempted_providers=attempted_providers,
                provider_failures=provider_failures,
                suggested_action=last_error.suggested_action,
            )
        raise TTSProviderError(
            code="no_provider_available",
            message="No configured TTS provider is currently usable.",
            provider_state=state,
            fallback_attempted=fallback_attempted,
            attempted_providers=attempted_providers,
            provider_failures=provider_failures,
            suggested_action="Install espeak-ng, configure OpenVoice, or choose a different provider.",
        )

    def synthesize_dialogue(
        self,
        *,
        lines: list[dict[str, Any]],
        voice_profile_map: dict[str, dict[str, Any]],
        output_dir: Path,
        requested_provider: str | None = None,
        fallback_allowed: bool = True,
        options: dict[str, Any] | None = None,
    ) -> list[SpeechSegment]:
        output_dir.mkdir(parents=True, exist_ok=True)
        options = dict(options or {})
        profiler = options.get("profiler")
        if "provider_state" not in options:
            if profiler is not None and hasattr(profiler, "stage"):
                with profiler.stage("tts.provider_health_check"):
                    options["provider_state"] = self.provider_state()
            else:
                options["provider_state"] = self.provider_state()
        segments: list[SpeechSegment] = []
        slot_map: dict[str, int] = {}
        for index, line in enumerate(lines):
            speaker = str(line.get("speaker") or f"Speaker {index + 1}").strip()
            text = str(line.get("text") or "").strip()
            caption_text = str(line.get("caption_text") or text).strip()
            line_id = str(line.get("line_id") or "").strip() or None
            if not text:
                continue
            slot_index = slot_map.setdefault(speaker, len(slot_map))
            voice_profile = voice_profile_map[speaker]
            effective_requested_provider = requested_provider
            if effective_requested_provider is None:
                effective_requested_provider = voice_profile.get("requested_provider")
            effective_fallback_allowed = fallback_allowed
            if "fallback_allowed" in voice_profile:
                effective_fallback_allowed = bool(voice_profile.get("fallback_allowed"))
            output_path = output_dir / f"{index:03d}_{_slugify(speaker)}_{uuid.uuid4().hex}.wav"
            result = self.synthesize_line(
                text=text,
                voice_profile=voice_profile,
                output_path=output_path,
                requested_provider=effective_requested_provider,
                fallback_allowed=effective_fallback_allowed,
                options=options,
            )
            segments.append(
                SpeechSegment(
                    speaker=speaker,
                    text=text,
                    voice=result.voice,
                    slot_index=slot_index,
                    audio_path=result.audio_path,
                    duration_seconds=result.duration_seconds,
                    caption_text=caption_text,
                    line_id=line_id,
                    voice_profile_id=result.voice_profile_id,
                    provider_used=result.provider_used,
                    fallback_used=result.fallback_used,
                    controls_applied=result.controls_applied,
                    reference_audio_count=result.reference_audio_count,
                    provider_state=result.provider_state,
                    provider_failures=getattr(result, "provider_failures", None),
                    fallback_reason=getattr(result, "fallback_reason", None),
                    recipe_used=getattr(result, "recipe_used", None),
                    golden_preview_wav=getattr(result, "golden_preview_wav", None),
                    cache_hit=getattr(result, "cache_hit", False),
                )
            )
        if not segments:
            raise TTSProviderError(
                code="no_spoken_lines",
                message="Cannot render a dialogue video without spoken lines.",
                provider_state=self.provider_state(),
                suggested_action="Add at least one spoken script line before rendering.",
            )
        return segments
