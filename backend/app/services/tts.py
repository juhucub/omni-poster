from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.domains.voice.providers import (
    BaseTTSProvider,
    EspeakProvider,
    ProviderCapability,
    ProviderRegistry as DomainProviderRegistry,
    SpeechSegment,
    SynthesisResult,
    TTSProviderError,
    TextToSpeechError,
    available_provider_names,
)
from app.domains.voice.providers.base import _slugify
from app.domains.voice.previews import (
    build_ephemeral_voice_profile,
    normalize_manifest_voice_profile,
    select_preview_provider,
    voice_profile_model_payload,
)
from app.domains.voice.synthesis import (
    TTSOrchestrator as DomainTTSOrchestrator,
    apply_voice_lab_overrides,
    audio_stats as _audio_stats,
)
from app.services.voice_profiles import (
    get_character_preset_model,
    resolve_character_preset_for_speaker,
    resolve_preset_for_project_speaker,
)

logger = logging.getLogger(__name__)


# Compatibility shim — OpenVoiceProvider moved to domains/voice/providers/openvoice.py
from app.domains.voice.providers.openvoice import OpenVoiceProvider  # noqa: F401


# Compatibility shim — XTTSProvider moved to domains/voice/providers/xtts.py
from app.domains.voice.providers.xtts import XTTSProvider  # noqa: F401


# Compatibility shim — RVCProvider moved to domains/voice/providers/rvc.py
from app.domains.voice.providers.rvc import RVCProvider  # noqa: F401


class ProviderRegistry(DomainProviderRegistry):
    def __init__(self) -> None:
        super().__init__(
            {
                "espeak": EspeakProvider(),
                "openvoice": OpenVoiceProvider(),
                "xtts": XTTSProvider(),
                "rvc": RVCProvider(),
            }
        )


class TTSOrchestrator(DomainTTSOrchestrator):
    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        super().__init__(registry or ProviderRegistry())


