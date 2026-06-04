import React, { useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  FileUp,
  PencilLine,
  RefreshCw,
  Save,
  Sparkles,
} from 'lucide-react';

import type {
  ContentFormatPreset,
  GeneratedScript,
  GeneratedScriptLine,
  PlatformTarget,
  RenderReadinessEstimate,
  ScriptGenerationProviderMetadata,
  ScriptLine,
  ScriptRevision,
} from '../../api/models';

export type ScriptViewState = 'empty' | 'generating' | 'generatedAccepted' | 'failed';

export type ScriptDiagnosticRow = {
  label: string;
  value: string;
  tone: 'neutral' | 'ready' | 'warning' | 'failed' | 'info';
};

type TimelineLine = {
  key: string;
  idLabel: string;
  stableId: string | null;
  section: string;
  speaker: string;
  text: string;
  captionText: string | null;
  durationSeconds: number | null;
  status: 'ready' | 'pending' | 'warning' | 'failed';
  missingStableId: boolean;
};

export type ScriptViewModel = {
  state: ScriptViewState;
  heroTitle: string;
  heroDescription: string;
  statusLabel: string;
  statusTone: 'active' | 'ready' | 'warning' | 'failed' | 'info';
  lineCount: number;
  speakerCount: number;
  estimatedDurationSeconds: number;
  targetDurationSeconds: number;
  canProceed: boolean;
  canAccept: boolean;
  canGenerate: boolean;
  hasAcceptedRevision: boolean;
  captionReady: boolean;
  parserStatus: 'empty' | 'pending' | 'parsed' | 'warning' | 'failed';
  failureReason: string | null;
  warnings: string[];
  hardWarnings: string[];
  missingStableLineIds: number;
  timelineLines: TimelineLine[];
};

export type DeriveScriptViewModelInput = {
  script: ScriptRevision | null;
  scriptDraft: string;
  scriptLines: ScriptLine[];
  generatedScript: GeneratedScript | null;
  isGenerating: boolean;
  scriptFailure: string | null;
  validationWarnings: string[];
  renderReadiness: RenderReadinessEstimate | null;
  targetDurationSeconds: number;
  generatedScriptHasHardWarnings?: boolean;
};

const hardWarningMarkers = [
  'Hard quality failure',
  'has no spoken lines',
  'references missing speaker',
  'has no caption text',
  'Speaker count',
  'Parser error',
  'parse error',
  'invalid',
];

const compactDuration = (seconds: number) => {
  if (!Number.isFinite(seconds) || seconds <= 0) {
    return '0s';
  }
  return `${Math.round(seconds)}s`;
};

const estimateLineDuration = (text: string) => {
  const words = text.trim().split(/\s+/).filter(Boolean).length;
  return words ? Math.max(1.4, words / 2.45) : 0;
};

const normalizeText = (value: string | null | undefined, fallback = '') => String(value || fallback).trim();

const sanitizeDisplayText = (value: string | null | undefined, fallback = 'Unavailable') => {
  const firstLine = normalizeText(value).split('\n')[0] || fallback;
  return firstLine
    .replace(/\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi, '[email]')
    .replace(/\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|secret|password)\b\s*[:=]\s*\S+/gi, '[redacted]')
    .replace(/(?:\/Users|\/private|\/var|\/tmp|\/home|[A-Za-z]:\\)[^\s,;)]*/g, '[path]')
    .replace(/\s+at\s+\S+\(.+\)/g, ' [stack hidden]')
    .slice(0, 220);
};

const generatedLineToTimeline = (line: GeneratedScriptLine, index: number): TimelineLine => ({
  key: line.id || `generated-${index}`,
  idLabel: line.id || `line_${String(index + 1).padStart(3, '0')}`,
  stableId: line.id || null,
  section: normalizeText(line.section, 'Body') || 'Body',
  speaker: normalizeText(line.speaker_label, `Speaker ${index + 1}`) || `Speaker ${index + 1}`,
  text: normalizeText(line.text, 'Pending line') || 'Pending line',
  captionText: normalizeText(line.caption_text) || null,
  durationSeconds: Number.isFinite(line.estimated_duration_sec) ? Number(line.estimated_duration_sec) : null,
  status: 'ready',
  missingStableId: !line.id,
});

const scriptLineToTimeline = (line: ScriptLine, index: number): TimelineLine => {
  const stableId = line.line_id || null;
  return {
    key: stableId || `${line.speaker}-${index}`,
    idLabel: stableId || `line_${String(index + 1).padStart(3, '0')}`,
    stableId,
    section: normalizeText(line.section, 'Body') || 'Body',
    speaker: normalizeText(line.speaker, `Speaker ${index + 1}`) || `Speaker ${index + 1}`,
    text: normalizeText(line.text, 'Pending line') || 'Pending line',
    captionText: normalizeText(line.caption_text) || null,
    durationSeconds: estimateLineDuration(line.caption_text || line.text),
    status: stableId ? 'ready' : 'warning',
    missingStableId: !stableId,
  };
};

