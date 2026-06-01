from __future__ import annotations


def is_video_mime(mime_type: str) -> bool:
    return mime_type.startswith("video/")


def is_image_mime(mime_type: str) -> bool:
    return mime_type.startswith("image/")


def is_preview_output_kind(output_kind: str) -> bool:
    return output_kind == "preview"
