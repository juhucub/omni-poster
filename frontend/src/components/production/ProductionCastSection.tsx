import React, { useMemo, useState } from 'react';
import {
  AlertTriangle,
  ArrowRight,
  CheckCircle2,
  CircleDashed,
  Mic2,
  RefreshCw,
  ShieldCheck,
  User,
  Volume2,
  XCircle,
} from 'lucide-react';

import type {
  CharacterPreset,
  GenerationJob,
  RenderReadinessEstimate,
  ScriptLine,
  SpeakerBinding,
} from '../../api/models';

// ── Types ──────────────────────────────────────────────────────────────────

export type CastViewState = 'missing' | 'warning' | 'verified' | 'failed';

const CLONE_PROVIDERS = new Set(['openvoice', 'xtts', 'rvc', 'openvoice2']);

interface CastSpeakerViewModel {
  name: string;
  state: CastViewState;
  binding: SpeakerBinding | null;
  preset: CharacterPreset | null;
  lineCount: number;
  isCloneProvider: boolean;
}

interface CacheSegmentViewModel {
  line_id: string;
  speaker: string;
  text_preview: string;
  status: 'hit' | 'regen' | 'check' | 'invalid';
  provider: string;
}

export interface CastViewModel {
  overallState: CastViewState;
  speakers: CastSpeakerViewModel[];
  assignedCount: number;
  totalCount: number;
  cacheSegments: CacheSegmentViewModel[];
  cacheHits: number;
  cacheMisses: number;
  cacheTotal: number;
  cachePercent: number;
  cloneMisses: number;
  allAssigned: boolean;
  canContinue: boolean;
}

export interface DerivecastViewModelInput {
  detectedSpeakers: string[];
  speakerBindings: SpeakerBinding[];
  characterPresets: CharacterPreset[];
  renderReadiness: RenderReadinessEstimate | null;
  scriptLines: ScriptLine[];
}

export function deriveCastViewModel({
  detectedSpeakers,
  speakerBindings,
  characterPresets,
  renderReadiness,
  scriptLines,
}: DerivecastViewModelInput): CastViewModel {
  const warmth = (renderReadiness?.cache_warmth || {}) as any;
  const rawSegments: any[] = Array.isArray(warmth.tts_segments) ? warmth.tts_segments : [];

  const lineCounts: Record<string, number> = {};
  for (const line of scriptLines) {
    if (line.speaker) {
      lineCounts[line.speaker] = (lineCounts[line.speaker] || 0) + 1;
    }
  }

  const speakers: CastSpeakerViewModel[] = detectedSpeakers.map((name) => {
    const binding = speakerBindings.find((b) => b.speaker_name === name) || null;
    const preset = binding ? characterPresets.find((p) => p.id === binding.character_preset_id) || null : null;
    const isCloneProvider = Boolean(binding?.provider && CLONE_PROVIDERS.has(binding.provider));

    let state: CastViewState = 'missing';
    if (binding) {
      state = isCloneProvider && !binding.voice_profile_id ? 'warning' : 'verified';
    }

    return {
      name,
      state,
      binding,
      preset,
      lineCount: lineCounts[name] || 0,
      isCloneProvider,
    };
  });

  const assignedCount = speakers.filter((s) => s.state !== 'missing').length;
  const totalCount = speakers.length;
  const allAssigned = totalCount > 0 && assignedCount === totalCount;

  const cacheSegments: CacheSegmentViewModel[] = rawSegments.map((seg: any) => {
    let status: CacheSegmentViewModel['status'] = 'check';
    if (seg.cached === true) status = 'hit';
    else if (seg.cached === false && seg.provider) status = 'regen';
    else if (seg.cached === null || seg.cached === undefined) status = 'check';
    if (!seg.line_id) status = 'invalid';
    return {
      line_id: seg.line_id || '—',
      speaker: seg.speaker || '—',
      text_preview: seg.text_preview || '',
      status,
      provider: seg.provider || '—',
    };
  });

  const hits = Number(warmth.tts_segment_hits || 0);
  const misses = Number(warmth.tts_segment_misses || 0);
  const cacheTotal = hits + misses;
  const cachePercent = cacheTotal ? Math.round((hits / cacheTotal) * 100) : 0;
  const cloneMisses = Number(warmth.clone_provider_misses || 0);

  let overallState: CastViewState = 'missing';
  if (speakers.some((s) => s.state === 'failed')) {
    overallState = 'failed';
  } else if (!allAssigned && totalCount > 0) {
    overallState = 'missing';
  } else if (speakers.some((s) => s.state === 'warning') || (cacheTotal > 0 && misses > 0)) {
    overallState = 'warning';
  } else if (allAssigned) {
    overallState = 'verified';
  }

  const canContinue = allAssigned;

  return {
    overallState,
    speakers,
    assignedCount,
    totalCount,
    cacheSegments,
    cacheHits: hits,
    cacheMisses: misses,
    cacheTotal,
    cachePercent,
    cloneMisses,
    allAssigned,
    canContinue,
  };
}