const buildTimelineLines = (
  generatedScript: GeneratedScript | null,
  scriptLines: ScriptLine[],
  isGenerating: boolean
) => {
  const source = generatedScript?.lines?.length
    ? generatedScript.lines.map(generatedLineToTimeline)
    : scriptLines.map(scriptLineToTimeline);
  if (!isGenerating || source.length >= 6) {
    return source;
  }
  const next = [...source];
  while (next.length < 6) {
    const index = next.length;
    next.push({
      key: `pending-${index}`,
      idLabel: `line_${String(index + 1).padStart(3, '0')}`,
      stableId: null,
      section: 'Body',
      speaker: index % 2 === 0 ? 'Host' : 'Guest',
      text: 'Generation pending...',
      captionText: null,
      durationSeconds: null,
      status: 'pending',
      missingStableId: true,
    });
  }
  return next;
};

export const deriveScriptViewModel = ({
  script,
  scriptDraft,
  scriptLines,
  generatedScript,
  isGenerating,
  scriptFailure,
  validationWarnings,
  renderReadiness,
  targetDurationSeconds,
  generatedScriptHasHardWarnings = false,
}: DeriveScriptViewModelInput): ScriptViewModel => {
  const timelineLines = buildTimelineLines(generatedScript, scriptLines, isGenerating);
  const lineCount = timelineLines.filter((line) => line.status !== 'pending').length;
  const speakers = new Set(timelineLines.filter((line) => line.status !== 'pending').map((line) => line.speaker).filter(Boolean));
  const estimatedDurationSeconds =
    Number(generatedScript?.total_estimated_duration_sec || generatedScript?.estimated_total_duration_sec || 0) ||
    timelineLines.reduce((total, line) => total + (line.durationSeconds || 0), 0);
  const target =
    Number(generatedScript?.target_duration_sec || renderReadiness?.target_seconds || targetDurationSeconds || 0);
  const hardWarnings = validationWarnings.filter((warning) =>
    hardWarningMarkers.some((marker) => warning.toLowerCase().includes(marker.toLowerCase()))
  );
  const failureReason = scriptFailure ? sanitizeDisplayText(scriptFailure, 'Script operation failed.') : null;
  const hasAcceptedRevision = Boolean(script?.id && script?.parsed_lines?.length);
  const hasDraftText = Boolean(normalizeText(scriptDraft));
  const hasAnyLines = lineCount > 0 || Boolean(generatedScript?.lines?.length);
  const captionReady = lineCount > 0 && timelineLines.slice(0, lineCount).every((line) => Boolean(line.captionText || line.text));
  const missingStableLineIds = timelineLines.filter((line) => line.status !== 'pending' && line.missingStableId).length;

  let state: ScriptViewState = 'empty';
  if (isGenerating) {
    state = 'generating';
  } else if (failureReason || generatedScriptHasHardWarnings || hardWarnings.length > 0) {
    state = 'failed';
  } else if (hasAnyLines || hasAcceptedRevision || hasDraftText) {
    state = 'generatedAccepted';
  }

  const overBudget = target > 0 && estimatedDurationSeconds > target * 1.1;
  const warnings = [
    ...validationWarnings.map((warning) => sanitizeDisplayText(warning, 'Validation warning')),
    ...(missingStableLineIds > 0 ? [`${missingStableLineIds} line${missingStableLineIds === 1 ? '' : 's'} missing stable IDs`] : []),
    ...(overBudget ? [`Estimated duration ${compactDuration(estimatedDurationSeconds)} exceeds ${compactDuration(target)} target`] : []),
    ...(renderReadiness?.blocking_reasons || []).map((reason) => sanitizeDisplayText(reason, 'Readiness warning')),
  ];

  const copyByState: Record<ScriptViewState, Pick<ScriptViewModel, 'heroTitle' | 'heroDescription' | 'statusLabel' | 'statusTone' | 'parserStatus'>> = {
    empty: {
      heroTitle: 'Generate the script.',
      heroDescription:
        'No script yet. Generate from the production brief or import a speaker-separated draft. The editor and timeline fill in as lines are parsed.',
      statusLabel: 'No script',
      statusTone: 'info',
      parserStatus: 'empty',
    },
    generating: {
      heroTitle: 'Writing the script...',
      heroDescription:
        'Generation is in progress. The layout stays stable while pending rows reserve the editing surface and Cast handoff remains locked.',
      statusLabel: 'Writing',
      statusTone: 'active',
      parserStatus: 'pending',
    },
    generatedAccepted: {
      heroTitle: 'Editor and timeline, side by side.',
      heroDescription:
        'The idea is now speaker-separated, caption-ready dialogue. Stable line IDs, speakers, and captions stay visible before Cast and Voices.',
      statusLabel: hasAcceptedRevision ? 'Script saved' : 'Ready to accept',
      statusTone: 'ready',
      parserStatus: warnings.length ? 'warning' : 'parsed',
    },
    failed: {
      heroTitle: 'Generation failed - repair to continue.',
      heroDescription:
        'The last recoverable draft stays in the editor. Repair the broken span, retry generation, or import a clean script before continuing.',
      statusLabel: 'Generation failed',
      statusTone: 'failed',
      parserStatus: 'failed',
    },
  };

  return {
    state,
    ...copyByState[state],
    lineCount,
    speakerCount: speakers.size,
    estimatedDurationSeconds,
    targetDurationSeconds: target,
    canProceed: state === 'generatedAccepted' && lineCount > 0 && hardWarnings.length === 0 && !generatedScriptHasHardWarnings,
    canAccept: Boolean(generatedScript?.lines?.length) && hardWarnings.length === 0 && !generatedScriptHasHardWarnings,
    canGenerate: !isGenerating,
    hasAcceptedRevision,
    captionReady,
    parserStatus: state === 'failed' ? 'failed' : copyByState[state].parserStatus,
    failureReason,
    warnings,
    hardWarnings,
    missingStableLineIds,
    timelineLines,
  };
};

