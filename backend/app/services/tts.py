from __future__ import annotations

import hashlib
import importlib.util
import logging
import os
import re
import resource
import shutil
import subprocess
import sys
import threading
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.core.config import settings
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

    def _melo_speaker_id(self, model: Any, language_code: str) -> Any:
        speaker_map = dict(getattr(getattr(model, "hps", None), "data", None).spk2id)
        preferred = [
            f"{language_code}-Default",
            f"{language_code}_DEFAULT",
            next(iter(speaker_map.keys()), None),
        ]
        for key in preferred:
            if key in speaker_map:
                return speaker_map[key]
        return next(iter(speaker_map.values()))

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
            if not item.get("storage_path"):
                continue
            try:
                reference_id = int(item.get("id") or 0)
            except (TypeError, ValueError):
                reference_id = 0
            if reference_id not in processed_reference_ids:
                fallback_paths.append(Path(item["storage_path"]))
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
        base_speaker_path = checkpoints_dir / "base_speakers" / "ses" / f"{language_code.lower()}-default.pth"
        if not converter_dir.exists():
            raise TTSProviderError(
                code="openvoice_models_missing",
                message="OpenVoice is configured but checkpoints_v2 were not found.",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Install OpenVoice checkpoints or preview with espeak.",
            )
        if not base_speaker_path.exists():
            raise TTSProviderError(
                code="openvoice_source_embedding_missing",
                message=f"OpenVoice source speaker embedding is missing: {base_speaker_path}",
                provider_state={self.provider_name: self.healthcheck()},
                suggested_action="Install the OpenVoice base speaker embeddings before generating cloned previews.",
            )

        temp_src_path = output_path.with_name(f"{output_path.stem}_src.wav")
        stage_callback = options.get("stage_callback")
        try:
            model = self._get_melo_model(language_code, device, TTS)
            speaker_id = self._melo_speaker_id(model, language_code)
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
            source_se = self._get_source_embedding(base_speaker_path, device, torch)
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


class ProviderRegistry:
    def __init__(self) -> None:
        self.providers: dict[str, BaseTTSProvider] = {
            "espeak": EspeakProvider(),
            "openvoice": OpenVoiceProvider(),
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
        reference_hash = hashlib.sha256(
            "|".join(sorted(str(item.get("sha256") or item.get("storage_path") or "") for item in voice_profile.get("reference_audios") or [])).encode("utf-8")
        ).hexdigest()
        controls = dict(voice_profile.get("controls") or {})
        fallback_settings = dict(voice_profile.get("fallback_voice_settings") or {})
        supported_control_names = tuple(getattr(provider, "supported_control_names", ()) or ())
        if provider_name == "openvoice":
            cache_settings = {
                "controls": {key: controls.get(key) for key in supported_control_names if controls.get(key) is not None},
                "language": voice_profile.get("language"),
                "model_id": voice_profile.get("model_id"),
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
            cache_key = self._voice_cache_key(provider_name, text, voice_profile, provider)
            cache_hit = self._copy_cache_if_present(cache_key, output_path)
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
                result = provider.synthesize_line(text=text, voice_profile=voice_profile, output_path=output_path, options=options)
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
        segments: list[SpeechSegment] = []
        slot_map: dict[str, int] = {}
        for index, line in enumerate(lines):
            speaker = str(line.get("speaker") or f"Speaker {index + 1}").strip()
            text = str(line.get("text") or "").strip()
            if not text:
                continue
            slot_index = slot_map.setdefault(speaker, len(slot_map))
            voice_profile = voice_profile_map[speaker]
            output_path = output_dir / f"{index:03d}_{_slugify(speaker)}_{uuid.uuid4().hex}.wav"
            result = self.synthesize_line(
                text=text,
                voice_profile=voice_profile,
                output_path=output_path,
                requested_provider=requested_provider,
                fallback_allowed=fallback_allowed,
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
    ) -> None:
        self.db = db
        self.project_id = project_id
        self.speaker_voice_overrides = {
            _slugify(speaker): dict(config) for speaker, config in (speaker_voice_overrides or {}).items()
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
        return {
            "id": f"ephemeral_{_slugify(speaker)}",
            "display_name": speaker,
            "provider": str(payload.get("tts_provider") or payload.get("provider") or "espeak").lower(),
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
        }

    def _resolved_profile_for_speaker(self, speaker: str, slot_index: int) -> dict[str, Any]:
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
                            "sha256": item.sha256,
                            "mime_type": item.mime_type,
                        }
                        for item in profile.reference_audios
                    ],
                    "language": profile.language,
                    "model_id": profile.model_id,
                    "embedding_path": profile.embedding_path,
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
            voice_profile_map[speaker] = self._resolved_profile_for_speaker(speaker, slot_index)
        return self.orchestrator.synthesize_dialogue(
            lines=parsed_lines,
            voice_profile_map=voice_profile_map,
            output_dir=work_dir,
            fallback_allowed=True,
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
