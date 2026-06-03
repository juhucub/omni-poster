import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ChevronDown, ExternalLink, FileUp, Play, RefreshCw, Sparkles } from 'lucide-react';

import apiClient, { apiBaseUrl } from '../../api/client';
import type {
  BackgroundPreset,
  CharacterPreset,
  ContentFormatPreset,
  GeneratedMediaItem,
  GeneratedScript,
  GenerationJob,
  OutputVideo,
  PlatformMetadata,
  PlatformTarget,
  Project,
  PublishJob,
  PublishedPost,
  RenderReadinessEstimate,
  ScriptRevision,
  SocialAccount,
  VoiceProfile,
} from '../../api/models';
import { useAuth } from '../../context/AuthContext';
import {
  computeProductionReadiness,
  defaultPreviewSettings,
  normalizePreviewSettings,
  type ProductionReadiness,
} from '../production/ProductionReadinessPanel';
import { StudioShell, type StudioSyncState } from '../studio/StudioShell';
import {
  FALLBACK_CONTENT_FORMATS,
  durationLabel,
  findFormat,
  speakerCountLabel,
} from '../script-generation/formatBrowserData';

export type CommandRoomMode = 'firstRun' | 'active' | 'allClear';
type CommandTone = 'active' | 'ready' | 'warning' | 'failed' | 'info' | 'brand' | 'muted';
type ProductionRowFamily = 'attention' | 'ready' | 'failed' | 'running';

type CommandRoomData = {
  projects: Project[];
  currentProject: Project | null;
  script: ScriptRevision | null;
  jobs: GenerationJob[];
  outputs: OutputVideo[];
  generatedMedia: GeneratedMediaItem[];
  accounts: SocialAccount[];
  history: { jobs: PublishJob[]; posts: PublishedPost[] };
  metadata: PlatformMetadata | null;
  metadataByProjectId: Record<number, PlatformMetadata | null>;
  characterPresets: CharacterPreset[];
  voiceProfiles: VoiceProfile[];
  backgroundPresets: BackgroundPreset[];
  contentFormats: ContentFormatPreset[];
  renderReadiness: RenderReadinessEstimate | null;
};

export type CommandRoomStageChip = {
  label: string;
  tone: CommandTone;
};

export type CommandRoomQueueItem = {
  label: string;
  detail: string;
  value: string;
  tone: CommandTone;
};

export type CommandRoomProductionRow = {
  project: Project;
  latestJob: GenerationJob | null;
  readiness: ProductionReadiness;
  family: ProductionRowFamily;
  statusLabel: string;
  statusDetail: string;
  stageChips: CommandRoomStageChip[];
  supportChips: CommandRoomStageChip[];
  actionLabel: string;
  actionHref: string;
};

export type CommandRoomViewModel = {
  mode: CommandRoomMode;
  modeLabel: string;
  modeTone: CommandTone;
  hasProductionActivity: boolean;
  counts: {
    queued: number;
    rendering: number;
    failed: number;
    attention: number;
    ready: number;
    blocked: number;
    totalJobs: number;
    cacheHits: number;
  };
  runtimeChips: CommandRoomStageChip[];
  queueItems: CommandRoomQueueItem[];
  productionRows: CommandRoomProductionRow[];
  latestPreview: {
    label: string;
    href: string;
    projectName: string;
    detail: string;
  } | null;
  releasePrep: {
    label: string;
    detail: string;
    tone: CommandTone;
  };
};

export type CommandRoomViewModelInput = Partial<CommandRoomData>;

const LOWER_WORKSPACE_STORAGE_KEY = 'omniposter.commandRoom.lowerWorkspaceOpen';
const ACTIVE_JOB_STATUSES = new Set(['queued', 'processing', 'running', 'retrying']);
const FAILED_JOB_STATUSES = new Set(['failed', 'blocked']);
const ACTIVITY_STATUSES = new Set([
  'script_ready',
  'assets_ready',
  'preview_ready',
  'approved',
  'published',
  'render_queued',
  'rendering',
  'in_review',
  'changes_requested',
  'publish_queued',
  'scheduled',
  'publishing',
]);

const platformTargets: Array<{ id: PlatformTarget; label: string }> = [
  { id: 'youtube_shorts', label: 'YouTube Shorts' },
  { id: 'tiktok', label: 'TikTok' },
  { id: 'instagram_reels', label: 'Instagram Reels' },
];

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
  script_generation_settings: {
    content_format_id: 'debate_format',
    platform: 'youtube_shorts',
    target_duration_sec: 45,
    tone: 'sharp',
    audience: 'general short-form viewers',
    speaker_names: ['Moderator', 'Speaker A', 'Speaker B'],
  },
};

const emptyData: CommandRoomData = {
  projects: [],
  currentProject: null,
  script: null,
  jobs: [],
  outputs: [],
  generatedMedia: [],
  accounts: [],
  history: { jobs: [], posts: [] },
  metadata: null,
  metadataByProjectId: {},
  characterPresets: [],
  voiceProfiles: [],
  backgroundPresets: [],
  contentFormats: FALLBACK_CONTENT_FORMATS,
  renderReadiness: null,
};

const chipClass = (tone: CommandTone) => {
  if (tone === 'ready') return 'is-ready';
  if (tone === 'warning') return 'is-warning';
  if (tone === 'failed') return 'is-failed';
  if (tone === 'info') return 'is-info';
  if (tone === 'active') return 'is-active';
  if (tone === 'brand') return 'is-brand';
  return 'plain';
};

