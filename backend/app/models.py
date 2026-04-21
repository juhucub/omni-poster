from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
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
    channel_id: Mapped[str] = mapped_column(String(255), nullable=False)
    channel_title: Mapped[str] = mapped_column(String(255), nullable=False)
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
    projects: Mapped[list["Project"]] = relationship(back_populates="selected_social_account")
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
    selected_social_account_id: Mapped[int | None] = mapped_column(
        ForeignKey("social_accounts.id", ondelete="SET NULL"), nullable=True
    )
    current_script_revision_id: Mapped[int | None] = mapped_column(
        ForeignKey("script_revisions.id", ondelete="SET NULL"), nullable=True
    )
    current_output_video_id: Mapped[int | None] = mapped_column(
        ForeignKey("output_videos.id", ondelete="SET NULL"), nullable=True
    )
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
    assets: Mapped[list["Asset"]] = relationship(back_populates="project", cascade="all, delete-orphan")
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


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    storage_key: Mapped[str] = mapped_column(Text, nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(128), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(back_populates="assets")
    generation_jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="input_asset")
    output_videos: Mapped[list["OutputVideo"]] = relationship(back_populates="asset")


class ScriptRevision(Base):
    __tablename__ = "script_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    parsed_lines_json: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    characters_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    source: Mapped[str] = mapped_column(String(32), default="manual", nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(
        back_populates="script_revisions", foreign_keys=[project_id]
    )
    generation_jobs: Mapped[list["GenerationJob"]] = relationship(back_populates="script_revision")


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    input_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    script_revision_id: Mapped[int] = mapped_column(ForeignKey("script_revisions.id", ondelete="CASCADE"))
    style_preset: Mapped[str] = mapped_column(String(32), default="none", nullable=False)
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


class OutputVideo(Base):
    __tablename__ = "output_videos"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    generation_job_id: Mapped[int] = mapped_column(
        ForeignKey("generation_jobs.id", ondelete="CASCADE"), unique=True
    )
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id", ondelete="CASCADE"))
    is_preview: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

    project: Mapped["Project"] = relationship(
        back_populates="output_videos", foreign_keys=[project_id]
    )
    generation_job: Mapped["GenerationJob"] = relationship(back_populates="output_video")
    asset: Mapped["Asset"] = relationship(back_populates="output_videos")
    publish_jobs: Mapped[list["PublishJob"]] = relationship(back_populates="output_video")


class PlatformMetadata(Base):
    __tablename__ = "platform_metadata"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    platform: Mapped[str] = mapped_column(String(32), default="youtube", nullable=False)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    tags_json: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
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
