from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.domains.voice.providers.base import BaseTTSProvider, TTSProviderError


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
