export interface SessionInfo {
  expires_at: string;
}

export interface PreferencesSummary {
  default_platform: string;
  default_social_account_id: number | null;
  metadata_style: string;
  auto_select_default_account: boolean;
  automation_mode: 'manual' | 'assisted' | 'auto';
  preferred_account_type: string | null;
  allowed_platforms: string[];
  publish_windows: Array<Record<string, unknown>>;
}

export interface UserSummary {
  id: number;
  username: string;
}

export interface AuthResponse {
  user: UserSummary;
  session: SessionInfo;
}

export interface MeResponse {
  id: number;
  username: string;
  preferences_summary: PreferencesSummary;
}

export interface SocialAccount {
  id: number;
  platform: string;
  account_type: string;
  channel_id: string;
  channel_title: string;
  status: string;
  token_status: string;
  capabilities: string[];
  default_preference_rank: number;
  routing_eligible: boolean;
  last_validated_at: string | null;
}

export interface ScriptLine {
  id?: number | null;
  speaker: string;
  text: string;
  order: number;
}

export interface ScriptRevision {
  id: number;
  parent_revision_id: number | null;
  raw_text: string;
  parsed_lines: ScriptLine[];
  characters: string[];
  source: string;
  generation_provider: string | null;
  is_current: boolean;
  created_at: string;
}

export interface Asset {
  id: number;
  kind: string;
  source_type: string;
  preset_key: string | null;
  provider_name: string | null;
  mime_type: string;
  original_filename: string;
  size_bytes: number;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  content_url: string;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface BackgroundPreset {
  key: string;
  name: string;
  description: string;
  filename: string;
  content_url: string;
}

export interface CharacterPreset {
  id: string;
  display_name: string;
  speaker_names: string[];
  portrait_filename: string | null;
  portrait_url: string | null;
  tts_provider: string;
  voice: string;
  rate: number;
  pitch: number;
  word_gap: number;
  amplitude: number;
  notes: string;
  sample_text: string;
  source: string;
}

export interface VoiceLabPreview {
  preset_id: string;
  voice: string;
  duration_seconds: number;
  sample_text: string;
  content_url: string;
}

export interface GenerationJob {
  id: number;
  project_id: number;
  status: string;
  progress: number;
  style_preset: string;
  output_kind: string;
  provider_name: string;
  error_message: string | null;
  output_video_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface OutputVideo {
  id: number;
  project_id: number;
  output_kind: string;
  provider_name: string;
  is_preview: boolean;
  duration_ms: number | null;
  asset: Asset;
  created_at: string;
}

export interface ReviewComment {
  id: number;
  author_user_id: number;
  kind: string;
  body: string;
  created_at: string;
}

export interface ReviewQueueItem {
  id: number;
  project_id: number;
  output_video_id: number;
  submitted_by_user_id: number;
  reviewer_user_id: number | null;
  status: string;
  decision_summary: string | null;
  rejection_reason: string | null;
  submitted_at: string;
  reviewed_at: string | null;
  comments: ReviewComment[];
}

export interface PlatformMetadata {
  id: number;
  project_id: number;
  platform: string;
  title: string;
  description: string;
  tags: string[];
  extras: Record<string, unknown>;
  validation_errors: string[];
  source: string;
  updated_at: string;
}

export interface RoutingSuggestion {
  project_id: number;
  recommended_platform: string;
  social_account_id: number | null;
  reason: string;
  eligible_accounts: SocialAccount[];
  metadata_ready: boolean;
  output_ready: boolean;
  automation_mode: string;
}

export interface PublishJob {
  id: number;
  project_id: number;
  social_account_id: number;
  output_video_id: number;
  platform_metadata_id: number;
  routing_platform: string;
  automation_mode: string;
  status: string;
  scheduled_for: string | null;
  attempt_count: number;
  last_error: string | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
  published_post_url: string | null;
}

export interface PublishedPost {
  id: number;
  project_id: number;
  publish_job_id: number;
  platform: string;
  external_post_id: string;
  external_url: string;
  published_at: string;
}

export interface NotificationSummary {
  id: number;
  category: string;
  message: string;
  payload: Record<string, unknown>;
  is_read: boolean;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  status: string;
  target_platform: string;
  background_style: 'none' | 'blur' | 'grayscale';
  background_source_type: string;
  background_asset_id: number | null;
  selected_social_account_id: number | null;
  current_script_revision_id: number | null;
  current_output_video_id: number | null;
  automation_mode: 'manual' | 'assisted' | 'auto';
  preferred_account_type: string | null;
  allowed_platforms: string[];
  publish_windows: Array<Record<string, unknown>>;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  current_script: ScriptRevision | null;
  latest_preview: Asset | null;
  latest_output: OutputVideo | null;
  latest_review: ReviewQueueItem | null;
  latest_notifications: NotificationSummary[];
}
