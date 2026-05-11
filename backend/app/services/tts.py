from __future__ import annotations

import hashlib
import inspect
import importlib.util
import json
import logging
import os
import re
import resource
import shlex
import shutil
import subprocess
import sys
import threading
import uuid
import wave
from collections import OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
from app.services.character_voice_recipes import CharacterVoiceRecipeError, validate_selected_character_recipe
from app.services.voice_profiles import (
    get_character_preset_model,
    reference_audio_content_hash_from_paths,
    resolve_character_preset_for_speaker,
    resolve_preset_for_project_speaker,
    voice_embedding_artifact_path_for_reference,
    voice_cache_dir,
)

logger = logging.getLogger(__name__)


def _slugify(value: str) -> str:
    # Segment filenames include speakers, so normalize names before they touch the filesystem.
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "speaker"


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


class EspeakProvider(BaseTTSProvider):
    provider_name = "espeak"
    supported_control_names = (
        "speaking_rate",
        "pitch",
        "energy",
        "pause_length",
    )

    def healthcheck(self) -> dict[str, Any]:
        espeak_ng_binary = shutil.which("espeak-ng")
        espeak_binary = shutil.which("espeak")
        available = bool(espeak_ng_binary or espeak_binary)
        return {
            "available": available,
            "reason": None if available else "missing_binary",
            "metadata": {"binary": espeak_ng_binary or espeak_binary},
        }

    def synthesize_line(
        self,
        text: str,
        voice_profile: dict[str, Any],
        output_path: Path,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            raise TTSProviderError(
                code="espeak_not_installed",
                message="Local espeak fallback is unavailable because espeak-ng is not installed.",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Install espeak-ng in the runtime image or choose a different provider.",
            )
        controls = dict(voice_profile.get("controls") or {})
        fallback_settings = dict(voice_profile.get("fallback_voice_settings") or {})
        rate = int(fallback_settings.get("rate") or voice_profile.get("espeak_rate") or settings.TTS_ESPEAK_RATE)
        pitch = int(fallback_settings.get("pitch") or voice_profile.get("espeak_pitch") or settings.TTS_ESPEAK_PITCH)
        word_gap = int(
            fallback_settings.get("word_gap")
            if fallback_settings.get("word_gap") is not None
            else voice_profile.get("espeak_word_gap") or settings.TTS_ESPEAK_WORD_GAP
        )
        amplitude = int(fallback_settings.get("amplitude") or voice_profile.get("espeak_amplitude") or settings.TTS_ESPEAK_AMPLITUDE)

        voice = str(fallback_settings.get("voice") or voice_profile.get("voice") or voice_profile.get("espeak_voice") or settings.TTS_ESPEAK_VOICE_SLOT_1)
        command = [
            binary,
            "-w",
            str(output_path),
            "-s",
            str(rate),
            "-p",
            str(pitch),
            "-g",
            str(word_gap),
            "-a",
            str(amplitude),
            "-v",
            voice,
            text,
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise TTSProviderError(
                code="synthesis_failure",
                message=f"espeak synthesis failed: {exc.stderr.strip()}",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Verify the espeak voice settings and try a simpler preview.",
            ) from exc

        duration_seconds = _audio_stats(output_path)["duration_seconds"]
        controls_applied = {
            "speaking_rate": controls.get("speaking_rate"),
            "pitch": pitch,
            "pause_length": word_gap,
            "energy": amplitude,
        }
        return {
            "audio_path": str(output_path),
            "voice": voice,
            "duration_seconds": max(duration_seconds, 0.6),
            "provider_used": self.provider_name,
            "controls_applied": {key: value for key, value in controls_applied.items() if value is not None},
            "reference_audio_count": len(voice_profile.get("reference_audios") or []),
        }


class OpenVoiceProvider(BaseTTSProvider):
    provider_name = "openvoice"
    clone_capable = True
    prepare_capable = True
    _cache_lock = threading.Lock()
    _melo_model_cache: dict[tuple[str, str], Any] = {}
    _converter_cache: dict[tuple[str, str], Any] = {}
    _source_embedding_cache: dict[tuple[str, str], Any] = {}
    _target_embedding_cache: dict[str, Any] = {}
    _silero_vad_ready_devices: set[str] = set()
    supported_control_names = ("speaking_rate",)

    def _repo_dir(self) -> Path | None:
        if not settings.OPENVOICE_REPO_DIR:
            return None
        return Path(settings.OPENVOICE_REPO_DIR)

    def _checkpoints_dir(self) -> Path | None:
        if not settings.OPENVOICE_CHECKPOINTS_DIR:
            return None
        return Path(settings.OPENVOICE_CHECKPOINTS_DIR)

    def _ensure_repo_on_path(self) -> None:
        repo_dir = self._repo_dir()
        if repo_dir and repo_dir.exists():
            repo_path = str(repo_dir.resolve())
            if repo_path not in sys.path:
                sys.path.insert(0, repo_path)

    def _device(self) -> tuple[str, str | None]:
        requested = settings.OPENVOICE_DEVICE.strip().lower()
        if requested and requested != "auto":
            return requested, None
        try:
            import torch

            if torch.cuda.is_available():
                return "cuda", None
        except Exception:
            pass
        return "cpu", "gpu_unavailable_using_cpu"

    def healthcheck(self) -> dict[str, Any]:
        if not settings.OPENVOICE_ENABLED:
            return {"available": False, "reason": "disabled", "metadata": {}}
        repo_dir = self._repo_dir()
        checkpoints_dir = self._checkpoints_dir()
        if not repo_dir or not repo_dir.exists():
            return {"available": False, "reason": "missing_repo", "metadata": {"repo_dir": settings.OPENVOICE_REPO_DIR}}
        if not checkpoints_dir or not checkpoints_dir.exists():
            return {
                "available": False,
                "reason": "missing_models",
                "metadata": {"checkpoints_dir": settings.OPENVOICE_CHECKPOINTS_DIR},
            }
        self._ensure_repo_on_path()
        device, warning = self._device()
        metadata = {"repo_dir": str(repo_dir), "checkpoints_dir": str(checkpoints_dir), "device": device}
        if warning:
            metadata["warning"] = warning
        openvoice_spec = importlib.util.find_spec("openvoice")
        melo_spec = importlib.util.find_spec("melo") or importlib.util.find_spec("melo.api")
        if not (openvoice_spec and melo_spec):
            return {
                "available": False,
                "reason": "package_missing",
                "metadata": metadata,
            }
        try:
            from melo.api import TTS  # type: ignore
            from openvoice import se_extractor  # type: ignore
            from openvoice.api import ToneColorConverter  # type: ignore
        except Exception as exc:
            metadata["import_error"] = f"{type(exc).__name__}: {exc}"
            return {
                "available": False,
                "reason": "package_import_failed",
                "metadata": metadata,
            }
        return {
            "available": True,
            "reason": None,
            "metadata": metadata,
        }

    def _melo_language(self, language: str | None) -> str:
        mapping = {
            "en": "EN",
            "english": "EN",
            "es": "ES",
            "spanish": "ES",
            "fr": "FR",
            "french": "FR",
            "zh": "ZH",
            "chinese": "ZH",
            "jp": "JP",
            "ja": "JP",
            "japanese": "JP",
            "kr": "KR",
            "ko": "KR",
            "korean": "KR",
        }
        return mapping.get((language or "en").lower(), "EN")

    def _melo_speaker_id(self, model: Any, language_code: str, voice_profile: dict[str, Any] | None = None) -> tuple[str, Any]:
        speaker_map = dict(getattr(getattr(model, "hps", None), "data", None).spk2id)
        style = dict((voice_profile or {}).get("style") or {})
        requested_base_speaker = str(
            (voice_profile or {}).get("base_speaker")
            or style.get("base_speaker")
            or ""
        ).strip()
        preferred = [
            requested_base_speaker,
            requested_base_speaker.upper().replace("-", "_") if requested_base_speaker else None,
            requested_base_speaker.replace("_", "-") if requested_base_speaker else None,
            f"{language_code}-Default",
            f"{language_code}_DEFAULT",
            next(iter(speaker_map.keys()), None),
        ]
        for key in preferred:
            if key in speaker_map:
                return key, speaker_map[key]
        first_key = next(iter(speaker_map.keys()))
        return first_key, speaker_map[first_key]

    def _memory_mb(self) -> float:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        if sys.platform == "darwin":
            return rss / (1024 * 1024)
        return rss / 1024

    def _log_memory_stage(self, stage: str, **metadata: Any) -> None:
        logger.info("openvoice.memory stage=%s rss_mb=%.1f metadata=%s", stage, self._memory_mb(), metadata)

    def _reference_audio_cache_key(self, reference_paths: list[Path], device: str) -> str:
        reference_hash = reference_audio_content_hash_from_paths(reference_paths)
        return hashlib.sha256(f"{reference_hash}|{device}".encode("utf-8")).hexdigest()

    def _reference_audio_hash(self, reference_paths: list[Path]) -> str:
        return reference_audio_content_hash_from_paths(reference_paths)

    def _get_melo_model(self, language_code: str, device: str, tts_cls: Any) -> Any:
        cache_key = (language_code, device)
        with self._cache_lock:
            model = self._melo_model_cache.get(cache_key)
            if model is not None:
                self._log_memory_stage("melo_model_cache_hit", language=language_code, device=device)
                return model
        self._log_memory_stage("melo_model_init_begin", language=language_code, device=device)
        model = tts_cls(language=language_code, device=device)
        with self._cache_lock:
            self._melo_model_cache[cache_key] = model
        self._log_memory_stage("melo_model_init_end", language=language_code, device=device)
        return model

    def _get_converter(self, converter_dir: Path, device: str, converter_cls: Any) -> Any:
        cache_key = (str(converter_dir.resolve()), device)
        with self._cache_lock:
            converter = self._converter_cache.get(cache_key)
            if converter is not None:
                self._log_memory_stage("converter_cache_hit", device=device)
                return converter
        self._log_memory_stage("converter_init_begin", device=device)
        converter = converter_cls(str(converter_dir / "config.json"), device=device)
        converter.load_ckpt(str(converter_dir / "checkpoint.pth"))
        with self._cache_lock:
            self._converter_cache[cache_key] = converter
        self._log_memory_stage("converter_init_end", device=device)
        return converter

    def _get_source_embedding(self, base_speaker_path: Path, device: str, torch_module: Any) -> Any:
        cache_key = (str(base_speaker_path.resolve()), device)
        with self._cache_lock:
            source_embedding = self._source_embedding_cache.get(cache_key)
            if source_embedding is not None:
                self._log_memory_stage("source_embedding_cache_hit", device=device)
                return source_embedding
        self._log_memory_stage("source_embedding_load_begin", device=device)
        source_embedding = torch_module.load(str(base_speaker_path), map_location=device)
        with self._cache_lock:
            self._source_embedding_cache[cache_key] = source_embedding
        self._log_memory_stage("source_embedding_load_end", device=device)
        return source_embedding

    def _artifact_cache_key(self, artifact_path: Path, device: str) -> str:
        stat = artifact_path.stat()
        payload = "|".join([str(artifact_path.resolve()), str(int(stat.st_mtime_ns)), str(stat.st_size), device])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _reference_audio_paths(self, voice_profile: dict[str, Any]) -> list[Path]:
        metadata = dict(voice_profile.get("provider_metadata") or {})
        processed_paths = [Path(str(path)) for path in metadata.get("processed_reference_paths") or [] if path]
        processed_reference_ids = {int(item) for item in metadata.get("processed_reference_audio_ids") or [] if str(item).isdigit()}
        fallback_paths = []
        for item in voice_profile.get("reference_audios") or []:
            reference_path = item.get("processed_storage_path") or item.get("storage_path")
            if not reference_path:
                continue
            try:
                reference_id = int(item.get("id") or 0)
            except (TypeError, ValueError):
                reference_id = 0
            if reference_id not in processed_reference_ids:
                fallback_paths.append(Path(str(reference_path)))
        return processed_paths + fallback_paths if processed_paths else fallback_paths

    def _embedding_artifact_path(self, voice_profile: dict[str, Any], reference_hash: str) -> Path:
        return voice_embedding_artifact_path_for_reference(str(voice_profile.get("id") or uuid.uuid4().hex), reference_hash)

    def _embedding_fingerprint(self, target_embedding: Any) -> str:
        try:
            tensor = target_embedding.detach().cpu().contiguous()
            payload = tensor.numpy().tobytes()
        except Exception:
            payload = repr(target_embedding).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    def _embedding_stats(self, target_embedding: Any) -> dict[str, Any]:
        stats: dict[str, Any] = {"target_embedding_hash": self._embedding_fingerprint(target_embedding)}
        try:
            tensor = target_embedding.detach().float().cpu()
            stats.update(
                {
                    "embedding_shape": list(getattr(tensor, "shape", []) or []),
                    "embedding_mean": float(tensor.mean().item()),
                    "embedding_std": float(tensor.std().item()),
                    "embedding_norm": float(tensor.norm().item()),
                }
            )
        except Exception:
            stats.update(
                {
                    "embedding_shape": list(getattr(target_embedding, "shape", []) or []),
                    "embedding_mean": None,
                    "embedding_std": None,
                    "embedding_norm": None,
                }
            )
        return stats

    def _applied_controls(self, voice_profile: dict[str, Any]) -> dict[str, Any]:
        speaking_rate = (voice_profile.get("controls") or {}).get("speaking_rate")
        return {"speaking_rate": speaking_rate} if speaking_rate is not None else {}

    def _import_runtime(self) -> tuple[Any, Any, Any, Any]:
        self._ensure_repo_on_path()
        from melo.api import TTS  # type: ignore
        from openvoice import se_extractor  # type: ignore
        from openvoice.api import ToneColorConverter  # type: ignore
        import torch  # type: ignore

        return TTS, se_extractor, ToneColorConverter, torch

    def _ensure_silero_vad_ready(self, torch_module: Any) -> None:
        device, _warning = self._device()
        with self._cache_lock:
            if device in self._silero_vad_ready_devices:
                return
        self._log_memory_stage("silero_vad_prewarm_begin", device=device)
        try:
            torch_module.hub.load(
                repo_or_dir="snakers4/silero-vad",
                model="silero_vad",
                trust_repo=True,
                skip_validation=True,
                onnx=False,
            )
        except Exception as exc:
            raise TTSProviderError(
                code="openvoice_vad_bootstrap_failed",
                message=f"OpenVoice could not initialize Silero VAD non-interactively: {exc}",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Rebuild the Docker image with network access or pre-populate the torch hub cache for snakers4/silero-vad.",
            ) from exc
        with self._cache_lock:
            self._silero_vad_ready_devices.add(device)
        self._log_memory_stage("silero_vad_prewarm_end", device=device)

    def _extract_reference_embedding(self, reference_path: Path, converter: Any, se_extractor: Any, device: str) -> Any:
        cache_key = self._reference_audio_cache_key([reference_path], device)
        with self._cache_lock:
            target_embedding = self._target_embedding_cache.get(cache_key)
            if target_embedding is not None:
                self._log_memory_stage("target_embedding_cache_hit", device=device, reference_audio_path=str(reference_path))
                return target_embedding
        reference_hash = self._reference_audio_hash([reference_path])
        self._log_memory_stage(
            "target_embedding_extract_begin",
            device=device,
            reference_audio_path=str(reference_path),
            reference_audio_sha256=reference_hash,
            reference_audio_size_bytes=reference_path.stat().st_size,
        )
        try:
            target_embedding, _ = se_extractor.get_se(str(reference_path), converter, vad=False)
        except Exception as exc:
            raise TTSProviderError(
                code="reference_embedding_extraction_failed",
                message=f"OpenVoice could not extract a speaker embedding from the selected reference audio: {exc}",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Try a clearer authorized reference clip or check the OpenVoice runtime logs.",
            ) from exc
        with self._cache_lock:
            self._target_embedding_cache[cache_key] = target_embedding
        self._log_memory_stage(
            "target_embedding_extract_end",
            device=device,
            reference_audio_path=str(reference_path),
            reference_audio_sha256=reference_hash,
            **self._embedding_stats(target_embedding),
        )
        return target_embedding

    def _load_cached_target_embedding(self, artifact_path: Path, device: str, torch_module: Any) -> Any | None:
        if not artifact_path.exists():
            return None
        cache_key = self._artifact_cache_key(artifact_path, device)
        with self._cache_lock:
            target_embedding = self._target_embedding_cache.get(cache_key)
            if target_embedding is not None:
                self._log_memory_stage("target_embedding_artifact_cache_hit", device=device)
                return target_embedding
        self._log_memory_stage("target_embedding_artifact_load_begin", device=device, target_embedding_path=str(artifact_path))
        target_embedding = torch_module.load(str(artifact_path), map_location=device)
        with self._cache_lock:
            self._target_embedding_cache[cache_key] = target_embedding
        self._log_memory_stage(
            "target_embedding_artifact_load_end",
            device=device,
            target_embedding_path=str(artifact_path),
            target_embedding_hash=self._embedding_fingerprint(target_embedding),
        )
        return target_embedding

    def _persist_target_embedding(self, target_embedding: Any, artifact_path: Path, torch_module: Any) -> None:
        artifact_path.parent.mkdir(parents=True, exist_ok=True)
        torch_module.save(target_embedding.detach().cpu(), str(artifact_path))
        self._log_memory_stage(
            "target_embedding_artifact_saved",
            target_embedding_path=str(artifact_path),
            target_embedding_hash=self._embedding_fingerprint(target_embedding),
        )

    def _get_target_embedding(
        self,
        reference_paths: list[Path],
        converter: Any,
        se_extractor: Any,
        device: str,
        torch_module: Any,
        artifact_path: Path | None = None,
    ) -> Any:
        cache_key = self._reference_audio_cache_key(reference_paths, device)
        reference_hash = self._reference_audio_hash(reference_paths)
        with self._cache_lock:
            target_embedding = self._target_embedding_cache.get(cache_key)
            if target_embedding is not None:
                self._log_memory_stage(
                    "target_embedding_multi_cache_hit",
                    device=device,
                    references=len(reference_paths),
                    reference_audio_sha256=reference_hash,
                    target_embedding_hash=self._embedding_fingerprint(target_embedding),
                )
                return target_embedding
        if artifact_path:
            target_embedding = self._load_cached_target_embedding(artifact_path, device, torch_module)
            if target_embedding is not None:
                # Reuse durable OpenVoice embeddings, but still synthesize fresh segment audio per render line.
                with self._cache_lock:
                    self._target_embedding_cache[cache_key] = target_embedding
                self._log_memory_stage(
                    "target_embedding_artifact_reused",
                    device=device,
                    references=len(reference_paths),
                    reference_audio_sha256=reference_hash,
                    target_embedding_path=str(artifact_path),
                    target_embedding_hash=self._embedding_fingerprint(target_embedding),
                )
                return target_embedding
        embeddings = [
            self._extract_reference_embedding(reference_path, converter, se_extractor, device)
            for reference_path in reference_paths
        ]
        target_embedding = embeddings[0] if len(embeddings) == 1 else torch_module.stack(embeddings).mean(dim=0)
        if artifact_path:
            self._persist_target_embedding(target_embedding, artifact_path, torch_module)
        with self._cache_lock:
            self._target_embedding_cache[cache_key] = target_embedding
        self._log_memory_stage(
            "target_embedding_ready",
            device=device,
            references=len(reference_paths),
            reference_audio_sha256=reference_hash,
            target_embedding_path=str(artifact_path) if artifact_path else None,
            **self._embedding_stats(target_embedding),
        )
        return target_embedding

    def prepare_voice_profile(self, voice_profile: dict[str, Any]) -> dict[str, Any]:
        health = self.healthcheck()
        if not health["available"]:
            raise TTSProviderError(
                code=f"openvoice_{health.get('reason')}",
                message="OpenVoice is unavailable and cannot prepare this voice profile.",
                provider_state={self.provider_name: health},
                suggested_action="Install the OpenVoice repo and checkpoints_v2, or preview with espeak.",
            )
        reference_paths = self._reference_audio_paths(voice_profile)
        if not reference_paths:
            raise TTSProviderError(
                code="reference_audio_missing",
                message="OpenVoice requires at least one authorized reference audio clip.",
                provider_state={self.provider_name: health},
                suggested_action="Upload a short authorized reference clip before preparing the voice.",
            )
        try:
            _tts_cls, se_extractor, converter_cls, torch = self._import_runtime()
        except Exception as exc:
            raise TTSProviderError(
                code="openvoice_package_missing",
                message="OpenVoice runtime packages are not importable.",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Install the OpenVoice and MeloTTS Python packages, or use espeak fallback.",
            ) from exc

        device = health["metadata"].get("device") or "cpu"
        checkpoints_dir = Path(settings.OPENVOICE_CHECKPOINTS_DIR)
        converter_dir = checkpoints_dir / "converter"
        if not converter_dir.exists():
            raise TTSProviderError(
                code="openvoice_models_missing",
                message="OpenVoice is configured but checkpoints_v2 were not found.",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Install OpenVoice checkpoints or preview with espeak.",
            )

        reference_hash = self._reference_audio_hash(reference_paths)
        artifact_path = self._embedding_artifact_path(voice_profile, reference_hash)
        converter = self._get_converter(converter_dir, device, converter_cls)
        target_embedding = self._get_target_embedding(reference_paths, converter, se_extractor, device, torch, artifact_path=artifact_path)
        target_embedding_hash = self._embedding_fingerprint(target_embedding)
        logger.info(
            "openvoice.voice_profile_prepared metadata=%s",
            {
                "voice_profile_id": voice_profile.get("id"),
                "reference_audio_path": [str(path) for path in reference_paths],
                "reference_audio_sha256": reference_hash,
                "target_embedding_path": str(artifact_path),
                "target_embedding_hash": target_embedding_hash,
            },
        )
        return {
            "prepared": True,
            "cached_artifact_path": str(artifact_path),
            "message": f"OpenVoice prepared a cached voice embedding from {len(reference_paths)} reference clip(s).",
            "provider_metadata": {
                "embedding_status": "ready",
                "embedding_ready": True,
                "embedding_artifact_path": str(artifact_path),
                "reference_audio_sha256": reference_hash,
                "target_embedding_hash": target_embedding_hash,
                "active_reference_count": len(reference_paths),
                "reference_audio_mode": "average_all_clips" if len(reference_paths) > 1 else "single_clip",
                "base_speaker": (voice_profile.get("base_speaker") or dict(voice_profile.get("style") or {}).get("base_speaker")),
            },
        }

    def synthesize_line(
        self,
        text: str,
        voice_profile: dict[str, Any],
        output_path: Path,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        health = self.healthcheck()
        if not health["available"]:
            reason = health.get("reason") or "not_available"
            raise TTSProviderError(
                code=f"openvoice_{reason}",
                message="OpenVoice is configured but unavailable in this environment.",
                provider_state={self.provider_name: health},
                suggested_action="Install the OpenVoice repo and checkpoints_v2, or allow espeak fallback.",
            )
        reference_paths = self._reference_audio_paths(voice_profile)
        if not reference_paths:
            raise TTSProviderError(
                code="reference_audio_missing",
                message="OpenVoice requires at least one reference audio clip for cloning.",
                provider_state={self.provider_name: health},
                suggested_action="Upload an authorized reference clip or use the espeak fallback.",
            )

        try:
            TTS, se_extractor, ToneColorConverter, torch = self._import_runtime()
        except Exception as exc:
            raise TTSProviderError(
                code="openvoice_package_missing",
                message="OpenVoice runtime packages are not importable.",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Install the OpenVoice and MeloTTS Python packages, or use espeak fallback.",
            ) from exc

        language_code = self._melo_language(voice_profile.get("language"))
        device = health["metadata"].get("device") or "cpu"
        checkpoints_dir = Path(settings.OPENVOICE_CHECKPOINTS_DIR)
        converter_dir = checkpoints_dir / "converter"
        if not converter_dir.exists():
            raise TTSProviderError(
                code="openvoice_models_missing",
                message="OpenVoice is configured but checkpoints_v2 were not found.",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Install OpenVoice checkpoints or preview with espeak.",
            )
        style = dict(voice_profile.get("style") or {})
        requested_base_speaker = str(voice_profile.get("base_speaker") or style.get("base_speaker") or "").strip()
        if not requested_base_speaker:
            default_source_path = checkpoints_dir / "base_speakers" / "ses" / f"{language_code.lower()}-default.pth"
            if not default_source_path.exists():
                raise TTSProviderError(
                    code="openvoice_source_embedding_missing",
                    message=f"OpenVoice source speaker embedding is missing: {default_source_path}",
                    provider_state={self.provider_name: self.healthcheck()},
                    suggested_action="Install the OpenVoice base speaker embeddings before generating cloned previews.",
                )

        temp_src_path = output_path.with_name(f"{output_path.stem}_src.wav")
        stage_callback = options.get("stage_callback")
        try:
            model = self._get_melo_model(language_code, device, TTS)
            speaker_key, speaker_id = self._melo_speaker_id(model, language_code, voice_profile)
            controls = dict(voice_profile.get("controls") or {})
            unsupported_controls = {
                key: value
                for key, value in controls.items()
                if value is not None and key not in self.supported_control_names
            }
            if unsupported_controls:
                logger.info(
                    "openvoice.performance_controls_unsupported metadata=%s",
                    {
                        "voice_profile_id": voice_profile.get("id"),
                        "unsupported_controls": sorted(unsupported_controls.keys()),
                        "supported_controls": list(self.supported_control_names),
                    },
                )
            speed = float(controls.get("speaking_rate") or 1.0)
            self._log_memory_stage("tts_infer_begin", language=language_code, device=device)
            model.tts_to_file(text, speaker_id, str(temp_src_path), speed=speed)
            self._log_memory_stage("tts_infer_end", language=language_code, device=device)

            converter = self._get_converter(converter_dir, device, ToneColorConverter)
            reference_hash = self._reference_audio_hash(reference_paths)
            artifact_path = self._embedding_artifact_path(voice_profile, reference_hash)
            if callable(stage_callback):
                stage_callback("extracting_reference", 55)
            target_se = self._get_target_embedding(reference_paths, converter, se_extractor, device, torch, artifact_path=artifact_path)
            voice_profile["embedding_path"] = str(artifact_path)
            source_speaker_key = speaker_key.lower().replace("_", "-")
            source_speaker_path = checkpoints_dir / "base_speakers" / "ses" / f"{source_speaker_key}.pth"
            if not source_speaker_path.exists():
                raise TTSProviderError(
                    code="openvoice_source_embedding_missing",
                    message=f"OpenVoice source speaker embedding is missing: {source_speaker_path}",
                    provider_state={self.provider_name: self.healthcheck()},
                    suggested_action="Install the OpenVoice base speaker embeddings before generating cloned previews.",
                )
            source_se = self._get_source_embedding(source_speaker_path, device, torch)
            if callable(stage_callback):
                stage_callback("converting", 70)
            target_embedding_hash = self._embedding_fingerprint(target_se)
            voice_profile["provider_metadata"] = {
                **dict(voice_profile.get("provider_metadata") or {}),
                "embedding_status": "ready",
                "embedding_ready": True,
                "embedding_artifact_path": str(artifact_path),
                "reference_audio_sha256": reference_hash,
                "target_embedding_hash": target_embedding_hash,
                "active_reference_count": len(reference_paths),
                "reference_audio_mode": "average_all_clips" if len(reference_paths) > 1 else "single_clip",
                "base_speaker": source_speaker_key,
                "last_preview_source_audio_path": str(temp_src_path),
                "last_preview_output_path": str(output_path),
                "openvoice_conversion_applied": True,
            }
            logger.info(
                "openvoice.preview_conversion metadata=%s",
                {
                    "voice_profile_id": voice_profile.get("id"),
                    "reference_audio_path": [str(path) for path in reference_paths],
                    "reference_audio_sha256": reference_hash,
                    "target_embedding_path": str(artifact_path),
                    "target_embedding_hash": target_embedding_hash,
                    "base_speaker": source_speaker_key,
                    "source_audio_path": str(temp_src_path),
                    "converted_output_path": str(output_path),
                    "openvoice_conversion_applied": True,
                    "fallback_default_voice_used": False,
                },
            )
            logger.info(
                "OpenVoice conversion applied: true metadata=%s",
                {
                    "source_audio_path": str(temp_src_path),
                    "converted_audio_path": str(output_path),
                    "target_voice_profile_id": voice_profile.get("id"),
                    "target_embedding_hash": target_embedding_hash,
                },
            )
            self._log_memory_stage("voice_conversion_begin", device=device, target_embedding_hash=target_embedding_hash)
            converter.convert(
                audio_src_path=str(temp_src_path),
                src_se=source_se,
                tgt_se=target_se,
                output_path=str(output_path),
                message="@OmniPoster",
            )
            self._log_memory_stage("voice_conversion_end", device=device)
        except TTSProviderError:
            raise
        except Exception as exc:
            raise TTSProviderError(
                code="synthesis_failure",
                message=f"OpenVoice synthesis failed: {exc}",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Check the reference audio, OpenVoice checkpoints, and selected language.",
            ) from exc
        finally:
            if temp_src_path.exists():
                temp_src_path.unlink(missing_ok=True)

        duration_seconds = _audio_stats(output_path)["duration_seconds"]
        controls_applied = self._applied_controls(voice_profile)
        return {
            "audio_path": str(output_path),
            "voice": str(voice_profile.get("display_name") or voice_profile.get("voice") or "openvoice"),
            "duration_seconds": max(duration_seconds, 0.6),
            "provider_used": self.provider_name,
            "controls_applied": controls_applied,
            "reference_audio_count": len(reference_paths),
        }


@dataclass
class _XTTSSelectedRecipeRuntime:
    cache_key: str
    model: Any
    gpt_cond_latent: Any
    speaker_embedding: Any
    inference_parameter_names: tuple[str, ...]
    lock: threading.Lock
    cache_enabled: bool


@dataclass
class _XTTSCheckpointDirectoryRecipe:
    character: str
    provider: str
    checkpoint_dir: Path
    checkpoint_file: Path
    config_path: Path
    vocab_path: Path
    reference_wavs: list[Path]
    language: str
    settings: dict[str, Any]


class XTTSProvider(BaseTTSProvider):
    provider_name = "xtts"
    clone_capable = True
    prepare_capable = False
    supported_control_names = ("speaking_rate",)
    _runtime_cache_lock = threading.Lock()
    _runtime_cache: OrderedDict[str, _XTTSSelectedRecipeRuntime] = OrderedDict()
    _torch_runtime_lock = threading.Lock()
    _torch_runtime_configured = False
    _torch_runtime_metadata: dict[str, Any] = {}

    @classmethod
    def clear_worker_cache(cls) -> None:
        with cls._runtime_cache_lock:
            cls._runtime_cache.clear()
        with cls._torch_runtime_lock:
            cls._torch_runtime_configured = False
            cls._torch_runtime_metadata = {}

    def _profile_stage(self, profiler: Any | None, name: str, **metadata: Any):
        if profiler is not None and hasattr(profiler, "stage"):
            return profiler.stage(name, **metadata)
        return None

    def _recipe_file_identity(self, path: Path) -> dict[str, Any]:
        stat = path.stat()
        return {
            "path": str(path.resolve()),
            "mtime_ns": int(stat.st_mtime_ns),
            "size_bytes": int(stat.st_size),
        }

    def _selected_recipe_cache_key(self, selected_recipe: Any, device: str) -> str:
        payload = {
            "character": selected_recipe.character,
            "provider": selected_recipe.provider,
            "checkpoint_dir": str(selected_recipe.checkpoint_dir.resolve()),
            "checkpoint_file": self._recipe_file_identity(selected_recipe.checkpoint_file),
            "config_path": self._recipe_file_identity(selected_recipe.config_path),
            "vocab_path": self._recipe_file_identity(selected_recipe.vocab_path),
            "device": device,
            "language": selected_recipe.language,
            "settings": dict(selected_recipe.settings),
            "reference_wavs": [self._recipe_file_identity(path) for path in selected_recipe.reference_wavs],
        }
        return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()

    def _checkpoint_directory_recipe(
        self,
        *,
        voice_profile: dict[str, Any],
        checkpoint_dir: Path,
        reference_paths: list[str],
    ) -> _XTTSCheckpointDirectoryRecipe:
        config_path = checkpoint_dir / "config.json"
        vocab_path = checkpoint_dir / "vocab.json"
        checkpoint_file = checkpoint_dir / "model.pth"
        missing = [str(path) for path in (config_path, vocab_path, checkpoint_file) if not path.exists()]
        if missing:
            raise TTSProviderError(
                code="xtts_checkpoint_files_missing",
                message="XTTS checkpoint directory is missing required files.",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Use a checkpoint directory containing config.json, vocab.json, and model.pth.",
            )

        recipe = dict(voice_profile.get("selected_recipe") or {})
        controls = dict(voice_profile.get("controls") or {})
        speed = recipe.get("speed")
        if speed is None:
            speed = recipe.get("speaking_rate")
        if speed is None:
            speed = controls.get("speaking_rate")
        settings_payload = {
            "temperature": float(recipe.get("temperature") or 0.7),
            "speed": float(speed) if speed is not None else 1.0,
            "split_sentences": recipe.get("split_sentences", True),
        }
        character = str(
            voice_profile.get("character_slug")
            or voice_profile.get("display_name")
            or voice_profile.get("id")
            or "xtts"
        )
        return _XTTSCheckpointDirectoryRecipe(
            character=character,
            provider="xtts",
            checkpoint_dir=checkpoint_dir,
            checkpoint_file=checkpoint_file,
            config_path=config_path,
            vocab_path=vocab_path,
            reference_wavs=[Path(path) for path in reference_paths],
            language=str(voice_profile.get("language") or "en"),
            settings=settings_payload,
        )

    def _record_xtts_stage(self, profiler: Any | None, name: str, **metadata: Any) -> None:
        stage = self._profile_stage(profiler, name, **metadata)
        if stage is None:
            return
        with stage:
            pass

    def _configure_torch_runtime(self, torch_module: Any, profiler: Any | None) -> dict[str, Any]:
        with self._torch_runtime_lock:
            if self._torch_runtime_configured:
                return dict(self._torch_runtime_metadata)

            requested_num_threads = max(0, int(settings.XTTS_CPU_NUM_THREADS or 0))
            requested_interop_threads = max(0, int(settings.XTTS_CPU_INTEROP_THREADS or 0))
            metadata: dict[str, Any] = {
                "requested_num_threads": requested_num_threads,
                "requested_interop_threads": requested_interop_threads,
                "inference_mode_enabled": bool(settings.XTTS_TORCH_INFERENCE_MODE_ENABLED),
            }

            def configure() -> None:
                if requested_num_threads > 0 and hasattr(torch_module, "set_num_threads"):
                    try:
                        torch_module.set_num_threads(requested_num_threads)
                    except Exception as exc:
                        metadata["set_num_threads_error"] = f"{type(exc).__name__}: {exc}"
                if requested_interop_threads > 0 and hasattr(torch_module, "set_num_interop_threads"):
                    try:
                        torch_module.set_num_interop_threads(requested_interop_threads)
                    except Exception as exc:
                        metadata["set_num_interop_threads_error"] = f"{type(exc).__name__}: {exc}"
                if hasattr(torch_module, "get_num_threads"):
                    try:
                        metadata["actual_num_threads"] = int(torch_module.get_num_threads())
                    except Exception as exc:
                        metadata["get_num_threads_error"] = f"{type(exc).__name__}: {exc}"
                if hasattr(torch_module, "get_num_interop_threads"):
                    try:
                        metadata["actual_interop_threads"] = int(torch_module.get_num_interop_threads())
                    except Exception as exc:
                        metadata["get_num_interop_threads_error"] = f"{type(exc).__name__}: {exc}"

            if profiler is not None and hasattr(profiler, "stage"):
                with profiler.stage(
                    "xtts.torch_runtime_config",
                    requested_num_threads=requested_num_threads,
                    requested_interop_threads=requested_interop_threads,
                    inference_mode_enabled=metadata["inference_mode_enabled"],
                ):
                    configure()
            else:
                configure()

            self._torch_runtime_configured = True
            self._torch_runtime_metadata = dict(metadata)
            return dict(metadata)

    def _inference_mode_context(self, torch_module: Any):
        if not settings.XTTS_TORCH_INFERENCE_MODE_ENABLED:
            return nullcontext()
        inference_mode = getattr(torch_module, "inference_mode", None)
        if callable(inference_mode):
            try:
                return inference_mode()
            except Exception:
                return nullcontext()
        no_grad = getattr(torch_module, "no_grad", None)
        if callable(no_grad):
            try:
                return no_grad()
            except Exception:
                return nullcontext()
        return nullcontext()

    def _split_sentences_override(self, output_kind: str | None) -> bool | None:
        if output_kind != "preview":
            return None
        raw_value = str(settings.XTTS_PREVIEW_SPLIT_SENTENCES_OVERRIDE or "").strip().lower()
        if raw_value in {"true", "1", "yes", "on"}:
            return True
        if raw_value in {"false", "0", "no", "off"}:
            return False
        return None

    def _load_selected_recipe_runtime(
        self,
        *,
        selected_recipe: Any,
        device: str,
        XttsConfig: Any,
        Xtts: Any,
        profiler: Any | None,
    ) -> _XTTSSelectedRecipeRuntime:
        cache_key = self._selected_recipe_cache_key(selected_recipe, device)
        # The worker cache holds XTTS model/conditioning state only; rendered WAVs remain per-segment artifacts.
        cache_enabled = bool(settings.XTTS_WORKER_CACHE_ENABLED and int(settings.XTTS_WORKER_CACHE_MAX_ENTRIES or 0) > 0)
        if cache_enabled:
            with self._runtime_cache_lock:
                cached = self._runtime_cache.get(cache_key)
                if cached is not None:
                    self._runtime_cache.move_to_end(cache_key)
                    self._record_xtts_stage(
                        profiler,
                        "xtts.runtime_cache_hit",
                        cache_key=cache_key,
                        character=selected_recipe.character,
                        device=device,
                    )
                    self._record_xtts_stage(
                        profiler,
                        "xtts.conditioning_latents_cache_hit",
                        cache_key=cache_key,
                        reference_count=len(selected_recipe.reference_wavs),
                    )
                    return cached

        self._record_xtts_stage(
            profiler,
            "xtts.runtime_cache_miss",
            cache_key=cache_key,
            character=selected_recipe.character,
            device=device,
            cache_enabled=cache_enabled,
        )
        if profiler is not None and hasattr(profiler, "stage"):
            with profiler.stage("xtts.config_load", config_path=selected_recipe.config_path):
                config = XttsConfig()
                config.load_json(str(selected_recipe.config_path))
            with profiler.stage("xtts.model_init", checkpoint_dir=selected_recipe.checkpoint_dir):
                model = Xtts.init_from_config(config)
            with profiler.stage("xtts.checkpoint_load", checkpoint_dir=selected_recipe.checkpoint_dir):
                model.load_checkpoint(config, checkpoint_dir=str(selected_recipe.checkpoint_dir), eval=True)
            with profiler.stage("xtts.device_move", device=device):
                model.to(device)
            with profiler.stage("xtts.conditioning_latents", reference_count=len(selected_recipe.reference_wavs)):
                gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
                    audio_path=[str(path) for path in selected_recipe.reference_wavs]
                )
        else:
            config = XttsConfig()
            config.load_json(str(selected_recipe.config_path))
            model = Xtts.init_from_config(config)
            model.load_checkpoint(config, checkpoint_dir=str(selected_recipe.checkpoint_dir), eval=True)
            model.to(device)
            gpt_cond_latent, speaker_embedding = model.get_conditioning_latents(
                audio_path=[str(path) for path in selected_recipe.reference_wavs]
            )
        inference_parameter_names = tuple(inspect.signature(model.inference).parameters.keys())

        runtime = _XTTSSelectedRecipeRuntime(
            cache_key=cache_key,
            model=model,
            gpt_cond_latent=gpt_cond_latent,
            speaker_embedding=speaker_embedding,
            inference_parameter_names=inference_parameter_names,
            lock=threading.Lock(),
            cache_enabled=cache_enabled,
        )
        if cache_enabled:
            with self._runtime_cache_lock:
                existing = self._runtime_cache.get(cache_key)
                if existing is not None:
                    self._runtime_cache.move_to_end(cache_key)
                    return existing
                self._runtime_cache[cache_key] = runtime
                max_entries = max(1, int(settings.XTTS_WORKER_CACHE_MAX_ENTRIES or 1))
                while len(self._runtime_cache) > max_entries:
                    self._runtime_cache.popitem(last=False)
        return runtime

    def healthcheck(self) -> dict[str, Any]:
        if not settings.XTTS_ENABLED:
            return {"available": False, "reason": "disabled", "metadata": {}}
        model_dir = Path(settings.XTTS_MODEL_DIR) if settings.XTTS_MODEL_DIR else None
        if model_dir and not model_dir.exists():
            return {"available": False, "reason": "missing_model_dir", "metadata": {"model_dir": settings.XTTS_MODEL_DIR}}
        if importlib.util.find_spec("TTS") is None:
            return {"available": False, "reason": "package_missing", "metadata": {"model_dir": str(model_dir) if model_dir else None}}
        return {
            "available": True,
            "reason": None,
            "metadata": {"model_dir": str(model_dir) if model_dir else None, "device": settings.XTTS_DEVICE},
        }

    def _reference_audio_paths(self, voice_profile: dict[str, Any]) -> list[str]:
        metadata = dict(voice_profile.get("provider_metadata") or {})
        paths = [str(path) for path in metadata.get("processed_reference_paths") or [] if path]
        for item in voice_profile.get("reference_audios") or []:
            path = item.get("processed_storage_path") or item.get("storage_path")
            if path and path not in paths:
                paths.append(str(path))
        return [path for path in paths if Path(path).exists()]

    def synthesize_line(
        self,
        text: str,
        voice_profile: dict[str, Any],
        output_path: Path,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        options = dict(options or {})
        profiler = options.get("profiler")
        provider_state = dict(options.get("provider_state") or {})
        health = dict(provider_state.get(self.provider_name) or self.healthcheck())
        if not health["available"]:
            raise TTSProviderError(
                code=f"xtts_{health.get('reason') or 'not_available'}",
                message="XTTS is selected but unavailable in this environment.",
                provider_state={self.provider_name: health},
                suggested_action="Configure XTTS_MODEL_DIR and install Coqui TTS, or choose another provider.",
            )
        selected_character_recipe = self._selected_character_recipe(voice_profile)
        if selected_character_recipe is not None:
            return self._synthesize_selected_character_recipe(
                text=text,
                voice_profile=voice_profile,
                output_path=output_path,
                health=health,
                selected_recipe=selected_character_recipe,
                profiler=profiler,
                output_kind=str(options.get("output_kind") or ""),
            )

        model_checkpoint = Path(str(voice_profile.get("model_checkpoint_path") or settings.XTTS_MODEL_DIR))
        if not model_checkpoint.exists():
            raise TTSProviderError(
                code="xtts_model_missing",
                message=f"XTTS model/checkpoint path is missing: {model_checkpoint}",
                provider_state={self.provider_name: health},
                suggested_action="Attach a trained XTTS model path before rendering this character profile.",
            )
        references = self._reference_audio_paths(voice_profile)
        if not references:
            raise TTSProviderError(
                code="xtts_reference_audio_missing",
                message="XTTS requires at least one processed reference WAV for multi-reference cloning.",
                provider_state={self.provider_name: health},
                suggested_action="Upload and analyze a character reference dataset first.",
            )
        if model_checkpoint.is_dir():
            directory_recipe = self._checkpoint_directory_recipe(
                voice_profile=voice_profile,
                checkpoint_dir=model_checkpoint,
                reference_paths=references,
            )
            return self._synthesize_checkpoint_directory_recipe(
                text=text,
                voice_profile=voice_profile,
                output_path=output_path,
                health=health,
                selected_recipe=directory_recipe,
                profiler=profiler,
                output_kind=str(options.get("output_kind") or ""),
            )
        try:
            from TTS.api import TTS as CoquiTTS  # type: ignore
        except Exception as exc:
            raise TTSProviderError(
                code="xtts_package_missing",
                message="Coqui TTS runtime is not importable.",
                provider_state={self.provider_name: health},
                suggested_action="Install Coqui TTS in the runtime image.",
            ) from exc
        try:
            device = "cpu" if settings.XTTS_DEVICE in {"", "auto"} else settings.XTTS_DEVICE
            if profiler is not None and hasattr(profiler, "stage"):
                with profiler.stage("xtts.model_load", model_checkpoint=model_checkpoint, device=device):
                    model = CoquiTTS(model_path=str(model_checkpoint), config_path=None).to(device)
                with profiler.stage("xtts.inference_and_wav_save", reference_count=len(references), output_path=output_path):
                    model.tts_to_file(
                        text=text,
                        speaker_wav=references,
                        language=str(voice_profile.get("language") or "en"),
                        file_path=str(output_path),
                    )
            else:
                model = CoquiTTS(model_path=str(model_checkpoint), config_path=None).to(device)
                model.tts_to_file(
                    text=text,
                    speaker_wav=references,
                    language=str(voice_profile.get("language") or "en"),
                    file_path=str(output_path),
                )
        except Exception as exc:
            raise TTSProviderError(
                code="xtts_synthesis_failed",
                message=f"XTTS synthesis failed: {exc}",
                provider_state={self.provider_name: health},
                suggested_action="Check the XTTS checkpoint, references, and runtime logs.",
            ) from exc
        duration_seconds = _audio_stats(output_path)["duration_seconds"]
        return {
            "audio_path": str(output_path),
            "voice": str(voice_profile.get("display_name") or "xtts"),
            "duration_seconds": max(duration_seconds, 0.6),
            "provider_used": self.provider_name,
            "controls_applied": {"speaking_rate": (voice_profile.get("controls") or {}).get("speaking_rate")},
            "reference_audio_count": len(references),
        }

    def _synthesize_checkpoint_directory_recipe(
        self,
        *,
        text: str,
        voice_profile: dict[str, Any],
        output_path: Path,
        health: dict[str, Any],
        selected_recipe: _XTTSCheckpointDirectoryRecipe,
        profiler: Any | None = None,
        output_kind: str | None = None,
    ) -> dict[str, Any]:
        try:
            from TTS.tts.configs.xtts_config import XttsConfig  # type: ignore
            from TTS.tts.models.xtts import Xtts  # type: ignore
            import torch  # type: ignore
            import torchaudio  # type: ignore
        except Exception as exc:
            raise TTSProviderError(
                code="xtts_package_missing",
                message="Coqui XTTS runtime is not importable.",
                provider_state={self.provider_name: health},
                suggested_action="Install Coqui TTS, torch, and torchaudio in the runtime image.",
            ) from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        device = "cpu" if settings.XTTS_DEVICE in {"", "auto"} else settings.XTTS_DEVICE
        recipe_settings = dict(selected_recipe.settings)
        try:
            torch_runtime_metadata = self._configure_torch_runtime(torch, profiler)
            if profiler is not None and hasattr(profiler, "add_context"):
                profiler.add_context(xtts_torch_runtime=torch_runtime_metadata)
            runtime = self._load_selected_recipe_runtime(
                selected_recipe=selected_recipe,
                device=device,
                XttsConfig=XttsConfig,
                Xtts=Xtts,
                profiler=profiler,
            )
            inference_kwargs = {
                "temperature": float(recipe_settings.get("temperature", 0.7)),
            }
            if recipe_settings.get("speed") is not None:
                inference_kwargs["speed"] = float(recipe_settings["speed"])
            split_sentences = recipe_settings.get("split_sentences")
            split_override = self._split_sentences_override(output_kind)
            if split_override is not None:
                split_sentences = split_override
            inference_parameter_names = set(runtime.inference_parameter_names)
            if "split_sentences" in inference_parameter_names and split_sentences is not None:
                inference_kwargs["split_sentences"] = bool(split_sentences)
            if "enable_text_splitting" in inference_parameter_names and split_sentences is not None:
                inference_kwargs["enable_text_splitting"] = bool(split_sentences)
            with runtime.lock:
                inference_metadata = {
                    "language": selected_recipe.language,
                    "runtime_cache_key": runtime.cache_key,
                    "inference_mode_enabled": bool(settings.XTTS_TORCH_INFERENCE_MODE_ENABLED),
                    "effective_inference_kwargs": dict(inference_kwargs),
                    "split_sentences_source": "preview_override" if split_override is not None else "recipe",
                    **torch_runtime_metadata,
                }
                if profiler is not None and hasattr(profiler, "stage"):
                    with profiler.stage("xtts.inference", **inference_metadata):
                        with self._inference_mode_context(torch):
                            wav = runtime.model.inference(
                                text,
                                selected_recipe.language,
                                runtime.gpt_cond_latent,
                                runtime.speaker_embedding,
                                **inference_kwargs,
                            )["wav"]
                    with profiler.stage("xtts.wav_save", output_path=output_path, sample_rate=24000):
                        wav_tensor = torch.tensor(wav).unsqueeze(0)
                        torchaudio.save(str(output_path), wav_tensor, 24000)
                else:
                    with self._inference_mode_context(torch):
                        wav = runtime.model.inference(
                            text,
                            selected_recipe.language,
                            runtime.gpt_cond_latent,
                            runtime.speaker_embedding,
                            **inference_kwargs,
                        )["wav"]
                    wav_tensor = torch.tensor(wav).unsqueeze(0)
                    torchaudio.save(str(output_path), wav_tensor, 24000)
        except TTSProviderError:
            raise
        except Exception as exc:
            raise TTSProviderError(
                code="xtts_synthesis_failed",
                message=f"XTTS synthesis failed from checkpoint directory: {exc}",
                provider_state={self.provider_name: health},
                suggested_action="Check the XTTS checkpoint directory, references, and runtime logs.",
            ) from exc

        duration_seconds = _audio_stats(output_path)["duration_seconds"]
        return {
            "audio_path": str(output_path),
            "voice": str(voice_profile.get("display_name") or selected_recipe.character),
            "duration_seconds": max(duration_seconds, 0.6),
            "provider_used": self.provider_name,
            "controls_applied": {
                "temperature": recipe_settings.get("temperature"),
                "speed": recipe_settings.get("speed"),
                "split_sentences": recipe_settings.get("split_sentences"),
                "language": selected_recipe.language,
            },
            "reference_audio_count": len(selected_recipe.reference_wavs),
            "recipe_used": {
                "provider": "xtts",
                "character": selected_recipe.character,
                "checkpoint_dir": str(selected_recipe.checkpoint_dir),
                "config_path": str(selected_recipe.config_path),
                "reference_wavs": [str(path) for path in selected_recipe.reference_wavs],
                "language": selected_recipe.language,
                "settings": recipe_settings,
            },
        }

    def _selected_character_recipe(self, voice_profile: dict[str, Any]):
        character = str(voice_profile.get("character_slug") or "").strip().lower()
        if character != "stewie_griffin":
            return None
        try:
            return validate_selected_character_recipe("stewie_griffin")
        except CharacterVoiceRecipeError as exc:
            raise TTSProviderError(
                code=exc.code,
                message=exc.message,
                provider_state={self.provider_name: {**self.healthcheck(), "selected_recipe_error": exc.as_dict()}},
                suggested_action="Fix backend/storage/voice_models/stewie_griffin/selected_recipe.json and its referenced files.",
            ) from exc

    def _synthesize_selected_character_recipe(
        self,
        *,
        text: str,
        voice_profile: dict[str, Any],
        output_path: Path,
        health: dict[str, Any],
        selected_recipe,
        profiler: Any | None = None,
        output_kind: str | None = None,
    ) -> dict[str, Any]:
        try:
            from TTS.tts.configs.xtts_config import XttsConfig  # type: ignore
            from TTS.tts.models.xtts import Xtts  # type: ignore
            import torch  # type: ignore
            import torchaudio  # type: ignore
        except Exception as exc:
            raise TTSProviderError(
                code="xtts_package_missing",
                message="Coqui XTTS runtime is not importable.",
                provider_state={self.provider_name: health},
                suggested_action="Install Coqui TTS, torch, and torchaudio in the runtime image.",
            ) from exc

        output_path.parent.mkdir(parents=True, exist_ok=True)
        device = "cpu" if settings.XTTS_DEVICE in {"", "auto"} else settings.XTTS_DEVICE
        recipe_settings = dict(selected_recipe.settings)
        try:
            torch_runtime_metadata = self._configure_torch_runtime(torch, profiler)
            if profiler is not None and hasattr(profiler, "add_context"):
                profiler.add_context(xtts_torch_runtime=torch_runtime_metadata)
            runtime = self._load_selected_recipe_runtime(
                selected_recipe=selected_recipe,
                device=device,
                XttsConfig=XttsConfig,
                Xtts=Xtts,
                profiler=profiler,
            )
            inference_kwargs = {
                "temperature": float(recipe_settings.get("temperature", 0.7)),
            }
            if recipe_settings.get("speed") is not None:
                inference_kwargs["speed"] = float(recipe_settings["speed"])
            split_sentences = recipe_settings.get("split_sentences")
            split_override = self._split_sentences_override(output_kind)
            if split_override is not None:
                split_sentences = split_override
            inference_parameter_names = set(runtime.inference_parameter_names)
            if "split_sentences" in inference_parameter_names and split_sentences is not None:
                inference_kwargs["split_sentences"] = bool(split_sentences)
            if "enable_text_splitting" in inference_parameter_names and split_sentences is not None:
                inference_kwargs["enable_text_splitting"] = bool(split_sentences)
            inference_metadata = {
                "language": selected_recipe.language,
                "runtime_cache_key": runtime.cache_key,
                "inference_mode_enabled": bool(settings.XTTS_TORCH_INFERENCE_MODE_ENABLED),
                "effective_inference_kwargs": dict(inference_kwargs),
                "split_sentences_source": "preview_override" if split_override is not None else "recipe",
                **torch_runtime_metadata,
            }
            with runtime.lock:
                if profiler is not None and hasattr(profiler, "stage"):
                    with profiler.stage("xtts.inference", **inference_metadata):
                        with self._inference_mode_context(torch):
                            wav = runtime.model.inference(
                                text,
                                selected_recipe.language,
                                runtime.gpt_cond_latent,
                                runtime.speaker_embedding,
                                **inference_kwargs,
                            )["wav"]
                    with profiler.stage("xtts.wav_save", output_path=output_path, sample_rate=24000):
                        wav_tensor = torch.tensor(wav).unsqueeze(0)
                        torchaudio.save(str(output_path), wav_tensor, 24000)
                else:
                    with self._inference_mode_context(torch):
                        wav = runtime.model.inference(
                            text,
                            selected_recipe.language,
                            runtime.gpt_cond_latent,
                            runtime.speaker_embedding,
                            **inference_kwargs,
                        )["wav"]
                    wav_tensor = torch.tensor(wav).unsqueeze(0)
                    torchaudio.save(str(output_path), wav_tensor, 24000)
        except TTSProviderError:
            raise
        except Exception as exc:
            raise TTSProviderError(
                code="xtts_synthesis_failed",
                message=f"XTTS synthesis failed from selected Stewie recipe: {exc}",
                provider_state={self.provider_name: health},
                suggested_action="Check the Stewie selected recipe checkpoint, references, and runtime logs.",
            ) from exc

        duration_seconds = _audio_stats(output_path)["duration_seconds"]
        recipe_payload = selected_recipe.public_payload()
        logger.info(
            "xtts.selected_recipe character=%s checkpoint_dir=%s reference_wavs=%s language=%s recipe_settings=%s output_wav=%s",
            selected_recipe.character,
            selected_recipe.checkpoint_dir,
            [str(path) for path in selected_recipe.reference_wavs],
            selected_recipe.language,
            recipe_settings,
            output_path,
        )
        return {
            "audio_path": str(output_path),
            "voice": str(voice_profile.get("display_name") or selected_recipe.character),
            "duration_seconds": max(duration_seconds, 0.6),
            "provider_used": self.provider_name,
            "controls_applied": {
                "temperature": recipe_settings.get("temperature"),
                "speed": recipe_settings.get("speed"),
                "split_sentences": recipe_settings.get("split_sentences"),
                "language": selected_recipe.language,
            },
            "reference_audio_count": len(selected_recipe.reference_wavs),
            "recipe_used": recipe_payload,
            "golden_preview_wav": str(selected_recipe.golden_preview_wav),
        }


class RVCProvider(BaseTTSProvider):
    provider_name = "rvc"
    clone_capable = True
    prepare_capable = False
    supported_control_names = (
        "speaking_rate",
        "pitch",
        "rvc_pitch_shift",
        "rvc_index_rate",
        "rvc_protect",
        "rvc_filter_radius",
    )

    def healthcheck(self) -> dict[str, Any]:
        if not settings.RVC_ENABLED:
            return {"available": False, "reason": "disabled", "metadata": {}}
        model_dir = Path(settings.RVC_MODELS_DIR) if settings.RVC_MODELS_DIR else None
        if not model_dir or not model_dir.exists():
            return {"available": False, "reason": "missing_model_dir", "metadata": {"model_dir": settings.RVC_MODELS_DIR}}
        if not settings.RVC_INFER_COMMAND:
            return {"available": False, "reason": "missing_infer_command", "metadata": {"model_dir": str(model_dir)}}
        rmvpe_path = Path(settings.RVC_RMVPE_PATH) if settings.RVC_RMVPE_PATH else None
        return {
            "available": True,
            "reason": None,
            "metadata": {
                "model_dir": str(model_dir),
                "rmvpe_path": str(rmvpe_path) if rmvpe_path else None,
                "pitch_extractor": "rmvpe" if rmvpe_path and rmvpe_path.exists() else "runtime_default",
            },
        }

    def synthesize_line(
        self,
        text: str,
        voice_profile: dict[str, Any],
        output_path: Path,
        options: dict[str, Any],
    ) -> dict[str, Any]:
        health = self.healthcheck()
        if not health["available"]:
            raise TTSProviderError(
                code=f"rvc_{health.get('reason') or 'not_available'}",
                message="RVC is selected but unavailable in this environment.",
                provider_state={self.provider_name: health},
                suggested_action="Configure RVC model paths and inference command before rendering this character profile.",
            )
        model_path = Path(str(voice_profile.get("model_checkpoint_path") or ""))
        if not model_path.exists():
            raise TTSProviderError(
                code="rvc_model_missing",
                message=f"RVC model/checkpoint path is missing: {model_path}",
                provider_state={self.provider_name: health},
                suggested_action="Attach a trained RVC model path before rendering this character profile.",
            )
        source_path = output_path.with_name(f"{output_path.stem}_source.wav")
        source_profile = {
            **voice_profile,
            "provider": "espeak",
            "fallback_provider": "espeak",
        }
        source_result = EspeakProvider().synthesize_line(text, source_profile, source_path, options)
        controls = dict(voice_profile.get("controls") or {})
        recipe = dict(voice_profile.get("selected_recipe") or {})
        replacements = {
            "input": str(source_path),
            "output": str(output_path),
            "model": str(model_path),
            "index": str(recipe.get("model_index_path") or ""),
            "pitch_shift": str(recipe.get("rvc_pitch_shift", controls.get("rvc_pitch_shift", 0))),
            "index_rate": str(recipe.get("rvc_index_rate", controls.get("rvc_index_rate", 0.75))),
            "protect": str(recipe.get("rvc_protect", controls.get("rvc_protect", 0.33))),
            "filter_radius": str(recipe.get("rvc_filter_radius", controls.get("rvc_filter_radius", 3))),
            "rmvpe": settings.RVC_RMVPE_PATH or "",
        }
        command_template = settings.RVC_INFER_COMMAND.format(**replacements)
        try:
            subprocess.run(shlex.split(command_template), check=True, capture_output=True, text=True)
        except Exception as exc:
            raise TTSProviderError(
                code="rvc_conversion_failed",
                message=f"RVC conversion failed: {exc}",
                provider_state={self.provider_name: health},
                suggested_action="Check the RVC inference command, model path, index, and RMVPE configuration.",
            ) from exc
        finally:
            source_path.unlink(missing_ok=True)
        duration_seconds = _audio_stats(output_path)["duration_seconds"]
        return {
            "audio_path": str(output_path),
            "voice": str(voice_profile.get("display_name") or "rvc"),
            "duration_seconds": max(duration_seconds, source_result["duration_seconds"], 0.6),
            "provider_used": self.provider_name,
            "controls_applied": {
                "speaking_rate": controls.get("speaking_rate"),
                "rvc_pitch_shift": replacements["pitch_shift"],
                "rvc_index_rate": replacements["index_rate"],
                "rvc_protect": replacements["protect"],
                "rvc_filter_radius": replacements["filter_radius"],
            },
            "reference_audio_count": len(voice_profile.get("reference_audios") or []),
        }


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers: dict[str, BaseTTSProvider] = {
            "espeak": EspeakProvider(),
            "openvoice": OpenVoiceProvider(),
            "xtts": XTTSProvider(),
            "rvc": RVCProvider(),
        }

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


class TTSOrchestrator:
    def __init__(self, registry: ProviderRegistry | None = None) -> None:
        self.registry = registry or ProviderRegistry()

    def provider_capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "provider": capability.provider,
                "available": capability.available,
                "reason": capability.reason,
                "supports_voice_cloning": capability.supports_voice_cloning,
                "supports_prepare": capability.supports_prepare,
                "supported_controls": capability.supported_controls,
                "metadata": capability.metadata,
            }
            for capability in self.registry.capabilities()
        ]

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
        selection_order = self._selection_order(voice_profile, requested_provider, fallback_allowed)
        selected_provider = next(
            (provider_name for provider_name in selection_order if (state.get(provider_name) or {}).get("available")),
            selection_order[0] if selection_order else None,
        )
        return {
            "selection_order": selection_order,
            "selected_provider": selected_provider,
            "provider_state": state,
            "fallback_allowed": fallback_allowed,
        }

    def _selection_order(self, voice_profile: dict[str, Any], requested_provider: str | None, fallback_allowed: bool) -> list[str]:
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

    def _voice_cache_key(self, provider_name: str, text: str, voice_profile: dict[str, Any], provider: BaseTTSProvider) -> str:
        provider_metadata = dict(voice_profile.get("provider_metadata") or {})
        reference_hash = hashlib.sha256(
            "|".join(
                sorted(
                    str(
                        item.get("processed_sha256")
                        or item.get("sha256")
                        or item.get("processed_storage_path")
                        or item.get("storage_path")
                        or ""
                    )
                    for item in voice_profile.get("reference_audios") or []
                )
            ).encode("utf-8")
        ).hexdigest()
        reference_hash = str(provider_metadata.get("reference_audio_sha256") or reference_hash)
        controls = dict(voice_profile.get("controls") or {})
        style = dict(voice_profile.get("style") or {})
        fallback_settings = dict(voice_profile.get("fallback_voice_settings") or {})
        selected_recipe = dict(voice_profile.get("selected_recipe") or {})
        supported_control_names = tuple(getattr(provider, "supported_control_names", ()) or ())
        if provider_name == "openvoice":
            cache_settings = {
                "controls": {key: controls.get(key) for key in supported_control_names if controls.get(key) is not None},
                "language": voice_profile.get("language"),
                "model_id": voice_profile.get("model_id"),
                "base_speaker": voice_profile.get("base_speaker") or style.get("base_speaker"),
                "style_preset": style.get("style_preset"),
                "embedding_path": voice_profile.get("embedding_path") or provider_metadata.get("embedding_artifact_path"),
                "target_embedding_hash": provider_metadata.get("target_embedding_hash"),
            }
        elif provider_name in {"xtts", "rvc"}:
            cache_settings = {
                "controls": {key: controls.get(key) for key in supported_control_names if controls.get(key) is not None},
                "language": voice_profile.get("language"),
                "model_id": voice_profile.get("model_id"),
                "model_checkpoint_path": voice_profile.get("model_checkpoint_path"),
                "selected_recipe": selected_recipe,
                "base_speaker": voice_profile.get("base_speaker") or style.get("base_speaker"),
                "style_preset": style.get("style_preset"),
            }
        else:
            cache_settings = {
                "controls": {key: controls.get(key) for key in supported_control_names if controls.get(key) is not None},
                "fallback": {
                    "voice": fallback_settings.get("voice") or voice_profile.get("voice") or voice_profile.get("espeak_voice"),
                    "rate": fallback_settings.get("rate") or voice_profile.get("espeak_rate"),
                    "pitch": fallback_settings.get("pitch") or voice_profile.get("espeak_pitch"),
                    "word_gap": fallback_settings.get("word_gap") if fallback_settings.get("word_gap") is not None else voice_profile.get("espeak_word_gap"),
                    "amplitude": fallback_settings.get("amplitude") or voice_profile.get("espeak_amplitude"),
                },
            }
        style_hash = hashlib.sha256(repr(cache_settings).encode("utf-8")).hexdigest()
        payload = "|".join(
            [
                provider_name,
                text,
                str(voice_profile.get("id") or ""),
                reference_hash,
                style_hash,
            ]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

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
                provider_failures[provider_name] = {
                    "code": "unknown_provider",
                    "message": f"Unknown TTS provider requested: {provider_name}",
                }
                logger.warning("tts.select skipped_provider=%s reason=unknown_provider", provider_name)
                continue
            if not provider_health.get("available"):
                provider_failures[provider_name] = {
                    "code": provider_health.get("reason") or "not_available",
                    "message": f"Provider {provider_name} is not available in this environment.",
                    "provider_state": provider_health,
                }
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
            # XTTS render segments must not be satisfied from the shared preview/audio cache.
            cache_enabled = provider_name != "xtts" and not recipe_requires_validation
            cache_key = self._voice_cache_key(provider_name, text, voice_profile, provider) if cache_enabled else None
            cache_hit = self._copy_cache_if_present(cache_key, output_path) if cache_key else False
            if cache_hit:
                duration_seconds = _audio_stats(output_path)["duration_seconds"]
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
                return SynthesisResult(
                    audio_path=str(output_path),
                    voice=str(voice_profile.get("voice") or voice_profile.get("espeak_voice") or voice_profile.get("display_name") or provider_name),
                    duration_seconds=max(duration_seconds, 0.6),
                    provider_used=provider_name,
                    fallback_used=index > 0,
                    controls_applied=controls_applied,
                    reference_audio_count=len(voice_profile.get("reference_audios") or []),
                    provider_state=state,
                    cache_hit=True,
                    voice_profile_id=str(voice_profile.get("id") or ""),
                    provider_failures=dict(provider_failures),
                    fallback_reason=next(iter(provider_failures.values()), {}).get("code") if index > 0 and provider_failures else None,
                    recipe_used=dict(voice_profile.get("selected_recipe") or {}),
                    golden_preview_wav=None,
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
                return SynthesisResult(
                    audio_path=result["audio_path"],
                    voice=result["voice"],
                    duration_seconds=result["duration_seconds"],
                    provider_used=result["provider_used"],
                    fallback_used=index > 0,
                    controls_applied=result.get("controls_applied") or {},
                    reference_audio_count=int(result.get("reference_audio_count") or 0),
                    provider_state=state,
                    cache_hit=False,
                    voice_profile_id=str(voice_profile.get("id") or ""),
                    provider_failures=dict(provider_failures),
                    fallback_reason=next(iter(provider_failures.values()), {}).get("code") if index > 0 and provider_failures else None,
                    recipe_used=dict(result.get("recipe_used") or voice_profile.get("selected_recipe") or {}),
                    golden_preview_wav=result.get("golden_preview_wav"),
                )
            except TTSProviderError as exc:
                last_error = exc
                fallback_attempted = fallback_attempted or index > 0 or index + 1 < len(selection_order)
                provider_failures[provider_name] = {
                    "code": exc.code,
                    "message": exc.message,
                    "provider_state": exc.provider_state,
                    "fallback_attempted": exc.fallback_attempted,
                    "suggested_action": exc.suggested_action,
                }
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
            # Unique filenames keep each script segment inspectable even when text and speaker repeat.
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
        return {name for name, state in self.orchestrator.provider_state().items() if state.get("available")}

    def _provider_for_voice_profile(self, voice_profile: dict[str, Any], available_providers: set[str]) -> str:
        requested_provider = str(
            voice_profile.get("tts_provider") or voice_profile.get("provider") or "espeak"
        ).strip().lower()
        if requested_provider in available_providers:
            return requested_provider
        fallback = str(voice_profile.get("fallback_provider") or "").strip().lower()
        if fallback and fallback in available_providers:
            return fallback
        if "espeak" in available_providers:
            return "espeak"
        raise TTSProviderError(
            code="no_provider_available",
            message="Voice preview synthesis is unavailable because no supported TTS provider is installed.",
            provider_state=self.orchestrator.provider_state(),
            suggested_action="Install espeak-ng or configure OpenVoice before previewing voices.",
        )

    def _ephemeral_profile(self, speaker: str, payload: dict[str, Any]) -> dict[str, Any]:
        provider = str(payload.get("tts_provider") or payload.get("provider") or "espeak").lower()
        return {
            "id": f"ephemeral_{_slugify(speaker)}",
            "display_name": speaker,
            "provider": provider,
            "fallback_provider": str(payload.get("fallback_provider") or "espeak").lower(),
            "voice": payload.get("voice") or settings.TTS_ESPEAK_VOICE_SLOT_1,
            "espeak_voice": payload.get("voice") or settings.TTS_ESPEAK_VOICE_SLOT_1,
            "espeak_rate": payload.get("rate") if payload.get("rate") is not None else settings.TTS_ESPEAK_RATE,
            "espeak_pitch": payload.get("pitch") if payload.get("pitch") is not None else settings.TTS_ESPEAK_PITCH,
            "espeak_word_gap": payload.get("word_gap") if payload.get("word_gap") is not None else settings.TTS_ESPEAK_WORD_GAP,
            "espeak_amplitude": payload.get("amplitude") if payload.get("amplitude") is not None else settings.TTS_ESPEAK_AMPLITUDE,
            "controls": dict(payload.get("controls") or {}),
            "style": dict(payload.get("style") or {}),
            "fallback_voice_settings": {
                "voice": payload.get("voice"),
                "rate": payload.get("rate"),
                "pitch": payload.get("pitch"),
                "word_gap": payload.get("word_gap"),
                "amplitude": payload.get("amplitude"),
            },
            "reference_audios": list(payload.get("reference_audios") or []),
            "language": payload.get("language") or "en",
            "model_id": payload.get("model_id"),
            "embedding_path": payload.get("embedding_path"),
            "fallback_allowed": provider not in {"openvoice", "xtts", "rvc"},
        }

    def _manifest_profile_for_speaker(self, speaker: str) -> dict[str, Any] | None:
        manifest_entry = self.voice_manifest.get(speaker) or self.voice_manifest_by_slug.get(_slugify(speaker))
        if not manifest_entry:
            return None
        voice_profile = dict(manifest_entry.get("voice_profile") or {})
        if not voice_profile:
            return None
        provider = str(manifest_entry.get("requested_provider") or voice_profile.get("provider") or "espeak").lower()
        default_fallback_allowed = provider not in {"openvoice", "xtts", "rvc"}
        fallback_allowed = bool(manifest_entry.get("fallback_allowed", voice_profile.get("fallback_allowed", default_fallback_allowed)))
        return {
            **voice_profile,
            "requested_provider": provider,
            "fallback_allowed": fallback_allowed,
        }

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
                profile = preset_model.voice_profile
                return {
                    "id": profile.id,
                    "display_name": preset_model.display_name,
                    "provider": profile.provider,
                    "fallback_provider": profile.fallback_provider,
                    "voice": profile.espeak_voice,
                    "espeak_voice": profile.espeak_voice,
                    "espeak_rate": profile.espeak_rate,
                    "espeak_pitch": profile.espeak_pitch,
                    "espeak_word_gap": profile.espeak_word_gap,
                    "espeak_amplitude": profile.espeak_amplitude,
                    "controls": dict(profile.controls_json or {}),
                    "style": dict(profile.style_json or {}),
                    "fallback_voice_settings": dict(profile.fallback_voice_settings_json or {}),
                    "reference_audios": [
                        {
                            "id": item.id,
                            "storage_path": item.storage_path,
                            "original_storage_path": item.original_storage_path,
                            "processed_storage_path": item.processed_storage_path or item.storage_path,
                            "sha256": item.sha256,
                            "processed_sha256": item.processed_sha256,
                            "mime_type": item.mime_type,
                            "validation_status": item.validation_status,
                            "validation": dict(item.validation_json or {}),
                        }
                        for item in profile.reference_audios
                    ],
                    "language": profile.language,
                    "model_id": profile.model_id,
                    "model_checkpoint_path": profile.model_checkpoint_path,
                    "selected_recipe": dict(profile.selected_recipe_json or {}),
                    "reference_dataset_id": profile.reference_dataset_id,
                    "character_slug": profile.character_slug,
                    "calibration_score": profile.calibration_score,
                    "last_verified_render_job_id": profile.last_verified_render_job_id,
                    "embedding_path": profile.embedding_path,
                    "provider_metadata": dict(profile.provider_metadata_json or {}),
                    "fallback_allowed": str(profile.provider or "").lower() not in {"openvoice", "xtts", "rvc"},
                }
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

    def synthesize_dialogue(self, parsed_lines: list[dict[str, Any]], work_dir: Path) -> list[SpeechSegment]:
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


def _audio_stats(audio_path: Path) -> dict[str, float | int]:
    with wave.open(str(audio_path), "rb") as handle:
        frame_rate = handle.getframerate()
        frame_count = handle.getnframes()
        channels = handle.getnchannels()
    duration_seconds = float(frame_count / frame_rate) if frame_rate else 0.0
    return {
        "sample_rate": frame_rate,
        "frame_count": frame_count,
        "channels": channels,
        "duration_seconds": duration_seconds,
    }
