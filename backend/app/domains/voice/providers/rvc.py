from __future__ import annotations

import shlex
import subprocess
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.domains.voice.providers.base import BaseTTSProvider, TTSProviderError
from app.domains.voice.providers.espeak import EspeakProvider
from app.domains.voice.synthesis import audio_stats as _audio_stats


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
