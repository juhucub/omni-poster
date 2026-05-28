from __future__ import annotations

from pathlib import Path


def ffprobe_json_command(path: str | Path) -> list[str]:
    return [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
