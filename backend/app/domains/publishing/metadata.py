from __future__ import annotations

from app.domains.publishing.platforms import validate_platform_metadata  # noqa: F401 — re-export


def normalize_tags(tags_json: list | None) -> list[str]:
    return [str(tag) for tag in (tags_json or []) if str(tag).strip()]
