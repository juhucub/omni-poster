from __future__ import annotations

from pathlib import Path
import wave


def audio_stats(audio_path: Path) -> dict[str, float | int]:
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
