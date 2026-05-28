from __future__ import annotations

import re
import uuid
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _slugify(value: str) -> str:
    # Segment filenames include speakers, so normalize names before they touch the filesystem.
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "speaker"


@dataclass(frozen=True)
class ProviderCapability:
    provider: str
    available: bool
    reason: str | None
    supports_voice_cloning: bool
    supports_prepare: bool
    supported_controls: list[str]
    metadata: dict[str, Any]


class TTSProviderError(RuntimeError):
    def __init__(
        self,
        *,
        code: str,
        message: str,
        provider_state: dict[str, Any] | None = None,
        fallback_attempted: bool = False,
        attempted_providers: list[str] | None = None,
        provider_failures: dict[str, Any] | None = None,
        suggested_action: str = "Try a different provider or check the TTS configuration.",
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.provider_state = provider_state or {}
        self.fallback_attempted = fallback_attempted
        self.attempted_providers = list(attempted_providers or [])
        self.provider_failures = dict(provider_failures or {})
        self.suggested_action = suggested_action

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message,
            "provider_state": self.provider_state,
            "fallback_attempted": self.fallback_attempted,
            "attempted_providers": self.attempted_providers,
            "provider_failures": self.provider_failures,
            "suggested_action": self.suggested_action,
        }


TextToSpeechError = TTSProviderError


@dataclass(frozen=True)
class SpeechSegment:
    speaker: str
    text: str
    voice: str
    slot_index: int
    audio_path: str
    duration_seconds: float
    caption_text: str | None = None
    line_id: str | None = None
    voice_profile_id: str = ""
    provider_used: str = "espeak"
    fallback_used: bool = False
    controls_applied: dict[str, Any] | None = None
    reference_audio_count: int = 0
    provider_state: dict[str, Any] | None = None
    provider_failures: dict[str, Any] | None = None
    fallback_reason: str | None = None
    recipe_used: dict[str, Any] | None = None
    golden_preview_wav: str | None = None
    cache_hit: bool = False
    cache_key: str | None = None
    cache_source_path: str | None = None
    normalized_audio_path: str | None = None
    normalized_cache_hit: bool = False
    normalized_cache_key: str | None = None


@dataclass(frozen=True)
class SynthesisResult:
    audio_path: str
    voice: str
    duration_seconds: float
    provider_used: str
    fallback_used: bool
    controls_applied: dict[str, Any]
    reference_audio_count: int
    provider_state: dict[str, Any]
    cache_hit: bool
    voice_profile_id: str
    provider_failures: dict[str, Any] | None = None
    fallback_reason: str | None = None
    recipe_used: dict[str, Any] | None = None
    golden_preview_wav: str | None = None


class BaseTTSProvider:
    provider_name = "base"
    clone_capable = False
    prepare_capable = False
    supported_control_names: tuple[str, ...] = ()

    def is_available(self) -> bool:
        return bool(self.healthcheck()["available"])

    def _profile_stage(self, profiler: Any | None, name: str, **metadata: Any):
        if profiler is not None and hasattr(profiler, "stage"):
            return profiler.stage(name, **metadata)
        return nullcontext()

    def _record_profile_stage(self, profiler: Any | None, name: str, **metadata: Any) -> None:
        with self._profile_stage(profiler, name, **metadata):
            pass

    def healthcheck(self) -> dict[str, Any]:
        raise NotImplementedError

    def supported_controls(self) -> ProviderCapability:
        health = self.healthcheck()
        return ProviderCapability(
            provider=self.provider_name,
            available=health["available"],
            reason=health.get("reason"),
            supports_voice_cloning=self.clone_capable,
            supports_prepare=self.prepare_capable,
            supported_controls=list(self.supported_control_names),
            metadata=dict(health.get("metadata") or {}),
        )

    def prepare_voice_profile(self, voice_profile: dict[str, Any]) -> dict[str, Any]:
        return {
            "prepared": False,
            "cached_artifact_path": voice_profile.get("embedding_path"),
            "message": f"{self.provider_name} does not require preparation.",
            "provider_metadata": {},
        }

    def synthesize_line(
        self,
        text: str,
        voice_profile: dict[str, Any],
        output_path: Path,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        raise NotImplementedError

    def synthesize_dialogue(
        self,
        lines: list[dict[str, Any]],
        voice_profile_map: dict[str, dict[str, Any]],
        output_dir: Path,
        options: dict[str, Any],
    ) -> list[dict[str, Any]]:
        output_dir.mkdir(parents=True, exist_ok=True)
        results: list[dict[str, Any]] = []
        for index, line in enumerate(lines):
            speaker = str(line.get("speaker") or f"Speaker {index + 1}").strip()
            text = str(line.get("text") or "").strip()
            caption_text = str(line.get("caption_text") or text).strip()
            line_id = str(line.get("line_id") or "").strip() or None
            if not text:
                continue
            profile = voice_profile_map[speaker]
            result = self.synthesize_line(
                text=text,
                voice_profile=profile,
                output_path=output_dir / f"{index:03d}_{_slugify(speaker)}_{uuid.uuid4().hex}.wav",
                options=options,
            )
            results.append({"speaker": speaker, "text": text, **result})
        return results
