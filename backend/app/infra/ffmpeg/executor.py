from __future__ import annotations

import subprocess

from app.infra.ffmpeg.errors import FFprobeCommandError, FFprobeNotFoundError


def run_ffprobe_json(command: list[str], *, timeout: float | None = 10) -> str:
    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise FFprobeNotFoundError("ffprobe is required but was not found.") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() if exc.stderr else str(exc)
        raise FFprobeCommandError(message) from exc
    except subprocess.TimeoutExpired as exc:
        if timeout is None:
            raise FFprobeCommandError("ffprobe timed out") from exc
        raise FFprobeCommandError(f"ffprobe timed out after {timeout:g}s") from exc
    return result.stdout or "{}"
