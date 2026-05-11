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


class CharacterPresetSummary(BaseModel):
    id: str
    display_name: str
    speaker_names: list[str]
    portrait_filename: str | None = None
    portrait_url: str | None = None
    voice_profile_id: str
    tts_provider: str
    provider_preference: str = "auto"
    fallback_provider: str | None = None
    voice: str
    rate: int
    pitch: int
    word_gap: int
    amplitude: int
    language: str | None = None
    model_id: str | None = None
    controls: dict = Field(default_factory=dict)
    style: dict = Field(default_factory=dict)
    base_speaker: str | None = Field(default=None, max_length=128)
    style_preset: str | None = Field(default=None, max_length=64)
    emotion: str | None = Field(default=None, max_length=64)
    pace: float | None = Field(default=None, ge=0.25, le=3.0)
    energy: float | None = Field(default=None)
    pause_bias: float | None = Field(default=None)
    accent: str | None = Field(default=None, max_length=64)
    fallback_voice_settings: dict = Field(default_factory=dict)
    reference_audio_count: int = 0
    notes: str = ""
    sample_text: str = ""
    source: str


class CharacterPresetListResponse(BaseModel):
    items: list[CharacterPresetSummary]


class VoiceReferenceAudioSummary(BaseModel):
    id: int
    voice_profile_id: str
    reference_dataset_id: int | None = None
    storage_path: str
    original_storage_path: str | None = None
    processed_storage_path: str | None = None
    original_content_url: str | None = None
    processed_content_url: str | None = None
    mime_type: str
    duration_ms: int | None = None
    sha256: str
    processed_sha256: str | None = None
    validation_status: str = "not_validated"
    validation: dict = Field(default_factory=dict)
    authorization_confirmed: bool
    authorization_note: str | None = None
    created_at: datetime


class VoiceReferenceDatasetSummary(BaseModel):
    id: int
    voice_profile_id: str
    character_slug: str
    display_name: str
    storage_path: str
    status: str
    total_duration_seconds: float = 0.0
    clean_speech_duration_seconds: float = 0.0
    accepted_clip_count: int = 0
    rejected_clip_count: int = 0
    metrics: dict = Field(default_factory=dict)
    prosody_metrics: dict = Field(default_factory=dict)
    selected_recipe: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class VoiceProfileSummary(BaseModel):
    id: str
    display_name: str
    provider: str
    model_id: str | None = None
    language: str | None = None
    embedding_path: str | None = None
    fallback_provider: str | None = None
    fallback_voice_settings: dict = Field(default_factory=dict)
    style: dict = Field(default_factory=dict)
    controls: dict = Field(default_factory=dict)
    provider_metadata: dict = Field(default_factory=dict)
    base_speaker: str | None = None
    style_preset: str | None = None
    emotion: str | None = None
    pace: float | None = None
    pitch: float | None = None
    energy: float | None = None
    pause_bias: float | None = None
    accent: str | None = None
    voice: str | None = None
    espeak_rate: int | None = None
    espeak_pitch: int | None = None
    espeak_word_gap: int | None = None
    espeak_amplitude: int | None = None
    character_slug: str | None = None
    reference_dataset_id: int | None = None
    model_checkpoint_path: str | None = None
    selected_recipe: dict = Field(default_factory=dict)
    calibration_score: float | None = None
    last_verified_render_job_id: int | None = None
    associated_character_preset_id: str | None = None
    associated_character_display_name: str | None = None
    associated_character_image_url: str | None = None
    reference_audio_count: int = 0
    reference_audios: list[VoiceReferenceAudioSummary] = Field(default_factory=list)
    reference_datasets: list[VoiceReferenceDatasetSummary] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class VoiceProfileListResponse(BaseModel):
    items: list[VoiceProfileSummary]


class VoiceControlPayload(BaseModel):
    speaking_rate: float | None = None
    pitch: float | None = None
    energy: float | None = None
    emotion: str | None = None
    accent: str | None = None
    rhythm: float | None = None
    pause_length: float | None = None
    intonation: float | None = None
    expressiveness: float | None = None


class VoiceProfileRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    provider: str = Field(default="espeak", max_length=32)
    model_id: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=32)
    fallback_provider: str | None = Field(default=None, max_length=32)
    fallback_voice_settings: dict = Field(default_factory=dict)
    style: dict = Field(default_factory=dict)
    controls: dict = Field(default_factory=dict)
    provider_metadata: dict = Field(default_factory=dict)
    base_speaker: str | None = Field(default=None, max_length=128)
    style_preset: str | None = Field(default=None, max_length=64)
    emotion: str | None = Field(default=None, max_length=64)
    pace: float | None = Field(default=None, ge=0.25, le=3.0)
    pitch: float | None = Field(default=None)
    energy: float | None = Field(default=None)
    pause_bias: float | None = Field(default=None)
    accent: str | None = Field(default=None, max_length=64)
    embedding_path: str | None = Field(default=None, max_length=1000)
    voice: str | None = Field(default=None, max_length=64)
    espeak_rate: int | None = Field(default=None, ge=80, le=260)
    espeak_pitch: int | None = Field(default=None, ge=0, le=99)
    espeak_word_gap: int | None = Field(default=None, ge=0, le=20)
    espeak_amplitude: int | None = Field(default=None, ge=0, le=200)
    character_slug: str | None = Field(default=None, max_length=128)
    reference_dataset_id: int | None = None
    model_checkpoint_path: str | None = Field(default=None, max_length=1000)
    selected_recipe: dict = Field(default_factory=dict)
    calibration_score: float | None = None
    last_verified_render_job_id: int | None = None


class CharacterPresetRequest(BaseModel):
    display_name: str = Field(min_length=1, max_length=120)
    speaker_names: list[str] = Field(default_factory=list)
    portrait_filename: str | None = Field(default=None, max_length=255)
    voice_profile_id: str | None = Field(default=None, max_length=64)
    tts_provider: str = Field(default="espeak", max_length=32)
    provider_preference: str = Field(default="auto", max_length=32)
    fallback_provider: str | None = Field(default=None, max_length=32)
    model_id: str | None = Field(default=None, max_length=128)
    language: str | None = Field(default=None, max_length=32)
    character_slug: str | None = Field(default=None, max_length=128)
    reference_dataset_id: int | None = None
    model_checkpoint_path: str | None = Field(default=None, max_length=1000)
    selected_recipe: dict = Field(default_factory=dict)
    calibration_score: float | None = None
    last_verified_render_job_id: int | None = None
    voice: str = Field(min_length=1, max_length=64)
    rate: int = Field(ge=80, le=260)
    pitch: int = Field(ge=0, le=99)
    word_gap: int = Field(ge=0, le=20)
    amplitude: int = Field(ge=0, le=200)
    controls: dict = Field(default_factory=dict)
    style: dict = Field(default_factory=dict)
    fallback_voice_settings: dict = Field(default_factory=dict)
    notes: str = Field(default="", max_length=2000)
    sample_text: str = Field(default="", max_length=500)


class VoiceReferenceAudioUploadResponse(BaseModel):
    voice_profile: VoiceProfileSummary
    reference_audio: VoiceReferenceAudioSummary


class VoiceReferenceDatasetCreateRequest(BaseModel):
    display_name: str | None = Field(default=None, max_length=120)
    character_slug: str | None = Field(default=None, max_length=128)


class VoiceReferenceDatasetResponse(BaseModel):
    voice_profile: VoiceProfileSummary
    dataset: VoiceReferenceDatasetSummary


class VoiceReferenceDatasetClipUploadResponse(BaseModel):
    voice_profile: VoiceProfileSummary
    dataset: VoiceReferenceDatasetSummary
    reference_audio: VoiceReferenceAudioSummary


class VoiceModelAttachRequest(BaseModel):
    provider: Literal["openvoice", "xtts", "rvc"]
    character_slug: str | None = Field(default=None, max_length=128)
    model_checkpoint_path: str = Field(min_length=1, max_length=1000)
    model_index_path: str | None = Field(default=None, max_length=1000)
    reference_dataset_id: int | None = None
    recipe: dict = Field(default_factory=dict)


