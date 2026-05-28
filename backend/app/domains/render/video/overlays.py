from __future__ import annotations

import textwrap
from typing import Any

from app.domains.render.geometry import (
    ACTIVE_PORTRAIT_HEIGHT,
    ACTIVE_POSITIONS,
    BASE_PORTRAIT_HEIGHT,
    BASE_POSITIONS,
    CAPTION_CARD_POSITION,
    CAPTION_CARD_SIZE,
    REFERENCE_CANVAS_HEIGHT,
    layout_scaled_height,
    scale_box,
)
from app.domains.render.planning import RenderPreset


STATIC_OVERLAY_PORTRAIT_ALPHA = 0.26
SPEAKER_PALETTES = (
    {
        "accent": (105, 224, 255, 255),
        "body": (19, 84, 122, 238),
        "plate": (35, 155, 208, 228),
    },
    {
        "accent": (255, 196, 87, 255),
        "body": (134, 76, 16, 238),
        "plate": (214, 120, 36, 228),
    },
)


def speaker_palette(slot_index: int) -> dict[str, tuple[int, int, int, int]]:
    return dict(SPEAKER_PALETTES[slot_index % len(SPEAKER_PALETTES)])


def speaker_initials(speaker: str) -> str:
    return "".join(part[0] for part in speaker.split()[:2]).upper() or "S"


def speaker_slots_from_lines(parsed_lines: list[dict[str, Any]]) -> dict[str, int]:
    slots: dict[str, int] = {}
    for index, line in enumerate(parsed_lines):
        speaker = str(line.get("speaker") or f"Speaker {index + 1}").strip()
        text = str(line.get("text") or "").strip()
        if speaker and text and speaker not in slots:
            slots[speaker] = len(slots)
    return slots


def primary_cast_segments(segments: list[Any]) -> list[Any]:
    cast: list[Any] = []
    seen: set[str] = set()
    for segment in segments:
        if segment.speaker in seen:
            continue
        cast.append(segment)
        seen.add(segment.speaker)
        if len(cast) == 2:
            break
    return cast


def static_overlay_cast(speaker_slots: dict[str, int]) -> list[tuple[str, int]]:
    return list(speaker_slots.items())[:2]


def static_overlay_portrait_entries(
    cast: list[tuple[str, int]],
    render_layout: dict[str, Any],
    preset: RenderPreset,
) -> list[dict[str, Any]]:
    character_scale = float(render_layout["character_scale"])
    height = layout_scaled_height(
        BASE_PORTRAIT_HEIGHT,
        character_scale,
        preset_height=preset.height,
        canvas_height=REFERENCE_CANVAS_HEIGHT,
    )
    return [
        {
            "speaker": speaker,
            "slot_index": slot_index,
            "height": height,
            "position": scale_box(BASE_POSITIONS[min(slot_index, 1)], preset),
            "alpha": STATIC_OVERLAY_PORTRAIT_ALPHA,
        }
        for speaker, slot_index in cast
    ]


def dynamic_frame_portrait_entry(
    slot_index: int,
    render_layout: dict[str, Any],
    preset: RenderPreset,
) -> dict[str, Any]:
    character_scale = float(render_layout["character_scale"])
    return {
        "height": layout_scaled_height(
            ACTIVE_PORTRAIT_HEIGHT,
            character_scale,
            preset_height=preset.height,
            canvas_height=REFERENCE_CANVAS_HEIGHT,
        ),
        "position": scale_box(ACTIVE_POSITIONS[min(slot_index, 1)], preset),
    }


def dynamic_frame_caption_entry(
    render_layout: dict[str, Any],
    preset: RenderPreset,
) -> dict[str, Any]:
    return {
        "font_size_px": int(render_layout["chat_font_size_px"]),
        "size": scale_box(CAPTION_CARD_SIZE, preset),
        "position": scale_box(CAPTION_CARD_POSITION, preset),
    }


def dynamic_frame_composition_payload(
    slot_index: int,
    render_layout: dict[str, Any],
    preset: RenderPreset,
) -> dict[str, Any]:
    return {
        "portrait": dynamic_frame_portrait_entry(slot_index, render_layout, preset),
        "caption": dynamic_frame_caption_entry(render_layout, preset),
    }


def dialogue_card_layout_payload(
    *,
    speaker: str,
    text: str,
    chat_font_size_px: int = 18,
) -> dict[str, Any]:
    label_font_size = max(24, int(chat_font_size_px * 1.45))
    body_font_size = max(28, int(chat_font_size_px * 2))
    wrapped_lines = textwrap.wrap(text, width=24)[:4]
    return {
        "size": (900, 380),
        "background": {
            "box": (0, 0, 900, 380),
            "radius": 48,
            "fill": (6, 10, 18, 228),
        },
        "accent_bar": {
            "box": (0, 0, 900, 22),
            "radius": 22,
        },
        "label": {
            "text": speaker.upper(),
            "position": (70, 74),
            "font_size": label_font_size,
        },
        "body": {
            "font_size": body_font_size,
            "fill": (245, 248, 255, 255),
            "lines": [
                {
                    "text": line,
                    "position": (70, 138 + (index * 64)),
                }
                for index, line in enumerate(wrapped_lines)
            ],
        },
    }


def generated_portrait_layout_payload(speaker: str, slot_index: int) -> dict[str, Any]:
    palette = speaker_palette(slot_index)
    return {
        "size": (760, 1100),
        "palette": palette,
        "head": {
            "box": (180, 60, 580, 460),
            "fill": palette["accent"],
        },
        "body": {
            "box": (140, 420, 620, 1060),
            "radius": 180,
            "fill": palette["body"],
        },
        "plate": {
            "box": (120, 780, 640, 1060),
            "radius": 140,
            "fill": palette["plate"],
        },
        "initials": {
            "text": speaker_initials(speaker),
            "position": (380, 250),
            "anchor": "mm",
            "fill": (255, 255, 255, 255),
            "font_size": 176,
        },
        "name_plate": {
            "box": (80, 880, 680, 1030),
            "radius": 50,
            "fill": (10, 14, 20, 230),
        },
        "name": {
            "text": speaker,
            "position": (380, 956),
            "anchor": "mm",
            "fill": (243, 248, 255, 255),
            "font_size": 54,
        },
    }