// ── Sub-components ─────────────────────────────────────────────────────────

const stateIcon = (state: CastViewState, className = 'h-4 w-4') => {
  if (state === 'verified') return <CheckCircle2 className={`${className} text-emerald-400`} />;
  if (state === 'warning') return <AlertTriangle className={`${className} text-amber-400`} />;
  if (state === 'failed') return <XCircle className={`${className} text-rose-400`} />;
  return <CircleDashed className={`${className} text-slate-500`} />;
};

const stateLabelClass: Record<CastViewState, string> = {
  verified: 'text-emerald-400',
  warning: 'text-amber-400',
  failed: 'text-rose-400',
  missing: 'text-slate-500',
};

const stateLabel: Record<CastViewState, string> = {
  verified: 'Verified',
  warning: 'Warning',
  failed: 'Failed',
  missing: 'Missing',
};

const cacheStatusConfig: Record<CacheSegmentViewModel['status'], { label: string; className: string }> = {
  hit: { label: 'Cached', className: 'bg-emerald-400/15 text-emerald-300 border border-emerald-400/20' },
  regen: { label: 'Will regen', className: 'bg-amber-400/15 text-amber-300 border border-amber-400/20' },
  check: { label: 'Check', className: 'bg-slate-700/60 text-slate-400 border border-white/10' },
  invalid: { label: 'Invalid', className: 'bg-rose-400/15 text-rose-400 border border-rose-400/20' },
};

// ── CastStateStrip ─────────────────────────────────────────────────────────

const CastStateStrip: React.FC<{ vm: CastViewModel }> = ({ vm }) => {
  const stripBg: Record<CastViewState, string> = {
    verified: 'border-emerald-300/20 bg-emerald-400/[0.07]',
    warning: 'border-amber-300/20 bg-amber-400/[0.07]',
    failed: 'border-rose-300/20 bg-rose-400/[0.07]',
    missing: 'border-white/10 bg-white/[0.03]',
  };

  return (
    <div className={`flex flex-wrap items-center gap-3 rounded-2xl border px-4 py-3 text-sm ${stripBg[vm.overallState]}`}>
      <div className="flex items-center gap-1.5">
        {stateIcon(vm.overallState)}
        <span className={`font-medium ${stateLabelClass[vm.overallState]}`}>{stateLabel[vm.overallState]}</span>
      </div>
      <span className="text-slate-500">·</span>
      <span className="text-slate-400">
        {vm.assignedCount} / {vm.totalCount} speakers assigned
      </span>
      {vm.cacheTotal > 0 && (
        <>
          <span className="text-slate-500">·</span>
          <span className="text-slate-400">
            {vm.cachePercent}% voice cache warm ({vm.cacheHits} hit, {vm.cacheMisses} regen)
          </span>
        </>
      )}
      {vm.cloneMisses > 0 && (
        <>
          <span className="text-slate-500">·</span>
          <span className="text-amber-400">{vm.cloneMisses} clone-provider miss(es)</span>
        </>
      )}
    </div>
  );
};

// ── CastAssignmentsPanel ───────────────────────────────────────────────────

