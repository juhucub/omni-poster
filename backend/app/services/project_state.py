from __future__ import annotations

from typing import Any

from app.domains.projects.aliases import asset_content_url  # noqa: F401 — re-export
from app.domains.publishing.lifecycle import publish_job_public_status
from app.domains.projects.diagnostics import latest_preview_asset, latest_review  # noqa: F401 — re-export
from app.domains.projects.preview_settings import (  # noqa: F401 — re-export
    DEFAULT_CHARACTER_SCALE,
    DEFAULT_CHAT_FONT_SIZE_PX,
    normalize_preview_layout,
)
from app.domains.projects.speaker_bindings import extract_script_speaker_samples
from app.domains.projects.workflow import sync_project_state  # noqa: F401 — compatibility shim
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
    ProjectScriptGenerationSettings,
    ProjectPreviewSettings,
    ProjectPreviewSpeakerMapping,
    PublishJobSummary,
    ReviewCommentSummary,
    ReviewQueueItemSummary,
    SpeakerBindingSummary,
    DialogueScriptLine,
    GeneratedScript,
    ScriptRevisionSummary,
)
from app.services.voice_profiles import character_preset_portrait_url


def _background_asset_for_project(project: Project) -> Asset | None:
    if project.background_asset_id:
        selected = next((asset for asset in project.assets if asset.id == project.background_asset_id), None)
        if selected:
            return selected
    background_assets = [asset for asset in project.assets if asset.kind in {"background_video", "background_preset", "background_image"}]
    background_assets.sort(key=lambda asset: asset.created_at, reverse=True)
    return background_assets[0] if background_assets else None


def _preview_settings_from_stored(project: Project) -> ProjectPreviewSettings:
    stored = dict(project.preview_settings_json or {})
    return ProjectPreviewSettings(
        background_asset_id=stored.get("background_asset_id"),
        background_preset_id=stored.get("background_preset_id"),
        background_source_type=stored.get("background_source_type"),
        background_url=stored.get("background_url"),
        background_metadata=dict(stored.get("background_metadata") or {}),
        speaker_mappings=[
            ProjectPreviewSpeakerMapping(**item)
            for item in list(stored.get("speaker_mappings") or [])
            if isinstance(item, dict)
        ],
        layout=normalize_preview_layout(dict(stored.get("layout") or {})),
        layout_preset=str(stored.get("layout_preset") or "left_right_locked"),
        caption_style=str(stored.get("caption_style") or "bold_bubble"),
        speaker_png_size=str(stored.get("speaker_png_size") or "standard"),
        render_preset=str(stored.get("render_preset") or "shorts_1080x1920"),
    )

def to_project_preview_settings(project: Project) -> ProjectPreviewSettings:
    stored = _preview_settings_from_stored(project)
    background_asset = _background_asset_for_project(project)
    if background_asset:
        # Rehydrate persisted preview state from the selected asset so refreshes keep the same Video Lab view.
        stored.background_asset_id = background_asset.id
        stored.background_preset_id = background_asset.preset_key
        stored.background_source_type = background_asset.source_type
        stored.background_url = asset_content_url(background_asset.id)
        stored.background_metadata = {
            "kind": background_asset.kind,
            "source_type": background_asset.source_type,
            "preset_key": background_asset.preset_key,
            "original_filename": background_asset.original_filename,
            "mime_type": background_asset.mime_type,
            **dict(background_asset.metadata_json or {}),
        }

    sample_by_speaker = extract_script_speaker_samples(
        project.current_script_revision.parsed_lines_json if project.current_script_revision else []
    )

    binding_by_speaker = {binding.speaker_name: binding for binding in project.speaker_bindings}
    speaker_names = list(sample_by_speaker) or list(binding_by_speaker)
    mappings: list[ProjectPreviewSpeakerMapping] = []
    for speaker_name in speaker_names:
        # Script speakers drive the preview order; bindings only fill in character/profile details.
        binding = binding_by_speaker.get(speaker_name)
        preset = binding.character_preset if binding else None
        mappings.append(
            ProjectPreviewSpeakerMapping(
                speaker_name=speaker_name,
                voice_profile_id=preset.voice_profile_id if preset else None,
                character_preset_id=preset.id if preset else None,
                character_display_name=preset.display_name if preset else None,
                character_portrait_filename=preset.portrait_filename if preset else None,
                character_portrait_url=character_preset_portrait_url(preset) if preset else None,
                display_label=preset.display_name if preset else speaker_name,
                sample_text=sample_by_speaker.get(speaker_name),
            )
        )
    stored.speaker_mappings = mappings
    return stored


def to_project_script_generation_settings(project: Project) -> ProjectScriptGenerationSettings:
    stored = dict(project.script_generation_settings_json or {})
    return ProjectScriptGenerationSettings(
        content_format_id=str(stored.get("content_format_id") or "educational_short"),
        platform=stored.get("platform") or "tiktok",
        target_duration_sec=int(stored.get("target_duration_sec") or 45),
        tone=str(stored.get("tone") or "engaging"),
        audience=str(stored.get("audience") or "general short-form viewers"),
        speaker_names=[str(item) for item in list(stored.get("speaker_names") or []) if str(item).strip()],
    )


