import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  Clock,
  Play,
  Radio,
  RefreshCw,
  Rocket,
  Settings,
  UploadCloud,
  UserRound,
} from 'lucide-react';

import apiClient, { apiBaseUrl } from '../../api/client';
import type {
  BackgroundPreset,
  CharacterPreset,
  GenerationJob,
  GeneratedScript,
  PlatformTarget,
  Project,
  ProjectPreviewSettings,
  ProjectPreviewSpeakerMapping,
  PublishJob,
  PublishedPost,
  ScriptLine,
  ScriptRevision,
  SocialAccount,
  VoiceProfile,
} from '../../api/models';
import { useAuth } from '../../context/AuthContext';
import { StudioShell } from '../studio/StudioShell';

type StudioSyncState = 'local' | 'paused' | 'active';

type CommandRoomData = {
  projects: Project[];
  currentProject: Project | null;
  script: ScriptRevision | null;
  jobs: GenerationJob[];
  outputs: any[];
  accounts: SocialAccount[];
  history: { jobs: PublishJob[]; posts: PublishedPost[] };
  characterPresets: CharacterPreset[];
  voiceProfiles: VoiceProfile[];
  backgroundPresets: BackgroundPreset[];
};

const contentFormats = [
  { id: 'character_dialogue', label: 'Character Dialogue' },
  { id: 'reddit_story', label: 'Reddit Story' },
  { id: 'podcast_clip', label: 'Podcast Clip' },
  { id: 'debate_format', label: 'Debate Format' },
  { id: 'meme_news_reaction', label: 'Meme News Reaction' },
];

const platformTargets: Array<{ id: PlatformTarget; label: string }> = [
  { id: 'youtube_shorts', label: 'YouTube Shorts' },
  { id: 'tiktok', label: 'TikTok' },
  { id: 'instagram_reels', label: 'Instagram Reels' },
];

const defaultPreviewSettings: ProjectPreviewSettings = {
  background_asset_id: null,
  background_preset_id: null,
  background_source_type: null,
  background_url: null,
  background_metadata: {},
  speaker_mappings: [],
  layout: { character_scale: 1, chat_font_size_px: 18 },
  layout_preset: 'left_right_locked',
  caption_style: 'bold_bubble',
  speaker_png_size: 'standard',
  render_preset: 'shorts_1080x1920',
};

const localDraftProject: Project = {
  id: -1,
  name: 'Local Production Draft',
  status: 'draft',
  target_platform: 'youtube_shorts',
  background_style: 'none',
  background_source_type: 'local',
  background_asset_id: null,
  selected_social_account_id: null,
  current_script_revision_id: null,
  current_output_video_id: null,
  automation_mode: 'manual',
  preferred_account_type: null,
  allowed_platforms: ['youtube_shorts'],
  publish_windows: [],
  approved_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  current_script: null,
  latest_preview: null,
  latest_output: null,
  latest_review: null,
  latest_notifications: [],
  speaker_bindings: [],
  preview_settings: defaultPreviewSettings,
};

const toApiHref = (url: string | null | undefined) => {
  if (!url) {
    return '';
  }
  if (/^https?:\/\//.test(url)) {
    return url;
  }
  return `${apiBaseUrl}${url.startsWith('/') ? url : `/${url}`}`;
};

const titleCase = (value: string | null | undefined) =>
  String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());

const initials = (value: string | null | undefined) =>
  String(value || 'OP')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'OP';

const currentStep = (project: Project | null, job: GenerationJob | null, readiness: string[]) => {
  if (!project) return 'Create Production';
  if (job && ['queued', 'processing', 'running'].includes(job.status)) return 'Render Running';
  if (readiness.length) return 'Blocked';
  if (!project.approved_at && project.current_output_video_id) return 'Preview Review';
  if (project.current_output_video_id) return 'Release Ready';
  return project.current_script ? 'Preview Setup' : 'Script';
};

const getSyncState = (isAuthenticated: boolean): StudioSyncState => {
  if (!isAuthenticated) {
    return 'local';
  }
  if (typeof window === 'undefined') {
    return 'paused';
  }
  return window.localStorage.getItem('omniposter.studioSync') === 'active' ? 'active' : 'paused';
};

const normalizePreview = (settings?: Partial<ProjectPreviewSettings> | null): ProjectPreviewSettings => ({
  ...defaultPreviewSettings,
  ...(settings || {}),
  background_metadata: settings?.background_metadata || {},
  speaker_mappings: settings?.speaker_mappings || [],
  layout: {
    ...defaultPreviewSettings.layout,
    ...(settings?.layout || {}),
  },
});

const scriptLinesFor = (script: ScriptRevision | null): ScriptLine[] => script?.parsed_lines || [];

const speakersFor = (script: ScriptRevision | null, preview: ProjectPreviewSettings) => {
  const fromScript = scriptLinesFor(script).map((line) => line.speaker).filter(Boolean);
  const fromPreview = preview.speaker_mappings.map((item) => item.speaker_name).filter(Boolean);
  return Array.from(new Set([...fromScript, ...fromPreview]));
};

const voiceById = (profiles: VoiceProfile[]) => new Map(profiles.map((profile) => [profile.id, profile]));

const badgeClassForStatus = (status: string) => {
  if (['completed', 'published', 'approved'].includes(status)) return 'op-badge-success';
  if (['failed', 'blocked'].includes(status)) return 'op-badge-error';
  if (['queued', 'processing', 'running', 'render_queued'].includes(status)) return 'op-badge-warning';
  return 'op-badge-muted';
};

export const CommandRoomHero: React.FC<{
  syncState: StudioSyncState;
  queueCount: number;
  onConnect: () => void;
  onResumeSync: () => void;
  onPauseSync: () => void;
}> = ({ syncState, queueCount, onConnect, onResumeSync, onPauseSync }) => {
  const isLocal = syncState === 'local';
  const isPaused = syncState === 'paused';
  return (
    <section className="op-hero" id="command-room" aria-label="Control Room status" style={{ '--hero-glow': isPaused ? 'rgba(251,146,60,0.04)' : 'rgba(0,220,200,0.04)' } as React.CSSProperties}>
      <div className="op-hero-eyebrow">OmniPoster Control Room</div>
      <div className="op-hero-top">
        <div>
          <h1 className="op-hero-title">Production Command</h1>
          <p className="op-hero-subtitle">
            {isLocal
              ? 'Local production work is available, but cloud sync and publishing are unavailable until an account is connected.'
              : isPaused
                ? "You're signed in, but Studio Sync and automation are paused. Local edits are safe. Channel sync, token refresh, and scheduled publishing will not run until sync is resumed."
                : 'Studio Sync is active. Local production, channel prep, and release controls are available where the backend supports them.'}
          </p>
        </div>
        <div className={`op-hero-status-pill ${isLocal ? 'local' : isPaused ? 'paused' : 'active'}`} role="status">
          <span className="op-dot" />
          {isLocal ? 'Local workspace · Not authenticated' : isPaused ? 'Authenticated · Studio Sync paused' : 'Authenticated · Studio Sync active'}
        </div>
      </div>
      <div className="op-hero-stats">
        <div className="op-hero-stat">
          <span className="op-hero-stat-label">Mode</span>
          <span className="op-hero-stat-value" style={{ color: isLocal ? 'var(--local)' : undefined }}>
            {isLocal ? 'Local' : 'Signed in'}
          </span>
          <span className="op-hero-stat-sub">{isLocal ? 'Offline workspace' : 'Authenticated'}</span>
        </div>
        <div className="op-hero-stat-divider" />
        <div className="op-hero-stat">
          <span className="op-hero-stat-label">Queue</span>
          <span className="op-hero-stat-value">{queueCount}</span>
          <span className="op-hero-stat-sub">{queueCount === 1 ? 'job' : 'jobs'}</span>
        </div>
        <div className="op-hero-stat-divider" />
        <div className="op-hero-stat">
          <span className="op-hero-stat-label">Sync</span>
          <span className="op-hero-stat-value" style={{ color: isPaused ? 'var(--paused)' : isLocal ? 'var(--text-muted)' : 'var(--success)' }}>
            {isLocal ? '-' : isPaused ? 'Paused' : 'Active'}
          </span>
          <span className="op-hero-stat-sub">{isLocal ? 'Not connected' : isPaused ? 'Resume to activate' : 'Automation enabled'}</span>
        </div>
      </div>
      <div className="op-workflow-rail" role="list" aria-label="Production workflow stages">
        {['Idea', 'Script', 'Cast Voices', 'Scene', 'Preview', 'Render', 'Release'].map((stage) => (
          <div key={stage} className="op-workflow-pill active-anim" role="listitem">
            {stage}
          </div>
        ))}
      </div>
      <div className="op-hero-controls">
        {isLocal ? (
          <button className="op-btn op-btn-primary" type="button" onClick={onConnect}>
            <UserRound size={16} /> Connect Workspace
          </button>
        ) : isPaused ? (
          <>
            <button className="op-btn op-btn-paused" type="button" onClick={onResumeSync}>
              <RefreshCw size={16} /> Resume Sync
            </button>
            <a className="op-btn op-btn-secondary" href="#channels">Sync Settings</a>
            <a className="op-btn op-btn-secondary" href="#channels">Refresh Tokens</a>
            <Link className="op-btn op-btn-secondary" to="/accounts">Manage Channels</Link>
          </>
        ) : (
          <>
            <button className="op-btn op-btn-secondary" type="button" onClick={onPauseSync}>Pause Sync</button>
            <Link className="op-btn op-btn-secondary" to="/accounts">Manage Channels</Link>
          </>
        )}
      </div>
    </section>
  );
};

