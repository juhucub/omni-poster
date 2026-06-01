from __future__ import annotations

ALLOWED_BACKGROUND_VIDEO_TYPES: frozenset[str] = frozenset({"video/mp4", "video/webm", "video/mpeg"})
ALLOWED_BACKGROUND_IMAGE_TYPES: frozenset[str] = frozenset({"image/png", "image/jpeg", "image/webp"})
ALLOWED_BACKGROUND_TYPES: frozenset[str] = ALLOWED_BACKGROUND_VIDEO_TYPES | ALLOWED_BACKGROUND_IMAGE_TYPES


def detect_background_mime_type(header: bytes) -> str | None:
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "image/webp"
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return "video/mp4"
    if header.startswith(b"\x1aE\xdf\xa3"):
        return "video/webm"
    if header.startswith(b"\x00\x00\x01\xba") or header.startswith(b"\x00\x00\x01\xb3"):
        return "video/mpeg"
    return None


def background_duration_exceeds_limit(duration_seconds: float, max_duration: float, mime_type: str) -> bool:
    if max_duration <= 0 or mime_type not in ALLOWED_BACKGROUND_VIDEO_TYPES:
        return False
    return duration_seconds > max_duration
