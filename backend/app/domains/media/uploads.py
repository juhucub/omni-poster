from __future__ import annotations


def declared_upload_mime_type(content_type: str) -> str:
    return (content_type or "").split(";", 1)[0].strip().lower()


def mime_types_match(declared: str, detected: str) -> bool:
    return declared == detected
