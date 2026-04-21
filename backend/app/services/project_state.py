from __future__ import annotations

from app.models import Asset, OutputVideo, Project, ScriptRevision
from app.schemas import AssetSummary, GenerationJobSummary, PlatformMetadataResponse, ProjectSummary, PublishJobSummary, ScriptLine, ScriptRevisionSummary


def asset_content_url(asset_id: int) -> str:
    return f"/assets/{asset_id}/content"


def to_asset_summary(asset: Asset) -> AssetSummary:
    return AssetSummary(
        id=asset.id,
        kind=asset.kind,
        mime_type=asset.mime_type,
        original_filename=asset.original_filename,
        size_bytes=asset.size_bytes,
        duration_ms=asset.duration_ms,
        width=asset.width,
        height=asset.height,
        content_url=asset_content_url(asset.id),
        created_at=asset.created_at,
    )


def to_script_summary(revision: ScriptRevision | None) -> ScriptRevisionSummary | None:
    if not revision:
        return None
    return ScriptRevisionSummary(
        id=revision.id,
        raw_text=revision.raw_text,
        parsed_lines=[ScriptLine(**line) for line in revision.parsed_lines_json],
        characters=revision.characters_json,
        source=revision.source,
        is_current=revision.is_current,
        created_at=revision.created_at,
    )


def latest_preview_asset(project: Project) -> Asset | None:
    if not project.current_output_video or not project.current_output_video.asset:
        return None
    return project.current_output_video.asset


def to_project_summary(project: Project) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        status=project.status,
        target_platform=project.target_platform,
        background_style=project.background_style,
        selected_social_account_id=project.selected_social_account_id,
        current_script_revision_id=project.current_script_revision_id,
        current_output_video_id=project.current_output_video_id,
        approved_at=project.approved_at,
        created_at=project.created_at,
        updated_at=project.updated_at,
        current_script=to_script_summary(project.current_script_revision),
        latest_preview=to_asset_summary(latest_preview_asset(project)) if latest_preview_asset(project) else None,
    )


def sync_project_state(project: Project) -> None:
    has_background = any(asset.kind == "background_video" for asset in project.assets)
    has_script = project.current_script_revision_id is not None
    has_preview = project.current_output_video_id is not None

    if project.archived_at:
        return
    if project.status in {"publishing", "published", "scheduled"}:
        return
    if project.approved_at and has_preview:
        project.status = "approved"
        return
    if has_preview:
        project.status = "preview_ready"
        return
    if has_background and has_script:
        project.status = "assets_ready"
        return
    project.status = "draft"
