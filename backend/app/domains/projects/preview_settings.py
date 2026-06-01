from __future__ import annotations

from typing import Any

from app.schemas import ProjectPreviewLayout

DEFAULT_CHARACTER_SCALE: float = 1.0
DEFAULT_CHAT_FONT_SIZE_PX: int = 18


def clamp_float(value: Any, minimum: float, maximum: float, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        numeric = default
    return min(max(numeric, minimum), maximum)


def clamp_int(value: Any, minimum: int, maximum: int, default: int) -> int:
    try:
        numeric = int(value)
    except (TypeError, ValueError):
        numeric = default
    return min(max(numeric, minimum), maximum)


def normalize_preview_layout(payload: dict | None) -> ProjectPreviewLayout:
    layout = dict(payload or {})
    # These bounds mirror the renderer so UI state cannot request off-canvas portraits or unreadable captions.
    return ProjectPreviewLayout(
        character_scale=clamp_float(layout.get("character_scale"), 0.75, 1.5, DEFAULT_CHARACTER_SCALE),
        chat_font_size_px=clamp_int(layout.get("chat_font_size_px"), 12, 32, DEFAULT_CHAT_FONT_SIZE_PX),
    )
