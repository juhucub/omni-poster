from __future__ import annotations

from pathlib import Path
from typing import Any

from app.domains.render.planning import RenderPreset


FINAL_VIDEO_OVERLAY_FILTER = "[0:v][1:v]overlay=0:0:format=auto[tmp];[tmp][2:v]overlay=0:0:format=auto[v]"


def final_video_ffmpeg_command(
    *,
    background_path: Path,
    static_overlay_path: Path,
    dynamic_overlay_path: Path,
    audio_path: Path,
    output_path: Path,
    preset: RenderPreset,
    duration_seconds: float,
    audio_bitrate: str,
    ffmpeg_threads: int,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-i",
        str(background_path),
        "-loop",
        "1",
        "-i",
        str(static_overlay_path),
        "-i",
        str(dynamic_overlay_path),
        "-i",
        str(audio_path),
        "-filter_complex",
        FINAL_VIDEO_OVERLAY_FILTER,
        "-map",
        "[v]",
        "-map",
        "3:a",
        "-t",
        f"{duration_seconds:.3f}",
        "-c:v",
        "libx264",
        "-preset",
        preset.x264_preset,
        "-crf",
        str(preset.crf),
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        audio_bitrate,
        "-movflags",
        "+faststart",
        "-threads",
        str(ffmpeg_threads),
        "-shortest",
        str(output_path),
    ]


def dynamic_overlay_concat_list_contents(frame_entries: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for entry in frame_entries:
        escaped = str(Path(entry["path"]).resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
        lines.append(f"duration {float(entry['duration_seconds']):.3f}")
    if frame_entries:
        escaped = str(Path(frame_entries[-1]["path"]).resolve()).replace("'", "'\\''")
        lines.append(f"file '{escaped}'")
    return "\n".join(lines) + "\n"


def dynamic_overlay_ffmpeg_command(
    *,
    concat_list_path: Path,
    output_path: Path,
    preset: RenderPreset,
) -> list[str]:
    return [
        "ffmpeg",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_list_path),
        "-vf",
        f"fps={preset.fps},format=rgba",
        "-c:v",
        "qtrle",
        str(output_path),
    ]
