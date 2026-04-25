from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utcnow() -> datetime:
    return datetime.utcnow()


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    preferences: Mapped["UserPreference | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )
    social_accounts: Mapped[list["SocialAccount"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    projects: Mapped[list["Project"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    submitted_reviews: Mapped[list["ReviewQueueItem"]] = relationship(
        foreign_keys="ReviewQueueItem.submitted_by_user_id", back_populates="submitted_by"
    )
    assigned_reviews: Mapped[list["ReviewQueueItem"]] = relationship(
        foreign_keys="ReviewQueueItem.reviewer_user_id", back_populates="reviewer"
    )
    review_comments: Mapped[list["ReviewComment"]] = relationship(
        back_populates="author", cascade="all, delete-orphan"
    )
    notifications: Mapped[list["NotificationEvent"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    voice_profiles: Mapped[list["VoiceProfile"]] = relationship(
        back_populates="created_by", cascade="all, delete-orphan"
    )
    character_presets: Mapped[list["CharacterPreset"]] = relationship(
        back_populates="created_by", cascade="all, delete-orphan"
    )
    voice_reference_audios: Mapped[list["VoiceReferenceAudio"]] = relationship(
        back_populates="created_by", cascade="all, delete-orphan"
    )
    voice_preview_jobs: Mapped[list["VoicePreviewJob"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)
    default_platform: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)
    default_social_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True
    )
    metadata_style: Mapped[str] = mapped_column(String(32), default="default", nullable=False)
    auto_select_default_account: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    automation_mode: Mapped[str] = mapped_column(String(32), default="assisted", nullable=False)
    preferred_account_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allowed_platforms_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    publish_windows_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="preferences")


class SocialAccount(Base):
    __tablename__ = "social_accounts"
    __table_args__ = (
        UniqueConstraint("platform", "channel_id", name="uq_social_account_platform_channel"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)
    account_type: Mapped[str] = mapped_column(String(32), default="owned_channel", nullable=False)
    channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    token_status: Mapped[str] = mapped_column(String(32), default="healthy", nullable=False)
    default_preference_rank: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="linked", nullable=False)
    last_validated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="social_accounts")
    projects: Mapped[list["Project"]] = relationship(
        back_populates="selected_social_account", foreign_keys="Project.selected_social_account_id"
    )
    publish_jobs: Mapped[list["PublishJob"]] = relationship(back_populates="social_account")
    published_posts: Mapped[list["PublishedPost"]] = relationship(back_populates="social_account")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    target_platform: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)
    background_style: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    background_source_type: Mapped[str] = mapped_column(String(32), default="upload", nullable=False)
    background_asset_id: Mapped[int | None] = mapped_column(
        ForeignKey("assets.id", ondelete="SET NULL"), nullable=True
    )
    selected_social_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True
    )
    current_script_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("script_revisions.id", ondelete="SET NULL"), nullable=True
    )
    current_output_video_id: Mapped[int | None] = mapped_column(
        ForeignKey("output_videos.id", ondelete="SET NULL"), nullable=True
    )
    automation_mode: Mapped[str] = mapped_column(String(32), default="assisted", nullable=False)
    preferred_account_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    allowed_platforms_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    publish_windows_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    archived_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    user: Mapped["User"] = relationship(back_populates="projects")
    selected_social_account: Mapped["SocialAccount | None"] = relationship(
        back_populates="projects", foreign_keys=[selected_social_account_id]
    )
    background_asset: Mapped["Asset | None"] = relationship(
        foreign_keys=[background_asset_id], post_update=True
    )
    assets: Mapped[list["Asset"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="Asset.project_id",
    )
    script_revisions: Mapped[list["ScriptRevision"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", foreign_keys="ScriptRevision.project_id"
    )
    generation_jobs: Mapped[list["GenerationJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    output_videos: Mapped[list["OutputVideo"]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        foreign_keys="OutputVideo.project_id",
    )
    review_queue_items: Mapped[list["ReviewQueueItem"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ReviewQueueItem.created_at.desc()"
    )
    publish_jobs: Mapped[list["PublishJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    published_posts: Mapped[list["PublishedPost"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    metadata_entries: Mapped[list["PlatformMetadata"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    current_script_revision: Mapped["ScriptRevision | None"] = relationship(
        foreign_keys=[current_script_revision_id], post_update=True
    )
    current_output_video: Mapped["OutputVideo | None"] = relationship(
        foreign_keys=[current_output_video_id], post_update=True
    )
    notifications: Mapped[list["NotificationEvent"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    speaker_bindings: Mapped[list["ProjectSpeakerBinding"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", order_by="ProjectSpeakerBinding.speaker_name.asc()"
    )


class VoiceProfile(Base):
    __tablename__ = "voice_profiles"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    provider: Mapped[str] = mapped_column(String(32), default="espeak", nullable=False)
    model_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    language: Mapped[str | None] = mapped_column(String(32), nullable=True)
    embedding_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    fallback_provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fallback_voice_settings_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    style_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    controls_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provider_metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    espeak_voice: Mapped[str | None] = mapped_column(String(64), nullable=True)
    espeak_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    espeak_pitch: Mapped[int | None] = mapped_column(Integer, nullable=True)
    espeak_word_gap: Mapped[int | None] = mapped_column(Integer, nullable=True)
    espeak_amplitude: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    created_by: Mapped["User | None"] = relationship(back_populates="voice_profiles")
    presets: Mapped[list["CharacterPreset"]] = relationship(back_populates="voice_profile")
    reference_audios: Mapped[list["VoiceReferenceAudio"]] = relationship(
        back_populates="voice_profile", cascade="all, delete-orphan", order_by="VoiceReferenceAudio.created_at.asc()"
    )
    voice_preview_jobs: Mapped[list["VoicePreviewJob"]] = relationship(back_populates="voice_profile")


class CharacterPreset(Base):
    __tablename__ = "character_presets"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    speaker_names_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    portrait_filename: Mapped[str | None] = mapped_column(String(255), nullable=True)
    voice_profile_id: Mapped[str] = mapped_column(
        ForeignKey("voice_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sample_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    source: Mapped[str] = mapped_column(String(32), default="runtime", nullable=False)
    is_seeded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    voice_profile: Mapped["VoiceProfile"] = relationship(back_populates="presets")
    created_by: Mapped["User | None"] = relationship(back_populates="character_presets")
    project_bindings: Mapped[list["ProjectSpeakerBinding"]] = relationship(back_populates="character_preset")
    voice_preview_jobs: Mapped[list["VoicePreviewJob"]] = relationship(back_populates="preset")


class VoiceReferenceAudio(Base):
    __tablename__ = "voice_reference_audios"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voice_profile_id: Mapped[str] = mapped_column(
        ForeignKey("voice_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    authorization_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    authorization_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    voice_profile: Mapped["VoiceProfile"] = relationship(back_populates="reference_audios")
    created_by: Mapped["User | None"] = relationship(back_populates="voice_reference_audios")


class ProjectSpeakerBinding(Base):
    __tablename__ = "project_speaker_bindings"
    __table_args__ = (
        UniqueConstraint("project_id", "speaker_name", name="uq_project_speaker_binding"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    speaker_name: Mapped[str] = mapped_column(String(128), nullable=False)
    character_preset_id: Mapped[str] = mapped_column(
        ForeignKey("character_presets.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="speaker_bindings")
    character_preset: Mapped["CharacterPreset"] = relationship(back_populates="project_bindings")


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    source_type: Mapped[str] = mapped_column(String(32), default="upload", nullable=False)
    preset_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    provider_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="assets", foreign_keys=[project_id])
    generation_jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="input_asset")
    output_videos: Mapped[list["OutputVideo"]] = relationship(back_populates="asset")


class ScriptRevision(Base):
    __tablename__ = "script_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    parent_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("script_revisions.id", ondelete="SET NULL"), nullable=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_lines_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    characters_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    generation_provider: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(
        back_populates="script_revisions", foreign_keys=[project_id]
    )
    parent_revision: Mapped["ScriptRevision | None"] = relationship(remote_side=[id])
    line_items: Mapped[list["ScriptLineItem"]] = relationship(
        back_populates="revision", cascade="all, delete-orphan", order_by="ScriptLineItem.line_order.asc()"
    )
    generation_jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="script_revision")


class ScriptLineItem(Base):
    __tablename__ = "script_line_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision_id: Mapped[int] = mapped_column(
        ForeignKey("script_revisions.id", ondelete="CASCADE"), index=True
    )
    line_order: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker: Mapped[str] = mapped_column(String(128), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    revision: Mapped["ScriptRevision"] = relationship(back_populates="line_items")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    input_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    script_revision_id: Mapped[int] = mapped_column(ForeignKey("script_revisions.id", ondelete="CASCADE"))
    style_preset: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
    output_kind: Mapped[str] = mapped_column(String(32), default="preview", nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), default="local-compositor", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="generation_jobs")
    input_asset: Mapped["Asset"] = relationship(back_populates="generation_jobs")
    script_revision: Mapped["ScriptRevision"] = relationship(back_populates="generation_jobs")
    output_video: Mapped["OutputVideo | None"] = relationship(
        back_populates="generation_job", uselist=False
    )


class VoicePreviewJob(Base):
    __tablename__ = "voice_preview_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    preset_id: Mapped[str] = mapped_column(ForeignKey("character_presets.id", ondelete="CASCADE"), index=True)
    voice_profile_id: Mapped[str] = mapped_column(ForeignKey("voice_profiles.id", ondelete="CASCADE"), index=True)
    requested_provider: Mapped[str] = mapped_column(String(32), default="auto", nullable=False)
    fallback_allowed: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sample_text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="queued", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stage: Mapped[str | None] = mapped_column(String(64), nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    voice: Mapped[str | None] = mapped_column(String(128), nullable=True)
    provider_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    controls_applied_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    provider_state_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    error_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    reference_audio_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    preview_audio_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="voice_preview_jobs")
    preset: Mapped["CharacterPreset"] = relationship(back_populates="voice_preview_jobs")
    voice_profile: Mapped["VoiceProfile"] = relationship(back_populates="voice_preview_jobs")


class OutputVideo(Base):
    __tablename__ = "output_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    generation_job_id: Mapped[int] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), unique=True
    )
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    output_kind: Mapped[str] = mapped_column(String(32), default="preview", nullable=False)
    provider_name: Mapped[str] = mapped_column(String(64), default="local-compositor", nullable=False)
    is_preview: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(
        back_populates="output_videos", foreign_keys=[project_id]
    )
    generation_job: Mapped["GenerationJob"] = relationship(back_populates="output_video")
    asset: Mapped["Asset"] = relationship(back_populates="output_videos")
    review_queue_items: Mapped[list["ReviewQueueItem"]] = relationship(back_populates="output_video")
    publish_jobs: Mapped[list["PublishJob"]] = relationship(back_populates="output_video")


class ReviewQueueItem(Base):
    __tablename__ = "review_queue_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    output_video_id: Mapped[int] = mapped_column(ForeignKey("output_videos.id", ondelete="CASCADE"))
    submitted_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    reviewer_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", nullable=False)
    decision_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="review_queue_items")
    output_video: Mapped["OutputVideo"] = relationship(back_populates="review_queue_items")
    submitted_by: Mapped["User"] = relationship(
        foreign_keys=[submitted_by_user_id], back_populates="submitted_reviews"
    )
    reviewer: Mapped["User | None"] = relationship(
        foreign_keys=[reviewer_user_id], back_populates="assigned_reviews"
    )
    comments: Mapped[list["ReviewComment"]] = relationship(
        back_populates="review_queue_item", cascade="all, delete-orphan", order_by="ReviewComment.created_at.asc()"
    )


class ReviewComment(Base):
    __tablename__ = "review_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    review_queue_item_id: Mapped[int] = mapped_column(
        ForeignKey("review_queue_items.id", ondelete="CASCADE"), index=True
    )
    author_user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    kind: Mapped[str] = mapped_column(String(32), default="note", nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    review_queue_item: Mapped["ReviewQueueItem"] = relationship(back_populates="comments")
    author: Mapped["User"] = relationship(back_populates="review_comments")


class PlatformMetadata(Base):
    __tablename__ = "platform_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    extras_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    validation_errors_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    project: Mapped["Project"] = relationship(back_populates="metadata_entries")
    publish_jobs: Mapped[list["PublishJob"]] = relationship(back_populates="platform_metadata")


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    social_account_id: Mapped[int] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE")
    )
    output_video_id: Mapped[int] = mapped_column(ForeignKey("output_videos.id", ondelete="CASCADE"))
    platform_metadata_id: Mapped[int] = mapped_column(
        ForeignKey("platform_metadata.id", ondelete="CASCADE")
    )
    routing_platform: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)
    automation_mode: Mapped[str] = mapped_column(String(32), default="assisted", nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(128), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="publish_jobs")
    social_account: Mapped["SocialAccount"] = relationship(back_populates="publish_jobs")
    output_video: Mapped["OutputVideo"] = relationship(back_populates="publish_jobs")
    platform_metadata: Mapped["PlatformMetadata"] = relationship(back_populates="publish_jobs")
    published_post: Mapped["PublishedPost | None"] = relationship(
        back_populates="publish_job", uselist=False
    )


class PublishedPost(Base):
    __tablename__ = "published_posts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    publish_job_id: Mapped[int] = mapped_column(
        ForeignKey("publish_jobs.id", ondelete="CASCADE"), unique=True
    )
    social_account_id: Mapped[int] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="CASCADE")
    )
    platform: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)
    external_post_id: Mapped[str] = mapped_column(String(255), nullable=False)
    external_url: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="published_posts")
    publish_job: Mapped["PublishJob"] = relationship(back_populates="published_post")
    social_account: Mapped["SocialAccount"] = relationship(back_populates="published_posts")


class NotificationEvent(Base):
    __tablename__ = "notification_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="notifications")
    project: Mapped["Project | None"] = relationship(back_populates="notifications")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    user: Mapped["User"] = relationship(back_populates="audit_logs")