const toApiHref = (url: string | null | undefined) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${apiBaseUrl}${url.startsWith('/') ? url : `/${url}`}`;
};

const titleCase = (value: string | null | undefined) =>
  String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());

const clampText = (value: string, max = 84) => {
  const compact = value.replace(/\s+/g, ' ').trim();
  return compact.length > max ? `${compact.slice(0, max - 1)}...` : compact;
};

const formatMidpoint = (format: ContentFormatPreset) =>
  Math.round((format.ideal_duration_range_sec[0] + format.ideal_duration_range_sec[1]) / 2);

const hasReleaseMetadata = (metadata?: PlatformMetadata | null) =>
  Boolean(metadata?.title?.trim() && metadata?.description?.trim() && !metadata.validation_errors?.length);

const hasOutput = (project: Project) => Boolean(project.current_output_video_id || project.latest_output);

const hasProjectActivity = (project: Project) =>
  project.id > 0 && (
    Boolean(project.current_script_revision_id || project.current_script || hasOutput(project) || project.approved_at) ||
    ACTIVITY_STATUSES.has(project.status)
  );

const latestJobByProject = (jobs: GenerationJob[]) => {
  const sorted = [...jobs].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));
  const byProject = new Map<number, GenerationJob>();
  sorted.forEach((job) => {
    if (!byProject.has(job.project_id)) {
      byProject.set(job.project_id, job);
    }
  });
  return byProject;
};

const cacheHitCount = (job: GenerationJob | null) =>
  Number((job?.cache_statistics as any)?.hits || (job?.cache_statistics as any)?.hit_count || 0);

const getProjectScript = (project: Project, currentProject: Project | null | undefined, script: ScriptRevision | null | undefined) =>
  project.id === currentProject?.id ? script || project.current_script : project.current_script;

const stageChipsFor = (
  project: Project,
  latestJob: GenerationJob | null,
  readiness: ProductionReadiness
): CommandRoomStageChip[] => {
  const preview = normalizePreviewSettings(project.preview_settings);
  const scriptReady = Boolean(project.current_script_revision_id || project.current_script);
  const castReady = Boolean(preview.speaker_mappings.length && !readiness.missingVoiceSpeakers.length && !readiness.missingCharacterImageSpeakers.length);
  const previewReady = hasOutput(project);
  const renderReady = Boolean(project.latest_output || latestJob?.output_video_id || latestJob?.status === 'completed');
  return [
    { label: 'Script', tone: scriptReady ? 'ready' : 'muted' },
    { label: 'Cast', tone: castReady ? 'ready' : readiness.missingVoiceSpeakers.length || readiness.missingCharacterImageSpeakers.length ? 'warning' : 'muted' },
    { label: 'Preview', tone: previewReady ? project.approved_at ? 'ready' : 'warning' : 'muted' },
    {
      label: 'Render',
      tone: latestJob && FAILED_JOB_STATUSES.has(latestJob.status)
        ? 'failed'
        : latestJob && ACTIVE_JOB_STATUSES.has(latestJob.status)
          ? 'warning'
          : renderReady
            ? 'ready'
            : 'muted',
    },
  ];
};

const supportChipsFor = (
  project: Project,
  latestJob: GenerationJob | null,
  readiness: ProductionReadiness,
  metadata: PlatformMetadata | null | undefined
): CommandRoomStageChip[] => {
  const chips: CommandRoomStageChip[] = [];
  const hits = cacheHitCount(latestJob);
  if (hits) chips.push({ label: `Cache ${hits} hit${hits === 1 ? '' : 's'}`, tone: 'ready' });
  if (latestJob?.status === 'failed') chips.push({ label: clampText(latestJob.error_message || 'Render failed', 42), tone: 'failed' });
  if (readiness.missingVoiceSpeakers[0]) chips.push({ label: `Voice: ${readiness.missingVoiceSpeakers[0]}`, tone: 'warning' });
  if (readiness.missingCharacterImageSpeakers[0]) chips.push({ label: `PNG: ${readiness.missingCharacterImageSpeakers[0]}`, tone: 'warning' });
  if (hasOutput(project)) chips.push({ label: project.approved_at ? 'Preview approved' : 'Preview needs approval', tone: project.approved_at ? 'ready' : 'warning' });
  if (project.approved_at || hasOutput(project)) chips.push({ label: hasReleaseMetadata(metadata) || project.status === 'published' ? 'Metadata ready' : 'Metadata needed', tone: hasReleaseMetadata(metadata) || project.status === 'published' ? 'ready' : 'info' });
  if (!chips.length) chips.push({ label: titleCase(project.status || 'Draft'), tone: 'info' });
  return chips.slice(0, 3);
};

const rowFamilyFor = (
  project: Project,
  latestJob: GenerationJob | null,
  readiness: ProductionReadiness
): ProductionRowFamily => {
  if (latestJob && FAILED_JOB_STATUSES.has(latestJob.status)) return 'failed';
  if (latestJob && ACTIVE_JOB_STATUSES.has(latestJob.status)) return 'running';
  if (readiness.rows.some((row) => ['failed', 'warning', 'missing'].includes(row.state))) return 'attention';
  return 'ready';
};

const actionForRow = (project: Project, family: ProductionRowFamily, readiness: ProductionReadiness) => {
  if (family === 'failed') {
    return { label: 'Retry cast', href: `/projects/${project.id}?tab=cast#step-cast` };
  }
  if (family === 'running') {
    return { label: 'Open render', href: `/projects/${project.id}?tab=render#step-render` };
  }
  if (family === 'ready' && project.status === 'published') {
    return { label: 'Open media', href: '/generated-media' };
  }
  if (family === 'ready' && project.approved_at) {
    return { label: 'Publish', href: `/projects/${project.id}?tab=release#step-release` };
  }
  if (family === 'ready' && hasOutput(project)) {
    return { label: 'Approve', href: `/projects/${project.id}?tab=preview#step-preview` };
  }
  return {
    label: readiness.nextAction.step === 'preview' && hasOutput(project) ? 'Fix preview' : readiness.nextAction.label,
    href: readiness.nextAction.href.startsWith('/')
      ? readiness.nextAction.href
      : `/projects/${project.id}?tab=${readiness.nextAction.step}#step-${readiness.nextAction.step}`,
  };
};