def update_project_script_generation_settings(project: Project, payload: dict[str, Any]) -> ProjectScriptGenerationSettings:
    current = to_project_script_generation_settings(project)
    data = current.model_dump()
    for key in ("content_format_id", "platform", "target_duration_sec", "tone", "audience", "speaker_names"):
        if key in payload and payload[key] is not None:
            data[key] = payload[key]
    next_settings = ProjectScriptGenerationSettings(**data)
    project.script_generation_settings_json = next_settings.model_dump()
    return next_settings


def update_project_preview_settings(project: Project, payload: dict[str, Any]) -> ProjectPreviewSettings:
    current = _preview_settings_from_stored(project)
    if "layout" in payload and payload["layout"] is not None:
        current.layout = normalize_preview_layout(dict(payload["layout"] or {}))
    for key in ("background_asset_id", "background_preset_id", "background_source_type", "background_url"):
        if key in payload:
            setattr(current, key, payload[key])
    for key in ("layout_preset", "caption_style", "speaker_png_size", "render_preset"):
        if key in payload and payload[key] is not None:
            setattr(current, key, str(payload[key]))
    if "background_metadata" in payload and payload["background_metadata"] is not None:
        current.background_metadata = dict(payload["background_metadata"] or {})
    if "speaker_mappings" in payload and payload["speaker_mappings"] is not None:
        current.speaker_mappings = [
            ProjectPreviewSpeakerMapping(**item)
            for item in list(payload["speaker_mappings"] or [])
            if isinstance(item, dict)
        ]
    project.preview_settings_json = current.model_dump()
    return current


def sync_project_preview_background(project: Project, asset: Asset) -> ProjectPreviewSettings:
    current = _preview_settings_from_stored(project)
    current.background_asset_id = asset.id
    current.background_preset_id = asset.preset_key
    current.background_source_type = asset.source_type
    current.background_url = asset_content_url(asset.id)
    current.background_metadata = {
        "kind": asset.kind,
        "source_type": asset.source_type,
        "preset_key": asset.preset_key,
        "original_filename": asset.original_filename,
        "mime_type": asset.mime_type,
        **dict(asset.metadata_json or {}),
    }
    project.preview_settings_json = current.model_dump()
    return current


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
        DialogueScriptLine(id=line.id, speaker=line.speaker, text=line.text, order=line.line_order)
        for line in revision.line_items
    ]
    if not line_items:
        line_items = [DialogueScriptLine(**line) for line in revision.parsed_lines_json]
    generated_script = None
    if revision.generated_script_json:
        try:
            generated_script = GeneratedScript(**revision.generated_script_json)
        except Exception:
            generated_script = None

    return ScriptRevisionSummary(
        id=revision.id,
        parent_revision_id=revision.parent_revision_id,
        raw_text=revision.raw_text,
        parsed_lines=line_items,
        characters=revision.characters_json,
        generated_script=generated_script,
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
    tts_result = job.tts_result_json or {}
    assembly = dict(tts_result.get("assembly") or {})
    render_profile = dict(tts_result.get("render_profile") or {})
    render_plan = dict(tts_result.get("render_plan") or {})
    cache_report = dict(tts_result.get("cache_report") or {})
    performance_summary = dict(tts_result.get("performance_summary") or {})
    debug_extraction = dict(assembly.get("debug_audio_extraction") or {})
    return GenerationJobSummary(
        id=job.id,
        project_id=job.project_id,
        status=job.status,
        progress=job.progress,
        style_preset=job.style_preset,
        output_kind=job.output_kind,
        provider_name=job.provider_name,
        error_message=job.error_message,
        voice_manifest=job.voice_manifest_json or {},
        preview_settings=ProjectPreviewSettings(**(job.render_settings_json or {})),
        tts_result=tts_result,
        provider_state=job.provider_state_json or {},
        current_phase=tts_result.get("current_phase") or job.status,
        cache_statistics=dict(cache_report.get("summary") or {}),
        timing_breakdown=dict(render_profile.get("summary") or {}),
        performance_summary=performance_summary,
        artifact_urls={
            "render_plan": render_plan.get("artifact_url"),
            "cache_report": cache_report.get("artifact_url"),
            "render_profile": render_profile.get("artifact_url"),
            "composite_audio": assembly.get("composite_audio_artifact_url"),
            "final_video_audio": assembly.get("final_video_audio_artifact_url"),
        },
        debug_artifacts={
            "final_video_audio": assembly.get("final_video_audio_artifact_url"),
            "debug_audio_extraction": debug_extraction,
        },
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
    public_status = publish_job_public_status(job.status)
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


def to_speaker_binding_summary(binding) -> SpeakerBindingSummary:
    portrait_url = character_preset_portrait_url(binding.character_preset)
    return SpeakerBindingSummary(
        id=binding.id,
        speaker_name=binding.speaker_name,
        character_preset_id=binding.character_preset_id,
        character_display_name=binding.character_preset.display_name,
        voice_profile_id=binding.character_preset.voice_profile_id,
        provider=binding.character_preset.voice_profile.provider,
        character_portrait_filename=binding.character_preset.portrait_filename,
        character_portrait_url=portrait_url,
    )


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
        speaker_bindings=[to_speaker_binding_summary(item) for item in project.speaker_bindings],
        preview_settings=to_project_preview_settings(project),
        script_generation_settings=to_project_script_generation_settings(project),
    )