export const getSafeScriptDiagnostics = ({
  providerMetadata,
  providerLabel,
  viewModel,
  warnings,
  renderReadiness,
}: {
  providerMetadata: ScriptGenerationProviderMetadata | null;
  providerLabel: string | null;
  viewModel: ScriptViewModel;
  warnings: string[];
  renderReadiness: RenderReadinessEstimate | null;
}): ScriptDiagnosticRow[] => {
  const rows: ScriptDiagnosticRow[] = [
    {
      label: 'Generation provider',
      value: sanitizeDisplayText(providerLabel || providerMetadata?.provider_name || 'Not run yet'),
      tone: providerMetadata?.fallback_used ? 'warning' : providerMetadata ? 'ready' : 'neutral',
    },
    {
      label: 'Parser status',
      value:
        viewModel.parserStatus === 'parsed'
          ? 'Parsed dialogue lines'
          : viewModel.parserStatus === 'pending'
            ? 'Generation pending'
            : viewModel.parserStatus === 'failed'
              ? 'Repair required'
              : viewModel.parserStatus === 'warning'
                ? 'Parsed with warnings'
                : 'Waiting for script',
      tone: viewModel.parserStatus === 'failed' ? 'failed' : viewModel.parserStatus === 'warning' ? 'warning' : viewModel.parserStatus === 'empty' ? 'neutral' : 'ready',
    },
    {
      label: 'Caption readiness',
      value: viewModel.captionReady ? 'Caption text available' : 'Caption text derives from dialogue',
      tone: viewModel.captionReady ? 'ready' : 'info',
    },
    {
      label: 'Timing budget',
      value: `${compactDuration(viewModel.estimatedDurationSeconds)} estimated / ${compactDuration(viewModel.targetDurationSeconds)} target`,
      tone:
        viewModel.targetDurationSeconds > 0 && viewModel.estimatedDurationSeconds > viewModel.targetDurationSeconds * 1.1
          ? 'warning'
          : 'ready',
    },
  ];

  if (providerMetadata?.failure_type) {
    rows.push({
      label: 'Provider note',
      value: sanitizeDisplayText(providerMetadata.failure_type, 'Provider fallback'),
      tone: providerMetadata.fallback_used ? 'warning' : 'info',
    });
  }

  const validationSummary = warnings.slice(0, 4).map((warning) => sanitizeDisplayText(warning, 'Validation warning')).join(' | ');
  rows.push({
    label: 'Validation messages',
    value: validationSummary || 'No blocking validation messages',
    tone: warnings.length ? 'warning' : 'ready',
  });

  if (renderReadiness) {
    rows.push({
      label: 'Render readiness',
      value: renderReadiness.draft_ready ? 'Draft render prerequisites look ready' : 'Render readiness has blockers',
      tone: renderReadiness.draft_ready ? 'ready' : 'warning',
    });
  }

  return rows;
};

type ScriptControlsAccordionProps = {
  viewModel: ScriptViewModel;
  contentFormats: ContentFormatPreset[];
  platformTargets: Array<{ id: PlatformTarget; label: string }>;
  selectedFormat: ContentFormatPreset | null;
  scriptFormatId: string;
  scriptPlatform: PlatformTarget;
  scriptTargetDuration: number;
  scriptTone: string;
  scriptAudience: string;
  scriptSpeakerNames: string;
  scriptPrompt: string;
  providerMetadata: ScriptGenerationProviderMetadata | null;
  providerLabel: string | null;
  warnings: string[];
  renderReadiness: RenderReadinessEstimate | null;
  revisions: ScriptRevision[];
  busy: string | null;
  onPromptChange: (value: string) => void;
  onFormatChange: (formatId: string) => void;
  onPlatformChange: (platform: PlatformTarget) => void;
  onDurationChange: (duration: number) => void;
  onToneChange: (tone: string) => void;
  onAudienceChange: (audience: string) => void;
  onSpeakerNamesChange: (speakers: string) => void;
  onGenerate: () => void;
  onImportFile: (file: File) => void;
  onSaveScript: () => void;
  onRestoreRevision: (revisionId: number) => void;
};

const toneChipClass = (tone: ScriptViewModel['statusTone'] | 'neutral' | 'queued') => {
  if (tone === 'ready') return 'is-ready';
  if (tone === 'warning') return 'is-warning';
  if (tone === 'failed') return 'is-failed';
  if (tone === 'active') return 'is-active';
  if (tone === 'queued' || tone === 'info') return 'is-info';
  return 'plain';
};

