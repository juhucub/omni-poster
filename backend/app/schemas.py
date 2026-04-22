from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PlatformType = Literal["youtube", "instagram", "tiktok", "facebook"]
AutomationMode = Literal["manual", "assisted", "auto"]

PROJECT_STATES = Literal[
    "draft",
    "script_ready",
    "assets_ready",
    "render_queued",
    "rendering",
    "preview_ready",
    "in_review",
    "changes_requested",
    "approved",
    "publish_queued",
    "scheduled",
    "publishing",
    "published",
    "failed",
    "archived",
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
    automation_mode: AutomationMode = "assisted"
    preferred_account_type: str | None = None
    allowed_platforms: list[str] = Field(default_factory=lambda: ["youtube"])
    publish_windows: list[dict] = Field(default_factory=list)


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
    automation_mode: AutomationMode | None = None
    preferred_account_type: str | None = None
    allowed_platforms: list[str] | None = None
    publish_windows: list[dict] | None = None


class PreferenceResponse(BaseModel):
    preferences: PreferencesSummary


class SocialAccountSummary(BaseModel):
    id: int
    platform: str
    account_type: str
    channel_id: str
    channel_title: str
    status: str
    token_status: str
    capabilities: list[str]
    default_preference_rank: int
    routing_eligible: bool
    last_validated_at: datetime | None


class SocialAccountListResponse(BaseModel):
    items: list[SocialAccountSummary]


class OAuthStartResponse(BaseModel):
    authorization_url: str
    state: str


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    target_platform: PlatformType = "youtube"
    automation_mode: AutomationMode = "assisted"
    allowed_platforms: list[PlatformType] = Field(default_factory=lambda: ["youtube"])


class ProjectUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    selected_social_account_id: int | None = None
    background_style: Literal["none", "blur", "grayscale"] | None = None
    automation_mode: AutomationMode | None = None
    preferred_account_type: str | None = None
    allowed_platforms: list[PlatformType] | None = None
    publish_windows: list[dict] | None = None


class AssetSummary(BaseModel):
    id: int
    kind: str
    source_type: str
    preset_key: str | None = None
    provider_name: str | None = None
    mime_type: str
    original_filename: str
    size_bytes: int
    duration_ms: int | None = None
    width: int | None = None
    height: int | None = None
    content_url: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class BackgroundPresetSummary(BaseModel):
    key: str
    name: str
    description: str
    filename: str
    content_url: str


class ScriptLine(BaseModel):
    id: int | None = None
    speaker: str
    text: str
    order: int


class ScriptRevisionSummary(BaseModel):
    id: int
    parent_revision_id: int | None = None
    raw_text: str
    parsed_lines: list[ScriptLine]
    characters: list[str]
    source: str
    generation_provider: str | None = None
    is_current: bool
    created_at: datetime


class ScriptResponse(BaseModel):
    current_revision: ScriptRevisionSummary | None


class ScriptRevisionListResponse(BaseModel):
    items: list[ScriptRevisionSummary]


class ScriptUpdateRequest(BaseModel):
    raw_text: str | None = None
    parsed_lines: list[ScriptLine] | None = None
    source: str = "manual"
    parent_revision_id: int | None = None

    @model_validator(mode="after")
    def validate_script_payload(self) -> "ScriptUpdateRequest":
        if not self.raw_text and not self.parsed_lines:
            raise ValueError("Provide raw_text or parsed_lines.")
        return self


class ScriptGenerateRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=1000)
    character_names: list[str] = Field(default_factory=lambda: ["Host", "Guest"])
    tone: str = Field(default="explanatory", max_length=64)


class GenerationJobCreateRequest(BaseModel):
    script_revision_id: int | None = None
    background_style: Literal["none", "blur", "grayscale"] = "none"
    output_kind: Literal["preview", "final"] = "preview"
    provider_name: str = "local-compositor"


class GenerationJobSummary(BaseModel):
    id: int
    project_id: int
    status: str
    progress: int
    style_preset: str
    output_kind: str
    provider_name: str
    error_message: str | None = None
    output_video_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class OutputVideoSummary(BaseModel):
    id: int
    project_id: int
    output_kind: str
    provider_name: str
    is_preview: bool
    duration_ms: int | None = None
    asset: AssetSummary
    created_at: datetime


class OutputVideoListResponse(BaseModel):
    items: list[OutputVideoSummary]


class ReviewCommentCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=5000)
    kind: Literal["note", "change_request", "approval"] = "note"


class ReviewCommentSummary(BaseModel):
    id: int
    author_user_id: int
    kind: str
    body: str
    created_at: datetime


class ReviewSubmitRequest(BaseModel):
    output_video_id: int
    reviewer_user_id: int | None = None
    note: str | None = Field(default=None, max_length=5000)


class ReviewDecisionRequest(BaseModel):
    summary: str | None = Field(default=None, max_length=5000)
    rejection_reason: str | None = Field(default=None, max_length=5000)


class ReviewQueueItemSummary(BaseModel):
    id: int
    project_id: int
    output_video_id: int
    submitted_by_user_id: int
    reviewer_user_id: int | None
    status: str
    decision_summary: str | None
    rejection_reason: str | None
    submitted_at: datetime
    reviewed_at: datetime | None
    comments: list[ReviewCommentSummary] = Field(default_factory=list)


class ReviewQueueListResponse(BaseModel):
    items: list[ReviewQueueItemSummary]


class PlatformMetadataUpdateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=5000)
    tags: list[str] = Field(default_factory=list)
    extras: dict = Field(default_factory=dict)
    source: str = "manual"


class PlatformMetadataResponse(BaseModel):
    id: int
    project_id: int
    platform: str
    title: str
    description: str
    tags: list[str]
    extras: dict
    validation_errors: list[str]
    source: str
    updated_at: datetime


class RoutingSuggestionResponse(BaseModel):
    project_id: int
    recommended_platform: str
    social_account_id: int | None
    reason: str
    eligible_accounts: list[SocialAccountSummary]
    metadata_ready: bool
    output_ready: bool
    automation_mode: str


class PublishRequest(BaseModel):
    platform: PlatformType = "youtube"
    social_account_id: int | None = None
    output_video_id: int
    platform_metadata_id: int
    publish_mode: Literal["now", "schedule"] = "now"
    scheduled_for: datetime | None = None
    automation_mode: AutomationMode = "assisted"

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
    routing_platform: str
    automation_mode: str
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


class NotificationSummary(BaseModel):
    id: int
    category: str
    message: str
    payload: dict
    is_read: bool
    created_at: datetime


class ProjectSummary(BaseModel):
    id: int
    name: str
    status: str
    target_platform: str
    background_style: str
    background_source_type: str
    background_asset_id: int | None
    selected_social_account_id: int | None
    current_script_revision_id: int | None
    current_output_video_id: int | None
    automation_mode: str
    preferred_account_type: str | None
    allowed_platforms: list[str]
    publish_windows: list[dict]
    approved_at: datetime | None
    created_at: datetime
    updated_at: datetime
    current_script: ScriptRevisionSummary | None = None
    latest_preview: AssetSummary | None = None
    latest_output: OutputVideoSummary | None = None
    latest_review: ReviewQueueItemSummary | None = None
    latest_notifications: list[NotificationSummary] = Field(default_factory=list)


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]


class OkResponse(BaseModel):
    ok: bool = True
