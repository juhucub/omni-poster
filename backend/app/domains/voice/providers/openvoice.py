from __future__ import annotations

import hashlib
import importlib.util
import logging
import resource
import sys
import threading
import uuid
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.domains.voice.providers.base import BaseTTSProvider, TTSProviderError
from app.domains.voice.profiles import (
    reference_audio_content_hash_from_paths,
    voice_embedding_artifact_path_for_reference,
)
from app.domains.voice.synthesis import audio_stats as _audio_stats

logger = logging.getLogger(__name__)


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

    def _get_melo_model(self, language_code: str, device: str, tts_cls: Any, profiler: Any | None = None) -> Any:
        cache_key = (language_code, device)
        with self._cache_lock:
            model = self._melo_model_cache.get(cache_key)
            if model is not None:
                self._log_memory_stage("melo_model_cache_hit", language=language_code, device=device)
                self._record_profile_stage(
                    profiler,
                    "openvoice.melo_model_cache_hit",
                    language=language_code,
                    device=device,
                    cache_key=f"{language_code}:{device}",
                )
                return model
        self._log_memory_stage("melo_model_init_begin", language=language_code, device=device)
        with self._profile_stage(profiler, "openvoice.melo_model_init", language=language_code, device=device):
            model = tts_cls(language=language_code, device=device)
        with self._cache_lock:
            self._melo_model_cache[cache_key] = model
        self._log_memory_stage("melo_model_init_end", language=language_code, device=device)
        return model

    def _get_converter(self, converter_dir: Path, device: str, converter_cls: Any, profiler: Any | None = None) -> Any:
        cache_key = (str(converter_dir.resolve()), device)
        with self._cache_lock:
            converter = self._converter_cache.get(cache_key)
            if converter is not None:
                self._log_memory_stage("converter_cache_hit", device=device)
                self._record_profile_stage(
                    profiler,
                    "openvoice.converter_cache_hit",
                    converter_dir=converter_dir,
                    device=device,
                )
                return converter
        self._log_memory_stage("converter_init_begin", device=device)
        with self._profile_stage(profiler, "openvoice.converter_load", converter_dir=converter_dir, device=device):
            converter = converter_cls(str(converter_dir / "config.json"), device=device)
            converter.load_ckpt(str(converter_dir / "checkpoint.pth"))
        with self._cache_lock:
            self._converter_cache[cache_key] = converter
        self._log_memory_stage("converter_init_end", device=device)
        return converter

    def _get_source_embedding(self, base_speaker_path: Path, device: str, torch_module: Any, profiler: Any | None = None) -> Any:
        cache_key = (str(base_speaker_path.resolve()), device)
        with self._cache_lock:
            source_embedding = self._source_embedding_cache.get(cache_key)
            if source_embedding is not None:
                self._log_memory_stage("source_embedding_cache_hit", device=device)
                self._record_profile_stage(
                    profiler,
                    "openvoice.source_embedding_cache_hit",
                    device=device,
                    base_speaker_path=base_speaker_path,
                )
                return source_embedding
        self._log_memory_stage("source_embedding_load_begin", device=device)
        with self._profile_stage(profiler, "openvoice.source_embedding_load", device=device, base_speaker_path=base_speaker_path):
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

    def _extract_reference_embedding(
        self,
        reference_path: Path,
        converter: Any,
        se_extractor: Any,
        device: str,
        profiler: Any | None = None,
    ) -> Any:
        cache_key = self._reference_audio_cache_key([reference_path], device)
        with self._cache_lock:
            target_embedding = self._target_embedding_cache.get(cache_key)
            if target_embedding is not None:
                self._log_memory_stage("target_embedding_cache_hit", device=device, reference_audio_path=str(reference_path))
                self._record_profile_stage(
                    profiler,
                    "openvoice.target_embedding_cache_hit",
                    device=device,
                    reference_audio_path=str(reference_path),
                )
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
            with self._profile_stage(
                profiler,
                "openvoice.target_embedding_extract",
                device=device,
                reference_audio_path=str(reference_path),
                reference_audio_sha256=reference_hash,
            ):
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

    def _load_cached_target_embedding(self, artifact_path: Path, device: str, torch_module: Any, profiler: Any | None = None) -> Any | None:
        if not artifact_path.exists():
            return None
        cache_key = self._artifact_cache_key(artifact_path, device)
        with self._cache_lock:
            target_embedding = self._target_embedding_cache.get(cache_key)
            if target_embedding is not None:
                self._log_memory_stage("target_embedding_artifact_cache_hit", device=device)
                self._record_profile_stage(
                    profiler,
                    "openvoice.target_embedding_artifact_cache_hit",
                    device=device,
                    target_embedding_path=str(artifact_path),
                )
                return target_embedding
        self._log_memory_stage("target_embedding_artifact_load_begin", device=device, target_embedding_path=str(artifact_path))
        with self._profile_stage(
            profiler,
            "openvoice.target_embedding_artifact_load",
            device=device,
            target_embedding_path=str(artifact_path),
        ):
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
        profiler: Any | None = None,
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
                self._record_profile_stage(
                    profiler,
                    "openvoice.target_embedding_multi_cache_hit",
                    device=device,
                    references=len(reference_paths),
                    reference_audio_sha256=reference_hash,
                )
                return target_embedding
        if artifact_path:
            if profiler is None:
                target_embedding = self._load_cached_target_embedding(artifact_path, device, torch_module)
            else:
                target_embedding = self._load_cached_target_embedding(artifact_path, device, torch_module, profiler)
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
            self._extract_reference_embedding(reference_path, converter, se_extractor, device, profiler)
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
        options = dict(options or {})
        profiler = options.get("profiler")
        provider_state = dict(options.get("provider_state") or {})
        if self.provider_name in provider_state:
            health = dict(provider_state.get(self.provider_name) or {})
            self._record_profile_stage(
                profiler,
                "openvoice.provider_health_reused",
                available=health.get("available"),
                reason=health.get("reason"),
            )
        else:
            with self._profile_stage(profiler, "openvoice.provider_health_check"):
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
            with self._profile_stage(profiler, "openvoice.runtime_import"):
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
            model = (
                self._get_melo_model(language_code, device, TTS)
                if profiler is None
                else self._get_melo_model(language_code, device, TTS, profiler)
            )
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
            with self._profile_stage(
                profiler,
                "openvoice.base_tts_inference",
                language=language_code,
                device=device,
                speaker_key=speaker_key,
                speed=speed,
                text_length=len(text),
            ):
                model.tts_to_file(text, speaker_id, str(temp_src_path), speed=speed)
            self._log_memory_stage("tts_infer_end", language=language_code, device=device)

            converter = (
                self._get_converter(converter_dir, device, ToneColorConverter)
                if profiler is None
                else self._get_converter(converter_dir, device, ToneColorConverter, profiler)
            )
            reference_hash = self._reference_audio_hash(reference_paths)
            artifact_path = self._embedding_artifact_path(voice_profile, reference_hash)
            if callable(stage_callback):
                stage_callback("extracting_reference", 55)
            target_se = (
                self._get_target_embedding(
                    reference_paths,
                    converter,
                    se_extractor,
                    device,
                    torch,
                    artifact_path=artifact_path,
                )
                if profiler is None
                else self._get_target_embedding(
                    reference_paths,
                    converter,
                    se_extractor,
                    device,
                    torch,
                    artifact_path=artifact_path,
                    profiler=profiler,
                )
            )
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
            source_se = (
                self._get_source_embedding(source_speaker_path, device, torch)
                if profiler is None
                else self._get_source_embedding(source_speaker_path, device, torch, profiler)
            )
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
            with self._profile_stage(
                profiler,
                "openvoice.voice_conversion",
                device=device,
                target_embedding_hash=target_embedding_hash,
                output_path=output_path,
            ):
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