export const AuthStatusBanner: React.FC<{ syncState: StudioSyncState; onConnect: () => void; onResumeSync: () => void }> = ({
  syncState,
  onConnect,
  onResumeSync,
}) => {
  if (syncState === 'active') return null;
  const local = syncState === 'local';
  return (
    <div className={`op-banner ${local ? 'warning' : 'paused'}`} role="alert" aria-live="polite">
      <span aria-hidden="true">{local ? '!' : 'II'}</span>
      <div className="op-banner-body">
        <div className="op-banner-title">{local ? 'Not Authenticated - Local Workspace Only' : 'Studio Sync is Paused'}</div>
        <div className="op-banner-text">
          {local
            ? 'Your studio work can be drafted locally in this view. Connect an account to sync channels, refresh publishing tokens, or publish releases.'
            : 'Local edits are safe, but channel sync, token refresh, scheduled publishing, and release automation will not run until sync is resumed.'}
        </div>
      </div>
      <div className="op-banner-actions">
        <button className={`op-btn ${local ? 'op-btn-primary' : 'op-btn-paused'} op-btn-sm`} type="button" onClick={local ? onConnect : onResumeSync}>
          {local ? 'Connect Account' : 'Resume Sync'}
        </button>
      </div>
    </div>
  );
};

const ReadinessList: React.FC<{ items: Array<{ label: string; state: 'done' | 'warn' | 'pending' | 'paused' | 'local' }> }> = ({ items }) => (
  <div className="op-readiness-list">
    {items.map((item) => (
      <div key={item.label} className="op-readiness-item">
        <span className={`op-ri-dot op-ri-${item.state === 'pending' ? 'pend' : item.state}`} />
        {item.label}
      </div>
    ))}
  </div>
);

export const CurrentProductionCard: React.FC<{
  project: Project | null;
  script: ScriptRevision | null;
  latestJob: GenerationJob | null;
  syncState: StudioSyncState;
  readinessReasons: string[];
  onApprovePreview: () => void;
  onRender: () => void;
  onResumeSync: () => void;
}> = ({ project, script, latestJob, syncState, readinessReasons, onApprovePreview, onRender, onResumeSync }) => {
  const step = currentStep(project, latestJob, readinessReasons);
  const speakerMappings = normalizePreview(project?.preview_settings).speaker_mappings;
  const cast = speakerMappings.slice(0, 2);
  return (
    <section className="op-current-production" aria-labelledby="current-prod-title" style={{ '--state-line': syncState === 'paused' ? 'rgba(251,146,60,0.25)' : 'rgba(167,139,250,0.3)', '--next-color': syncState === 'paused' ? 'var(--paused)' : 'var(--warning)' } as React.CSSProperties}>
      <div className="op-prod-top">
        <div>
          <div className="op-prod-meta">
            <span className="op-badge op-badge-info">{titleCase(script?.generated_script?.content_format_id || 'Production')}</span>
            <span className="op-badge op-badge-muted">{titleCase(project?.target_platform || 'YouTube Shorts')}</span>
            <span className={`op-badge ${syncState === 'local' ? 'op-badge-local' : syncState === 'paused' ? 'op-badge-paused' : 'op-badge-success'}`}>
              {syncState === 'local' ? 'Local Only' : syncState === 'paused' ? 'Sync Paused' : 'Sync Active'}
            </span>
          </div>
          <h2 className="op-prod-title-main" id="current-prod-title">{project?.name || 'Start a Production'}</h2>
        </div>
      </div>
      <div className="op-prod-next-action">
        <span className="op-prod-next-label">Next Step</span>
        <span className="op-prod-next-text">
          {readinessReasons.length ? readinessReasons[0] : syncState === 'local' ? 'Approve local preview / Connect account to publish' : syncState === 'paused' ? 'Resume Sync to activate release - or approve preview locally' : 'Render final cut or prepare release'}
        </span>
        <span style={{ marginLeft: 'auto' }}>
          <span className={`op-badge ${readinessReasons.length ? 'op-badge-error' : 'op-badge-warning'}`}>{step}</span>
        </span>
      </div>
      <div className="op-prod-details-grid">
        <div className="op-prod-detail"><span className="op-prod-detail-label">Format</span><span className="op-prod-detail-value">{titleCase(script?.generated_script?.content_format_id || 'Not selected')}</span></div>
        <div className="op-prod-detail"><span className="op-prod-detail-label">Target</span><span className="op-prod-detail-value">{titleCase(project?.target_platform || 'Not selected')}</span></div>
        <div className="op-prod-detail"><span className="op-prod-detail-label">Current Step</span><span className="op-prod-detail-value" style={{ color: readinessReasons.length ? 'var(--error)' : 'var(--warning)' }}>{step}</span></div>
        <div className="op-prod-detail"><span className="op-prod-detail-label">Selected Scene</span><span className="op-prod-detail-value cyan">{String(project?.preview_settings?.background_metadata?.original_filename || project?.preview_settings?.background_preset_id || 'Select a scene')}</span></div>
        {cast.map((mapping) => (
          <div key={mapping.speaker_name} className="op-prod-detail">
            <span className="op-prod-detail-label">Cast - {mapping.speaker_name}</span>
            <span className="op-prod-detail-value">{mapping.character_display_name || mapping.voice_profile_id || 'Unassigned'}</span>
          </div>
        ))}
      </div>
      <div className="op-prod-actions">
        <button className="op-btn op-btn-primary" type="button" onClick={onApprovePreview} disabled={!project || !project.current_output_video_id}>
          Approve Preview
        </button>
        <button className="op-btn op-btn-secondary" type="button" onClick={onRender} disabled={!project || readinessReasons.length > 0}>
          Render Cut
        </button>
        {syncState === 'paused' && <button className="op-btn op-btn-paused" type="button" onClick={onResumeSync}>Resume Sync</button>}
        {project && <Link className="op-btn op-btn-secondary" to={`/projects/${project.id}`}>Edit Production</Link>}
        <button className="op-btn op-btn-ghost" type="button" disabled={syncState !== 'active'}>
          {syncState === 'local' ? 'Connect to Publish' : syncState === 'paused' ? 'Publish Paused' : 'Prepare Release'}
        </button>
      </div>
    </section>
  );
};