const diagnosticToneClass = (tone: ScriptDiagnosticRow['tone']) =>
  tone === 'ready' ? 'ready' : tone === 'warning' ? 'warn' : tone === 'failed' ? 'fail' : tone === 'info' ? 'queued' : '';

const ScriptControlsAccordion: React.FC<ScriptControlsAccordionProps> = ({
  viewModel,
  contentFormats,
  platformTargets,
  selectedFormat,
  scriptFormatId,
  scriptPlatform,
  scriptTargetDuration,
  scriptTone,
  scriptAudience,
  scriptSpeakerNames,
  scriptPrompt,
  providerMetadata,
  providerLabel,
  warnings,
  renderReadiness,
  revisions,
  busy,
  onPromptChange,
  onFormatChange,
  onPlatformChange,
  onDurationChange,
  onToneChange,
  onAudienceChange,
  onSpeakerNamesChange,
  onGenerate,
  onImportFile,
  onSaveScript,
  onRestoreRevision,
}) => {
  const [open, setOpen] = useState(false);
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const diagnostics = useMemo(
    () => getSafeScriptDiagnostics({ providerMetadata, providerLabel, viewModel, warnings, renderReadiness }),
    [providerMetadata, providerLabel, renderReadiness, viewModel, warnings]
  );

  return (
    <section className={`script-controls-accordion ${open ? 'is-open' : ''}`} data-testid="script-controls-accordion">
      <button
        type="button"
        className="script-controls-summary"
        aria-expanded={open}
        aria-controls="script-controls-body"
        onClick={() => setOpen((current) => !current)}
      >
        <span>Generation controls · script budget · advanced diagnostics</span>
        <span className="script-controls-summary-meta">
          <span className="chip is-active plain">{open ? 'Expanded' : 'Collapsed'}</span>
          <ChevronDown size={16} aria-hidden="true" />
        </span>
      </button>

      <div id="script-controls-body" className="script-controls-body" hidden={!open}>
        <section className="script-control-card">
          <div className="script-control-card-head">
            <h3>Generation controls</h3>
            <span className="chip is-active">{providerLabel || 'Local provider'}</span>
          </div>
          <label className="field">
            <span>Production idea</span>
            <textarea
              className="input script-prompt-input"
              value={scriptPrompt}
              onChange={(event) => onPromptChange(event.target.value)}
              rows={3}
              placeholder={selectedFormat ? `Idea for ${selectedFormat.display_name.toLowerCase()}` : 'Idea for script generation'}
            />
          </label>
          <div className="script-controls-grid">
            <label className="field">
              <span>Content format</span>
              <select className="select" value={scriptFormatId} onChange={(event) => onFormatChange(event.target.value)}>
                {contentFormats.map((format) => (
                  <option key={format.id} value={format.id}>
                    {format.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Platform</span>
              <select className="select" value={scriptPlatform} onChange={(event) => onPlatformChange(event.target.value as PlatformTarget)}>
                {platformTargets.map((platform) => (
                  <option key={platform.id} value={platform.id}>
                    {platform.label}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Target duration</span>
              <input
                className="input"
                type="number"
                min={10}
                max={180}
                step={5}
                value={scriptTargetDuration}
                onChange={(event) => onDurationChange(Number(event.target.value))}
              />
            </label>
            <label className="field">
              <span>Tone</span>
              <input className="input" value={scriptTone} onChange={(event) => onToneChange(event.target.value)} />
            </label>
            <label className="field">
              <span>Audience</span>
              <input className="input" value={scriptAudience} onChange={(event) => onAudienceChange(event.target.value)} />
            </label>
            <label className="field">
              <span>Speaker names</span>
              <input
                className="input"
                value={scriptSpeakerNames}
                onChange={(event) => onSpeakerNamesChange(event.target.value)}
                placeholder={selectedFormat?.default_speaker_roles.join(', ') || 'Host, Guest'}
              />
            </label>
          </div>
          {selectedFormat && (
            <div className="script-format-note">
              <span className="chip is-brand plain">{selectedFormat.display_name}</span>
              <span>{selectedFormat.best_use_case}</span>
            </div>
          )}
          <div className="script-action-row">
            <button
              type="button"
              className="btn primary"
              onClick={onGenerate}
              disabled={busy === 'script-generate' || !scriptPrompt.trim() || !viewModel.canGenerate}
            >
              <Sparkles size={15} />
              {viewModel.state === 'failed' ? 'Retry generation' : generatedButtonLabel(viewModel)}
            </button>
            <button type="button" className="btn ghost" onClick={() => importInputRef.current?.click()} disabled={Boolean(busy)}>
              <FileUp size={15} />
              Import script
            </button>
            <button type="button" className="btn ghost" onClick={onSaveScript} disabled={busy === 'script' || busy === 'script-generate'}>
              <Save size={15} />
              Save manual draft
            </button>
            <input
              ref={importInputRef}
              className="sr-only"
              type="file"
              accept=".txt,.md,.json,text/plain,application/json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  onImportFile(file);
                  event.target.value = '';
                }
              }}
            />
          </div>
        </section>

        <section className="script-control-card">
          <div className="script-control-card-head">
            <h3>Script budget</h3>
            <span className={`chip ${viewModel.warnings.length ? 'is-warning' : 'is-ready'}`}>
              {viewModel.warnings.length ? 'Review' : 'Ready'}
            </span>
          </div>
          <div className="script-budget-grid">
            <div className="metric">
              <b>{viewModel.lineCount}</b>
              <span>lines</span>
            </div>
            <div className="metric">
              <b>{viewModel.speakerCount}</b>
              <span>speakers</span>
            </div>
            <div className="metric">
              <b>{compactDuration(viewModel.estimatedDurationSeconds)}</b>
              <span>estimated</span>
            </div>
            <div className="metric">
              <b>{compactDuration(viewModel.targetDurationSeconds)}</b>
              <span>target</span>
            </div>
          </div>
          <div className="script-warning-list" aria-live="polite">
            {viewModel.warnings.length ? (
              viewModel.warnings.slice(0, 5).map((warning) => (
                <div key={warning} className="row lead warn">
                  <span>{warning}</span>
                </div>
              ))
            ) : (
              <div className="row lead ready">
                <span>Line count, speaker map, and caption text are ready for the next handoff.</span>
              </div>
            )}
          </div>
        </section>

        <section className="script-control-card">
          <div className="script-control-card-head">
            <h3>Advanced diagnostics</h3>
            <span className="chip is-info">Safe</span>
          </div>
          <div className="script-diagnostic-list">
            {diagnostics.map((row) => (
              <div key={row.label} className={`row lead ${diagnosticToneClass(row.tone)}`}>
                <div>
                  <div className="t">{row.label}</div>
                  <div className="m">{row.value}</div>
                </div>
              </div>
            ))}
          </div>
          {revisions.length > 0 && (
            <div className="script-revision-list" aria-label="Recent script revisions">
              <h4>Recent revisions</h4>
              {revisions.slice(0, 4).map((revision) => (
                <button
                  key={revision.id}
                  type="button"
                  className="script-revision-button"
                  onClick={() => onRestoreRevision(revision.id)}
                  disabled={busy === `restore-${revision.id}`}
                >
                  <span>Revision #{revision.id}</span>
                  <small>{sanitizeDisplayText(revision.source, 'manual')} · {sanitizeDisplayText(revision.raw_text, 'No preview')}</small>
                </button>
              ))}
            </div>
          )}
        </section>
      </div>
    </section>
  );
};

const generatedButtonLabel = (viewModel: ScriptViewModel) => {
  if (viewModel.state === 'empty') return 'Generate with Ollama';
  if (viewModel.state === 'generating') return 'Generating...';
  return 'Regenerate draft';
};

export type ProductionScriptSectionProps = {
  projectName: string | null | undefined;
  script: ScriptRevision | null;
  scriptRevisions: ScriptRevision[];
  scriptDraft: string;
  scriptLines: ScriptLine[];
  generatedScript: GeneratedScript | null;
  contentFormats: ContentFormatPreset[];
  selectedFormat: ContentFormatPreset | null;
  platformTargets: Array<{ id: PlatformTarget; label: string }>;
  scriptFormatId: string;
  scriptPlatform: PlatformTarget;
  scriptTargetDuration: number;
  scriptTone: string;
  scriptAudience: string;
  scriptSpeakerNames: string;
  scriptPrompt: string;
  providerMetadata: ScriptGenerationProviderMetadata | null;
  providerLabel: string | null;
  generationWarnings: string[];
  generatedScriptHasHardWarnings: boolean;
  scriptIsDirty: boolean;
  scriptFailure: string | null;
  renderReadiness: RenderReadinessEstimate | null;
  busy: string | null;
  onPromptChange: (value: string) => void;
  onFormatChange: (formatId: string) => void;
  onPlatformChange: (platform: PlatformTarget) => void;
  onDurationChange: (duration: number) => void;
  onToneChange: (tone: string) => void;
  onAudienceChange: (audience: string) => void;
  onSpeakerNamesChange: (speakers: string) => void;
  onDraftChange: (draft: string) => void;
  onGenerate: () => void;
  onSaveScript: () => void;
  onAcceptGeneratedScript: () => void;
  onAcceptAndContinue: () => void;
  onContinue: () => void;
  onImportFile: (file: File) => void;
  onRestoreRevision: (revisionId: number) => void;
};

const ProductionScriptSection: React.FC<ProductionScriptSectionProps> = ({
  projectName,
  script,
  scriptRevisions,
  scriptDraft,
  scriptLines,
  generatedScript,
  contentFormats,
  selectedFormat,
  platformTargets,
  scriptFormatId,
  scriptPlatform,
  scriptTargetDuration,
  scriptTone,
  scriptAudience,
  scriptSpeakerNames,
  scriptPrompt,
  providerMetadata,
  providerLabel,
  generationWarnings,
  generatedScriptHasHardWarnings,
  scriptIsDirty,
  scriptFailure,
  renderReadiness,
  busy,
  onPromptChange,
  onFormatChange,
  onPlatformChange,
  onDurationChange,
  onToneChange,
  onAudienceChange,
  onSpeakerNamesChange,
  onDraftChange,
  onGenerate,
  onSaveScript,
  onAcceptGeneratedScript,
  onAcceptAndContinue,
  onContinue,
  onImportFile,
  onRestoreRevision,
}) => {
  const viewModel = useMemo(
    () =>
      deriveScriptViewModel({
        script,
        scriptDraft,
        scriptLines,
        generatedScript,
        isGenerating: busy === 'script-generate',
        scriptFailure,
        validationWarnings: generationWarnings,
        renderReadiness,
        targetDurationSeconds: scriptTargetDuration,
        generatedScriptHasHardWarnings,
      }),
    [
      busy,
      generatedScript,
      generatedScriptHasHardWarnings,
      generationWarnings,
      renderReadiness,
      script,
      scriptDraft,
      scriptFailure,
      scriptLines,
      scriptTargetDuration,
    ]
  );
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [timelineExpanded, setTimelineExpanded] = useState(false);
  const TIMELINE_COLLAPSED_COUNT = 5;

  const cacheSegmentMap = useMemo(() => {
    const warmth = (renderReadiness?.cache_warmth || {}) as any;
    const rawSegments: any[] = Array.isArray(warmth.tts_segments) ? warmth.tts_segments : [];
    const map = new Map<string, { status: 'cached' | 'regen' | 'check'; provider: string }>();
    for (const seg of rawSegments) {
      if (!seg.line_id) continue;
      let status: 'cached' | 'regen' | 'check' = 'check';
      if (seg.cached === true) status = 'cached';
      else if (seg.cached === false && seg.provider) status = 'regen';
      map.set(seg.line_id, { status, provider: seg.provider || '' });
    }
    return map;
  }, [renderReadiness]);
  const canUseGeneratedActions = viewModel.canAccept && busy !== 'script' && busy !== 'script-generate';
  const canProceed = viewModel.canProceed && busy !== 'script' && busy !== 'script-generate';
  const editorStatusChip =
    viewModel.state === 'failed'
      ? 'Parse error'
      : viewModel.state === 'empty'
        ? 'Empty'
        : viewModel.state === 'generating'
          ? `${viewModel.lineCount} lines`
          : `${compactDuration(viewModel.estimatedDurationSeconds)} / ${compactDuration(viewModel.targetDurationSeconds)}`;
  const editorTone =
    viewModel.state === 'failed'
      ? 'failed'
      : viewModel.state === 'empty'
        ? 'info'
        : viewModel.warnings.length
          ? 'warning'
          : 'ready';

  return (
    <div id="step-script" className={`production-script-section script-state-${viewModel.state}`} data-script-state={viewModel.state}>
      <section className="statebar script-review-statebar" aria-label="Script state">
        <span className="statebar-label">Script states</span>
        <div className="statebar-seg">
          {[
            ['empty', 'Empty'],
            ['generating', 'Generating'],
            ['generatedAccepted', 'Generated / accepted'],
            ['failed', 'Failed'],
          ].map(([state, label]) => (
            <span key={state} className="script-state-pill" aria-current={viewModel.state === state ? 'true' : undefined}>
              {label}
            </span>
          ))}
        </div>
      </section>

      <section className="panel script-hero">
        <div className="script-hero-copy">
          <span className="eyebrow">Step 02 / Script</span>
          <h1 className="hero-title">{viewModel.heroTitle}</h1>
          <p className="lede">{viewModel.heroDescription}</p>
          <div className="script-hero-actions">
            <button type="button" className="btn ghost" onClick={() => importInputRef.current?.click()} disabled={Boolean(busy)}>
              <FileUp size={15} />
              Import script
            </button>
            <button
              type="button"
              className={`btn ${viewModel.state === 'failed' ? 'fail' : 'primary'}`}
              onClick={onGenerate}
              disabled={busy === 'script-generate' || !scriptPrompt.trim() || !viewModel.canGenerate}
            >
              {viewModel.state === 'failed' ? <RefreshCw size={15} /> : <Sparkles size={15} />}
              {viewModel.state === 'failed' ? 'Retry generation' : generatedButtonLabel(viewModel)}
            </button>
            <input
              ref={importInputRef}
              className="sr-only"
              type="file"
              accept=".txt,.md,.json,text/plain,application/json"
              onChange={(event) => {
                const file = event.target.files?.[0];
                if (file) {
                  onImportFile(file);
                  event.target.value = '';
                }
              }}
            />
          </div>
        </div>
        <div className="script-hero-side">
          <span className={`chip ${toneChipClass(viewModel.statusTone)}`}>{viewModel.statusLabel}</span>
          <span className="chip is-brand plain">{projectName || 'Untitled production'}</span>
        </div>
      </section>

      <section className="panel cyanish tight script-status-strip" aria-live="polite">
        <div className="status-strip">
          <span className={`chip ${toneChipClass(viewModel.statusTone)}`}>{viewModel.statusLabel}</span>
          <span className={viewModel.lineCount ? 'chip is-ready' : 'chip is-info'}>{viewModel.lineCount} lines</span>
          <span className={viewModel.speakerCount ? 'chip is-ready' : 'chip plain'}>{viewModel.speakerCount} speakers</span>
          <span className={viewModel.captionReady ? 'chip is-info' : 'chip is-warning'}>
            {viewModel.captionReady ? 'Captions ready' : 'Captions pending'}
          </span>
          {viewModel.missingStableLineIds > 0 && (
            <span className="chip is-warning">{viewModel.missingStableLineIds} missing IDs</span>
          )}
          {viewModel.state !== 'generatedAccepted' && <span className="chip is-warning">Cast handoff locked</span>}
          {viewModel.state === 'generatedAccepted' && <span className="chip is-info">Cast handoff next</span>}
          <span className="script-status-action">
            {generatedScript && !viewModel.hasAcceptedRevision ? (
              <button type="button" className="btn primary sm" onClick={onAcceptAndContinue} disabled={!canUseGeneratedActions}>
                Accept & Continue
                <ArrowRight size={14} />
              </button>
            ) : (
              <button type="button" className="btn primary sm" onClick={onContinue} disabled={!canProceed}>
                Continue to Cast & Voices
                <ArrowRight size={14} />
              </button>
            )}
          </span>
        </div>
      </section>

      <section className="script-workspace">
        <section className="panel script-editor-panel">
          <div className="panel-h">
            <div>
              <h3>Script Editor</h3>
              <p>Source of truth for line IDs, caption timing and active-speaker overlays.</p>
            </div>
            <span className={`chip ${toneChipClass(editorTone)}`}>{editorStatusChip}</span>
          </div>
          <div className="script-top-controls">
            <label className="field">
              <span>Format</span>
              <select className="select" value={scriptFormatId} onChange={(event) => onFormatChange(event.target.value)}>
                {contentFormats.map((format) => (
                  <option key={format.id} value={format.id}>
                    {format.display_name}
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Duration</span>
              <select className="select" value={scriptTargetDuration} onChange={(event) => onDurationChange(Number(event.target.value))}>
                {[15, 30, 45, 60, 90].map((duration) => (
                  <option key={duration} value={duration}>
                    {duration} seconds
                  </option>
                ))}
              </select>
            </label>
            <label className="field">
              <span>Tone</span>
              <input className="input" value={scriptTone} onChange={(event) => onToneChange(event.target.value)} />
            </label>
            <label className="field">
              <span>Platform</span>
              <select className="select" value={scriptPlatform} onChange={(event) => onPlatformChange(event.target.value as PlatformTarget)}>
                {platformTargets.map((platform) => (
                  <option key={platform.id} value={platform.id}>
                    {platform.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          {viewModel.failureReason && (
            <div className="script-failure-panel" role="alert">
              <AlertTriangle size={16} />
              <div>
                <strong>{viewModel.failureReason}</strong>
                <span>Repair the draft, retry generation, or import a clean script before continuing.</span>
              </div>
            </div>
          )}

          <label className="field script-draft-field">
            <span>
              {viewModel.state === 'empty'
                ? 'Script draft'
                : viewModel.state === 'generating'
                  ? 'Streaming script draft'
                  : viewModel.state === 'failed'
                    ? 'Recoverable draft'
                    : 'Accepted script draft'}
            </span>
            {viewModel.state === 'empty' && !scriptDraft.trim() ? (
              <div className="script-empty-pad">
                <strong>No dialogue yet</strong>
                <p>Generate to produce speaker-separated, caption-ready lines with stable IDs.</p>
                <button type="button" className="btn primary" onClick={onGenerate} disabled={busy === 'script-generate' || !scriptPrompt.trim()}>
                  <Sparkles size={15} />
                  Generate with Ollama
                </button>
              </div>
            ) : (
              <textarea
                className="input mono script-draft-textarea"
                value={scriptDraft}
                onChange={(event) => onDraftChange(event.target.value)}
                rows={viewModel.state === 'generatedAccepted' ? 7 : 8}
              />
            )}
          </label>

          <div className="script-editor-footer">
            <div className="script-chip-row">
              <span className={viewModel.missingStableLineIds ? 'chip is-warning' : 'chip is-ready'}>
                {viewModel.missingStableLineIds ? `${viewModel.missingStableLineIds} missing IDs` : `${viewModel.lineCount} line IDs`}
              </span>
              <span className={viewModel.speakerCount ? 'chip is-ready' : 'chip plain'}>{viewModel.speakerCount} speakers</span>
              <span className={viewModel.captionReady ? 'chip is-info' : 'chip is-warning'}>
                {viewModel.captionReady ? 'Captions ready' : 'Captions queued'}
              </span>
              {scriptIsDirty && <span className="chip is-warning">Unsaved changes</span>}
            </div>
            <div className="script-editor-actions">
              <button type="button" className="btn ghost sm" onClick={onSaveScript} disabled={busy === 'script' || busy === 'script-generate'}>
                <Save size={14} />
                {busy === 'script' ? 'Saving...' : 'Save revision'}
              </button>
              {generatedScript && (
                <button type="button" className="btn primary sm" onClick={onAcceptGeneratedScript} disabled={!canUseGeneratedActions}>
                  <CheckCircle2 size={14} />
                  Accept script
                </button>
              )}
            </div>
          </div>
        </section>

        <section className="panel brandish script-timeline-panel">
          <div className="panel-h">
            <div>
              <h3>Dialogue Timeline</h3>
              <p>Canonical timeline for audio and captions. Fills height and scrolls internally for long scripts.</p>
            </div>
            <span className={`chip ${viewModel.state === 'failed' ? 'is-failed' : viewModel.state === 'generating' ? 'is-active' : viewModel.lineCount ? 'is-ready' : 'is-info'}`}>
              {viewModel.state === 'failed' ? 'Parse error' : viewModel.state === 'generating' ? 'Streaming' : viewModel.lineCount ? 'Parsed' : 'Empty'}
            </span>
          </div>

          {viewModel.timelineLines.length === 0 ? (
            <div className="script-empty-pad timeline-empty">
              <strong>Timeline is empty</strong>
              <p>Parsed lines appear here once a script exists.</p>
            </div>
          ) : (
            <div className="script-timeline-scroll">
              {(timelineExpanded
                ? viewModel.timelineLines
                : viewModel.timelineLines.slice(0, TIMELINE_COLLAPSED_COUNT)
              ).map((line) => {
                const cacheEntry = cacheSegmentMap.get(line.idLabel);
                const badgeStatus = cacheEntry
                  ? cacheEntry.status
                  : (line.status as string);
                const badgeLabel: Record<string, string> = {
                  cached: 'Cached', regen: 'Regen', check: 'Check',
                  ready: 'Ready', pending: 'Pending', warning: 'Warning', failed: 'Failed',
                };
                const provider = cacheEntry?.provider;
                return (
                  <article key={line.key} className={`script-line-row ${line.status}`}>
                    <span className={`script-line-badge is-${badgeStatus}`}>
                      {badgeLabel[badgeStatus] ?? badgeStatus}
                    </span>
                    <div className="script-line-body">
                      <div className="script-line-meta">
                        <span className="script-line-meta-id">{line.idLabel}</span>
                        <span>·</span>
                        <span>{line.section}</span>
                        <span>·</span>
                        <span>{line.speaker}</span>
                        {provider && (
                          <>
                            <span>·</span>
                            <span className="script-line-provider">{provider}</span>
                          </>
                        )}
                      </div>
                      <div className="script-line-text">{line.text}</div>
                    </div>
                    <button
                      type="button"
                      className="btn ghost sm script-line-edit"
                      onClick={() => {
                        const editor = document.querySelector<HTMLTextAreaElement>('.script-draft-textarea');
                        if (!editor) return;
                        const idx = scriptDraft.indexOf(`[${line.idLabel}`);
                        editor.focus();
                        if (idx >= 0) {
                          editor.setSelectionRange(idx, idx);
                          const linesBefore = scriptDraft.slice(0, idx).split('\n').length - 1;
                          const lineHeight = parseFloat(getComputedStyle(editor).lineHeight) || 18;
                          editor.scrollTop = linesBefore * lineHeight;
                        }
                      }}
                      disabled={line.status === 'pending'}
                    >
                      <PencilLine size={13} />
                      Edit
                    </button>
                  </article>
                );
              })}
              {viewModel.timelineLines.length > TIMELINE_COLLAPSED_COUNT && (
                <button
                  type="button"
                  className="script-timeline-expand-btn"
                  onClick={() => setTimelineExpanded((v) => !v)}
                >
                  {timelineExpanded
                    ? 'Show fewer'
                    : `Show all ${viewModel.timelineLines.length} lines`}
                </button>
              )}
            </div>
          )}
        </section>
      </section>

      <ScriptControlsAccordion
        viewModel={viewModel}
        contentFormats={contentFormats}
        platformTargets={platformTargets}
        selectedFormat={selectedFormat}
        scriptFormatId={scriptFormatId}
        scriptPlatform={scriptPlatform}
        scriptTargetDuration={scriptTargetDuration}
        scriptTone={scriptTone}
        scriptAudience={scriptAudience}
        scriptSpeakerNames={scriptSpeakerNames}
        scriptPrompt={scriptPrompt}
        providerMetadata={providerMetadata}
        providerLabel={providerLabel}
        warnings={generationWarnings}
        renderReadiness={renderReadiness}
        revisions={scriptRevisions}
        busy={busy}
        onPromptChange={onPromptChange}
        onFormatChange={onFormatChange}
        onPlatformChange={onPlatformChange}
        onDurationChange={onDurationChange}
        onToneChange={onToneChange}
        onAudienceChange={onAudienceChange}
        onSpeakerNamesChange={onSpeakerNamesChange}
        onGenerate={onGenerate}
        onImportFile={onImportFile}
        onSaveScript={onSaveScript}
        onRestoreRevision={onRestoreRevision}
      />
    </div>
  );
};

export default ProductionScriptSection;