const CastAssignmentsPanel: React.FC<{
  vm: CastViewModel;
  characterPresets: CharacterPreset[];
  busy: string | null;
  projectId: number;
  onUpdateBinding: (speakerName: string, presetId: string) => void;
  toApiHref: (path: string | null | undefined) => string;
}> = ({ vm, characterPresets, busy, projectId, onUpdateBinding, toApiHref }) => (
  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
    <div className="flex items-center gap-2 pb-4">
      <User className="h-4 w-4 text-slate-400" />
      <h3 className="text-sm font-semibold text-slate-100">Cast Assignments</h3>
      <span className="ml-auto rounded-lg bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
        {vm.assignedCount}/{vm.totalCount}
      </span>
    </div>

    {vm.speakers.length === 0 ? (
      <div className="flex flex-col items-center gap-2 py-8 text-center">
        <Mic2 className="h-8 w-8 text-slate-600" />
        <p className="text-sm text-slate-500">
          Add named dialogue lines in the Script stage so OmniPoster can bind each speaker to a character.
        </p>
      </div>
    ) : (
      <div className="space-y-3">
        {vm.speakers.map((speaker) => (
          <div
            key={speaker.name}
            className={`rounded-xl border p-4 transition-colors ${
              speaker.state === 'verified'
                ? 'border-emerald-300/20 bg-emerald-400/[0.04]'
                : speaker.state === 'warning'
                  ? 'border-amber-300/20 bg-amber-400/[0.04]'
                  : 'border-white/10 bg-black/20'
            }`}
          >
            {/* Speaker header row */}
            <div className="flex items-start gap-3">
              {/* Portrait or avatar */}
              <div className="relative shrink-0">
                <div className="h-12 w-10 overflow-hidden rounded-lg border border-white/10 bg-black/30">
                  {speaker.preset?.portrait_url ? (
                    <img
                      src={toApiHref(speaker.preset.portrait_url)}
                      alt={speaker.preset.display_name}
                      className="h-full w-full object-cover"
                    />
                  ) : (
                    <div className="flex h-full w-full items-center justify-center text-[11px] font-medium text-slate-600">
                      {speaker.name.slice(0, 2).toUpperCase()}
                    </div>
                  )}
                </div>
                <div className={`absolute -bottom-1 -right-1 rounded-full border border-[var(--bg-0)] p-0.5 ${speaker.state === 'verified' ? 'bg-emerald-500' : speaker.state === 'warning' ? 'bg-amber-500' : 'bg-slate-700'}`}>
                  {stateIcon(speaker.state, 'h-2.5 w-2.5 text-white')}
                </div>
              </div>

              <div className="min-w-0 flex-1">
                <div className="flex items-baseline justify-between gap-2">
                  <span className="truncate text-sm font-semibold text-slate-100">{speaker.name}</span>
                  <span className="shrink-0 text-xs text-slate-500">{speaker.lineCount} line{speaker.lineCount !== 1 ? 's' : ''}</span>
                </div>
                {speaker.binding ? (
                  <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-xs text-slate-400">
                    <Volume2 className="h-3 w-3" />
                    <span>{speaker.binding.character_display_name}</span>
                    <span className="rounded bg-slate-800 px-1.5 py-0.5 font-mono text-[10px] text-slate-500">
                      {speaker.binding.provider}
                    </span>
                    {speaker.isCloneProvider && (
                      <span className="rounded bg-violet-400/10 px-1.5 py-0.5 text-[10px] text-violet-300 border border-violet-400/20">
                        clone
                      </span>
                    )}
                  </div>
                ) : (
                  <div className="mt-0.5 text-xs text-slate-500">No preset selected</div>
                )}
              </div>
            </div>

            {/* Voice profile dropdown */}
            <div className="mt-3">
              <label className="mb-1 block text-xs text-slate-500">Voice profile</label>
              <select
                value={speaker.binding?.character_preset_id || ''}
                disabled={Boolean(busy === `binding-${speaker.name}`)}
                onChange={(e) => {
                  if (e.target.value) onUpdateBinding(speaker.name, e.target.value);
                }}
                className="w-full appearance-none rounded-lg border border-white/10 bg-slate-900/80 px-3 py-2 text-sm text-slate-200 focus:border-cyan-400/40 focus:outline-none focus:ring-1 focus:ring-cyan-400/20 disabled:cursor-not-allowed disabled:opacity-50"
              >
                <option value="">Select a character preset…</option>
                {characterPresets.map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.display_name} · {preset.tts_provider}
                  </option>
                ))}
              </select>
            </div>

          </div>
        ))}
      </div>
    )}
  </div>
);

