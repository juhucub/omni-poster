from __future__ import annotations

from pathlib import Path


def ffmpeg_concat_file_line(audio_path: Path) -> str:
    escaped_audio_path = str(audio_path).replace("'", "'\\''")
    return f"file '{escaped_audio_path}'"


def ffmpeg_concat_file_contents(audio_paths: list[Path]) -> str:
    return "\n".join(ffmpeg_concat_file_line(path) for path in audio_paths) + "\n"


def concat_demuxer_audio_command(
    *,
    concat_list_path: Path,
    output_path: Path,
    sample_rate: int,
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
        "-acodec",
        "pcm_s16le",
        "-ar",
        str(sample_rate),
        "-ac",
        "2",
        str(output_path),
    ]


def concat_filter_complex(audio_count: int, sample_rate: int) -> str:
    if audio_count == 1:
        return f"[0:a]aresample={sample_rate}[a]"
    return "".join(f"[{index}:a]" for index in range(audio_count)) + f"concat=n={audio_count}:v=0:a=1,aresample={sample_rate}[a]"


def multi_input_audio_command(
    *,
    audio_paths: list[Path],
    output_path: Path,
    sample_rate: int,
) -> list[str]:
    command = ["ffmpeg", "-y"]
    for audio_path in audio_paths:
        command.extend(["-i", str(audio_path)])
    command.extend(
        [
            "-filter_complex",
            concat_filter_complex(len(audio_paths), sample_rate),
            "-map",
            "[a]",
            "-acodec",
            "pcm_s16le",
            "-ar",
            str(sample_rate),
            "-ac",
            "2",
            str(output_path),
        ]
    )
    return command