class LocalSpeechService:
    def __init__(
        self,
        *,
        db=None,
        project_id: int | None = None,
        speaker_voice_overrides: dict[str, dict[str, Any]] | None = None,
        voice_manifest: dict[str, Any] | None = None,
        profiler: Any | None = None,
        output_kind: str | None = None,
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.profiler = profiler
        self.output_kind = output_kind
        self.speaker_voice_overrides = {
            _slugify(speaker): dict(config) for speaker, config in (speaker_voice_overrides or {}).items()
        }
        manifest_speakers = dict((voice_manifest or {}).get("speakers") or {})
        # The manifest is the render-time contract from Video Lab; database changes after queueing should not drift it.
        self.voice_manifest = {
            str(speaker): dict(config) for speaker, config in manifest_speakers.items()
        }
        self.voice_manifest_by_slug = {
            _slugify(str(speaker)): dict(config) for speaker, config in manifest_speakers.items()
        }
        self.orchestrator = TTSOrchestrator()

    def _available_providers(self) -> set[str]:
        return available_provider_names(self.orchestrator.provider_state())

    def _provider_for_voice_profile(self, voice_profile: dict[str, Any], available_providers: set[str]) -> str:
        provider = select_preview_provider(voice_profile, available_providers)
        if provider:
            return provider
        raise TTSProviderError(
            code="no_provider_available",
            message="Voice preview synthesis is unavailable because no supported TTS provider is installed.",
            provider_state=self.orchestrator.provider_state(),
            suggested_action="Install espeak-ng or configure OpenVoice before previewing voices.",
        )

    def _ephemeral_profile(self, speaker: str, payload: dict[str, Any]) -> dict[str, Any]:
        return build_ephemeral_voice_profile(
            speaker,
            payload,
            default_voice=settings.TTS_ESPEAK_VOICE_SLOT_1,
            default_rate=settings.TTS_ESPEAK_RATE,
            default_pitch=settings.TTS_ESPEAK_PITCH,
            default_word_gap=settings.TTS_ESPEAK_WORD_GAP,
            default_amplitude=settings.TTS_ESPEAK_AMPLITUDE,
        )

    def _manifest_profile_for_speaker(self, speaker: str) -> dict[str, Any] | None:
        manifest_entry = self.voice_manifest.get(speaker) or self.voice_manifest_by_slug.get(_slugify(speaker))
        if not manifest_entry:
            return None
        return normalize_manifest_voice_profile(manifest_entry)

    def _resolved_profile_for_speaker(self, speaker: str, slot_index: int) -> dict[str, Any]:
        manifest_profile = self._manifest_profile_for_speaker(speaker)
        if manifest_profile:
            return manifest_profile
        override = self.speaker_voice_overrides.get(_slugify(speaker))
        if override:
            return self._ephemeral_profile(speaker, override)
        preset = None
        if self.project_id is not None and self.db is not None:
            preset = resolve_preset_for_project_speaker(self.project_id, speaker, self.db)
        if not preset and self.db is not None:
            preset_model = resolve_character_preset_for_speaker(speaker, self.db)
            preset = preset_model
        if not preset and self.db is None:
            preset = resolve_character_preset_for_speaker(speaker)
        if preset:
            preset_model = get_character_preset_model(preset["id"], self.db) if self.db is not None else get_character_preset_model(preset["id"], None)
            if preset_model:
                return voice_profile_model_payload(preset_model)
        default_voice = settings.TTS_ESPEAK_VOICE_SLOT_1 if slot_index % 2 == 0 else settings.TTS_ESPEAK_VOICE_SLOT_2
        return self._ephemeral_profile(
            speaker,
            {
                "tts_provider": "espeak",
                "voice": default_voice,
                "rate": settings.TTS_ESPEAK_RATE,
                "pitch": settings.TTS_ESPEAK_PITCH,
                "word_gap": settings.TTS_ESPEAK_WORD_GAP,
                "amplitude": settings.TTS_ESPEAK_AMPLITUDE,
            },
        )

    def resolve_voice_profile_map(self, parsed_lines: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        voice_profile_map: dict[str, dict[str, Any]] = {}
        slot_map: dict[str, int] = {}
        for index, line in enumerate(parsed_lines):
            speaker = str(line.get("speaker") or f"Speaker {index + 1}").strip()
            if speaker in voice_profile_map:
                continue
            slot_index = slot_map.setdefault(speaker, len(slot_map))
            if self.profiler is not None and hasattr(self.profiler, "stage"):
                with self.profiler.stage("tts.resolve_voice_profile", speaker=speaker, slot_index=slot_index):
                    voice_profile_map[speaker] = self._resolved_profile_for_speaker(speaker, slot_index)
            else:
                voice_profile_map[speaker] = self._resolved_profile_for_speaker(speaker, slot_index)
        return voice_profile_map

    def synthesize_dialogue(self, parsed_lines: list[dict[str, Any]], work_dir: Path) -> list[SpeechSegment]:
        voice_profile_map = self.resolve_voice_profile_map(parsed_lines)
        return self.orchestrator.synthesize_dialogue(
            lines=parsed_lines,
            voice_profile_map=voice_profile_map,
            output_dir=work_dir,
            fallback_allowed=True,
            options={
                "profiler": self.profiler,
                "output_kind": self.output_kind,
            },
        )

    def build_audio_clip(self, audio_path: str):
        from moviepy import AudioArrayClip

        with wave.open(audio_path, "rb") as handle:
            frame_rate = handle.getframerate()
            channels = handle.getnchannels()
            raw_frames = handle.readframes(handle.getnframes())

        samples = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            raise TTSProviderError(
                code="empty_audio",
                message=f"Synthesized speech file is empty: {audio_path}",
                suggested_action="Retry the preview or check the provider logs.",
            )
        peak = float(np.max(np.abs(samples)))
        if peak > 0:
            samples = samples * min(0.92 / peak, 1.35)
        if channels > 1:
            samples = samples.reshape((-1, channels))
        else:
            samples = samples.reshape((-1, 1))
        return AudioArrayClip(samples, fps=frame_rate)