export const deriveCommandRoomViewModel = (input: CommandRoomViewModelInput = {}): CommandRoomViewModel => {
  const projects = input.projects || [];
  const currentProject = input.currentProject || null;
  const jobs = input.jobs || [];
  const outputs = input.outputs || [];
  const generatedMedia = input.generatedMedia || [];
  const meaningfulProjects = projects.filter(hasProjectActivity);
  const hasProductionActivity = Boolean(meaningfulProjects.length || jobs.length || outputs.length || generatedMedia.length);
  const jobsByProject = latestJobByProject(jobs);

  const productionRows = meaningfulProjects.map((project) => {
    const latestJob = jobsByProject.get(project.id) || null;
    const rowScript = getProjectScript(project, currentProject, input.script || null);
    const rowMetadata = input.metadataByProjectId?.[project.id] ?? (project.id === currentProject?.id ? input.metadata || null : null);
    const readiness = computeProductionReadiness({
      project,
      script: rowScript || null,
      latestJob,
      metadata: rowMetadata,
      draftEstimate: project.id === currentProject?.id ? input.renderReadiness || null : null,
      linkMode: 'productionLab',
    });
    const family = rowFamilyFor(project, latestJob, readiness);
    const action = actionForRow(project, family, readiness);
    const statusLabel =
      family === 'failed'
        ? 'Needs retry'
        : family === 'running'
          ? 'Rendering'
          : family === 'attention'
            ? 'Needs attention'
            : project.status === 'published'
              ? 'Released'
              : project.approved_at
                ? 'Ready to publish'
                : hasOutput(project)
                  ? 'Ready to approve'
                  : 'Healthy';
    const statusDetail =
      family === 'failed'
        ? clampText(latestJob?.error_message || 'Latest render job failed.', 96)
        : family === 'running'
          ? latestJob?.current_phase || 'Render job is still active.'
          : family === 'attention'
            ? readiness.nextAction.label
            : project.status === 'published'
              ? 'Generated media is available.'
              : 'No blockers detected.';

    return {
      project,
      latestJob,
      readiness,
      family,
      statusLabel,
      statusDetail,
      stageChips: stageChipsFor(project, latestJob, readiness),
      supportChips: supportChipsFor(project, latestJob, readiness, rowMetadata),
      actionLabel: action.label,
      actionHref: action.href,
    };
  });

  const queued = jobs.filter((job) => job.status === 'queued').length;
  const rendering = jobs.filter((job) => ['processing', 'running', 'retrying'].includes(job.status)).length;
  const failed = jobs.filter((job) => FAILED_JOB_STATUSES.has(job.status)).length;
  const attention = productionRows.filter((row) => row.family === 'attention').length;
  const ready = productionRows.filter((row) => row.family === 'ready' || hasOutput(row.project)).length;
  const cacheHits = jobs.reduce((total, job) => total + cacheHitCount(job), 0);
  const blocked = attention + failed;
  const mode: CommandRoomMode = !hasProductionActivity ? 'firstRun' : blocked || queued || rendering ? 'active' : 'allClear';
  const modeLabel = mode === 'firstRun' ? 'First run' : mode === 'allClear' ? 'All clear' : 'Active';
  const modeTone: CommandTone = mode === 'firstRun' ? 'active' : mode === 'allClear' ? 'ready' : failed ? 'failed' : attention ? 'warning' : 'info';

  const runtimeChips: CommandRoomStageChip[] = mode === 'firstRun'
    ? [
        { label: 'First run', tone: 'active' },
        { label: 'No jobs yet', tone: 'info' },
        { label: 'Setup needed', tone: 'warning' },
      ]
    : mode === 'allClear'
      ? [
          { label: cacheHits ? 'Cache warm' : 'Cache ready', tone: 'ready' },
          { label: 'All clear', tone: 'ready' },
          { label: '0 blocked', tone: 'ready' },
        ]
      : [
          { label: cacheHits ? 'Cache warm' : 'Cache pending', tone: cacheHits ? 'ready' : 'info' },
          { label: `${attention} attention`, tone: attention ? 'warning' : 'ready' },
          { label: `${failed} failed`, tone: failed ? 'failed' : 'ready' },
        ];

  const queueItems: CommandRoomQueueItem[] = mode === 'firstRun'
    ? [
        { label: 'Choose a format & write the idea', detail: 'Pick a preset to set pacing, speakers, captions and render defaults.', value: 'Now', tone: 'active' },
        { label: 'Generate the script', detail: 'Turn the idea into speaker-separated dialogue.', value: 'Next', tone: 'info' },
        { label: 'Assign voices & preview', detail: 'Bind voices and portraits, then tune the authoritative preview.', value: 'Locked', tone: 'muted' },
      ]
    : [
        {
          label: 'Need attention',
          detail: attention ? 'voice validation · metadata · preview' : 'nothing blocked',
          value: String(attention),
          tone: attention ? 'warning' : 'ready',
        },
        {
          label: 'Failed jobs',
          detail: failed ? 'open diagnostics before retrying' : 'none',
          value: String(failed),
          tone: failed ? 'failed' : 'ready',
        },
        {
          label: mode === 'allClear' ? 'Ready to ship' : 'Ready drafts',
          detail: mode === 'allClear' ? 'review metadata & publish' : 'preview & approve',
          value: String(ready),
          tone: ready ? 'ready' : 'info',
        },
      ];

  const latestMedia = generatedMedia[0];
  const latestOutput = outputs[0];
  const latestPreview = latestMedia
    ? {
        label: latestMedia.output.asset.original_filename,
        href: toApiHref(latestMedia.output.asset.content_url),
        projectName: latestMedia.project_name,
        detail: titleCase(latestMedia.output.output_kind),
      }
    : latestOutput
      ? {
          label: latestOutput.asset.original_filename,
          href: toApiHref(latestOutput.asset.content_url),
          projectName: currentProject?.name || 'Current production',
          detail: titleCase(latestOutput.output_kind),
        }
      : null;

  const releasePrep = !hasProductionActivity
    ? { label: 'No release yet', detail: 'Create a production before release prep.', tone: 'muted' as CommandTone }
    : hasReleaseMetadata(input.metadata)
      ? { label: currentProject?.name || 'Current production', detail: 'Metadata ready', tone: 'ready' as CommandTone }
      : currentProject?.approved_at || currentProject?.current_output_video_id
        ? { label: currentProject.name, detail: 'Metadata needs review', tone: 'info' as CommandTone }
        : { label: currentProject?.name || 'Current production', detail: 'Preview or final output needed first', tone: blocked ? 'warning' as CommandTone : 'muted' as CommandTone };

  return {
    mode,
    modeLabel,
    modeTone,
    hasProductionActivity,
    counts: {
      queued,
      rendering,
      failed,
      attention,
      ready,
      blocked,
      totalJobs: jobs.length,
      cacheHits,
    },
    runtimeChips,
    queueItems,
    productionRows,
    latestPreview,
    releasePrep,
  };
};

