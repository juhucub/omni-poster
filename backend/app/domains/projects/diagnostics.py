from __future__ import annotations

from app.models import Asset, Project, ReviewQueueItem


def latest_preview_asset(project: Project) -> Asset | None:
    if not project.current_output_video or not project.current_output_video.asset:
        return None
    return project.current_output_video.asset


def latest_review(project: Project) -> ReviewQueueItem | None:
    reviews = sorted(project.review_queue_items, key=lambda item: item.created_at, reverse=True)
    return reviews[0] if reviews else None


def project_is_archived(project: Project) -> bool:
    return project.archived_at is not None