// ── VoicePreflightPanel ────────────────────────────────────────────────────

const VoicePreflightPanel: React.FC<{
  vm: CastViewModel;
  isRefreshing: boolean;
  onRunPreflight: () => void;
}> = ({ vm, isRefreshing, onRunPreflight }) => {
  const preflightState: CastViewState =
    vm.cacheTotal === 0 ? 'missing' : vm.cacheMisses > 0 ? 'warning' : 'verified';

  const preflightBg: Record<CastViewState, string> = {
    verified: 'border-emerald-300/20 bg-emerald-400/[0.06]',
    warning: 'border-amber-300/20 bg-amber-400/[0.06]',
    failed: 'border-rose-300/20 bg-rose-400/[0.06]',
    missing: 'border-white/10 bg-white/[0.03]',
  };

  return (
    <div className={`rounded-2xl border p-5 ${preflightBg[preflightState]}`}>
      <div className="flex items-center gap-2">
        <ShieldCheck className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-semibold text-slate-100">Voice Preflight</h3>
        <span className={`ml-auto text-xs font-medium ${stateLabelClass[preflightState]}`}>
          {stateLabel[preflightState]}
        </span>
      </div>

      <p className="mt-2 text-xs text-slate-500">
        Checks TTS cache for all assigned speakers against current script lines. Run after any voice or script changes.
      </p>

      <div className="mt-3 grid grid-cols-3 gap-3">
        {[
          { label: 'Cached', value: vm.cacheHits, tone: 'text-emerald-400' },
          { label: 'Will regen', value: vm.cacheMisses, tone: vm.cacheMisses > 0 ? 'text-amber-400' : 'text-slate-500' },
          { label: 'Cache warmth', value: `${vm.cachePercent}%`, tone: vm.cachePercent >= 80 ? 'text-emerald-400' : vm.cachePercent > 0 ? 'text-amber-400' : 'text-slate-500' },
        ].map((metric) => (
          <div key={metric.label} className="rounded-xl border border-white/10 bg-black/20 px-3 py-3 text-center">
            <div className={`text-lg font-bold tabular-nums ${metric.tone}`}>{metric.value}</div>
            <div className="mt-0.5 text-[11px] text-slate-500">{metric.label}</div>
          </div>
        ))}
      </div>

      <button
        type="button"
        onClick={onRunPreflight}
        disabled={isRefreshing}
        className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-white/10 bg-slate-800/60 px-4 py-2.5 text-sm text-slate-200 transition hover:bg-slate-700/60 disabled:cursor-not-allowed disabled:opacity-50"
      >
        <RefreshCw className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
        {isRefreshing ? 'Checking…' : 'Run Preflight'}
      </button>
    </div>
  );
};

// ── VoiceSegmentCachePanel ─────────────────────────────────────────────────

