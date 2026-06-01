from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import logging
import threading
from collections import OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.domains.voice.providers.base import BaseTTSProvider, TTSProviderError
from app.domains.voice.profiles.recipes import CharacterVoiceRecipeError, validate_selected_character_recipe
from app.domains.voice.synthesis import audio_stats as _audio_stats

logger = logging.getLogger(__name__)


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
        max_entries = max(1, int(settings.XTTS_WORKER_CACHE_MAX_ENTRIES or 1)) if cache_enabled else 0
        cache_size_before = 0
        if cache_enabled:
            with self._runtime_cache_lock:
                cache_size_before = len(self._runtime_cache)
                cached = self._runtime_cache.get(cache_key)
                if cached is not None:
                    self._runtime_cache.move_to_end(cache_key)
                    cache_size_after = len(self._runtime_cache)
                    self._record_xtts_stage(
                        profiler,
                        "xtts.runtime_cache_hit",
                        cache_key=cache_key,
                        character=selected_recipe.character,
                        device=device,
                        cache_enabled=cache_enabled,
                        cache_size_before=cache_size_before,
                        cache_size_after=cache_size_after,
                        max_entries=max_entries,
                    )
                    self._record_xtts_stage(
                        profiler,
                        "xtts.conditioning_latents_cache_hit",
                        cache_key=cache_key,
                        reference_count=len(selected_recipe.reference_wavs),
                        cache_size_after=cache_size_after,
                    )
                    return cached

        self._record_xtts_stage(
            profiler,
            "xtts.runtime_cache_miss",
            cache_key=cache_key,
            character=selected_recipe.character,
            device=device,
            cache_enabled=cache_enabled,
            cache_size_before=cache_size_before,
            max_entries=max_entries,
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
                    self._record_xtts_stage(
                        profiler,
                        "xtts.runtime_cache_race_hit",
                        cache_key=cache_key,
                        character=selected_recipe.character,
                        device=device,
                        cache_enabled=cache_enabled,
                        cache_size_after=len(self._runtime_cache),
                        max_entries=max_entries,
                    )
                    return existing
                self._runtime_cache[cache_key] = runtime
                evicted_key_prefixes: list[str] = []
                while len(self._runtime_cache) > max_entries:
                    evicted_key, _evicted_runtime = self._runtime_cache.popitem(last=False)
                    evicted_key_prefixes.append(evicted_key[:12])
                self._record_xtts_stage(
                    profiler,
                    "xtts.runtime_cache_store",
                    cache_key=cache_key,
                    character=selected_recipe.character,
                    device=device,
                    cache_enabled=cache_enabled,
                    cache_size_before=cache_size_before,
                    cache_size_after=len(self._runtime_cache),
                    max_entries=max_entries,
                    evicted_cache_key_prefixes=evicted_key_prefixes,
                )
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
