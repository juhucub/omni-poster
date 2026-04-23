from __future__ import annotations

import logging
import re
import shutil
import subprocess
import uuid
import wave
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.core.config import settings
from app.services.character_presets import resolve_character_preset_for_speaker

logger = logging.getLogger(__name__)


class TextToSpeechError(RuntimeError):
    """Raised when local TTS synthesis cannot proceed."""


@dataclass(frozen=True)
class SpeechSegment:
    speaker: str
    text: str
    voice: str
    slot_index: int
    audio_path: str
    duration_seconds: float


#Goal - Peter, brian, and stewie presets Configured
class LocalSpeechService:
    DEFAULT_VOICES = ("Samantha", "Daniel")
    DEFAULT_ESPEAK_VOICES = ("en-us+f3", "en-gb+m3")

    def __init__(
        self,
        speech_rate: int | None = None,
        espeak_rate: int | None = None,
        espeak_pitch: int | None = None,
        espeak_word_gap: int | None = None,
        espeak_amplitude: int | None = None,
        espeak_voices: tuple[str, str] | None = None,
        speaker_voice_overrides: dict[str, dict] | None = None,
    ) -> None:
        self.speech_rate = speech_rate or settings.TTS_SPEECH_RATE
        self.espeak_rate = espeak_rate or settings.TTS_ESPEAK_RATE
        self.espeak_pitch = espeak_pitch or settings.TTS_ESPEAK_PITCH
        self.espeak_word_gap = espeak_word_gap if espeak_word_gap is not None else settings.TTS_ESPEAK_WORD_GAP
        self.espeak_amplitude = espeak_amplitude or settings.TTS_ESPEAK_AMPLITUDE
        self.espeak_voices = espeak_voices or (
            settings.TTS_ESPEAK_VOICE_SLOT_1,
            settings.TTS_ESPEAK_VOICE_SLOT_2,
        )
        self.speaker_voice_overrides = {
            self._slugify(speaker): dict(config) for speaker, config in (speaker_voice_overrides or {}).items()
        }

    def synthesize_dialogue(self, parsed_lines: list[dict], work_dir: Path) -> list[SpeechSegment]:
        work_dir.mkdir(parents=True, exist_ok=True)
        segments: list[SpeechSegment] = []
        slot_map: dict[str, int] = {}
        available_providers = self._available_providers()
        logger.info(
            "Synthesizing dialogue with providers=%s speech_rate=%s espeak_rate=%s espeak_pitch=%s espeak_word_gap=%s espeak_amplitude=%s",
            sorted(available_providers),
            self.speech_rate,
            self.espeak_rate,
            self.espeak_pitch,
            self.espeak_word_gap,
            self.espeak_amplitude,
        )

        for index, line in enumerate(parsed_lines):
            speaker = str(line.get("speaker") or f"Speaker {index + 1}").strip()
            text = str(line.get("text") or "").strip()
            if not text:
                continue

            slot_index = slot_map.setdefault(speaker, len(slot_map))
            voice_profile = self._voice_profile_for_speaker(speaker, slot_index)
            provider = self._provider_for_voice_profile(voice_profile, available_providers)
            voice = self._resolve_voice_name(voice_profile, slot_index, provider)
            aiff_path = work_dir / f"{index:03d}_{self._slugify(speaker)}_{uuid.uuid4().hex}.aiff"
            audio_path = work_dir / f"{index:03d}_{self._slugify(speaker)}_{uuid.uuid4().hex}.wav"
            if provider == "macos":
                self._run_say(
                    text=text,
                    voice=voice,
                    output_path=aiff_path,
                    rate=int(voice_profile.get("speech_rate") or self.speech_rate),
                )
                self._convert_to_wav(source_path=aiff_path, output_path=audio_path)
            elif provider == "espeak":
                self._run_espeak(
                    text=text,
                    voice=voice,
                    output_path=audio_path,
                    rate=int(voice_profile.get("rate") or self.espeak_rate),
                    pitch=int(voice_profile.get("pitch") or self.espeak_pitch),
                    word_gap=int(voice_profile.get("word_gap") if voice_profile.get("word_gap") is not None else self.espeak_word_gap),
                    amplitude=int(voice_profile.get("amplitude") or self.espeak_amplitude),
                )
            else:
                raise RuntimeError("No supported text-to-speech provider is installed.")
            audio_stats = self._audio_stats(audio_path)
            duration_seconds = audio_stats["duration_seconds"]
            logger.info(
                "Generated speech segment speaker=%s voice=%s provider=%s rate=%s pitch=%s sample_rate=%s channels=%s duration=%.2fs path=%s",
                speaker,
                voice,
                provider,
                voice_profile.get("rate") if provider == "espeak" else voice_profile.get("speech_rate", self.speech_rate),
                voice_profile.get("pitch") if provider == "espeak" else "n/a",
                audio_stats["sample_rate"],
                audio_stats["channels"],
                duration_seconds,
                audio_path,
            )
            segments.append(
                SpeechSegment(
                    speaker=speaker,
                    text=text,
                    voice=voice,
                    slot_index=slot_index,
                    audio_path=str(audio_path),
                    duration_seconds=max(duration_seconds, 0.6),
                )
            )

        if not segments:
            raise RuntimeError("Cannot render a dialogue video without spoken lines.")
        return segments

    def _available_providers(self) -> set[str]:
        available: set[str] = set()
        say_binary = shutil.which("say")
        afconvert_binary = shutil.which("afconvert")
        espeak_ng_binary = shutil.which("espeak-ng")
        espeak_binary = shutil.which("espeak")
        if say_binary and afconvert_binary:
            available.add("macos")
        if espeak_ng_binary or espeak_binary:
            available.add("espeak")
        logger.info(
            "TTS provider discovery say=%s afconvert=%s espeak_ng=%s espeak=%s available=%s",
            bool(say_binary),
            bool(afconvert_binary),
            bool(espeak_ng_binary),
            bool(espeak_binary),
            sorted(available),
        )
        return available

    def _run_say(self, *, text: str, voice: str, output_path: Path, rate: int) -> None:
        commands = [
            ["say", "-v", voice, "-r", str(rate), "-o", str(output_path), text],
            ["say", "-r", str(rate), "-o", str(output_path), text],
        ]
        for command in commands:
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                return
            except FileNotFoundError as exc:
                raise TextToSpeechError("macOS text-to-speech is unavailable. Install or configure a TTS provider.") from exc
            except subprocess.CalledProcessError as exc:
                logger.warning("Speech synthesis attempt failed with %s: %s", command, exc.stderr.strip())
        raise TextToSpeechError("Speech synthesis failed for one or more dialogue lines.")

    def _run_espeak(
        self,
        *,
        text: str,
        voice: str,
        output_path: Path,
        rate: int,
        pitch: int,
        word_gap: int,
        amplitude: int,
    ) -> None:
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            raise TextToSpeechError("Linux text-to-speech is unavailable. Install espeak-ng in the runtime image.")
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
            raise TextToSpeechError(f"Speech synthesis failed for Linux provider: {exc.stderr.strip()}") from exc

    def _convert_to_wav(self, *, source_path: Path, output_path: Path) -> None:
        command = [
            "afconvert",
            "-f",
            "WAVE",
            "-d",
            "LEI16@22050",
            str(source_path),
            str(output_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError as exc:
            raise TextToSpeechError("macOS audio conversion tooling is unavailable for dialogue rendering.") from exc
        except subprocess.CalledProcessError as exc:
            raise TextToSpeechError(f"Could not convert synthesized speech to WAV: {exc.stderr.strip()}") from exc

    def _measure_duration(self, audio_path: Path) -> float:
        with wave.open(str(audio_path), "rb") as handle:
            frame_rate = handle.getframerate()
            frame_count = handle.getnframes()
        return float(frame_count / frame_rate) if frame_rate else 0.0

    def build_audio_clip(self, audio_path: str):
        from moviepy import AudioArrayClip

        with wave.open(audio_path, "rb") as handle:
            frame_rate = handle.getframerate()
            channels = handle.getnchannels()
            raw_frames = handle.readframes(handle.getnframes())

        samples = np.frombuffer(raw_frames, dtype=np.int16).astype(np.float32) / 32768.0
        if samples.size == 0:
            raise TextToSpeechError(f"Synthesized speech file is empty: {audio_path}")
        peak = float(np.max(np.abs(samples)))
        if peak > 0:
            samples = samples * min(0.92 / peak, 1.35)
        if channels > 1:
            samples = samples.reshape((-1, channels))
        else:
            samples = samples.reshape((-1, 1))
        return AudioArrayClip(samples, fps=frame_rate)

    def _audio_stats(self, audio_path: Path) -> dict[str, float | int]:
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

    def _voice_profile_for_speaker(self, speaker: str, slot_index: int) -> dict:
        override = self.speaker_voice_overrides.get(self._slugify(speaker))
        if override:
            return {
                "tts_provider": override.get("tts_provider", "espeak"),
                "voice": override.get("voice", self.espeak_voices[slot_index % len(self.espeak_voices)]),
                "rate": override.get("rate", self.espeak_rate),
                "pitch": override.get("pitch", self.espeak_pitch),
                "word_gap": override.get("word_gap", self.espeak_word_gap),
                "amplitude": override.get("amplitude", self.espeak_amplitude),
                "speech_rate": override.get("speech_rate", self.speech_rate),
            }

        preset = resolve_character_preset_for_speaker(speaker)
        if preset:
            return {
                "tts_provider": preset.get("tts_provider", "espeak"),
                "voice": preset.get("voice", self.espeak_voices[slot_index % len(self.espeak_voices)]),
                "rate": int(preset.get("rate") or self.espeak_rate),
                "pitch": int(preset.get("pitch") or self.espeak_pitch),
                "word_gap": int(preset.get("word_gap") if preset.get("word_gap") is not None else self.espeak_word_gap),
                "amplitude": int(preset.get("amplitude") or self.espeak_amplitude),
                "speech_rate": self.speech_rate,
            }

        return {
            "tts_provider": "espeak",
            "voice": self.espeak_voices[slot_index % len(self.espeak_voices)],
            "rate": self.espeak_rate,
            "pitch": self.espeak_pitch,
            "word_gap": self.espeak_word_gap,
            "amplitude": self.espeak_amplitude,
            "speech_rate": self.speech_rate,
        }

    def _provider_for_voice_profile(self, voice_profile: dict, available_providers: set[str]) -> str:
        requested_provider = str(voice_profile.get("tts_provider") or "").strip().lower()
        if requested_provider in available_providers:
            return requested_provider
        if "espeak" in available_providers and requested_provider in {"", "linux"}:
            return "espeak"
        if "macos" in available_providers and requested_provider in {"", "say"}:
            return "macos"
        if "espeak" in available_providers:
            logger.info(
                "Requested TTS provider %s is unavailable; falling back to espeak for voice=%s",
                requested_provider or "default",
                voice_profile.get("voice"),
            )
            return "espeak"
        if "macos" in available_providers:
            logger.info(
                "Requested TTS provider %s is unavailable; falling back to macOS speech for voice=%s",
                requested_provider or "default",
                voice_profile.get("voice"),
            )
            return "macos"
        raise TextToSpeechError(
            "Voice preview synthesis is unavailable because no supported local TTS provider is installed. "
            "Install espeak-ng for Linux/dev Docker or use macOS with say and afconvert available."
        )

    def _resolve_voice_name(self, voice_profile: dict, slot_index: int, provider: str) -> str:
        configured_voice = str(voice_profile.get("voice") or "").strip()
        if provider == "espeak":
            return configured_voice or self.espeak_voices[slot_index % len(self.espeak_voices)]
        if configured_voice and self._looks_like_macos_voice(configured_voice):
            return configured_voice
        return self._fallback_macos_voice(configured_voice, slot_index)

    def _looks_like_macos_voice(self, voice: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]*", voice))

    def _fallback_macos_voice(self, configured_voice: str, slot_index: int) -> str:
        voice_lower = configured_voice.lower()
        if "+f" in voice_lower:
            return "Samantha"
        if "+m" in voice_lower:
            return "Daniel"
        return self.DEFAULT_VOICES[slot_index % len(self.DEFAULT_VOICES)]

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return slug or "speaker"
