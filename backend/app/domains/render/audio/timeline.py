from __future__ import annotations

import wave
from pathlib import Path
from typing import Any


def wav_duration_seconds(audio_path: Path) -> float:
    with wave.open(str(audio_path), "rb") as handle:
        frame_rate = handle.getframerate()
        frame_count = handle.getnframes()
    if frame_rate <= 0:
        return 0.0
    return float(frame_count) / float(frame_rate)


def timeline_duration_seconds(file_duration: float, segment_duration: float, minimum_duration: float = 0.6) -> float:
    return max(float(file_duration or 0.0), float(segment_duration or 0.0), minimum_duration)


def build_timed_segment(
    segment: Any,
    duration_seconds: float,
    normalized_audio_path: Path | None = None,
) -> dict[str, Any]:
    item: dict[str, Any] = {
        "segment": segment,
        "duration_seconds": duration_seconds,
    }
    if normalized_audio_path is not None:
        item["normalized_audio_path"] = normalized_audio_path
    return item


def build_timed_segments_from_durations(
    segments: list[Any],
    durations: list[float],
    normalized_paths: list[Path] | None = None,
) -> list[dict[str, Any]]:
    timed_segments: list[dict[str, Any]] = []
    if normalized_paths is None:
        for segment, file_duration in zip(segments, durations, strict=False):
            timed_segments.append(
                build_timed_segment(
                    segment,
                    timeline_duration_seconds(file_duration, getattr(segment, "duration_seconds", 0.0)),
                )
            )
        return timed_segments

    for segment, file_duration, normalized_path in zip(segments, durations, normalized_paths, strict=False):
        timed_segments.append(
            build_timed_segment(
                segment,
                timeline_duration_seconds(file_duration, getattr(segment, "duration_seconds", 0.0)),
                normalized_path,
            )
        )
    return timed_segments