class VoiceCalibrationCandidateRequest(BaseModel):
    provider: Literal["openvoice", "xtts", "rvc", "espeak"] = "xtts"
    base_speaker: str | None = Field(default=None, max_length=128)
    style_preset: str = Field(default="default", max_length=64)
    temperature: float = Field(default=0.7, ge=0.1, le=1.5)
    split_sentences: bool | None = True
    pitch_shift: float = 0.0
    rate: float = Field(default=1.0, ge=0.25, le=3.0)
    pause_scale: float = Field(default=1.0, ge=0.25, le=3.0)
    punctuation_pause_bias: float = Field(default=1.0, ge=0.25, le=3.0)
    energy_normalization: float = Field(default=1.0, ge=0.1, le=3.0)
    rvc_pitch_shift: float = 0.0
    rvc_index_rate: float = Field(default=0.75, ge=0.0, le=1.0)
    rvc_protect: float = Field(default=0.33, ge=0.0, le=0.5)
    rvc_filter_radius: int = Field(default=3, ge=0, le=10)
    openvoice_tone_color: bool = False
    model_checkpoint_path: str | None = Field(default=None, max_length=1000)


class VoiceCalibrationBatchRequest(BaseModel):
    voice_profile_id: str
    reference_dataset_id: int | None = None
    calibration_script: str = Field(
        default="This is the calibration line. The rhythm, pitch, and pauses should match the target character.",
        min_length=1,
        max_length=500,
    )
    candidates: list[VoiceCalibrationCandidateRequest] = Field(default_factory=list, max_length=12)


class VoiceCalibrationBatchSummary(BaseModel):
    id: int
    voice_profile_id: str
    reference_dataset_id: int | None = None
    status: str
    provider_state: dict = Field(default_factory=dict)
    candidates: list[dict] = Field(default_factory=list)
    rankings: list[dict] = Field(default_factory=list)
    error: dict | None = None
    created_at: datetime
    updated_at: datetime


class VoiceOperationJobSummary(BaseModel):
    id: int
    user_id: int
    voice_profile_id: str
    reference_dataset_id: int | None = None
    operation_type: str
    status: Literal["queued", "processing", "completed", "failed"]
    progress: int = 0
    stage: str | None = None
    request: dict = Field(default_factory=dict)
    result: dict | None = None
    error: dict | None = None
    celery_task_id: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None


class VoiceProviderCapabilitySummary(BaseModel):
    provider: str
    available: bool
    reason: str | None = None
    supports_voice_cloning: bool = False
    supports_prepare: bool = False
    supported_controls: list[str] = Field(default_factory=list)
    metadata: dict = Field(default_factory=dict)


class ProviderCapabilityListResponse(BaseModel):
    items: list[VoiceProviderCapabilitySummary]


class VoiceProfilePrepareResponse(BaseModel):
    voice_profile: VoiceProfileSummary
    provider_used: str
    provider_state: dict = Field(default_factory=dict)
    prepared: bool
    cached_artifact_path: str | None = None
    message: str


class TTSFailureResponse(BaseModel):
    code: str
    message: str
    provider_state: dict = Field(default_factory=dict)
    fallback_attempted: bool = False
    attempted_providers: list[str] = Field(default_factory=list)
    provider_failures: dict = Field(default_factory=dict)
    suggested_action: str


class VoiceLabPreviewRequest(BaseModel):
    preset_id: str
    text: str = Field(min_length=1, max_length=500)
    provider_preference: str = Field(default="auto", max_length=32)
    fallback_allowed: bool = True
    controls: dict = Field(default_factory=dict)
    rate: int | None = Field(default=None, ge=80, le=260)
    pitch: int | None = Field(default=None, ge=0, le=99)
    word_gap: int | None = Field(default=None, ge=0, le=20)
    amplitude: int | None = Field(default=None, ge=0, le=200)


class VoiceCalibrationRecipe(BaseModel):
    base_speaker: str | None = Field(default=None, max_length=128)
    style_preset: str = Field(default="default", max_length=64)
    speaking_rate: float = Field(default=1.0, ge=0.25, le=3.0)
    pause_bias: float | None = Field(default=None)
    pitch: float | None = None
    energy: float | None = None
    emotion: str | None = Field(default=None, max_length=64)
    accent: str | None = Field(default=None, max_length=64)


