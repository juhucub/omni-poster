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

logger = logging.getLogger(__name__)


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

    def synthesize_dialogue(self, parsed_lines: list[dict], work_dir: Path) -> list[SpeechSegment]:
        work_dir.mkdir(parents=True, exist_ok=True)
        segments: list[SpeechSegment] = []
        slot_map: dict[str, int] = {}
        provider = self._detect_provider()
        logger.info(
            "Synthesizing dialogue with provider=%s speech_rate=%s espeak_rate=%s espeak_pitch=%s espeak_word_gap=%s espeak_amplitude=%s",
            provider,
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
            voice = self.DEFAULT_VOICES[slot_index % len(self.DEFAULT_VOICES)]
            aiff_path = work_dir / f"{index:03d}_{self._slugify(speaker)}_{uuid.uuid4().hex}.aiff"
            audio_path = work_dir / f"{index:03d}_{self._slugify(speaker)}_{uuid.uuid4().hex}.wav"
            if provider == "macos":
                self._run_say(text=text, voice=voice, output_path=aiff_path)
                self._convert_to_wav(source_path=aiff_path, output_path=audio_path)
            elif provider == "espeak":
                voice = self.espeak_voices[slot_index % len(self.espeak_voices)]
                self._run_espeak(text=text, voice=voice, output_path=audio_path)
            else:
                raise RuntimeError("No supported text-to-speech provider is installed.")
            audio_stats = self._audio_stats(audio_path)
            duration_seconds = audio_stats["duration_seconds"]
            logger.info(
                "Generated speech segment speaker=%s voice=%s provider=%s rate=%s pitch=%s sample_rate=%s channels=%s duration=%.2fs path=%s",
                speaker,
                voice,
                provider,
                self.espeak_rate if provider == "espeak" else self.speech_rate,
                self.espeak_pitch if provider == "espeak" else "n/a",
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

    def _detect_provider(self) -> str:
        if shutil.which("say") and shutil.which("afconvert"):
            return "macos"
        if shutil.which("espeak-ng") or shutil.which("espeak"):
            return "espeak"
        return "none"

    def _run_say(self, *, text: str, voice: str, output_path: Path) -> None:
        commands = [
            ["say", "-v", voice, "-r", str(self.speech_rate), "-o", str(output_path), text],
            ["say", "-r", str(self.speech_rate), "-o", str(output_path), text],
        ]
        for command in commands:
            try:
                subprocess.run(command, check=True, capture_output=True, text=True)
                return
            except FileNotFoundError as exc:
                raise RuntimeError("macOS text-to-speech is unavailable. Install or configure a TTS provider.") from exc
            except subprocess.CalledProcessError as exc:
                logger.warning("Speech synthesis attempt failed with %s: %s", command, exc.stderr.strip())
        raise RuntimeError("Speech synthesis failed for one or more dialogue lines.")

    def _run_espeak(self, *, text: str, voice: str, output_path: Path) -> None:
        binary = shutil.which("espeak-ng") or shutil.which("espeak")
        if not binary:
            raise RuntimeError("Linux text-to-speech is unavailable. Install espeak-ng in the worker image.")
        command = [
            binary,
            "-w",
            str(output_path),
            "-s",
            str(self.espeak_rate),
            "-p",
            str(self.espeak_pitch),
            "-g",
            str(self.espeak_word_gap),
            "-a",
            str(self.espeak_amplitude),
            "-v",
            voice,
            text,
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Speech synthesis failed for Linux provider: {exc.stderr.strip()}") from exc

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
            raise RuntimeError("macOS audio conversion tooling is unavailable for dialogue rendering.") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Could not convert synthesized speech to WAV: {exc.stderr.strip()}") from exc

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
            raise RuntimeError(f"Synthesized speech file is empty: {audio_path}")
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

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
        return slug or "speaker"
