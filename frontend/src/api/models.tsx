export interface SessionInfo {
  expires_at: string;
}

export interface PreferencesSummary {
  default_platform: string;
  default_social_account_id: number | null;
  metadata_style: string;
  auto_select_default_account: boolean;
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
  channel_id: string;
  channel_title: string;
  status: string;
  last_validated_at: string | null;
}

export interface ScriptLine {
  speaker: string;
  text: string;
  order: number;
}

export interface ScriptRevision {
  id: number;
  raw_text: string;
  parsed_lines: ScriptLine[];
  characters: string[];
  source: string;
  is_current: boolean;
  created_at: string;
}

export interface Asset {
  id: number;
  kind: string;
  mime_type: string;
  original_filename: string;
  size_bytes: number;
  duration_ms: number | null;
  width: number | null;
  height: number | null;
  content_url: string;
  created_at: string;
}

export interface Project {
  id: number;
  name: string;
  status: string;
  target_platform: string;
  background_style: 'none' | 'blur' | 'grayscale';
  selected_social_account_id: number | null;
  current_script_revision_id: number | null;
  current_output_video_id: number | null;
  approved_at: string | null;
  created_at: string;
  updated_at: string;
  current_script: ScriptRevision | null;
  latest_preview: Asset | null;
}

export interface GenerationJob {
  id: number;
  project_id: number;
  status: string;
  progress: number;
  style_preset: string;
  error_message: string | null;
  output_video_id: number | null;
  started_at: string | null;
  finished_at: string | null;
  created_at: string;
}

export interface PlatformMetadata {
  id: number;
  project_id: number;
  platform: string;
  title: string;
  description: string;
  tags: string[];
  source: string;
  updated_at: string;
}

export interface PublishJob {
  id: number;
  project_id: number;
  social_account_id: number;
  output_video_id: number;
  platform_metadata_id: number;
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
