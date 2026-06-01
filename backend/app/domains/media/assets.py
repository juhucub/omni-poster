from __future__ import annotations

BACKGROUND_PRESET_EXTENSIONS: frozenset[str] = frozenset(
    {".mp4", ".webm", ".mpeg", ".png", ".jpg", ".jpeg", ".webp"}
)


def upload_asset_kind(mime_type: str) -> str:
    return "background_image" if mime_type.startswith("image/") else "background_video"


def preset_asset_kind(mime_type: str) -> str:
    return "background_image" if mime_type.startswith("image/") else "background_preset"