const CommandRoomWorkflowStrip: React.FC<{ project: Project | null; viewModel: CommandRoomViewModel }> = ({ project, viewModel }) => {
  const preview = normalizePreviewSettings(project?.preview_settings);
  const hasScript = Boolean(project?.current_script_revision_id || project?.current_script);
  const hasCast = Boolean(preview.speaker_mappings.length && preview.speaker_mappings.every((item) => item.voice_profile_id));
  const hasPreview = Boolean(project?.current_output_video_id || project?.latest_output);
  const hasRender = Boolean(project?.latest_output);
  const stages = [
    { label: 'Command', sub: 'Idea', done: true },
    { label: 'Script', sub: 'Write', done: hasScript },
    { label: 'Cast', sub: 'Voices', done: hasCast },
    { label: 'Preview', sub: 'Tune', done: hasPreview },
    { label: 'Render', sub: 'Draft / Final', done: hasRender },
    { label: 'Release', sub: 'Ship', done: viewModel.mode === 'allClear' },
  ];
  const activeIndex = Math.max(0, stages.findIndex((stage) => !stage.done));
  const selectedIndex = viewModel.mode === 'firstRun' ? 0 : activeIndex === -1 ? 0 : activeIndex;

  return (
    <section className="stage-strip command-room-stage-strip" aria-label="Command Room workflow stages">
      {stages.map((stage, index) => {
        const className = index === selectedIndex ? 'now' : stage.done ? 'done' : 'lock';
        return (
          <span key={stage.label} className={`stage ${className}`} aria-current={index === selectedIndex ? 'step' : undefined}>
            <span className="dot">{stage.done && index !== selectedIndex ? '✓' : String(index + 1).padStart(2, '0')}</span>
            <span className="stage-copy">
              <span className="k">{stage.label}</span>
              <span className="v">{stage.sub}</span>
            </span>
          </span>
        );
      })}
    </section>
  );
};

const CommandRoomStateBar: React.FC<{ mode: CommandRoomMode; counts: CommandRoomViewModel['counts'] }> = ({ mode, counts }) => {
  const states = [
    { key: 'firstRun' as const, label: 'First run' },
    { key: 'active' as const, label: `Active · ${counts.attention} attention · ${counts.ready} ready · ${counts.failed} failed` },
    { key: 'allClear' as const, label: 'All clear' },
  ];
  return (
    <div className="statebar cr-statebar" aria-label="Design-review states">
      <span className="statebar-label">Design-review states</span>
      <div className="statebar-seg">
        {states.map((state) => (
          <span key={state.key} className={`cr-state-pill ${state.key === mode ? 'is-selected' : ''}`} aria-current={state.key === mode ? 'true' : undefined}>
            {state.label}
          </span>
        ))}
      </div>
    </div>
  );
};

const QueueSetupPanel: React.FC<{
  viewModel: CommandRoomViewModel;
  onPrimaryAction: () => void;
  busy: boolean;
}> = ({ viewModel, onPrimaryAction, busy }) => {
  const firstRun = viewModel.mode === 'firstRun';
  return (
    <section className="panel cr-queue-panel" aria-labelledby="command-room-queue-title">
      <div className="panel-h">
        <div>
          <h3 id="command-room-queue-title">{firstRun ? 'First production setup' : "Today's queue"}</h3>
          <p>
            {firstRun
              ? 'No analytics yet. Command Room stays focused on one guided production.'
              : viewModel.mode === 'allClear'
                ? 'Everything is verified or shipped. Start something new.'
                : 'The smallest action that moves a video toward preview or release.'}
          </p>
        </div>
        <span className={`chip ${chipClass(firstRun ? 'ready' : viewModel.modeTone)}`}>
          {firstRun ? 'Guided' : viewModel.modeLabel}
        </span>
      </div>
      <div className="rows">
        {viewModel.queueItems.map((item, index) => (
          <div
            key={item.label}
            className={`row lead ${item.tone === 'failed' ? 'fail' : item.tone === 'warning' ? 'warn' : item.tone === 'ready' ? 'ready' : 'queued'} ready-row${firstRun ? ' first-step' : ''}`}
          >
            {firstRun && <span className="cr-first-step-num">{index + 1}</span>}
            <div>
              <div className="t">{item.label}</div>
              <div className="m">{item.detail}</div>
            </div>
            <span className={`chip ${chipClass(item.tone)}`}>{item.value}</span>
          </div>
        ))}
      </div>
      {!firstRun && (
        <div className={`callout ${viewModel.mode === 'allClear' ? 'ok' : 'info'}`}>
          <b>{viewModel.mode === 'allClear' ? 'All productions are healthy.' : 'Recommended:'}</b>{' '}
          {viewModel.mode === 'allClear'
            ? `${viewModel.counts.ready} production${viewModel.counts.ready === 1 ? '' : 's'} ready and nothing needs fixing.`
            : viewModel.productionRows[0]
              ? `Open ${viewModel.productionRows[0].project.name}.`
              : 'Open the current production.'}
        </div>
      )}
      <button className="btn primary wide" type="button" onClick={onPrimaryAction} disabled={busy}>
        {busy ? 'Starting...' : firstRun ? 'Start First Production' : viewModel.mode === 'allClear' ? 'Start a new production' : 'Open ready draft'}
      </button>
    </section>
  );
};

