from __future__ import annotations

from app.models import PublishedPost
from app.schemas import PublishedPostSummary


def to_post_summary(post: PublishedPost) -> PublishedPostSummary:
    return PublishedPostSummary(
        id=post.id,
        project_id=post.project_id,
        publish_job_id=post.publish_job_id,
        platform=post.platform,
        external_post_id=post.external_post_id,
        external_url=post.external_url,
        published_at=post.published_at,
    )
