from __future__ import annotations

from app.models import (
    Asset,
    GenerationJob,
    NotificationEvent,
    OutputVideo,
    PublishJob,
    Project,
    ReviewComment,
    ReviewQueueItem,
    ScriptRevision,
)
from app.schemas import (
    AssetSummary,
    GenerationJobSummary,
    NotificationSummary,
    OutputVideoSummary,
    ProjectSummary,
    PublishJobSummary,
    ReviewCommentSummary,
    ReviewQueueItemSummary,
    ScriptLine,
    ScriptRevisionSummary,
)


def asset_content_url(asset_id: int) -> str:
    return f"/assets/{asset_id}/content"


def to_asset_summary(asset: Asset) -> AssetSummary:
    return AssetSummary(
        id=asset.id,
        kind=asset.kind,
        source_type=asset.source_type,
        preset_key=asset.preset_key,
        provider_name=asset.provider_name,
        mime_type=asset.mime_type,
        original_filename=asset.original_filename,
        size_bytes=asset.size_bytes,
        duration_ms=asset.duration_ms,
        width=asset.width,
        height=asset.height,
        content_url=asset_content_url(asset.id),
        metadata=asset.metadata_json,
        created_at=asset.created_at,
    )


def to_script_summary(revision: ScriptRevision | None) -> ScriptRevisionSummary | None:
    if not revision:
        return None

    line_items = [
        ScriptLine(id=line.id, speaker=line.speaker, text=line.text, order=line.line_order)
        for line in revision.line_items
    ]
    if not line_items:
        line_items = [ScriptLine(**line) for line in revision.parsed_lines_json]

    return ScriptRevisionSummary(
        id=revision.id,
        parent_revision_id=revision.parent_revision_id,
        raw_text=revision.raw_text,
        parsed_lines=line_items,
        characters=revision.characters_json,
        source=revision.source,
        generation_provider=revision.generation_provider,
        is_current=revision.is_current,
        created_at=revision.created_at,
    )


def to_output_video_summary(output: OutputVideo) -> OutputVideoSummary:
    return OutputVideoSummary(
        id=output.id,
        project_id=output.project_id,
        output_kind=output.output_kind,
        provider_name=output.provider_name,
        is_preview=output.is_preview,
        duration_ms=output.duration_ms,
        asset=to_asset_summary(output.asset),
        created_at=output.created_at,
    )


def to_generation_summary(job: GenerationJob) -> GenerationJobSummary:
    return GenerationJobSummary(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        progress=job.progress,
        style_preset=job.style_preset,
        output_kind=job.output_kind,
        provider_name=job.provider_name,
        error_message=job.error_message,
        output_video_id=job.output_video.id if job.output_video else None,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
    )


def to_review_comment_summary(comment: ReviewComment) -> ReviewCommentSummary:
    return ReviewCommentSummary(
        id=comment.id,
        author_user_id=comment.author_user_id,
        kind=comment.kind,
        body=comment.body,
        created_at=comment.created_at,
    )


def to_review_summary(review: ReviewQueueItem | None) -> ReviewQueueItemSummary | None:
    if not review:
        return None
    return ReviewQueueItemSummary(
        id=review.id,
        project_id=review.project_id,
        output_video_id=review.output_video_id,
        submitted_by_user_id=review.submitted_by_user_id,
        reviewer_user_id=review.reviewer_user_id,
        status=review.status,
        decision_summary=review.decision_summary,
        rejection_reason=review.rejection_reason,
        submitted_at=review.submitted_at,
        reviewed_at=review.reviewed_at,
        comments=[to_review_comment_summary(comment) for comment in review.comments],
    )


def to_notification_summary(notification: NotificationEvent) -> NotificationSummary:
    return NotificationSummary(
        id=notification.id,
        category=notification.category,
        message=notification.message,
        payload=notification.payload_json,
        is_read=notification.is_read,
        created_at=notification.created_at,
    )


def to_publish_job_summary(job: PublishJob) -> PublishJobSummary:
    public_status = "queued" if job.status == "publish_queued" else job.status
    return PublishJobSummary(
        id=job.id,
        project_id=job.project_id,
        social_account_id=job.social_account_id,
        output_video_id=job.output_video_id,
        platform_metadata_id=job.platform_metadata_id,
        routing_platform=job.routing_platform,
        automation_mode=job.automation_mode,
        status=public_status,
        scheduled_for=job.scheduled_for,
        attempt_count=job.attempt_count,
        last_error=job.last_error,
        started_at=job.started_at,
        finished_at=job.finished_at,
        created_at=job.created_at,
        published_post_url=job.published_post.external_url if job.published_post else None,
    )


def latest_preview_asset(project: Project) -> Asset | None:
    if not project.current_output_video or not project.current_output_video.asset:
        return None
    return project.current_output_video.asset


def latest_review(project: Project) -> ReviewQueueItem | None:
    reviews = sorted(project.review_queue_items, key=lambda item: item.created_at, reverse=True)
    return reviews[0] if reviews else None


def to_project_summary(project: Project) -> ProjectSummary:
    recent_notifications = sorted(
        project.notifications, key=lambda item: item.created_at, reverse=True
    )[:3]
    return ProjectSummary(
        id=project.id,
        name=project.name,
        status=project.status,
        target_platform=project.target_platform,
        background_style=project.background_style,
        background_source_type=project.background_source_type,
        background_asset_id=project.background_asset_id,
        selected_social_account_id=project.selected_social_account_id,
        current_script_revision_id=project.current_script_revision_id,
        current_output_video_id=project.current_output_video_id,
        automation_mode=project.automation_mode,
        preferred_account_type=project.preferred_account_type,
        allowed_platforms=project.allowed_platforms_json or [project.target_platform],
        publish_windows=project.publish_windows_json or [],
        approved_at=project.approved_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
        current_script=to_script_summary(project.current_script_revision),
        latest_preview=to_asset_summary(latest_preview_asset(project)) if latest_preview_asset(project) else None,
        latest_output=to_output_video_summary(project.current_output_video) if project.current_output_video else None,
        latest_review=to_review_summary(latest_review(project)),
        latest_notifications=[to_notification_summary(item) for item in recent_notifications],
    )


def sync_project_state(project: Project) -> None:
    has_background = project.background_asset_id is not None or any(
        asset.kind in {"background_video", "background_preset"} for asset in project.assets
    )
    has_script = project.current_script_revision_id is not None
    has_output = project.current_output_video_id is not None
    current_review = latest_review(project)

    if project.archived_at:
        project.status = "archived"
        return
    if project.status in {"render_queued", "rendering", "publish_queued", "scheduled", "publishing", "published"}:
        return
    if current_review and current_review.status == "pending":
        project.status = "in_review"
        return
    if current_review and current_review.status == "changes_requested":
        project.status = "changes_requested"
        return
    if current_review and current_review.status == "approved" and has_output:
        project.status = "approved"
        return
    if project.approved_at and has_output:
        project.status = "approved"
        return
    if has_output:
        project.status = "preview_ready"
        return
    if has_background and has_script:
        project.status = "assets_ready"
        return
    if has_script:
        project.status = "script_ready"
        return
    project.status = "draft"