export const StartProductionPanel: React.FC<{
  isAuthenticated: boolean;
  onCreated: (projectId: number) => void;
  onConnect: () => void;
}> = ({ isAuthenticated, onCreated, onConnect }) => {
  const [name, setName] = useState('New Debate Short');
  const [idea, setIdea] = useState('Two characters debate whether preview settings should drive the final render.');
  const [contentFormat, setContentFormat] = useState('debate_format');
  const [platform, setPlatform] = useState<PlatformTarget>('youtube_shorts');
  const [castPreset, setCastPreset] = useState('Host, Guest');
  const [duration, setDuration] = useState(45);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const createProduction = async () => {
    if (!isAuthenticated) {
      window.localStorage.setItem('omniposter.localDraft', JSON.stringify({ name, idea, contentFormat, platform, castPreset, duration }));
      onConnect();
      return;
    }
    try {
      setBusy(true);
      setError(null);
      const projectResponse = await apiClient.post<Project>('/projects', {
        name,
        target_platform: platform === 'youtube_shorts' ? 'youtube' : platform,
        allowed_platforms: [platform === 'youtube_shorts' ? 'youtube' : platform],
      });
      const speakers = castPreset.split(',').map((item) => item.trim()).filter(Boolean);
      const scriptResponse = await apiClient.post<{ generated_script: GeneratedScript; provider_metadata: any; validation_warnings: string[]; fallback_used: boolean }>('/script-generation/generate', {
        idea,
        content_format_id: contentFormat,
        platform,
        target_duration_sec: duration,
        speaker_names: speakers,
      });
      const generated = scriptResponse.data.generated_script;
      await apiClient.put(`/projects/${projectResponse.data.id}/script`, {
        raw_text: generated.lines.map((line) => `<${line.speaker_label}> ${line.text}`).join('\n'),
        parsed_lines: generated.lines.map((line, index) => ({
          speaker: line.speaker_label,
          text: line.text,
          order: index,
        })),
        generated_script: generated,
        source: 'generated',
      });
      onCreated(projectResponse.data.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create production.');
    } finally {
      setBusy(false);
    }
  };

  return (
    <section id="start-production" aria-labelledby="start-production-title">
      <div className="op-section-header">
        <div>
          <h2 className="op-section-title" id="start-production-title">Start a Production</h2>
          <div className="op-section-title-sub">Format-first creation for repeatable short-form video packages.</div>
        </div>
        <span className="op-badge op-badge-cyan">Format presets ready</span>
      </div>
      <div className="op-panel">
        <div className="op-panel-body op-start-production-grid">
          <form className="op-form-grid" aria-label="Create a new production" onSubmit={(event) => { event.preventDefault(); void createProduction(); }}>
            <div className="op-field"><label htmlFor="production-name">Production Name</label><input className="op-input" id="production-name" value={name} onChange={(event) => setName(event.target.value)} /></div>
            <div className="op-field"><label htmlFor="content-format">Content Format</label><select className="op-select" id="content-format" value={contentFormat} onChange={(event) => setContentFormat(event.target.value)}>{contentFormats.map((format) => <option key={format.id} value={format.id}>{format.label}</option>)}</select></div>
            <div className="op-field"><label htmlFor="target-platform">Target Platform</label><select className="op-select" id="target-platform" value={platform} onChange={(event) => setPlatform(event.target.value as PlatformTarget)}>{platformTargets.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}</select></div>
            <div className="op-field"><label htmlFor="cast-preset">Cast Preset</label><input className="op-input" id="cast-preset" value={castPreset} onChange={(event) => setCastPreset(event.target.value)} /></div>
            <div className="op-field" style={{ gridColumn: '1 / -1' }}><label htmlFor="production-idea">Idea / Prompt</label><textarea className="op-textarea" id="production-idea" value={idea} onChange={(event) => setIdea(event.target.value)} /></div>
            <div className="op-field"><label htmlFor="duration-target">Duration Target</label><input className="op-input" id="duration-target" type="number" value={duration} onChange={(event) => setDuration(Number(event.target.value))} /></div>
          </form>
          <div>
            <div className="op-panel-section-label">Reusable package includes</div>
            <div className="op-asset-presets">
              {['Speaker-separated script', 'Voice profile assignment', 'Scene preset', 'Caption style', 'Render preset', 'Release metadata draft'].map((item) => <span key={item} className="op-chip">{item}</span>)}
            </div>
            {error && <div className="op-error" style={{ marginTop: 'var(--space-4)' }}>{error}</div>}
            <div style={{ marginTop: 'var(--space-4)', display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
              <button className="op-btn op-btn-primary" type="button" onClick={createProduction} disabled={busy}>{busy ? 'Creating...' : isAuthenticated ? 'Create Production' : 'Create Local Draft'}</button>
              <a className="op-btn op-btn-secondary" href="#voice-cast">Browse Formats</a>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export const PreviewRenderWorkspace: React.FC<{
  project: Project | null;
  script: ScriptRevision | null;
  latestJob: GenerationJob | null;
  syncState: StudioSyncState;
  backgroundPresets: BackgroundPreset[];
  readinessReasons: string[];
  onPreviewSettingsChange: (patch: Partial<ProjectPreviewSettings>) => void;
  onSelectBackground: (presetKey: string) => void;
  onApprovePreview: () => void;
  onRender: (kind: 'preview' | 'draft' | 'final' | 'debug') => void;
}> = ({ project, script, latestJob, syncState, backgroundPresets, readinessReasons, onPreviewSettingsChange, onSelectBackground, onApprovePreview, onRender }) => {
  const preview = normalizePreview(project?.preview_settings);
  const mappings = preview.speaker_mappings.length ? preview.speaker_mappings : [{ speaker_name: 'Speaker', sample_text: 'Dialogue text will appear here.' } as ProjectPreviewSpeakerMapping];
  const activeMapping = mappings[0];
  const bgUrl = toApiHref(preview.background_url);
  const mimeType = String(preview.background_metadata?.mime_type || '');
  const scale = preview.speaker_png_size === 'large' ? 1.18 : preview.speaker_png_size === 'compact' ? 0.82 : 1;
  const isVideo = mimeType.startsWith('video/');
  return (
    <section aria-labelledby="preview-workspace-title">
      <div className="op-section-header">
        <div>
          <h2 className="op-section-title" id="preview-workspace-title">Preview - Render Workspace</h2>
          <div className="op-section-title-sub">{project ? `Golden preview for ${project.name}` : 'Local visual shell - connect to render'}</div>
        </div>
        <span className={`op-badge ${readinessReasons.length ? 'op-badge-error' : syncState === 'paused' ? 'op-badge-paused' : 'op-badge-warning'}`}>
          <span className="op-dot" /> {readinessReasons.length ? 'Render blocked' : syncState === 'paused' ? 'Sync paused' : 'Preview needs approval'}
        </span>
      </div>
      <div className="op-panel">
        <div className="op-panel-body" style={{ padding: 'var(--space-6)' }}>
          <div className="op-grid-preview-render" style={{ alignItems: 'start' }}>
            <div className="op-video-frame-wrap">
              <div className="op-video-frame-label">9:16 Preview Frame - 1080x1920</div>
              <div className="op-video-frame" role="img" aria-label="Video preview frame">
                {bgUrl ? (isVideo ? <video className="op-scene-bg" src={bgUrl} muted playsInline /> : <img className="op-scene-bg" src={bgUrl} alt="" />) : <div className="op-scene-bg" />}
                <div className="op-scene-split-left" /><div className="op-scene-split-right" />
                <div className="op-scene-label">{String(preview.background_metadata?.original_filename || preview.background_preset_id || 'Select a Scene')}</div>
                <div className="op-frame-badge-top">1080x1920</div>
                {mappings.slice(0, 2).map((mapping, index) => (
                  <div key={mapping.speaker_name} className={`op-speaker-zone ${index === 0 ? 'left' : 'right'}`}>
                    <div className="op-speaker-avatar" style={{ width: `${52 * scale * preview.layout.character_scale}px`, height: `${72 * scale * preview.layout.character_scale}px` }}>
                      {mapping.character_portrait_url ? <img src={toApiHref(mapping.character_portrait_url)} alt={mapping.character_display_name || mapping.speaker_name} /> : <span className="op-speaker-initials">{initials(mapping.character_display_name || mapping.speaker_name)}</span>}
                    </div>
                    <div className="op-speaker-label-tag">{mapping.speaker_name.toUpperCase()} · {mapping.voice_profile_id ? 'VOICE' : 'UNASSIGNED'}</div>
                  </div>
                ))}
                <div className="op-caption-overlay">
                  <div className="op-caption-speaker-tag">{(activeMapping.display_label || activeMapping.speaker_name).toUpperCase()}</div>
                  <div className="op-caption-text" style={{ fontSize: `${Math.max(7, Math.round(preview.layout.chat_font_size_px / 2.35))}px` }}>
                    "{activeMapping.sample_text || scriptLinesFor(script)[0]?.text || 'Preview captions will follow the speaker timeline.'}"
                  </div>
                </div>
                {syncState === 'paused' && <div className="op-frame-paused-overlay"><div className="op-frame-paused-tag">SYNC PAUSED</div></div>}
                <div className="op-frame-timecode">00:00:08:04 · PREVIEW DRAFT</div>
              </div>
              <div style={{ display: 'flex', gap: 'var(--space-2)', marginTop: 'var(--space-3)', flexWrap: 'wrap', justifyContent: 'center' }}>
                <span className="op-chip">Speaker PNG: {titleCase(preview.layout_preset)}</span>
                <span className="op-chip">{titleCase(preview.caption_style)}</span>
              </div>
            </div>
            <div>
              <div className="op-panel-section-label">Editable Preview Settings</div>
              <div className="op-control-grid">
                <div className="op-control-card"><label className="op-control-label" htmlFor="background-preset">Background</label><select id="background-preset" className="op-select" value={preview.background_preset_id || ''} onChange={(event) => event.target.value && onSelectBackground(event.target.value)}><option value="">Select background</option>{backgroundPresets.map((preset) => <option key={preset.key} value={preset.key}>{preset.name}</option>)}</select></div>
                <div className="op-control-card"><label className="op-control-label" htmlFor="layout-preset">Layout Preset</label><select id="layout-preset" className="op-select" value={preview.layout_preset} onChange={(event) => onPreviewSettingsChange({ layout_preset: event.target.value } as Partial<ProjectPreviewSettings>)}><option value="left_right_locked">Left / Right speakers locked</option><option value="stacked_reaction">Stacked reaction</option><option value="narrator_only">Narrator only</option></select></div>
                <div className="op-control-card"><label className="op-control-label" htmlFor="bubble-font">Bubble Font Size</label><input id="bubble-font" className="op-input" type="number" min={12} max={32} value={preview.layout.chat_font_size_px} onChange={(event) => onPreviewSettingsChange({ layout: { ...preview.layout, chat_font_size_px: Number(event.target.value) } } as Partial<ProjectPreviewSettings>)} /></div>
                <div className="op-control-card"><label className="op-control-label" htmlFor="speaker-png-size">Speaker PNG Size</label><select id="speaker-png-size" className="op-select" value={preview.speaker_png_size} onChange={(event) => onPreviewSettingsChange({ speaker_png_size: event.target.value } as Partial<ProjectPreviewSettings>)}><option value="compact">Compact</option><option value="standard">Standard</option><option value="large">Large</option></select></div>
                <div className="op-control-card"><label className="op-control-label" htmlFor="caption-style">Caption Style</label><select id="caption-style" className="op-select" value={preview.caption_style} onChange={(event) => onPreviewSettingsChange({ caption_style: event.target.value } as Partial<ProjectPreviewSettings>)}><option value="bold_bubble">Bold bubble captions</option><option value="clean_lower_third">Clean lower-third</option><option value="large_karaoke">Large karaoke captions</option></select></div>
                <div className="op-control-card"><label className="op-control-label" htmlFor="render-preset">Render Preset</label><select id="render-preset" className="op-select" value={preview.render_preset} onChange={(event) => onPreviewSettingsChange({ render_preset: event.target.value } as Partial<ProjectPreviewSettings>)}><option value="shorts_1080x1920">1080x1920 Shorts</option><option value="reels_1080x1350">1080x1350 Reels</option><option value="draft_720x1280">720x1280 Draft</option></select></div>
              </div>
              <div className="op-divider" />
              <div className="op-panel-section-label">Audio Mapping</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)', marginBottom: 'var(--space-4)' }}>
                {mappings.slice(0, 4).map((mapping) => (
                  <div key={mapping.speaker_name} className="op-audio-map-row">
                    <span className="op-audio-map-speaker">{mapping.speaker_name}</span><span className="op-audio-map-arrow">→</span><span className="op-audio-map-voice">{mapping.character_display_name || mapping.voice_profile_id || 'Unassigned'}</span><span className="op-audio-map-provider">{mapping.voice_profile_id ? 'Profile' : 'Missing'}</span>
                  </div>
                ))}
              </div>
              <div className="op-panel-section-label">Render Readiness</div>
              <ReadinessList items={[
                { label: script ? 'Script ready' : 'Script missing', state: script ? 'done' : 'warn' },
                { label: readinessReasons.some((reason) => reason.includes('voice')) ? 'Voices need assignment' : 'Voices assigned', state: readinessReasons.some((reason) => reason.includes('voice')) ? 'warn' : 'done' },
                { label: preview.background_url ? 'Scene loaded' : 'Scene missing', state: preview.background_url ? 'done' : 'warn' },
                { label: project?.approved_at ? 'Preview approved' : 'Preview needs approval', state: project?.approved_at ? 'done' : 'warn' },
                { label: syncState === 'local' ? 'Render pending - local only' : syncState === 'paused' ? 'Release automation paused' : 'Release controls active', state: syncState === 'active' ? 'done' : syncState },
              ]} />
              <div style={{ display: 'flex', gap: 'var(--space-3)', marginTop: 'var(--space-5)', flexWrap: 'wrap' }}>
                <button className="op-btn op-btn-primary" type="button" onClick={onApprovePreview} disabled={!project?.current_output_video_id}>Approve Preview</button>
                <button className="op-btn op-btn-secondary op-btn-sm" type="button" onClick={() => onRender('preview')} disabled={!project || readinessReasons.length > 0}>Render Preview</button>
                <button className="op-btn op-btn-secondary op-btn-sm" type="button" onClick={() => onRender('final')} disabled={!project || readinessReasons.length > 0 || !project.approved_at}>Final Render</button>
                {latestJob && <a className="op-btn op-btn-ghost op-btn-sm" href="#render-queue">Inspect Artifacts</a>}
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export const ScriptVoiceMappingPanel: React.FC<{ script: ScriptRevision | null; project: Project | null; latestJob: GenerationJob | null }> = ({
  script,
  project,
  latestJob,
}) => {
  const preview = normalizePreview(project?.preview_settings);
  const bindingBySpeaker = new Map(preview.speaker_mappings.map((mapping) => [mapping.speaker_name, mapping]));
  const segments = ((latestJob?.tts_result as any)?.segments || []) as Array<Record<string, any>>;
  const segmentBySpeaker = new Map(segments.map((segment) => [String(segment.speaker), segment]));
  const lines = scriptLinesFor(script).slice(0, 8);
  return (
    <section aria-labelledby="voice-mapping-title">
      <div className="op-section-header">
        <div><h2 className="op-section-title" id="voice-mapping-title">Script - Voice Mapping</h2><div className="op-section-title-sub">Speaker-separated dialogue with assigned XTTS / OpenVoice profiles.</div></div>
        <span className={`op-badge ${preview.speaker_mappings.every((item) => item.voice_profile_id) && preview.speaker_mappings.length ? 'op-badge-success' : 'op-badge-warning'}`}>
          {preview.speaker_mappings.filter((item) => item.voice_profile_id).length} speakers mapped
        </span>
      </div>
      <div className="op-panel">
        <div style={{ padding: 'var(--space-4)' }}>
          {lines.length ? lines.map((line, index) => {
            const mapping = bindingBySpeaker.get(line.speaker);
            const segment = segmentBySpeaker.get(line.speaker);
            return (
              <div key={`${line.speaker}-${line.order}-${index}`} className="op-mapping-row">
                <div className="op-mapping-speaker"><span className="op-mapping-speaker-dot" style={{ background: ['#60a5fa', '#a78bfa', '#34d399', '#f5a623'][index % 4] }} /><span className="op-mapping-speaker-name">{line.speaker}</span></div>
                <div className="op-mapping-script">"{line.text}"</div>
                <div className="op-mapping-voice"><span className="op-mapping-voice-name">{mapping?.character_display_name || mapping?.voice_profile_id || 'Unassigned voice'}</span><span className="op-mapping-voice-provider">{segment?.provider_used || 'pending'} · {segment?.artifact_url ? String(segment.artifact_url).split('/').pop() : 'segment pending'}</span></div>
                <div className="op-mapping-status"><span className={`op-badge ${mapping?.voice_profile_id ? 'op-badge-success' : 'op-badge-error'}`}>{mapping?.voice_profile_id ? 'Mapped' : 'Missing'}</span>{segment?.artifact_url && <a className="op-badge op-badge-cyan" href={toApiHref(String(segment.artifact_url))}>WAV</a>}</div>
              </div>
            );
          }) : (
            <div className="op-panel-subtitle">No script lines yet. Generate a production script to populate speaker mapping.</div>
          )}
        </div>
      </div>
    </section>
  );
};

export const VoiceCastProfilesPanel: React.FC<{ profiles: VoiceProfile[]; characterPresets: CharacterPreset[]; project: Project | null }> = ({
  profiles,
  characterPresets,
  project,
}) => {
  const profileMap = voiceById(profiles);
  const selectedIds = new Set(normalizePreview(project?.preview_settings).speaker_mappings.map((mapping) => mapping.voice_profile_id).filter(Boolean) as string[]);
  const cards = profiles.filter((profile) => selectedIds.has(profile.id)).concat(profiles.filter((profile) => !selectedIds.has(profile.id)).slice(0, Math.max(0, 4 - selectedIds.size))).slice(0, 4);
  return (
    <section id="voice-cast" aria-labelledby="voice-cast-title">
      <div className="op-section-header">
        <div><h2 className="op-section-title" id="voice-cast-title">Voice Cast Profiles</h2><div className="op-section-title-sub">Reusable voice profiles with speaker images, reference counts, validation, and golden previews.</div></div>
        <span className="op-badge op-badge-success"><span className="op-dot" /> {cards.filter((item) => item.reference_audio_count || item.provider !== 'espeak').length} production-ready</span>
      </div>
      <div className="op-voice-cast-grid">
        {cards.map((profile) => {
          const preset = characterPresets.find((item) => item.voice_profile_id === profile.id);
          const imageUrl = profile.associated_character_image_url || preset?.portrait_url;
          return (
            <article key={profile.id} className="op-voice-profile-card">
              <div className="op-voice-head">
                <div className="op-voice-avatar">{imageUrl ? <img src={toApiHref(imageUrl)} alt={profile.display_name} /> : initials(profile.display_name)}</div>
                <div><div className="op-voice-name">{profile.display_name}</div><div className="op-voice-sub">{imageUrl ? 'Speaker image linked' : 'No speaker image linked'}</div></div>
              </div>
              <div className="op-voice-facts"><span className="op-chip">Provider: {profile.provider}</span><span className="op-chip">Refs: {profile.reference_audio_count}</span><span className="op-chip">Golden: {profile.selected_recipe && Object.keys(profile.selected_recipe).length ? 'saved' : 'missing'}</span><span className={`op-badge ${selectedIds.has(profile.id) ? 'op-badge-success' : 'op-badge-info'}`}>{selectedIds.has(profile.id) ? 'Assigned' : 'Available'}</span></div>
            </article>
          );
        })}
        {cards.length < 4 && <article className="op-voice-profile-card missing"><div className="op-voice-head"><div className="op-voice-avatar">+</div><div><div className="op-voice-name">New Character</div><div className="op-voice-sub">Missing references and image</div></div></div><div className="op-voice-facts"><span className="op-chip">Provider: unassigned</span><span className="op-chip">Refs: 0</span><span className="op-badge op-badge-error">Blocked</span></div></article>}
      </div>
    </section>
  );
};

export const SceneLibraryPanel: React.FC<{ presets: BackgroundPreset[]; project: Project | null; onSelect: (key: string) => void }> = ({
  presets,
  project,
  onSelect,
}) => {
  const preview = normalizePreview(project?.preview_settings);
  return (
    <section id="scene-library" aria-labelledby="scene-library-title">
      <div className="op-section-header"><div><h2 className="op-section-title" id="scene-library-title">Scene Library / Preview Presets</h2><div className="op-section-title-sub">Reusable backgrounds, speaker placement presets, and caption layouts for repeatable renders.</div></div><span className="op-badge op-badge-cyan">Selected: {preview.background_preset_id || 'None'}</span></div>
      <div className="op-scene-preset-grid">
        {presets.slice(0, 6).map((preset) => (
          <button key={preset.key} className={`op-scene-card ${preview.background_preset_id === preset.key ? 'selected' : ''}`} type="button" onClick={() => onSelect(preset.key)}>
            <div className="op-scene-thumb">{preset.mime_type.startsWith('image/') ? <img src={toApiHref(preset.content_url)} alt="" /> : <video src={toApiHref(preset.content_url)} muted playsInline />}</div>
            <div className="op-scene-name">{preset.name}</div>
            <div className="op-scene-meta">{preset.description || 'Background + speaker PNG slots'}</div>
          </button>
        ))}
        {!presets.length && <div className="op-panel-subtitle">No background presets found. Upload/select one in the production editor.</div>}
      </div>
    </section>
  );
};

export const PipelineStatusPanel: React.FC<{ project: Project | null; readinessReasons: string[]; syncState: StudioSyncState }> = ({
  project,
  readinessReasons,
  syncState,
}) => {
  const preview = normalizePreview(project?.preview_settings);
  const done = {
    idea: Boolean(project),
    script: Boolean(project?.current_script),
    cast: Boolean(preview.speaker_mappings.length && preview.speaker_mappings.every((item) => item.voice_profile_id)),
    scene: Boolean(preview.background_url),
    preview: Boolean(project?.current_output_video_id),
    render: Boolean(project?.latest_output),
  };
  const stages = [
    ['Idea', 'Concept locked', done.idea],
    ['Script', 'Speaker-separated', done.script],
    ['Cast', 'Profiles assigned', done.cast],
    ['Scene', 'Preset loaded', done.scene],
    ['Preview', project?.approved_at ? 'Approved' : 'Awaiting approval', done.preview],
    ['Render', project?.latest_output ? 'Final available' : 'Pending approval', done.render],
    ['Release', syncState === 'local' ? 'Local draft only' : syncState === 'paused' ? 'Automation paused' : 'Ready when approved', syncState === 'active' && Boolean(project?.approved_at)],
  ] as const;
  const activeIndex = Math.max(0, stages.findIndex((stage) => !stage[2]));
  return (
    <section aria-labelledby="pipeline-title">
      <div className="op-section-header"><h2 className="op-section-title" id="pipeline-title">Production Pipeline</h2><span className={`op-badge ${readinessReasons.length ? 'op-badge-error' : 'op-badge-warning'}`}>{readinessReasons.length ? 'Blocked' : `Step ${activeIndex + 1}`}</span></div>
      <div className="op-panel"><div className="op-panel-body" style={{ padding: 'var(--space-4) var(--space-2)' }}><div className="op-pipeline-rail" role="list" aria-label="Production pipeline stages">
        {stages.map((stage, index) => {
          const state = stage[2] ? 'done' : index === activeIndex ? 'active' : stage[0] === 'Release' ? syncState : 'pending';
          return <div key={stage[0]} className={`op-pipeline-stage op-ps-${state}`} role="listitem"><div className="op-pipeline-stage-number">{stage[2] ? '✓' : index + 1}</div><div className="op-pipeline-stage-name">{stage[0]}</div><div className="op-pipeline-stage-status">{stage[1]}</div></div>;
        })}
      </div></div></div>
    </section>
  );
};

export const StudioHealthPanel: React.FC<{ latestJob: GenerationJob | null; syncState: StudioSyncState; profiles: VoiceProfile[] }> = ({
  latestJob,
  syncState,
  profiles,
}) => {
  const cloneProvider = profiles.find((profile) => ['xtts', 'openvoice', 'rvc'].includes(profile.provider?.toLowerCase()))?.provider || 'Local TTS';
  const cacheHits = Number((latestJob?.cache_statistics as any)?.hits || (latestJob?.cache_statistics as any)?.total_events || 0);
  const cards = [
    ['Voice Engine', cloneProvider, 'OpenVoice / XTTS / local inference', 'success'],
    ['Preview Persistence', 'Persisted', 'Settings saved and reused by render', 'success'],
    ['Render Engine', latestJob?.status ? titleCase(latestJob.status) : 'Standby', latestJob?.current_phase || 'ffmpeg ready', latestJob?.status === 'failed' ? 'error' : 'warning'],
    ['Segment Cache', `${cacheHits} hits`, 'Voice segments cached locally', cacheHits ? 'success' : 'warning'],
    ['Artifact Storage', 'Local disk', 'Segment WAVs, final audio, MP4, and logs retained', 'success'],
    ['Studio Sync', syncState === 'local' ? 'Offline' : syncState === 'paused' ? 'Paused' : 'Active', syncState === 'active' ? 'Automation enabled' : 'Connect or resume to release', syncState === 'active' ? 'success' : syncState],
  ];
  return (
    <section aria-labelledby="studio-health-title">
      <div className="op-section-header"><h2 className="op-section-title" id="studio-health-title">Studio Health</h2></div>
      <div className="op-health-grid">
        {cards.map(([name, value, sub, state]) => <div key={name} className="op-health-card"><div className="op-health-card-header"><span className="op-health-card-name">{name}</span><span className={`op-badge op-badge-${state === 'local' ? 'local' : state === 'paused' ? 'paused' : state}` as string}><span className="op-dot" /> {titleCase(String(state))}</span></div><div className="op-health-card-value" style={{ color: state === 'paused' ? 'var(--paused)' : state === 'local' ? 'var(--local)' : undefined }}>{value}</div><div className="op-health-card-sub">{sub}</div></div>)}
      </div>
    </section>
  );
};

export const ActiveProductionsPanel: React.FC<{ projects: Project[]; syncState: StudioSyncState; onSelect: (projectId: number) => void }> = ({
  projects,
  syncState,
  onSelect,
}) => (
  <div className="op-panel op-span-col-rows" aria-labelledby="active-prod-panel-title">
    <div className="op-panel-header"><div><div className="op-panel-title" id="active-prod-panel-title">Active Productions</div><div className="op-panel-subtitle">{projects.length} productions in workspace</div></div><span className={`op-badge ${syncState === 'local' ? 'op-badge-local' : syncState === 'paused' ? 'op-badge-paused' : 'op-badge-success'}`}>{syncState === 'local' ? 'Local' : syncState === 'paused' ? 'Sync paused' : 'Synced'}</span></div>
    <div>
      {projects.slice(0, 6).map((project) => (
        <div key={project.id} className="op-production-item">
          <div className="op-prod-item-indicator" style={{ background: project.status === 'failed' ? 'var(--error)' : project.current_output_video_id ? 'var(--success)' : 'var(--warning)' }} />
          <div className="op-prod-item-body"><div className="op-prod-item-name">{project.name}</div><div className="op-prod-item-meta"><span>{titleCase(project.target_platform)}</span><span>·</span><span>{titleCase(project.status)}</span></div><div style={{ marginTop: 'var(--space-2)', display: 'flex', gap: 'var(--space-1)' }}><span className={`op-badge ${syncState === 'local' ? 'op-badge-local' : syncState === 'paused' ? 'op-badge-paused' : 'op-badge-success'}`}>{syncState === 'active' ? 'Release available' : syncState === 'paused' ? 'Release paused' : 'Local draft'}</span></div></div>
          <div className="op-prod-item-actions"><button className="op-btn op-btn-ghost op-btn-sm" type="button" onClick={() => onSelect(project.id)}>Open Studio</button><Link className="op-btn op-btn-secondary op-btn-sm" to={`/projects/${project.id}`}>Editor</Link></div>
        </div>
      ))}
      {!projects.length && <div className="op-panel-body"><div className="op-panel-subtitle">No productions yet. Start one above.</div></div>}
    </div>
  </div>
);

export const RenderQueuePanel: React.FC<{ jobs: GenerationJob[]; readinessReasons: string[] }> = ({ jobs, readinessReasons }) => (
  <div className="op-panel" id="render-queue" aria-labelledby="render-queue-title">
    <div className="op-panel-header"><div><div className="op-panel-title" id="render-queue-title">Render Queue</div><div className="op-panel-subtitle">Jobs, cache reuse, and artifact inspection</div></div></div>
    <div>
      {jobs.slice(0, 4).map((job) => {
        const artifactUrls = job.artifact_urls || {};
        const progressClass = job.status === 'completed' ? 'op-pb-done' : job.status === 'failed' ? 'op-pb-blocked' : 'op-pb-running';
        return (
          <div key={job.id} className="op-queue-item">
            <div className="op-queue-item-top"><span className="op-queue-item-name">{job.output_kind}_{job.id}.mp4</span><span className={`op-badge ${badgeClassForStatus(job.status)}`}><span className="op-dot" /> {titleCase(job.status)}</span></div>
            <div className="op-queue-item-meta">{job.current_phase || 'Queued'} · {job.provider_name}</div>
            <div className="op-progress-bar-wrap"><div className={`op-progress-bar-fill ${progressClass}`} style={{ width: `${Math.max(5, job.progress || 0)}%` }} /></div>
            <div className="op-artifact-grid">
              <a className="op-artifact-pill" href={toApiHref(String(artifactUrls.composite_audio || ''))}><span>final audio</span><strong>{artifactUrls.composite_audio ? 'saved' : 'pending'}</strong></a>
              <a className="op-artifact-pill" href={toApiHref(String(artifactUrls.render_plan || ''))}><span>render plan</span><strong>{artifactUrls.render_plan ? 'saved' : 'pending'}</strong></a>
              <a className="op-artifact-pill" href={toApiHref(String(artifactUrls.cache_report || ''))}><span>cache report</span><strong>{artifactUrls.cache_report ? 'saved' : 'pending'}</strong></a>
              <a className="op-artifact-pill" href={toApiHref(String(artifactUrls.render_profile || ''))}><span>render log</span><strong>{artifactUrls.render_profile ? 'saved' : 'live'}</strong></a>
            </div>
          </div>
        );
      })}
      {!jobs.length && <div className="op-queue-item"><div className="op-queue-item-top"><span className="op-queue-item-name">No render jobs yet</span><span className={`op-badge ${readinessReasons.length ? 'op-badge-error' : 'op-badge-muted'}`}>{readinessReasons.length ? 'Blocked' : 'Idle'}</span></div><div className="op-queue-item-meta">{readinessReasons[0] || 'Render a preview to populate artifacts.'}</div></div>}
    </div>
  </div>
);

export const ReleaseQueuePanel: React.FC<{ project: Project | null; history: { jobs: PublishJob[]; posts: PublishedPost[] }; syncState: StudioSyncState }> = ({
  project,
  history,
  syncState,
}) => (
  <div className="op-panel" id="release-queue" aria-labelledby="release-queue-title">
    <div className="op-panel-header"><div><div className="op-panel-title" id="release-queue-title">Release Queue</div><div className="op-panel-subtitle">{syncState === 'local' ? 'Local draft only - connect to publish' : syncState === 'paused' ? 'Automation paused - jobs waiting' : 'Publishing support where configured'}</div></div><span className={`op-badge ${syncState === 'active' ? 'op-badge-success' : syncState === 'paused' ? 'op-badge-paused' : 'op-badge-local'}`}>{titleCase(syncState)}</span></div>
    <div>
      {(history.jobs.length ? history.jobs.slice(0, 3) : [{ id: 0, status: project?.current_output_video_id ? 'draft' : 'waiting', routing_platform: project?.target_platform || 'youtube_shorts' } as PublishJob]).map((job) => (
        <div key={job.id || 'draft'} className="op-release-item">
          <div className="op-release-item-top"><span className="op-release-item-name">{project?.latest_output?.asset?.original_filename || `preview_${project?.id || 'draft'}.mp4`}</span><span className={`op-badge ${syncState === 'active' ? 'op-badge-muted' : syncState === 'paused' ? 'op-badge-paused' : 'op-badge-local'}`}>{syncState === 'active' ? titleCase(job.status) : syncState === 'paused' ? 'Waiting' : 'Local draft'}</span></div>
          <span className="op-release-platform">{titleCase(job.routing_platform)} · {syncState === 'local' ? 'no connected channel' : syncState === 'paused' ? 'sync paused' : 'ready when approved'}</span>
          <div className="op-release-prep-grid"><div className="op-release-prep">Metadata: {project ? 'drafted' : 'missing'}</div><div className="op-release-prep">Title: draft</div><div className="op-release-prep">Token: {syncState === 'active' ? 'eligible' : 'not synced'}</div><div className="op-release-prep">Schedule: {syncState === 'active' ? 'available' : 'unavailable'}</div></div>
          <div style={{ marginTop: 'var(--space-2)' }}><button className="op-btn op-btn-ghost op-btn-sm" type="button" disabled={syncState !== 'active' || project?.status !== 'approved'}>{syncState === 'local' ? 'Publish - connect required' : syncState === 'paused' ? 'Publish - resume sync first' : 'Publish'}</button></div>
        </div>
      ))}
    </div>
  </div>
);

export const ChannelsPanel: React.FC<{ accounts: SocialAccount[]; syncState: StudioSyncState; onConnect: () => void }> = ({ accounts, syncState, onConnect }) => {
  const platforms = [
    ['tiktok', 'TikTok', '#ff0050'],
    ['instagram', 'Instagram', '#e4405f'],
    ['youtube', 'YouTube', '#ff0000'],
  ];
  return (
    <section id="channels" aria-labelledby="channels-title">
      <div className="op-section-header"><h2 className="op-section-title" id="channels-title">Channels / Release Support</h2><span className={`op-badge ${syncState === 'active' ? 'op-badge-success' : syncState === 'paused' ? 'op-badge-paused' : 'op-badge-local'}`}>{syncState === 'local' ? 'Disconnected - local preview only' : syncState === 'paused' ? 'Connected - sync paused' : 'Connected'}</span></div>
      <div className="op-grid-3">
        {platforms.map(([key, label, color]) => {
          const platformAccounts = accounts.filter((account) => account.platform === key || (key === 'youtube' && account.platform === 'youtube'));
          const defaultAccount = platformAccounts[0];
          return (
            <div key={key} className="op-channel-card">
              <div className="op-channel-header"><div className="op-channel-name"><span className="op-channel-platform-dot" style={{ background: color }} />{label}</div><span className={`op-badge ${syncState === 'active' && defaultAccount ? 'op-badge-success' : syncState === 'paused' && defaultAccount ? 'op-badge-paused' : 'op-badge-local'}`}>{defaultAccount ? syncState === 'paused' ? 'Sync paused' : defaultAccount.token_status : 'Disconnected'}</span></div>
              <div className="op-channel-meta"><div className="op-channel-meta-row"><span>Accounts</span><span>{defaultAccount ? `${platformAccounts.length} connected` : '-'}</span></div><div className="op-channel-meta-row"><span>Default</span><span style={{ color: 'var(--text-primary)' }}>{defaultAccount?.channel_title || 'None'}</span></div><div className="op-channel-meta-row"><span>Token</span><span style={{ color: syncState === 'paused' ? 'var(--paused)' : 'var(--text-muted)' }}>{defaultAccount ? defaultAccount.token_status : 'Not synced'}</span></div></div>
              <div><button className={`op-btn ${defaultAccount ? 'op-btn-ghost' : 'op-btn-primary'} op-btn-sm`} style={{ width: '100%' }} type="button" onClick={defaultAccount ? undefined : onConnect}>{defaultAccount ? `Manage ${label}` : `Connect ${label}`}</button></div>
            </div>
          );
        })}
      </div>
    </section>
  );
};

const loadCommandRoomData = async (projectId?: number | null): Promise<CommandRoomData> => {
  const [projectsResponse, accountsResponse, characterResponse, voicesResponse, backgroundsResponse] = await Promise.all([
    apiClient.get<{ items: Project[] }>('/projects'),
    apiClient.get<{ items: SocialAccount[] }>('/social-accounts'),
    apiClient.get<{ items: CharacterPreset[] }>('/character-presets'),
    apiClient.get<{ items: VoiceProfile[] }>('/voice-profiles'),
    apiClient.get<BackgroundPreset[]>('/background-presets'),
  ]);
  const projects = projectsResponse.data.items || [];
  const currentProject = projectId ? projects.find((item) => item.id === projectId) || projects[0] || null : projects[0] || null;
  if (!currentProject) {
    return {
      projects,
      currentProject: null,
      script: null,
      jobs: [],
      outputs: [],
      accounts: accountsResponse.data.items || [],
      history: { jobs: [], posts: [] },
      characterPresets: characterResponse.data.items || [],
      voiceProfiles: voicesResponse.data.items || [],
      backgroundPresets: backgroundsResponse.data || [],
    };
  }
  const [projectResponse, scriptResponse, jobsResponse, outputsResponse, historyResponse] = await Promise.all([
    apiClient.get<Project>(`/projects/${currentProject.id}`),
    apiClient.get<{ current_revision: ScriptRevision | null }>(`/projects/${currentProject.id}/script`),
    apiClient.get<{ items: GenerationJob[] }>(`/projects/${currentProject.id}/generation-jobs`),
    apiClient.get<{ items: any[] }>(`/projects/${currentProject.id}/outputs`),
    apiClient.get<{ jobs: PublishJob[]; posts: PublishedPost[] }>(`/projects/${currentProject.id}/publish-history`),
  ]);
  return {
    projects,
    currentProject: projectResponse.data,
    script: scriptResponse.data.current_revision,
    jobs: jobsResponse.data.items || [],
    outputs: outputsResponse.data.items || [],
    accounts: accountsResponse.data.items || [],
    history: historyResponse.data,
    characterPresets: characterResponse.data.items || [],
    voiceProfiles: voicesResponse.data.items || [],
    backgroundPresets: backgroundsResponse.data || [],
  };
};

const computeReadiness = (project: Project | null, script: ScriptRevision | null, jobs: GenerationJob[]) => {
  if (!project) return ['Create or load a production before rendering.'];
  const preview = normalizePreview(project.preview_settings);
  const reasons: string[] = [];
  const speakers = speakersFor(script, preview);
  if (!script || !script.parsed_lines?.length) reasons.push('Add or generate a speaker-separated script.');
  if (!preview.background_url && !project.background_asset_id) reasons.push('Select a background or scene before rendering.');
  if (!speakers.length) reasons.push('Add named dialogue lines so speakers can be mapped.');
  const missingVoice = speakers.filter((speaker) => !preview.speaker_mappings.find((mapping) => mapping.speaker_name === speaker && mapping.voice_profile_id));
  if (missingVoice.length) reasons.push(`Assign voice profiles for ${missingVoice.join(', ')}.`);
  if (jobs.some((job) => ['queued', 'processing', 'running'].includes(job.status))) reasons.push('A render job is already running.');
  return reasons;
};

export const CommandRoomPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const [syncState, setSyncState] = useState<StudioSyncState>(() => getSyncState(isAuthenticated));
  const [data, setData] = useState<CommandRoomData>({
    projects: [],
    currentProject: isAuthenticated ? null : localDraftProject,
    script: null,
    jobs: [],
    outputs: [],
    accounts: [],
    history: { jobs: [], posts: [] },
    characterPresets: [],
    voiceProfiles: [],
    backgroundPresets: [],
  });
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const latestJob = data.jobs[0] || null;
  const readinessReasons = useMemo(() => computeReadiness(data.currentProject, data.script, data.jobs), [data.currentProject, data.script, data.jobs]);

  const load = async (projectId = selectedProjectId) => {
    if (!isAuthenticated) {
      setData((current) => ({ ...current, currentProject: localDraftProject }));
      setSyncState('local');
      return;
    }
    try {
      const next = await loadCommandRoomData(projectId);
      setData(next);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load Command Room data.');
    }
  };

  useEffect(() => {
    setSyncState(getSyncState(isAuthenticated));
    void load(selectedProjectId);
  }, [isAuthenticated, selectedProjectId]);

  const setSync = (next: StudioSyncState) => {
    if (next === 'active') {
      window.localStorage.setItem('omniposter.studioSync', 'active');
    } else if (next === 'paused') {
      window.localStorage.setItem('omniposter.studioSync', 'paused');
    }
    setSyncState(next);
  };

  const connect = () => navigate('/login');

  const patchPreviewSettings = async (patch: Partial<ProjectPreviewSettings>) => {
    if (!isAuthenticated || !data.currentProject || data.currentProject.id < 0) return;
    try {
      const response = await apiClient.patch<ProjectPreviewSettings>(`/projects/${data.currentProject.id}/preview-settings`, patch);
      setData((current) => current.currentProject ? { ...current, currentProject: { ...current.currentProject, preview_settings: response.data } } : current);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save preview settings.');
    }
  };

  const selectBackground = async (presetKey: string) => {
    if (!isAuthenticated || !data.currentProject || data.currentProject.id < 0) return;
    try {
      await apiClient.post(`/projects/${data.currentProject.id}/assets/background/preset/${presetKey}`);
      await load(data.currentProject.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to select scene.');
    }
  };

  const approvePreview = async () => {
    if (!data.currentProject || !isAuthenticated) return;
    try {
      await apiClient.post(`/projects/${data.currentProject.id}/approve-preview`);
      await load(data.currentProject.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Preview approval is unavailable until a preview output exists.');
    }
  };

  const render = async (outputKind: 'preview' | 'draft' | 'final' | 'debug' = 'preview') => {
    if (!data.currentProject || !isAuthenticated || readinessReasons.length) return;
    try {
      setBusy(`render-${outputKind}`);
      await apiClient.post<GenerationJob>(`/projects/${data.currentProject.id}/renders`, {
        background_style: data.currentProject.background_style || 'none',
        output_kind: outputKind,
        provider_name: 'local-compositor',
      });
      await load(data.currentProject.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to queue render.');
    } finally {
      setBusy(null);
    }
  };

  const currentProject = data.currentProject;
  const projects = isAuthenticated ? data.projects : [localDraftProject];

  return (
    <StudioShell currentProject={currentProject} syncState={syncState}>
      <CommandRoomHero
        syncState={syncState}
        queueCount={data.jobs.length}
        onConnect={connect}
        onResumeSync={() => setSync('active')}
        onPauseSync={() => setSync('paused')}
      />
      <AuthStatusBanner syncState={syncState} onConnect={connect} onResumeSync={() => setSync('active')} />
      {error && <div className="op-error">{error}</div>}
      {busy && <div className="op-badge op-badge-warning"><Clock size={14} /> {titleCase(busy)}</div>}
      <CurrentProductionCard project={currentProject} script={data.script} latestJob={latestJob} syncState={syncState} readinessReasons={readinessReasons} onApprovePreview={approvePreview} onRender={() => render('preview')} onResumeSync={() => setSync('active')} />
      <StartProductionPanel isAuthenticated={isAuthenticated} onCreated={(projectId) => setSelectedProjectId(projectId)} onConnect={connect} />
      <PreviewRenderWorkspace project={currentProject} script={data.script} latestJob={latestJob} syncState={syncState} backgroundPresets={data.backgroundPresets} readinessReasons={readinessReasons} onPreviewSettingsChange={patchPreviewSettings} onSelectBackground={selectBackground} onApprovePreview={approvePreview} onRender={render} />
      <ScriptVoiceMappingPanel script={data.script} project={currentProject} latestJob={latestJob} />
      <VoiceCastProfilesPanel profiles={data.voiceProfiles} characterPresets={data.characterPresets} project={currentProject} />
      <SceneLibraryPanel presets={data.backgroundPresets} project={currentProject} onSelect={selectBackground} />
      <PipelineStatusPanel project={currentProject} readinessReasons={readinessReasons} syncState={syncState} />
      <StudioHealthPanel latestJob={latestJob} syncState={syncState} profiles={data.voiceProfiles} />
      <section id="active-productions" aria-labelledby="productions-queues-title">
        <div className="op-section-header"><h2 className="op-section-title" id="productions-queues-title">Active Productions & Queues</h2></div>
        <div className="op-grid-active-queues">
          <ActiveProductionsPanel projects={projects} syncState={syncState} onSelect={setSelectedProjectId} />
          <RenderQueuePanel jobs={data.jobs} readinessReasons={readinessReasons} />
          <ReleaseQueuePanel project={currentProject} history={data.history} syncState={syncState} />
        </div>
      </section>
      <ChannelsPanel accounts={data.accounts} syncState={syncState} onConnect={connect} />
    </StudioShell>
  );
};

export default CommandRoomPage;
