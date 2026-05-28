from __future__ import annotations

from pathlib import Path

from app.domains.render.planning import RenderPreset


def background_video_filter(*, style_preset: str, preset: RenderPreset) -> str:
    scale_crop = (
        f"scale={preset.width}:{preset.height}:force_original_aspect_ratio=increase,"
        f"crop={preset.width}:{preset.height},fps={preset.fps}"
    )
    if style_preset == "blur":
        return f"{scale_crop},boxblur=20:1,format=yuv420p"
    if style_preset == "grayscale":
        return f"{scale_crop},hue=s=0,format=yuv420p"
    return f"{scale_crop},format=yuv420p"


def background_normalization_ffmpeg_command(
    *,
    background_path: Path,
    output_path: Path,
    style_preset: str,
    preset: RenderPreset,
    duration_seconds: float,
    is_image_background: bool,
    ffmpeg_threads: int,
) -> list[str]:
    command = ["ffmpeg", "-y"]
    if is_image_background:
        command.extend(["-loop", "1", "-i", str(background_path), "-t", f"{duration_seconds:.3f}"])
    else:
        command.extend(["-stream_loop", "-1", "-i", str(background_path), "-t", f"{duration_seconds:.3f}"])
    command.extend(
        [
            "-vf",
            background_video_filter(style_preset=style_preset, preset=preset),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            preset.x264_preset,
            "-crf",
            str(preset.crf),
            "-pix_fmt",
            "yuv420p",
            "-threads",
            str(ffmpeg_threads),
            str(output_path),
        ]
    )
    return command