const VoiceSegmentCachePanel: React.FC<{ vm: CastViewModel }> = ({ vm }) => {
  const [expanded, setExpanded] = useState(false);
  const shown = expanded ? vm.cacheSegments : vm.cacheSegments.slice(0, 5);

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
      <div className="flex items-center gap-2">
        <Volume2 className="h-4 w-4 text-slate-400" />
        <h3 className="text-sm font-semibold text-slate-100">Voice Segment Cache</h3>
        <span className="ml-auto rounded-lg bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
          {vm.cacheSegments.length} segment{vm.cacheSegments.length !== 1 ? 's' : ''}
        </span>
      </div>

      {vm.cacheSegments.length === 0 ? (
        <div className="mt-4 rounded-xl border border-dashed border-white/10 px-4 py-6 text-center">
          <p className="text-sm text-slate-500">
            No TTS cache data yet. Run preflight or queue a render to populate segment cache keys.
          </p>
        </div>
      ) : (
        <>
          <div className="mt-3 space-y-2">
            {shown.map((seg, i) => {
              const cfg = cacheStatusConfig[seg.status];
              return (
                <div key={`${seg.line_id}-${i}`} className="flex items-center gap-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2">
                  <span className={`shrink-0 rounded-md px-2 py-0.5 text-[11px] font-medium ${cfg.className}`}>
                    {cfg.label}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5 text-[11px] text-slate-500">
                      <span className="font-mono">{seg.line_id}</span>
                      <span>·</span>
                      <span>{seg.speaker}</span>
                      <span>·</span>
                      <span className="rounded bg-slate-800 px-1 font-mono text-[10px]">{seg.provider}</span>
                    </div>
                    {seg.text_preview && (
                      <div className="mt-0.5 truncate text-xs text-slate-400">{seg.text_preview}</div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>

          {vm.cacheSegments.length > 5 && (
            <button
              type="button"
              onClick={() => setExpanded((v) => !v)}
              className="script-timeline-expand-btn"
            >
              {expanded ? 'Show fewer' : `Show all ${vm.cacheSegments.length} segments`}
            </button>
          )}
        </>
      )}
    </div>
  );
};

// ── ProfileLibraryPanel ────────────────────────────────────────────────────

const ProfileLibraryPanel: React.FC<{
  characterPresets: CharacterPreset[];
  toApiHref: (path: string | null | undefined) => string;
}> = ({ characterPresets, toApiHref }) => (
  <div className="rounded-2xl border border-white/10 bg-white/[0.03] p-5">
    <div className="flex items-center gap-2 pb-4">
      <User className="h-4 w-4 text-slate-400" />
      <h3 className="text-sm font-semibold text-slate-100">Profile Library</h3>
      <span className="ml-auto rounded-lg bg-slate-800 px-2 py-0.5 text-xs text-slate-400">
        {characterPresets.length} preset{characterPresets.length !== 1 ? 's' : ''}
      </span>
    </div>

    {characterPresets.length === 0 ? (
      <div className="rounded-xl border border-dashed border-white/10 px-4 py-6 text-center">
        <p className="text-sm text-slate-500">No character presets available. Create presets in the Voice Lab first.</p>
      </div>
    ) : (
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
        {characterPresets.map((preset) => (
          <div
            key={preset.id}
            className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-black/20 p-2.5"
          >
            <div className="h-10 w-8 shrink-0 overflow-hidden rounded-lg border border-white/10 bg-black/30">
              {preset.portrait_url ? (
                <img
                  src={toApiHref(preset.portrait_url)}
                  alt={preset.display_name}
                  className="h-full w-full object-cover"
                />
              ) : (
                <div className="flex h-full w-full items-center justify-center text-[10px] font-medium text-slate-600">
                  {preset.display_name.slice(0, 2).toUpperCase()}
                </div>
              )}
            </div>
            <div className="min-w-0">
              <div className="truncate text-xs font-medium text-slate-200">{preset.display_name}</div>
              <div className="mt-0.5 truncate text-[11px] text-slate-500">{preset.tts_provider}</div>
            </div>
          </div>
        ))}
      </div>
    )}
  </div>
);

// ── CastRuleCards ──────────────────────────────────────────────────────────

const CAST_RULES = [
  {
    icon: <User className="h-4 w-4 text-cyan-400" />,
    title: 'One preset per speaker',
    desc: 'Each script speaker must map to exactly one character preset before rendering.',
  },
  {
    icon: <Volume2 className="h-4 w-4 text-cyan-400" />,
    title: 'Voice consistency',
    desc: 'All lines for the same speaker use the bound voice profile — changes apply globally.',
  },
  {
    icon: <ShieldCheck className="h-4 w-4 text-cyan-400" />,
    title: 'Cache warmth saves time',
    desc: 'Warm TTS cache means render skips voice synthesis — draft renders in under 60 s.',
  },
];

const CastRuleCards: React.FC = () => (
  <div className="grid gap-3 sm:grid-cols-3">
    {CAST_RULES.map((rule) => (
      <div
        key={rule.title}
        className="flex gap-3 rounded-xl border border-white/10 bg-white/[0.02] p-4"
      >
        <div className="mt-0.5 shrink-0">{rule.icon}</div>
        <div>
          <div className="text-xs font-semibold text-slate-200">{rule.title}</div>
          <div className="mt-1 text-[11px] leading-relaxed text-slate-500">{rule.desc}</div>
        </div>
      </div>
    ))}
  </div>
);

// ── ProductionCastSection (root) ───────────────────────────────────────────

export interface ProductionCastSectionProps {
  detectedSpeakers: string[];
  scriptLines: ScriptLine[];
  speakerBindings: SpeakerBinding[];
  characterPresets: CharacterPreset[];
  renderReadiness: RenderReadinessEstimate | null;
  generationJob: GenerationJob | null;
  busy: string | null;
  onUpdateBinding: (speakerName: string, presetId: string) => void;
  onRunPreflight: () => void;
  onContinue: () => void;
  projectId: number;
  toApiHref: (path: string | null | undefined) => string;
}

const ProductionCastSection: React.FC<ProductionCastSectionProps> = ({
  detectedSpeakers,
  scriptLines,
  speakerBindings,
  characterPresets,
  renderReadiness,
  generationJob: _generationJob,
  busy,
  onUpdateBinding,
  onRunPreflight,
  onContinue,
  projectId,
  toApiHref,
}) => {
  const [isRefreshing, setIsRefreshing] = useState(false);

  const vm = useMemo(
    () =>
      deriveCastViewModel({
        detectedSpeakers,
        speakerBindings,
        characterPresets,
        renderReadiness,
        scriptLines,
      }),
    [detectedSpeakers, speakerBindings, characterPresets, renderReadiness, scriptLines]
  );

  const handlePreflight = async () => {
    setIsRefreshing(true);
    try {
      await onRunPreflight();
    } finally {
      setIsRefreshing(false);
    }
  };

  return (
    <div id="step-cast" className="cast-section space-y-5">
      {/* Hero */}
      <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-semibold text-slate-100">Cast &amp; Voices</h2>
            <p className="mt-1.5 max-w-2xl text-sm text-slate-400">
              Assign each script speaker to a reusable character preset before rendering. OmniPoster uses these
              bindings to keep voices, captions, and character images consistent across all output formats.
            </p>
          </div>
          <div className="shrink-0">
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                vm.overallState === 'verified'
                  ? 'bg-emerald-400/15 text-emerald-300 border border-emerald-400/20'
                  : vm.overallState === 'warning'
                    ? 'bg-amber-400/15 text-amber-300 border border-amber-400/20'
                    : vm.overallState === 'failed'
                      ? 'bg-rose-400/15 text-rose-400 border border-rose-400/20'
                      : 'bg-white/5 text-slate-400 border border-white/10'
              }`}
            >
              {stateIcon(vm.overallState, 'h-3 w-3')}
              {stateLabel[vm.overallState]}
            </span>
          </div>
        </div>

        {/* State strip */}
        <div className="mt-4">
          <CastStateStrip vm={vm} />
        </div>
      </div>

      {/* Main panels grid */}
      <div className="cast-panels-grid">
        {/* Left column: rule cards + assignments + library */}
        <div className="space-y-4">
          <CastRuleCards />
          <CastAssignmentsPanel
            vm={vm}
            characterPresets={characterPresets}
            busy={busy}
            projectId={projectId}
            onUpdateBinding={onUpdateBinding}
            toApiHref={toApiHref}
          />
          <ProfileLibraryPanel characterPresets={characterPresets} toApiHref={toApiHref} />
        </div>

        {/* Right column: preflight + cache */}
        <div className="space-y-4">
          <VoicePreflightPanel vm={vm} isRefreshing={isRefreshing} onRunPreflight={handlePreflight} />
          <VoiceSegmentCachePanel vm={vm} />
        </div>
      </div>

      {/* Accept Cast & Continue CTA */}
      <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
        <div className="flex flex-col items-start gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-sm font-semibold text-slate-100">Accept Cast &amp; Continue</div>
            <div className="mt-1 text-sm text-slate-400">
              {vm.canContinue
                ? `All ${vm.totalCount} speaker${vm.totalCount !== 1 ? 's' : ''} have assigned voice profiles. Continue to Scene &amp; Preview.`
                : `Assign a voice preset to all ${vm.totalCount} detected speaker${vm.totalCount !== 1 ? 's' : ''} before continuing.`}
            </div>
          </div>
          <button
            type="button"
            onClick={onContinue}
            disabled={!vm.canContinue || Boolean(busy)}
            className="inline-flex shrink-0 items-center gap-2 rounded-xl bg-cyan-500 px-5 py-2.5 text-sm font-semibold text-slate-950 shadow-lg transition hover:bg-cyan-400 active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:active:scale-100"
          >
            Continue to Preview
            <ArrowRight className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  );
};

export default ProductionCastSection;
