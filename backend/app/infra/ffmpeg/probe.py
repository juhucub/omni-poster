from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.infra.ffmpeg.commands import ffprobe_json_command
from app.infra.ffmpeg.errors import FFprobeInvalidOutputError
from app.infra.ffmpeg.executor import run_ffprobe_json


def probe_media(path: str | Path, *, timeout: float | None = 10) -> dict[str, Any]:
    raw_output = run_ffprobe_json(ffprobe_json_command(path), timeout=timeout)
    try:
        payload = json.loads(raw_output or "{}")
    except json.JSONDecodeError as exc:
        raise FFprobeInvalidOutputError("ffprobe returned invalid JSON.") from exc
    if not isinstance(payload, dict):
        raise FFprobeInvalidOutputError("ffprobe JSON output must be an object.")
    return payload


def get_media_duration_seconds(path: str | Path, *, timeout: float | None = 10) -> float:
    payload = probe_media(path, timeout=timeout)
    duration = (payload.get("format") or {}).get("duration")
    if duration is None or duration == "":
        return 0.0
    try:
        return float(duration)
    except (TypeError, ValueError) as exc:
        raise FFprobeInvalidOutputError("ffprobe media duration was not numeric.") from exc


def has_audio_stream(path: str | Path, *, timeout: float | None = 10) -> bool:
    return _has_stream_type(path, "audio", timeout=timeout)


def has_video_stream(path: str | Path, *, timeout: float | None = 10) -> bool:
    return _has_stream_type(path, "video", timeout=timeout)


def _has_stream_type(path: str | Path, stream_type: str, *, timeout: float | None = 10) -> bool:
    payload = probe_media(path, timeout=timeout)
    streams = payload.get("streams") or []
    if not isinstance(streams, list):
        return False
    return any(isinstance(stream, dict) and stream.get("codec_type") == stream_type for stream in streams)
