from __future__ import annotations


class FFmpegInfraError(RuntimeError):
    """Base error for low-level FFmpeg/ffprobe infrastructure failures."""


class FFprobeNotFoundError(FFmpegInfraError):
    """Raised when ffprobe is not available in the runtime."""


class FFprobeCommandError(FFmpegInfraError):
    """Raised when ffprobe exits unsuccessfully."""


class FFprobeInvalidOutputError(FFmpegInfraError):
    """Raised when ffprobe returns unreadable or unexpected JSON."""
