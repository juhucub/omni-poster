from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


PROJECT_STATES = Literal[
    "draft",
    "assets_ready",
    "rendering",
    "preview_ready",
    "approved",
    "scheduled",
    "publishing",
    "published",
    "failed",
]


class SessionInfo(BaseModel):
    expires_at: datetime


class UserSummary(BaseModel):
    id: int
    username: str


class PreferencesSummary(BaseModel):
    default_platform: str = "youtube"
    default_social_account_id: int | None = None
    metadata_style: str = "default"
    auto_select_default_account: bool = True


class AuthResponse(BaseModel):
    user: UserSummary
    session: SessionInfo


class AuthRequest(BaseModel):
    username: str = Field(min_length=3, max_length=50, pattern=r"^[a-zA-Z0-9_]+$")
    password: str = Field(min_length=8, max_length=128)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        has_lower = any(char.islower() for char in value)
        has_upper = any(char.isupper() for char in value)
        has_digit = any(char.isdigit() for char in value)
        if not (has_lower and has_upper and has_digit):
            raise ValueError("Password must include upper, lower, and digit.")
        return value


class MeResponse(BaseModel):
    id: int
    username: str
    preferences_summary: PreferencesSummary


class PreferenceUpdate(BaseModel):
    default_platform: str | None = None
    default_social_account_id: int | None = None
    metadata_style: str | None = None
    auto_select_default_account: bool | None = None


class PreferenceResponse(BaseModel):
    preferences: PreferencesSummary


class SocialAccountSummary(BaseModel):
    id: int
    platform: str
    channel_id: str
    channel_title: str
    status: str
    last_validated_at: datetime | None


class SocialAccountListResponse(BaseModel):
    items: list[SocialAccountSummary]


class OAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_platform: str = "youtube"

    @field_validator("target_platform")
    @classmethod
    def validate_target_platform(cls, value: str) -> str:
        if value != "youtube":
            raise ValueError("Only YouTube Shorts is supported in this MVP.")
        return value


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    selected_social_account_id: int | None = None
    background_style: Literal["none", "blur", "grayscale"] | None = None


class AssetSummary(BaseModel):
    id: int
    kind: str
    mime_type: str
    original_filename: str
    size_bytes: int
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    content_url: str
    created_at: datetime


class ScriptLine(BaseModel):
    speaker: str
    text: str
    order: int


class ScriptRevisionSummary(BaseModel):
    id: int
    raw_text: str
    parsed_lines: list[ScriptLine]
    characters: list[str]
    source: str
    is_current: bool
    created_at: datetime


class ScriptResponse(BaseModel):
    current_revision: ScriptRevisionSummary | None


class ScriptUpdateRequest(BaseModel):
    raw_text: str = Field(min_length=1)
    source: str = "manual"


class GenerationJobCreateRequest(BaseModel):
    script_revision_id: int | None = None
    background_style: Literal["none", "blur", "grayscale"] = "none"


class GenerationJobSummary(BaseModel):
    id: int
    project_id: int
    status: str
    progress: int
    style_preset: str
    error_message: str | None = None
    output_video_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class PlatformMetadataUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    source: str = "manual"


class PlatformMetadataResponse(BaseModel):
    id: int
    project_id: int
    platform: str
    title: str
    description: str
    tags: list[str]
    source: str
    updated_at: datetime


class PublishJobCreateRequest(BaseModel):
    social_account_id: int
    output_video_id: int
    platform_metadata_id: int
    publish_mode: Literal["now", "schedule"]
    scheduled_for: datetime | None = None

    @field_validator("scheduled_for")
    @classmethod
    def validate_schedule(cls, value: datetime | None, info) -> datetime | None:
        publish_mode = info.data.get("publish_mode")
        if publish_mode == "schedule" and value is None:
            raise ValueError("scheduled_for is required when publish_mode is 'schedule'.")
        return value


class PublishJobSummary(BaseModel):
    id: int
    project_id: int
    social_account_id: int
    output_video_id: int
    platform_metadata_id: int
    status: str
    scheduled_for: datetime | None
    attempt_count: int
    last_error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    published_post_url: str | None = None


class PublishedPostSummary(BaseModel):
    id: int
    project_id: int
    publish_job_id: int
    platform: str
    external_post_id: str
    external_url: str
    published_at: datetime


class PublishHistoryResponse(BaseModel):
    jobs: list[PublishJobSummary]
    posts: list[PublishedPostSummary]


class ProjectSummary(BaseModel):
    id: int
    name: str
    status: str
    target_platform: str
    background_style: str
    selected_social_account_id: int | None
    current_script_revision_id: int | None
    current_output_video_id: int | None
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_script: ScriptRevisionSummary | None = None
    latest_preview: AssetSummary | None = None


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]


class OkResponse(BaseModel):
    ok: bool = True