const ProductionBriefPanel: React.FC<{
  formats: ContentFormatPreset[];
  project: Project | null;
  selectedFormat: ContentFormatPreset | null;
  brief: BriefState;
  busy: boolean;
  error: string | null;
  onBriefChange: (patch: Partial<BriefState>) => void;
  onSubmit: () => void;
}> = ({ formats, project, selectedFormat, brief, busy, error, onBriefChange, onSubmit }) => (
  <section className="panel cyanish cr-brief-panel" id="start-production" aria-labelledby="start-production-title">
    <div className="panel-h">
      <div>
        <h3 id="start-production-title">Start with the next video worth rendering.</h3>
        <p>Pick a format, write the idea, generate. OmniPoster carries the same voices, PNGs, scene, captions and cache from script all the way to final render.</p>
      </div>
      <span className={`chip ${project?.current_script_revision_id ? 'is-ready' : 'is-active'}`}>
        {project?.current_script_revision_id ? 'Draft loaded' : 'Step 01'}
      </span>
    </div>
    <div className="field">
      <label htmlFor="production-idea">Production brief</label>
      <textarea
        id="production-idea"
        className="input cr-idea-input"
        value={brief.idea}
        onChange={(event) => onBriefChange({ idea: event.target.value })}
        placeholder="A sharp debate about whether creators should automate their short-form workflow or keep editing every clip by hand."
      />
    </div>
    <div className="grid4 cr-brief-fields">
      <div className="field">
        <label htmlFor="brief-format">Format</label>
        <select
          id="brief-format"
          className="select"
          value={brief.contentFormatId}
          onChange={(event) => {
            const next = findFormat(formats, event.target.value);
            onBriefChange({
              contentFormatId: event.target.value,
              duration: next ? formatMidpoint(next) : brief.duration,
              speakerNames: next?.default_speaker_roles.join(', ') || brief.speakerNames,
            });
          }}
        >
          {formats.map((format) => <option key={format.id} value={format.id}>{format.display_name}</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="brief-duration">Duration</label>
        <select id="brief-duration" className="select" value={brief.duration} onChange={(event) => onBriefChange({ duration: Number(event.target.value) })}>
          {[30, 45, 60].map((duration) => <option key={duration} value={duration}>{duration} seconds</option>)}
        </select>
      </div>
      <div className="field">
        <label htmlFor="brief-tone">Tone</label>
        <select id="brief-tone" className="select" value={brief.tone} onChange={(event) => onBriefChange({ tone: event.target.value })}>
          {(selectedFormat?.tone_options?.length ? selectedFormat.tone_options : ['Playful / Sharp', 'Curious', 'Direct']).map((tone) => (
            <option key={tone} value={tone}>{titleCase(tone)}</option>
          ))}
        </select>
      </div>
      <div className="field">
        <label htmlFor="brief-platform">Platform</label>
        <select id="brief-platform" className="select" value={brief.platform} onChange={(event) => onBriefChange({ platform: event.target.value as PlatformTarget })}>
          {platformTargets.map((target) => <option key={target.id} value={target.id}>{target.label}</option>)}
        </select>
      </div>
    </div>
    {error && <div className="cr-inline-error" role="alert">{error}</div>}
    <div className="flex gap2 cr-brief-actions">
      <button className="btn primary" type="button" onClick={onSubmit} disabled={busy}>
        <Sparkles size={14} /> {busy ? 'Generating...' : project?.id && project.id > 0 && !project.current_script_revision_id ? 'Generate Script Brief' : 'Start Production'}
      </button>
      {project?.id && project.id > 0 ? (
        <Link className="btn ghost" to={`/projects/${project.id}?tab=script#step-script`}>Continue Draft</Link>
      ) : (
        <button className="btn ghost" type="button" disabled>Continue Draft</button>
      )}
      <button className="btn ghost" type="button" disabled title="Preset saving is not wired to a backend endpoint yet.">Save as Preset</button>
      <span className="chip is-ready">Draft est. {brief.duration}s</span>
    </div>
  </section>
);

const formatTags = (format: ContentFormatPreset) => [
  speakerCountLabel(format),
  durationLabel(format),
  titleCase(format.speaker_model || 'Shorts'),
].slice(0, 3);

const ContentPresetLibrary: React.FC<{
  formats: ContentFormatPreset[];
  selectedFormatId: string;
  onSelect: (format: ContentFormatPreset) => void;
}> = ({ formats, selectedFormatId, onSelect }) => (
  <section className="panel brandish cr-preset-library" id="content-preset-library" aria-labelledby="content-preset-library-title">
    <div className="panel-h">
      <div>
        <h3 id="content-preset-library-title">Content preset library</h3>
        <p>Reusable templates that define structure, pacing, speaker count and caption behavior. Choosing one starts a fresh brief, never an old production.</p>
      </div>
      <button className="btn ghost sm" type="button" disabled title="Preset management is not available from a backend endpoint yet.">Manage presets</button>
    </div>
    <div className="cr-preset-grid">
      {formats.slice(0, 4).map((format) => {
        const selected = selectedFormatId === format.id;
        return (
          <article key={format.id} className={`cr-preset ${selected ? 'sel' : ''}`}>
            <div className="flex between">
              <span className="chip is-active plain">Preset template</span>
              {selected && <span className="chip is-ready solid">Selected</span>}
            </div>
            <div>
              <h4>{format.display_name}</h4>
              <p>{format.short_description || format.best_use_case}</p>
            </div>
            <div className="flex gap2">
              {formatTags(format).map((tag) => <span key={tag} className="chip plain">{tag}</span>)}
            </div>
            <div className="cr-preset-struct">
              <span>Generated structure</span>
              {format.section_structure.join(' → ')}
            </div>
            <div className="flex gap2">
              <button className="btn primary sm grow" type="button" onClick={() => onSelect(format)}>Use preset</button>
              <button className="btn ghost sm" type="button" onClick={() => onSelect(format)}>Preview</button>
            </div>
          </article>
        );
      })}
    </div>
  </section>
);

const ActiveProductionsPanel: React.FC<{
  viewModel: CommandRoomViewModel;
  currentProject: Project | null;
  onApproveCurrentPreview: () => void;
}> = ({ viewModel, currentProject, onApproveCurrentPreview }) => (
  <section className="panel cr-active-productions" id="active-productions" aria-labelledby="active-productions-title">
    <div className="panel-h">
      <div>
        <h3 id="active-productions-title">Active productions</h3>
        <p>
          {viewModel.mode === 'firstRun'
            ? 'Nothing here yet — your first production appears once you generate a script.'
            : viewModel.mode === 'allClear'
              ? 'All current productions are verified or released.'
              : 'Grouped by attention. Each card shows stage progress, cache state, and the one action that unblocks it.'}
        </p>
      </div>
      <span className={`chip ${chipClass(viewModel.mode === 'firstRun' ? 'info' : viewModel.mode === 'allClear' ? 'ready' : 'info')}`}>
        {viewModel.mode === 'firstRun' ? 'Empty' : viewModel.mode === 'allClear' ? 'Healthy' : `${viewModel.productionRows.length} active`}
      </span>
    </div>
    {viewModel.mode !== 'firstRun' && (
      <div className="cr-lanes-head">
        <span className={`chip ${viewModel.counts.attention ? 'is-warning' : 'is-ready'}`}>Need attention · {viewModel.counts.attention}</span>
        <span className="chip is-ready">Ready · {viewModel.counts.ready}</span>
        <span className={`chip ${viewModel.counts.failed ? 'is-failed' : 'is-ready'}`}>Failed · {viewModel.counts.failed}</span>
      </div>
    )}
    <div className="cr-production-grid">
      {viewModel.productionRows.map((row) => (
        <article key={row.project.id} className={`cr-production-row ${row.family}`}>
          <div className="cr-production-top">
            <div className="cr-production-main">
              <div className="cr-production-title-line">
                <strong>{row.project.name}</strong>
                <span>prod_{String(row.project.id).padStart(4, '0')}</span>
              </div>
              <div className="cr-prod-stages">
                {row.stageChips.map((chip) => (
                  <span key={chip.label} className={`cr-stage-chip ${chip.tone}`}>{chip.label}</span>
                ))}
              </div>
              <p>{row.statusDetail}</p>
            </div>
            <div className="cr-production-action">
              {row.actionLabel === 'Approve' && row.project.id === currentProject?.id ? (
                <button className="btn primary sm" type="button" onClick={onApproveCurrentPreview}>Approve</button>
              ) : (
                <Link className={`btn sm ${row.family === 'failed' ? 'fail' : row.family === 'attention' ? 'warn' : row.family === 'ready' ? 'primary' : 'ghost'}`} to={row.actionHref}>
                  {row.actionLabel}
                </Link>
              )}
            </div>
          </div>
          <div className="flex gap2">
            {row.supportChips.map((chip) => (
              <span key={chip.label} className={`chip ${chipClass(chip.tone)}`}>{chip.label}</span>
            ))}
          </div>
        </article>
      ))}
      {!viewModel.productionRows.length && (
        <div className="callout info cr-empty-productions">
          <b>No productions yet.</b>
          <span>Start from a preset above. OmniPoster will keep your voices, PNGs, backgrounds and render presets reusable for every future video.</span>
        </div>
      )}
    </div>
  </section>
);

const LowerWorkspace: React.FC<{
  viewModel: CommandRoomViewModel;
  open: boolean;
  onToggle: (open: boolean) => void;
}> = ({ viewModel, open, onToggle }) => (
  <details
    className="drawer cr-lower-workspace"
    open={open}
    onToggle={(event) => onToggle(event.currentTarget.open)}
  >
    <summary>
      <span>Lower workspace · queue summary, latest preview, release</span>
      <span className={`chip ${open ? 'is-info' : 'is-active'}`}>{open ? 'Expanded' : 'Collapsed'}</span>
      <ChevronDown className="cr-drawer-icon" size={16} aria-hidden="true" />
    </summary>
    <div className="body">
      <div className="grid3 cr-lower-grid">
        <section className="panel tight cr-lower-card">
          <div className="cr-lower-title">Queue summary</div>
          <div className="grid3">
            <div className="metric"><b>{viewModel.counts.queued}</b><span>queued</span></div>
            <div className="metric"><b>{viewModel.counts.rendering}</b><span>rendering</span></div>
            <div className="metric"><b>{viewModel.counts.failed}</b><span>failed</span></div>
          </div>
        </section>
        <section className="panel tight cr-lower-card">
          <div className="cr-lower-title">Latest preview</div>
          {viewModel.latestPreview ? (
            <a className="cr-preview-thumb" href={viewModel.latestPreview.href}>
              <Play size={16} />
              <span>{viewModel.latestPreview.label}</span>
              <small>{viewModel.latestPreview.projectName} · {viewModel.latestPreview.detail}</small>
            </a>
          ) : (
            <div className="ph cr-preview-thumb-empty">9:16 preview thumbnail</div>
          )}
        </section>
        <section className="panel tight cr-lower-card">
          <div className="cr-lower-title">Release prep</div>
          <div className={`row lead ${viewModel.releasePrep.tone === 'ready' ? 'ready' : viewModel.releasePrep.tone === 'warning' ? 'warn' : 'queued'} ready-row`}>
            <div>
              <div className="t">{viewModel.releasePrep.label}</div>
              <div className="m">{viewModel.releasePrep.detail}</div>
            </div>
            <span className={`chip ${chipClass(viewModel.releasePrep.tone)}`}>{viewModel.releasePrep.tone === 'ready' ? 'Verified' : 'Open'}</span>
          </div>
        </section>
      </div>
    </div>
  </details>
);

type BriefState = {
  name: string;
  idea: string;
  contentFormatId: string;
  platform: PlatformTarget;
  speakerNames: string;
  duration: number;
  tone: string;
};

const defaultBrief: BriefState = {
  name: 'New Debate Short',
  idea: 'A sharp debate about whether creators should automate their short-form workflow or keep editing every clip by hand.',
  contentFormatId: 'debate_format',
  platform: 'youtube_shorts',
  speakerNames: 'Moderator, Speaker A, Speaker B',
  duration: 45,
  tone: 'Playful / Sharp',
};

const sortedJobs = (jobs: GenerationJob[]) =>
  [...jobs].sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')));

const loadLatestJobsForProjects = async (projects: Project[]) => {
  const visibleProjects = projects.slice(0, 8);
  const settled = await Promise.allSettled(
    visibleProjects.map((project) => apiClient.get<GenerationJob>(`/projects/${project.id}/generation-jobs/latest`))
  );
  return sortedJobs(
    settled.flatMap((result) => result.status === 'fulfilled' && result.value.data ? [result.value.data] : [])
  );
};

const loadMetadataForProjects = async (projects: Project[]) => {
  const visibleProjects = projects.slice(0, 8);
  const settled = await Promise.allSettled(
    visibleProjects.map((project) => apiClient.get<PlatformMetadata | null>(`/projects/${project.id}/metadata/youtube`))
  );
  return visibleProjects.reduce<Record<number, PlatformMetadata | null>>((metadataByProjectId, project, index) => {
    const result = settled[index];
    metadataByProjectId[project.id] = result?.status === 'fulfilled' ? result.value.data : null;
    return metadataByProjectId;
  }, {});
};

const loadCommandRoomData = async (projectId?: number | null): Promise<CommandRoomData> => {
  const [projectsResponse, accountsResponse, characterResponse, voicesResponse, backgroundsResponse, formatsResponse, generatedMediaResponse] = await Promise.all([
    apiClient.get<{ items: Project[] }>('/projects'),
    apiClient.get<{ items: SocialAccount[] }>('/social-accounts'),
    apiClient.get<{ items: CharacterPreset[] }>('/character-presets'),
    apiClient.get<{ items: VoiceProfile[] }>('/voice-profiles'),
    apiClient.get<BackgroundPreset[]>('/background-presets'),
    apiClient
      .get<{ items: ContentFormatPreset[] }>('/script-generation/formats')
      .catch(() => ({ data: { items: FALLBACK_CONTENT_FORMATS } })),
    apiClient
      .get<{ items: GeneratedMediaItem[] }>('/generated-media?limit=50')
      .catch(() => ({ data: { items: [] as GeneratedMediaItem[] } })),
  ]);

  const projects = projectsResponse.data.items || [];
  const currentProjectSummary = projectId ? projects.find((item) => item.id === projectId) || projects[0] || null : projects[0] || null;
  const workspaceJobs = await loadLatestJobsForProjects(projects);
  const workspaceMetadata = await loadMetadataForProjects(projects);

  if (!currentProjectSummary) {
    return {
      ...emptyData,
      projects,
      jobs: workspaceJobs,
      accounts: accountsResponse.data.items || [],
      characterPresets: characterResponse.data.items || [],
      voiceProfiles: voicesResponse.data.items || [],
      backgroundPresets: backgroundsResponse.data || [],
      contentFormats: formatsResponse.data.items?.length ? formatsResponse.data.items : FALLBACK_CONTENT_FORMATS,
      generatedMedia: generatedMediaResponse.data.items || [],
      metadataByProjectId: workspaceMetadata,
    };
  }

  const [projectResponse, scriptResponse, outputsResponse, historyResponse, metadataResponse, renderReadinessResponse] = await Promise.all([
    apiClient.get<Project>(`/projects/${currentProjectSummary.id}`),
    apiClient.get<{ current_revision: ScriptRevision | null }>(`/projects/${currentProjectSummary.id}/script`),
    apiClient.get<{ items: OutputVideo[] }>(`/projects/${currentProjectSummary.id}/outputs`),
    apiClient.get<{ jobs: PublishJob[]; posts: PublishedPost[] }>(`/projects/${currentProjectSummary.id}/publish-history`),
    apiClient.get<PlatformMetadata | null>(`/projects/${currentProjectSummary.id}/metadata/youtube`).catch(() => ({ data: null as PlatformMetadata | null })),
    apiClient.get<RenderReadinessEstimate>(`/projects/${currentProjectSummary.id}/render-readiness?output_kind=draft`).catch(() => ({ data: null as RenderReadinessEstimate | null })),
  ]);

  const selectedLatest = workspaceJobs.find((job) => job.project_id === currentProjectSummary.id);
  const selectedJobs = selectedLatest
    ? workspaceJobs
    : sortedJobs([
        ...workspaceJobs,
        ...(await apiClient
          .get<GenerationJob>(`/projects/${currentProjectSummary.id}/generation-jobs/latest`)
          .then((response) => [response.data])
          .catch(() => [] as GenerationJob[])),
      ]);

  return {
    projects,
    currentProject: projectResponse.data,
    script: scriptResponse.data.current_revision,
    jobs: selectedJobs,
    outputs: outputsResponse.data.items || [],
    generatedMedia: generatedMediaResponse.data.items || [],
    accounts: accountsResponse.data.items || [],
    history: historyResponse.data,
    metadata: metadataResponse.data,
    metadataByProjectId: {
      ...workspaceMetadata,
      [currentProjectSummary.id]: metadataResponse.data,
    },
    characterPresets: characterResponse.data.items || [],
    voiceProfiles: voicesResponse.data.items || [],
    backgroundPresets: backgroundsResponse.data || [],
    contentFormats: formatsResponse.data.items?.length ? formatsResponse.data.items : FALLBACK_CONTENT_FORMATS,
    renderReadiness: renderReadinessResponse.data,
  };
};

const getSyncState = (isAuthenticated: boolean): StudioSyncState => {
  if (!isAuthenticated) return 'local';
  if (typeof window === 'undefined') return 'paused';
  return window.localStorage.getItem('omniposter.studioSync') === 'active' ? 'active' : 'paused';
};

export const CommandRoomPage: React.FC = () => {
  const { isAuthenticated } = useAuth();
  const navigate = useNavigate();
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [data, setData] = useState<CommandRoomData>(() => ({
    ...emptyData,
    currentProject: isAuthenticated ? null : localDraftProject,
  }));
  const [selectedProjectId, setSelectedProjectId] = useState<number | null>(null);
  const [syncState, setSyncState] = useState<StudioSyncState>(() => getSyncState(isAuthenticated));
  const [brief, setBrief] = useState<BriefState>(defaultBrief);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lowerWorkspaceOpen, setLowerWorkspaceOpen] = useState(() => {
    if (typeof window === 'undefined') return false;
    return window.localStorage.getItem(LOWER_WORKSPACE_STORAGE_KEY) === 'true';
  });

  const selectedFormat = useMemo(() => findFormat(data.contentFormats, brief.contentFormatId) || data.contentFormats[0] || null, [brief.contentFormatId, data.contentFormats]);
  const viewModel = useMemo(
    () => deriveCommandRoomViewModel(data),
    [data]
  );

  const load = async (projectId = selectedProjectId) => {
    if (!isAuthenticated) {
      setData((current) => ({
        ...current,
        currentProject: localDraftProject,
        projects: [],
        jobs: [],
        outputs: [],
        generatedMedia: [],
      }));
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

  useEffect(() => {
    if (!selectedFormat) return;
    setBrief((current) => {
      if (findFormat(data.contentFormats, current.contentFormatId)) return current;
      return {
        ...current,
        contentFormatId: selectedFormat.id,
        duration: formatMidpoint(selectedFormat),
        speakerNames: selectedFormat.default_speaker_roles.join(', '),
      };
    });
  }, [data.contentFormats, selectedFormat]);

  useEffect(() => {
    const activeJobs = data.jobs.filter((job) => ACTIVE_JOB_STATUSES.has(job.status));
    if (!isAuthenticated || !activeJobs.length) return undefined;
    const timer = window.setInterval(async () => {
      const refreshed = await Promise.allSettled(activeJobs.map((job) => apiClient.get<GenerationJob>(`/generation-jobs/${job.id}`)));
      const nextJobs = refreshed.flatMap((result) => result.status === 'fulfilled' ? [result.value.data] : []);
      if (nextJobs.length) {
        setData((current) => ({
          ...current,
          jobs: sortedJobs([
            ...nextJobs,
            ...current.jobs.filter((job) => !nextJobs.some((next) => next.id === job.id)),
          ]),
        }));
      }
      if (nextJobs.some((job) => ['completed', 'failed', 'canceled'].includes(job.status))) {
        await load(selectedProjectId);
      }
    }, 1800);
    return () => window.clearInterval(timer);
  }, [isAuthenticated, data.jobs.map((job) => `${job.id}:${job.status}`).join('|'), selectedProjectId]);

  const updateBrief = (patch: Partial<BriefState>) => setBrief((current) => ({ ...current, ...patch }));

  const createOrSeedProduction = async () => {
    // Active mode: existing productions need action — navigate directly, no generation needed.
    if (viewModel.mode === 'active') {
      const href = viewModel.productionRows[0]?.action.href;
      if (href) {
        navigate(href);
      }
      return;
    }

    const format = selectedFormat || data.contentFormats[0];
    if (!format) return;
    const idea = brief.idea.trim();
    if (!idea) {
      setError('Add a production brief before generating the script.');
      return;
    }
    if (!isAuthenticated) {
      window.localStorage.setItem('omniposter.localDraft', JSON.stringify(brief));
      navigate('/login');
      return;
    }

    try {
      setBusy('production-create');
      setError(null);
      let projectId = viewModel.mode === 'firstRun' && data.currentProject?.id && data.currentProject.id > 0 ? data.currentProject.id : null;
      if (!projectId) {
        const projectResponse = await apiClient.post<Project>('/projects', {
          name: brief.name || `${format.display_name} Production`,
          target_platform: brief.platform === 'youtube_shorts' ? 'youtube' : brief.platform,
          allowed_platforms: [brief.platform === 'youtube_shorts' ? 'youtube' : brief.platform],
        });
        projectId = projectResponse.data.id;
      }
      const speakers = brief.speakerNames.split(',').map((item) => item.trim()).filter(Boolean);
      await apiClient.patch(`/projects/${projectId}/script-generation-settings`, {
        content_format_id: format.id,
        platform: brief.platform,
        target_duration_sec: brief.duration,
        tone: brief.tone,
        audience: 'general short-form viewers',
        speaker_names: speakers.length ? speakers : format.default_speaker_roles,
      });
      const scriptResponse = await apiClient.post<{ generated_script: GeneratedScript; provider_metadata: any; validation_warnings: string[]; fallback_used: boolean }>('/script-generation/generate', {
        idea,
        content_format_id: format.id,
        format_id: format.id,
        platform: brief.platform,
        platform_targets: [brief.platform],
        target_duration_sec: brief.duration,
        timing_target: { target_duration_sec: brief.duration },
        tone: brief.tone,
        speaker_names: speakers.length ? speakers : format.default_speaker_roles,
        speaker_roles: format.default_speaker_roles,
      });
      const generated = scriptResponse.data.generated_script;
      await apiClient.put(`/projects/${projectId}/script`, {
        raw_text: generated.lines.map((line) => `<${line.speaker_label}> ${line.text}`).join('\n'),
        parsed_lines: generated.lines.map((line, index) => ({
          speaker: line.speaker_label,
          text: line.text,
          caption_text: line.caption_text,
          section: line.section,
          line_id: line.id,
          order: index,
        })),
        generated_script: generated,
        source: 'generated',
      });
      setSelectedProjectId(projectId);
      navigate(`/projects/${projectId}?tab=script#step-script`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to start the production.');
    } finally {
      setBusy(null);
    }
  };

  const importScript = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || !data.currentProject || data.currentProject.id < 1) return;
    try {
      setBusy('script-import');
      setError(null);
      const formData = new FormData();
      formData.append('file', file);
      await apiClient.post(`/projects/${data.currentProject.id}/script/import`, formData);
      await load(data.currentProject.id);
      navigate(`/projects/${data.currentProject.id}?tab=script#step-script`);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to import script.');
    } finally {
      setBusy(null);
    }
  };

  const approvePreview = async () => {
    if (!data.currentProject || data.currentProject.id < 1 || !isAuthenticated) return;
    try {
      setBusy('preview-approve');
      await apiClient.post(`/projects/${data.currentProject.id}/approve-preview`);
      await load(data.currentProject.id);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Preview approval is unavailable until a preview output exists.');
    } finally {
      setBusy(null);
    }
  };

  const topbarRuntimeChips = (
    <>
      {viewModel.runtimeChips.map((chip) => (
        <span key={chip.label} className={`chip ${chipClass(chip.tone)}`}>{chip.label}</span>
      ))}
    </>
  );

  const topbarActions = (
    <>
      <input ref={importInputRef} className="cr-hidden-input" type="file" accept=".txt,.md,.csv,text/plain,text/markdown,text/csv" onChange={importScript} />
      <button
        className="btn ghost cr-import-action"
        type="button"
        onClick={() => importInputRef.current?.click()}
        disabled={!data.currentProject || data.currentProject.id < 1 || busy === 'script-import'}
        title={!data.currentProject || data.currentProject.id < 1 ? 'Start a production before importing a script.' : undefined}
      >
        <FileUp size={14} /> Import Script
      </button>
      {viewModel.mode === 'firstRun' && <button className="btn ghost cr-quick-tour-action" type="button" disabled title="Quick tour is not available yet.">View Quick Tour</button>}
      <button className="btn primary" type="button" onClick={createOrSeedProduction} disabled={Boolean(busy)}>
        {viewModel.mode === 'firstRun' ? 'Start First Production' : 'Start Production'}
      </button>
    </>
  );

  const selectPreset = (format: ContentFormatPreset) => {
    setBrief((current) => ({
      ...current,
      contentFormatId: format.id,
      duration: formatMidpoint(format),
      speakerNames: format.default_speaker_roles.join(', '),
      tone: format.tone_options[0] || current.tone,
    }));
    document.getElementById('start-production-title')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  };

  const setLowerOpen = (open: boolean) => {
    setLowerWorkspaceOpen(open);
    window.localStorage.setItem(LOWER_WORKSPACE_STORAGE_KEY, String(open));
  };

  const visibleProject = data.currentProject || (isAuthenticated ? null : localDraftProject);

  return (
    <StudioShell
      currentProject={visibleProject}
      syncState={syncState}
      topbarRuntimeChips={topbarRuntimeChips}
      topbarActions={topbarActions}
    >
      <CommandRoomWorkflowStrip project={visibleProject} viewModel={viewModel} />
      <CommandRoomStateBar mode={viewModel.mode} counts={viewModel.counts} />
      {error && <div className="cr-error" role="alert">{error}</div>}
      <section className="cr-hero">
        <ProductionBriefPanel
          formats={data.contentFormats}
          project={data.currentProject}
          selectedFormat={selectedFormat}
          brief={brief}
          busy={busy === 'production-create'}
          error={null}
          onBriefChange={updateBrief}
          onSubmit={createOrSeedProduction}
        />
        <QueueSetupPanel viewModel={viewModel} onPrimaryAction={createOrSeedProduction} busy={busy === 'production-create'} />
      </section>
      <ContentPresetLibrary formats={data.contentFormats} selectedFormatId={brief.contentFormatId} onSelect={selectPreset} />
      <ActiveProductionsPanel viewModel={viewModel} currentProject={data.currentProject} onApproveCurrentPreview={approvePreview} />
      <LowerWorkspace viewModel={viewModel} open={lowerWorkspaceOpen} onToggle={setLowerOpen} />
      <div className="cr-support-links" aria-label="Command Room supporting routes">
        <Link to="/generated-media"><ExternalLink size={13} /> Generated Media</Link>
        <Link to="/accounts">Release Prep</Link>
        <button type="button" onClick={() => void load(selectedProjectId)}><RefreshCw size={13} /> Refresh</button>
      </div>
    </StudioShell>
  );
};

export default CommandRoomPage;
