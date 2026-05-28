import React from 'react';

import type {
  GenerationJob,
  PlatformMetadata,
  Project,
  ProjectPreviewSettings,
  RenderReadinessEstimate,
  ScriptLine,
  ScriptRevision,
} from '../../api/models';

type ReadinessState = 'missing' | 'ready' | 'warning' | 'failed' | 'verified';
type WorkflowStep = 'idea' | 'script' | 'cast' | 'scene' | 'preview' | 'render' | 'release';

export type ProductionReadinessRow = {
  id: string;
  label: string;
  state: ReadinessState;
  readyText: string;
  needsText: string;
  actionLabel: string;
  step: WorkflowStep;
  speakerName?: string;
};

export type NextBestAction = {
  label: string;
  step: WorkflowStep;
  href: string;
  complete: boolean;
};

export type ProductionReadiness = {
  rows: ProductionReadinessRow[];
  nextAction: NextBestAction;
  speakers: string[];
  missingVoiceSpeakers: string[];
  missingCharacterImageSpeakers: string[];
  renderPrerequisitesReady: boolean;
};

export const defaultPreviewSettings: ProjectPreviewSettings = {
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

export const normalizePreviewSettings = (
  settings?: Partial<ProjectPreviewSettings> | null
): ProjectPreviewSettings => ({
  ...defaultPreviewSettings,
  ...(settings || {}),
  background_metadata: settings?.background_metadata || {},
  speaker_mappings: settings?.speaker_mappings || [],
  layout: {
    ...defaultPreviewSettings.layout,
    ...(settings?.layout || {}),
  },
});

export const scriptLinesForReadiness = (script: ScriptRevision | null): ScriptLine[] =>
  script?.parsed_lines || [];

export const speakersForReadiness = (
  script: ScriptRevision | null,
  preview: ProjectPreviewSettings
): string[] => {
  const fromScript = scriptLinesForReadiness(script).map((line) => line.speaker).filter(Boolean);
  const fromPreview = preview.speaker_mappings.map((item) => item.speaker_name).filter(Boolean);
  return Array.from(new Set([...fromScript, ...fromPreview]));
};

const activeRenderStatuses = new Set(['queued', 'processing', 'running', 'retrying']);

const stepTarget = (step: WorkflowStep) => `step-${step}`;

export const workflowHref = (
  step: WorkflowStep,
  projectId?: number | string | null,
  mode: 'anchor' | 'productionLab' = 'anchor'
) => {
  const hash = `#${stepTarget(step)}`;
  if (mode === 'productionLab' && projectId) {
    return `/projects/${projectId}?tab=${step}${hash}`;
  }
  return hash;
};

const hasReleaseMetadata = (metadata?: PlatformMetadata | null) =>
  Boolean(metadata?.title?.trim() && metadata?.description?.trim() && !metadata.validation_errors?.length);

export const computeProductionReadiness = ({
  project,
  script,
  latestJob,
  metadata,
  draftEstimate,
  linkMode = 'anchor',
}: {
  project: Project | null;
  script: ScriptRevision | null;
  latestJob?: GenerationJob | null;
  metadata?: PlatformMetadata | null;
  draftEstimate?: RenderReadinessEstimate | null;
  linkMode?: 'anchor' | 'productionLab';
}): ProductionReadiness => {
  const preview = normalizePreviewSettings(project?.preview_settings);
  const speakers = speakersForReadiness(script, preview);
  const mappingBySpeaker = new Map(preview.speaker_mappings.map((mapping) => [mapping.speaker_name, mapping]));
  const scriptReady = Boolean(script?.parsed_lines?.length);
  const sceneReady = Boolean(preview.background_url || project?.background_asset_id);
  const missingVoiceSpeakers = speakers.filter((speaker) => !mappingBySpeaker.get(speaker)?.voice_profile_id);
  const missingCharacterImageSpeakers = speakers.filter((speaker) => {
    const mapping = mappingBySpeaker.get(speaker);
    return !mapping?.character_portrait_url && !mapping?.character_portrait_filename;
  });
  const voiceReady = speakers.length > 0 && missingVoiceSpeakers.length === 0;
  const characterImageReady = speakers.length > 0 && missingCharacterImageSpeakers.length === 0;
  const activeRender = Boolean(latestJob && activeRenderStatuses.has(latestJob.status));
  const hasOutput = Boolean(project?.latest_output || project?.current_output_video_id || latestJob?.output_video_id);
  const previewApproved = Boolean(project?.approved_at);
  const releaseReady = hasReleaseMetadata(metadata);
  const draftEstimateReady = !draftEstimate || draftEstimate.draft_ready;
  const renderPrerequisitesReady = scriptReady && voiceReady && characterImageReady && sceneReady && !activeRender;
  const projectId = project?.id && project.id > 0 ? project.id : null;
  const href = (step: WorkflowStep) => workflowHref(step, projectId, linkMode);

  const rows: ProductionReadinessRow[] = [
    {
      id: 'script',
      label: 'Script',
      state: scriptReady ? 'ready' : 'missing',
      readyText: 'Ready',
      needsText: 'Missing script',
      actionLabel: 'Write script',
      step: 'script',
    },
    {
      id: 'voice-assignments',
      label: 'Speaker voice assignments',
      state: voiceReady ? 'ready' : 'missing',
      readyText: 'Ready',
      needsText: missingVoiceSpeakers[0]
        ? `Missing voice for ${missingVoiceSpeakers[0]}`
        : 'Missing voice assignments',
      actionLabel: 'Assign voices',
      step: 'cast',
      speakerName: missingVoiceSpeakers[0],
    },
    {
      id: 'character-images',
      label: 'Speaker character images',
      state: characterImageReady ? 'ready' : 'missing',
      readyText: 'Ready',
      needsText: missingCharacterImageSpeakers[0]
        ? `Missing character image for ${missingCharacterImageSpeakers[0]}`
        : 'Missing character images',
      actionLabel: 'Choose character images',
      step: 'cast',
      speakerName: missingCharacterImageSpeakers[0],
    },
    {
      id: 'scene',
      label: 'Scene',
      state: sceneReady ? 'ready' : 'missing',
      readyText: 'Ready',
      needsText: 'Missing scene',
      actionLabel: 'Select scene',
      step: 'scene',
    },
    {
      id: 'preview',
      label: 'Preview approval',
      state: previewApproved ? 'verified' : hasOutput ? 'warning' : 'missing',
      readyText: 'Verified',
      needsText: hasOutput ? 'Preview output needs verification' : 'Missing draft preview',
      actionLabel: hasOutput ? 'Approve preview' : 'Render draft',
      step: hasOutput ? 'preview' : 'render',
    },
    {
      id: 'render',
      label: 'Render',
      state: latestJob?.status === 'failed' ? 'failed' : activeRender ? 'warning' : renderPrerequisitesReady && draftEstimateReady ? 'ready' : 'missing',
      readyText: 'Ready',
      needsText: latestJob?.status === 'failed'
        ? 'Latest render failed'
        : activeRender
          ? 'Render is running'
          : draftEstimate?.blocking_reasons?.[0] || 'Missing render requirements',
      actionLabel: 'Open render',
      step: 'render',
    },
    {
      id: 'release',
      label: 'Release metadata',
      state: releaseReady ? 'ready' : 'missing',
      readyText: 'Ready',
      needsText: 'Missing release metadata',
      actionLabel: 'Prepare release',
      step: 'release',
    },
  ];

  let nextAction: NextBestAction;
  if (!project) {
    nextAction = { label: 'Start a production idea', step: 'idea', href: '#start-production-title', complete: false };
  } else if (!scriptReady) {
    nextAction = { label: 'Write or generate a speaker-separated script', step: 'script', href: href('script'), complete: false };
  } else if (missingVoiceSpeakers[0]) {
    nextAction = { label: `Assign a voice profile to ${missingVoiceSpeakers[0]}`, step: 'cast', href: href('cast'), complete: false };
  } else if (missingCharacterImageSpeakers[0]) {
    nextAction = { label: `Choose a character image for ${missingCharacterImageSpeakers[0]}`, step: 'cast', href: href('cast'), complete: false };
  } else if (!sceneReady) {
    nextAction = { label: 'Select a background or scene before rendering', step: 'scene', href: href('scene'), complete: false };
  } else if (activeRender) {
    nextAction = { label: 'Wait for the current render to finish', step: 'render', href: href('render'), complete: false };
  } else if (draftEstimate?.blocking_reasons?.[0] && !hasOutput) {
    nextAction = { label: draftEstimate.blocking_reasons[0], step: 'render', href: href('render'), complete: false };
  } else if (!hasOutput) {
    nextAction = { label: 'Render a draft before preparing release', step: 'render', href: href('render'), complete: false };
  } else if (!previewApproved) {
    nextAction = { label: 'Approve preview before final render', step: 'preview', href: href('preview'), complete: false };
  } else if (!releaseReady) {
    nextAction = { label: 'Prepare release title and description', step: 'release', href: href('release'), complete: false };
  } else {
    nextAction = { label: 'Production is ready for release', step: 'release', href: href('release'), complete: true };
  }

  return {
    rows,
    nextAction,
    speakers,
    missingVoiceSpeakers,
    missingCharacterImageSpeakers,
    renderPrerequisitesReady,
  };
};

const stateLabel = (state: ReadinessState) => {
  if (state === 'verified') return 'Verified';
  if (state === 'failed') return 'Failed';
  if (state === 'warning') return 'Warning';
  if (state === 'ready') return 'Ready';
  return 'Missing';
};

const stateClass = (state: ReadinessState) => {
  if (state === 'verified' || state === 'ready') return 'op-badge-success';
  if (state === 'failed') return 'op-badge-error';
  if (state === 'warning') return 'op-badge-warning';
  return 'op-badge-muted';
};

const ActionLink: React.FC<{ href: string; className?: string; children: React.ReactNode }> = ({
  href,
  className,
  children,
}) => <a className={className} href={href}>{children}</a>;

export const ProductionReadinessPanel: React.FC<{
  readiness: ProductionReadiness;
  title?: string;
  compact?: boolean;
  linkMode?: 'anchor' | 'productionLab';
  projectId?: number | string | null;
}> = ({ readiness, title = 'Production readiness', compact = false, linkMode = 'anchor', projectId = null }) => (
  <div className={`op-readiness-panel ${compact ? 'compact' : ''}`}>
    <div className="op-readiness-panel-head">
      <div className="op-panel-title">{title}</div>
      <span className={`op-badge ${readiness.nextAction.complete ? 'op-badge-success' : 'op-badge-warning'}`}>
        {readiness.nextAction.complete ? 'Verified' : 'Next action'}
      </span>
    </div>
    <div className="op-next-action-card">
      <div>
        <div className="op-prod-next-label">Next Best Action</div>
        <div className="op-prod-next-text">{readiness.nextAction.label}</div>
      </div>
      {!readiness.nextAction.complete && (
        <ActionLink className="op-btn op-btn-primary op-btn-sm" href={readiness.nextAction.href}>
          Open
        </ActionLink>
      )}
    </div>
    <div className="op-readiness-rows">
      {readiness.rows.map((row) => {
        const label = row.state === 'ready' || row.state === 'verified' ? row.readyText : row.needsText;
        const rowHref = workflowHref(row.step, projectId, linkMode);
        return (
          <div key={row.id} className={`op-readiness-row ${row.state}`}>
            <div className="op-readiness-row-main">
              <span className="op-readiness-row-label">{row.label}</span>
              <span className="op-readiness-row-copy">{label}</span>
            </div>
            <div className="op-readiness-row-actions">
              <span className={`op-badge ${stateClass(row.state)}`}>{stateLabel(row.state)}</span>
              {row.state !== 'ready' && row.state !== 'verified' && (
                <ActionLink className="op-btn op-btn-ghost op-btn-sm" href={rowHref}>
                  {row.actionLabel}
                </ActionLink>
              )}
            </div>
          </div>
        );
      })}
    </div>
  </div>
);

export default ProductionReadinessPanel;
