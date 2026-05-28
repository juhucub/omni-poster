from __future__ import annotations

from app.domains.render.planning import RenderPreset


REFERENCE_CANVAS_WIDTH = 1080
REFERENCE_CANVAS_HEIGHT = 1920
BASE_POSITIONS = ((56, 1080), (584, 1080))
ACTIVE_POSITIONS = ((4, 930), (472, 930))
BASE_PORTRAIT_HEIGHT = 620
ACTIVE_PORTRAIT_HEIGHT = 780
CAPTION_CARD_SIZE = (900, 380)
CAPTION_CARD_POSITION = (90, 1320)


def scale_box(
    box: tuple[int, int],
    preset: RenderPreset,
    *,
    canvas_width: int = REFERENCE_CANVAS_WIDTH,
    canvas_height: int = REFERENCE_CANVAS_HEIGHT,
) -> tuple[int, int]:
    return (int(round(box[0] * preset.width / canvas_width)), int(round(box[1] * preset.height / canvas_height)))


def layout_scaled_height(
    base_height: int,
    character_scale: float,
    *,
    preset_height: int | None = None,
    canvas_height: int = REFERENCE_CANVAS_HEIGHT,
) -> int:
    height = base_height * character_scale
    if preset_height is not None:
        height = height * preset_height / canvas_height
    return int(round(height))


def portrait_resize_dimensions(source_width: int, source_height: int, target_height: int) -> tuple[int, int]:
    ratio = target_height / max(source_height, 1)
    return (max(1, int(source_width * ratio)), target_height)