class VoiceCalibrationMatrixRequest(BaseModel):
    preset_id: str
    provider_preference: str = Field(default="openvoice", max_length=32)
    fallback_allowed: bool = False
    phrases: list[str] = Field(default_factory=list, max_length=6)
    recipes: list[VoiceCalibrationRecipe] = Field(default_factory=list, max_length=8)


class VoiceCalibrationRecipeSaveRequest(BaseModel):
    recipe: dict = Field(default_factory=dict)


class VoiceLabPreviewResponse(BaseModel):
    status: Literal["queued", "processing", "completed", "failed"]
    job_id: int | None = None
    preset_id: str
    voice_profile_id: str
    voice: str | None = None
    provider_used: str | None = None
    fallback_used: bool = False
    controls_applied: dict = Field(default_factory=dict)
    reference_audio_count: int = 0
    provider_state: dict = Field(default_factory=dict)
    duration_seconds: float | None = None
    sample_text: str
    content_url: str | None = None
    calibration: dict = Field(default_factory=dict)
    error: TTSFailureResponse | None = None


class VoiceCalibrationMatrixResponse(BaseModel):
    preset_id: str
    voice_profile_id: str
    provider_state: dict = Field(default_factory=dict)
    unsupported_controls: list[str] = Field(default_factory=list)
    items: list[VoiceLabPreviewResponse] = Field(default_factory=list)


class SpeakerBindingSummary(BaseModel):
    id: int
    speaker_name: str
    character_preset_id: str
    character_display_name: str
    voice_profile_id: str
    provider: str
    character_portrait_filename: str | None = None
    character_portrait_url: str | None = None


class SpeakerBindingItemRequest(BaseModel):
    speaker_name: str = Field(min_length=1, max_length=128)
    character_preset_id: str = Field(min_length=1, max_length=64)


class SpeakerBindingListResponse(BaseModel):
    items: list[SpeakerBindingSummary]


class SpeakerBindingRequest(BaseModel):
    items: list[SpeakerBindingItemRequest]


class ProjectPreviewLayout(BaseModel):
    character_scale: float = Field(default=1.0, ge=0.75, le=1.5)
    chat_font_size_px: int = Field(default=18, ge=12, le=32)


class ProjectPreviewSpeakerMapping(BaseModel):
    speaker_name: str
    voice_profile_id: str | None = None
    character_preset_id: str | None = None
    character_display_name: str | None = None
    character_portrait_filename: str | None = None
    character_portrait_url: str | None = None
    display_label: str | None = None
    sample_text: str | None = None


class ProjectPreviewSettings(BaseModel):
    background_asset_id: int | None = None
    background_preset_id: str | None = None
    background_source_type: str | None = None
    background_url: str | None = None
    background_metadata: dict = Field(default_factory=dict)
    speaker_mappings: list[ProjectPreviewSpeakerMapping] = Field(default_factory=list)
    layout: ProjectPreviewLayout = Field(default_factory=ProjectPreviewLayout)


class ProjectPreviewSettingsUpdate(BaseModel):
    background_asset_id: int | None = None
    background_preset_id: str | None = None
    background_source_type: str | None = None
    background_url: str | None = None
    background_metadata: dict | None = None
    speaker_mappings: list[ProjectPreviewSpeakerMapping] | None = None
    layout: ProjectPreviewLayout | None = None


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
    voice_manifest: dict = Field(default_factory=dict)
    preview_settings: ProjectPreviewSettings = Field(default_factory=ProjectPreviewSettings)
    tts_result: dict = Field(default_factory=dict)
    provider_state: dict = Field(default_factory=dict)
    output_video_id: int | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    created_at: datetime


class GenerationJobListResponse(BaseModel):
    items: list[GenerationJobSummary]


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
    speaker_bindings: list[SpeakerBindingSummary] = Field(default_factory=list)
    preview_settings: ProjectPreviewSettings = Field(default_factory=ProjectPreviewSettings)


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]


class OkResponse(BaseModel):
    ok: bool = True
