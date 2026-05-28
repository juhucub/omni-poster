from __future__ import annotations

import math
from typing import Any

from app.core.config import settings
from app.domains.render.planning import RenderPreset


def render_preset_for_output_kind(output_kind: str, settings=settings) -> RenderPreset:
    mode = output_kind if output_kind in {"preview", "draft", "final", "debug"} else "preview"
    if mode == "draft":
        return RenderPreset(
            mode=mode,
            width=settings.RENDER_DRAFT_WIDTH,
            height=settings.RENDER_DRAFT_HEIGHT,
            fps=settings.RENDER_DRAFT_FPS_CAP,
            x264_preset=settings.RENDER_DRAFT_ENCODE_PRESET,
            crf=settings.RENDER_DRAFT_CRF,
        )
    if mode == "preview":
        return RenderPreset(
            mode=mode,
            width=settings.RENDER_PREVIEW_WIDTH,
            height=settings.RENDER_PREVIEW_HEIGHT,
            fps=settings.RENDER_PREVIEW_FPS_CAP,
            x264_preset=settings.RENDER_PREVIEW_ENCODE_PRESET,
            crf=settings.RENDER_PREVIEW_CRF,
        )
    return RenderPreset(
        mode=mode,
        width=settings.RENDER_EXPORT_WIDTH,
        height=settings.RENDER_EXPORT_HEIGHT,
        fps=settings.RENDER_EXPORT_FPS_CAP,
        x264_preset=settings.RENDER_EXPORT_ENCODE_PRESET,
        crf=settings.RENDER_EXPORT_CRF,
        debug_audio_extract=mode == "debug",
    )


def background_cache_duration_seconds(duration_seconds: float, preset: RenderPreset) -> float:
    if preset.mode in {"preview", "draft"}:
        return max(duration_seconds, math.ceil(duration_seconds / 5.0) * 5.0)
    return duration_seconds


def normalize_render_layout(render_settings: dict | None) -> dict[str, float | int]:
    payload = dict(render_settings or {})
    layout = dict(payload.get("layout") or payload)
    try:
        character_scale = float(layout.get("character_scale", 1.0))
    except (TypeError, ValueError):
        character_scale = 1.0
    try:
        chat_font_size_px = int(layout.get("chat_font_size_px", 18))
    except (TypeError, ValueError):
        chat_font_size_px = 18
    return {
        "character_scale": min(max(character_scale, 0.75), 1.5),
        "chat_font_size_px": min(max(chat_font_size_px, 12), 32),
    }
