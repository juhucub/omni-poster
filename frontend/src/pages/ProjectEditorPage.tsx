import React, { useEffect, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import {
  CheckCircle2,
  CircleDashed,
  MessageSquarePlus,
  PlayCircle,
  RefreshCw,
  Sparkles,
  Upload,
  Wand2,
} from 'lucide-react';

import apiClient, { apiBaseUrl } from '../api/client';
import type {
  Asset,
  BackgroundPreset,
  CharacterPreset,
  ContentFormatPreset,
  GenerationJob,
  GeneratedScript,
  OutputVideo,
  PlatformTarget,
  PlatformMetadata,
  Project,
  RenderReadinessEstimate,
  ProjectScriptGenerationSettings,
  PublishJob,
  PublishedPost,
  ReviewQueueItem,
  RoutingSuggestion,
  SpeakerBinding,
  ScriptLine,
  ScriptRevision,
  SocialAccount,
  ProjectPreviewSettings,
  ScriptGenerationProviderMetadata,
  ScriptGenerationResponse,
} from '../api/models';
import StudioShell from '../components/studio/StudioShell';
import RenderDiagnosticsPanel from '../components/RenderDiagnosticsPanel';
import FormatBrowser from '../components/script-generation/FormatBrowser';
import ProductionReadinessPanel, {
  computeProductionReadiness,
} from '../components/production/ProductionReadinessPanel';
import ProductionPreviewFrame from '../components/production/ProductionPreviewFrame';
import {
  FALLBACK_CONTENT_FORMATS,
  durationLabel,
  findFormat,
  speakerCountLabel,
} from '../components/script-generation/formatBrowserData';

const STAGES = ['Idea', 'Script', 'Cast & Voices', 'Scene', 'Preview', 'Render', 'Release'] as const;
type Stage = (typeof STAGES)[number];

const defaultScript = '<Host> Welcome to Omni-poster.\n<Guest> We can keep revising this conversation before it ships.';

const platformTargets: Array<{ id: PlatformTarget; label: string }> = [
  { id: 'tiktok', label: 'TikTok' },
  { id: 'youtube_shorts', label: 'YouTube Shorts' },
  { id: 'instagram_reels', label: 'Instagram Reels' },
];

const formatMidpoint = (format: ContentFormatPreset) =>
  Math.round((format.ideal_duration_range_sec[0] + format.ideal_duration_range_sec[1]) / 2);

const speakerNamesForFormat = (format: ContentFormatPreset) => format.default_speaker_roles.join(', ');

const titleCase = (value: string | null | undefined) =>
  String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());

const parseDraftToLines = (value: string): ScriptLine[] =>
  value
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line, index) => {
      const match = line.match(/^<([^>]+)>\s*(.+)$/);
      return {
        id: undefined,
        speaker: match?.[1]?.trim() || `Speaker ${index + 1}`,
        text: match?.[2]?.trim() || line,
        order: index,
      };
    });

const linesToDraft = (lines: ScriptLine[]) =>
  lines.map((line) => `<${line.speaker}> ${line.text}`).join('\n');

const normalizeDraft = (value: string) => value.trim().replace(/\r\n/g, '\n');
const hardScriptWarnings = ['Hard quality failure', 'has no spoken lines', 'references missing speaker', 'has no caption text', 'Speaker count'];

const defaultPreviewSettings: ProjectPreviewSettings = {
  background_asset_id: null,
  background_preset_id: null,
  background_source_type: null,
  background_url: null,
  background_metadata: {},
  speaker_mappings: [],
  layout: {
    character_scale: 1,
    chat_font_size_px: 18,
  },
  layout_preset: 'left_right_locked',
  caption_style: 'bold_bubble',
  speaker_png_size: 'standard',
  render_preset: 'shorts_1080x1920',
};

const clampPreviewLayout = (settings: ProjectPreviewSettings): ProjectPreviewSettings => ({
  ...defaultPreviewSettings,
  ...settings,
  background_metadata: settings.background_metadata || {},
  speaker_mappings: settings.speaker_mappings || [],
  layout_preset: settings.layout_preset || defaultPreviewSettings.layout_preset,
  caption_style: settings.caption_style || defaultPreviewSettings.caption_style,
  speaker_png_size: settings.speaker_png_size || defaultPreviewSettings.speaker_png_size,
  render_preset: settings.render_preset || defaultPreviewSettings.render_preset,
  layout: {
    // Match backend renderer bounds so saved controls cannot create an impossible preview state.
    character_scale: Math.min(Math.max(Number(settings.layout?.character_scale || 1), 0.75), 1.5),
    chat_font_size_px: Math.min(Math.max(Number(settings.layout?.chat_font_size_px || 18), 12), 32),
  },
});

const generationStageLabel = (job: GenerationJob | null) => {
  if (!job) {
    return null;
  }
  if (job.status === 'queued') {
    return 'Queued';
  }
  if (job.status === 'completed') {
    return 'Completed';
  }
  if (job.status === 'failed') {
    return 'Failed';
  }
  if (job.progress >= 88) {
    return 'Packaging output';
  }
  if (job.progress >= 80) {
    return 'Encoding video';
  }
  if (job.progress >= 68) {
    return 'Assembling timeline';
  }
  if (job.progress >= 58) {
    return 'Preparing background';
  }
  if (job.progress >= 46) {
    return 'Generating voices';
  }
  return 'Starting render';
};

type ProductionStageState = 'Missing' | 'Ready' | 'Warning' | 'Failed' | 'Verified';

type RenderChangeItem = {
  label: string;
  state: ProductionStageState;
  detail: string;
  cacheKeys?: string[];
};

const stateBadgeClass = (state: ProductionStageState) => {
  if (state === 'Verified' || state === 'Ready') return 'op-badge-success';
  if (state === 'Failed') return 'op-badge-error';
  if (state === 'Warning') return 'op-badge-warning';
  return 'op-badge-muted';
};

const stableJson = (value: unknown) => JSON.stringify(value ?? null);

const changedSpeakerVoices = (
  current: ProjectPreviewSettings,
  previous?: ProjectPreviewSettings | null
) => {
  if (!previous) return [];
  const previousBySpeaker = new Map((previous.speaker_mappings || []).map((mapping) => [mapping.speaker_name, mapping]));
  return (current.speaker_mappings || []).filter((mapping) => {
    const prior = previousBySpeaker.get(mapping.speaker_name);
    return prior && prior.voice_profile_id !== mapping.voice_profile_id;
  });
};

const buildRenderChangeSummary = ({
  scriptIsDirty,
  generationJob,
  previewSettings,
  renderReadiness,
}: {
  scriptIsDirty: boolean;
  generationJob: GenerationJob | null;
  previewSettings: ProjectPreviewSettings;
  renderReadiness: RenderReadinessEstimate | null;
}): RenderChangeItem[] => {
  const warmth = (renderReadiness?.cache_warmth || {}) as any;
  const ttsSegments = Array.isArray(warmth.tts_segments) ? warmth.tts_segments : [];
  const missedSegments = ttsSegments.filter((segment: any) => !segment.cached);
  const missedKeys = missedSegments.map((segment: any) => String(segment.cache_key_prefix || '')).filter(Boolean).slice(0, 6);
  const previousPreview = generationJob?.preview_settings || null;
  const voiceChanges = changedSpeakerVoices(previewSettings, previousPreview);
  const backgroundChanged = Boolean(
    previousPreview &&
      (
        previousPreview.background_asset_id !== previewSettings.background_asset_id ||
        previousPreview.background_preset_id !== previewSettings.background_preset_id ||
        previousPreview.background_source_type !== previewSettings.background_source_type ||
        previousPreview.background_url !== previewSettings.background_url
      )
  );
  const layoutChanged = Boolean(
    previousPreview &&
      (
        stableJson(previousPreview.layout) !== stableJson(previewSettings.layout) ||
        previousPreview.layout_preset !== previewSettings.layout_preset ||
        previousPreview.caption_style !== previewSettings.caption_style ||
        previousPreview.speaker_png_size !== previewSettings.speaker_png_size ||
        previousPreview.render_preset !== previewSettings.render_preset
      )
  );

  return [
    {
      label: 'Script lines',
      state: scriptIsDirty || missedSegments.length ? 'Warning' : ttsSegments.length ? 'Verified' : 'Missing',
      detail: scriptIsDirty
        ? 'Unsaved dialogue will be saved first; voice cache keys may change.'
        : missedSegments.length
          ? `${missedSegments.length} line(s) need fresh voice WAVs.`
          : ttsSegments.length
            ? 'All current voice segment cache keys are warm.'
            : 'No script segment cache keys available yet.',
      cacheKeys: missedKeys,
    },
    {
      label: 'Voice profiles',
      state: voiceChanges.length ? 'Warning' : previousPreview ? 'Verified' : 'Missing',
      detail: voiceChanges.length
        ? `${voiceChanges.map((mapping) => mapping.speaker_name).slice(0, 3).join(', ')} changed voice profile assignment.`
        : previousPreview
          ? 'Voice profile assignments match the latest render snapshot.'
          : 'No previous render snapshot to compare voice assignments.',
    },
    {
      label: 'Background',
      state: backgroundChanged ? 'Warning' : previousPreview ? 'Verified' : 'Missing',
      detail: backgroundChanged
        ? 'Selected background changed; background normalization cache may invalidate.'
        : previousPreview
          ? 'Background selection matches the latest render snapshot.'
          : 'No previous render snapshot to compare background selection.',
      cacheKeys: backgroundChanged ? ['background layer'] : [],
    },
    {
      label: 'Layout and overlays',
      state: layoutChanged ? 'Warning' : previousPreview ? 'Verified' : 'Missing',
      detail: layoutChanged
        ? 'Layout, caption, speaker PNG size, or render preset changed; overlay/final MP4 cache may invalidate.'
        : previousPreview
          ? 'Layout and overlay settings match the latest render snapshot.'
          : 'No previous render snapshot to compare layout settings.',
      cacheKeys: layoutChanged ? ['overlay layer', 'final mp4'] : [],
    },
  ];
};

const ProjectEditorPage: React.FC = () => {
  const { projectId } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const id = Number(projectId);

  const [stage, setStage] = useState<Stage>('Idea');
  const [project, setProject] = useState<Project | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [presets, setPresets] = useState<BackgroundPreset[]>([]);
  const [characterPresets, setCharacterPresets] = useState<CharacterPreset[]>([]);
  const [script, setScript] = useState<ScriptRevision | null>(null);
  const [scriptRevisions, setScriptRevisions] = useState<ScriptRevision[]>([]);
  const [scriptDraft, setScriptDraft] = useState(defaultScript);
  const [scriptLines, setScriptLines] = useState<ScriptLine[]>(parseDraftToLines(defaultScript));
  const [scriptPrompt, setScriptPrompt] = useState('an explainer about why short-form distribution pipelines need review');
  const [contentFormats, setContentFormats] = useState<ContentFormatPreset[]>(FALLBACK_CONTENT_FORMATS);
  const [scriptFormatId, setScriptFormatId] = useState('educational_short');
  const [scriptPlatform, setScriptPlatform] = useState<PlatformTarget>('tiktok');
  const [scriptTargetDuration, setScriptTargetDuration] = useState(45);
  const [scriptTone, setScriptTone] = useState('explanatory');
  const [scriptAudience, setScriptAudience] = useState('general short-form viewers');
  const [scriptSpeakerNames, setScriptSpeakerNames] = useState('');
  const [generatedScript, setGeneratedScript] = useState<GeneratedScript | null>(null);
  const [scriptProviderStatus, setScriptProviderStatus] = useState<ScriptGenerationProviderMetadata | null>(null);
  const [scriptGenerationWarnings, setScriptGenerationWarnings] = useState<string[]>([]);
  const [showScriptDebug, setShowScriptDebug] = useState(false);
  const [metadata, setMetadata] = useState<PlatformMetadata | null>(null);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [outputs, setOutputs] = useState<OutputVideo[]>([]);
  const [reviews, setReviews] = useState<ReviewQueueItem[]>([]);
  const [routing, setRouting] = useState<RoutingSuggestion | null>(null);
  const [history, setHistory] = useState<{ jobs: PublishJob[]; posts: PublishedPost[] }>({ jobs: [], posts: [] });
  const [speakerBindings, setSpeakerBindings] = useState<SpeakerBinding[]>([]);
  const [previewSettings, setPreviewSettings] = useState<ProjectPreviewSettings>(defaultPreviewSettings);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(null);
  const [renderReadiness, setRenderReadiness] = useState<RenderReadinessEstimate | null>(null);
  const [publishJob, setPublishJob] = useState<PublishJob | null>(null);
  const [publishMode, setPublishMode] = useState<'now' | 'schedule'>('now');
  const [scheduledFor, setScheduledFor] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [reviewComment, setReviewComment] = useState('');
  const [decisionNote, setDecisionNote] = useState('Looks good for publish.');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const tab = searchParams.get('tab');
    const tabToStage: Record<string, Stage> = {
      idea: 'Idea',
      assets: 'Scene',
      scenes: 'Scene',
      scene: 'Scene',
      script: 'Script',
      cast: 'Cast & Voices',
      voices: 'Cast & Voices',
      generate: 'Render',
      preview: 'Preview',
      render: 'Render',
      review: 'Preview',
      metadata: 'Release',
      routing: 'Release',
      release: 'Release',
      publish: 'Release',
      history: 'Release',
    };
    if (tab && tabToStage[tab] && tabToStage[tab] !== stage) {
      setStage(tabToStage[tab]);
    }
  }, [searchParams]);

  const activeGeneration = useMemo(
    () => Boolean(generationJob && ['queued', 'processing', 'retrying'].includes(generationJob.status)),
    [generationJob]
  );
  const selectedAccount = useMemo(
    () => accounts.find((account) => account.id === (project?.selected_social_account_id || routing?.social_account_id || accounts[0]?.id)) || null,
    [accounts, project?.selected_social_account_id, routing?.social_account_id]
  );
  const latestReview = useMemo(() => reviews[0] || project?.latest_review || null, [project?.latest_review, reviews]);
  const latestOutput = useMemo(() => outputs[0] || project?.latest_output || null, [outputs, project?.latest_output]);
  const backgroundAsset = useMemo(
    () => assets.find((asset) => asset.id === project?.background_asset_id) || assets.find((asset) => asset.kind.startsWith('background')) || null,
    [assets, project?.background_asset_id]
  );
  const generationStage = useMemo(() => generationStageLabel(generationJob), [generationJob]);
  const generationVoiceEntries = useMemo(
    () => Object.values(((generationJob?.voice_manifest as any)?.speakers || {}) as Record<string, any>),
    [generationJob?.voice_manifest]
  );
  const generationSegments = useMemo(
    () => (((generationJob?.tts_result as any)?.segments || []) as any[]),
    [generationJob?.tts_result]
  );
  const generationAssembly = useMemo(
    () => (((generationJob?.tts_result as any)?.assembly || {}) as any),
    [generationJob?.tts_result]
  );
  const generationTtsError = (generationJob?.tts_result as any)?.error || null;
  const savedDraft = useMemo(() => normalizeDraft(script?.raw_text || defaultScript), [script?.raw_text]);
  const scriptIsDirty = useMemo(() => normalizeDraft(scriptDraft) !== savedDraft, [scriptDraft, savedDraft]);
  const selectedFormat = useMemo(() => findFormat(contentFormats, scriptFormatId), [contentFormats, scriptFormatId]);
  const detectedSpeakers = useMemo(() => {
    const names = (scriptLines.length ? scriptLines : script?.parsed_lines || []).map((line) => line.speaker.trim()).filter(Boolean);
    return Array.from(new Set(names));
  }, [script?.parsed_lines, scriptLines]);
  const generatedScriptHasHardWarnings = useMemo(
    () => scriptGenerationWarnings.some((warning) => hardScriptWarnings.some((marker) => warning.includes(marker))),
    [scriptGenerationWarnings]
  );
  const scriptProviderLabel = useMemo(() => {
    if (!scriptProviderStatus) {
      return null;
    }
    if (scriptProviderStatus.fallback_used) {
      if (scriptProviderStatus.failure_type === 'ollama_timeout') {
        return 'Timed out · fallback';
      }
      if (scriptProviderStatus.failure_type === 'invalid_json' || scriptProviderStatus.failure_type === 'invalid_json_after_repair') {
        return 'Invalid JSON · fallback';
      }
      if (scriptProviderStatus.failure_type?.includes('quality_validation')) {
        return 'Quality fallback';
      }
      return 'Fallback';
    }
    return scriptProviderStatus.provider_name === 'ollama' ? 'Ollama' : scriptProviderStatus.provider_name;
  }, [scriptProviderStatus]);
  const scriptDiagnostics = useMemo(() => {
    const diagnostics = (scriptProviderStatus?.diagnostics || {}) as Record<string, unknown>;
    const targetDuration = Number(generatedScript?.target_duration_sec || diagnostics.target_duration_sec || scriptTargetDuration || 0);
    const estimatedDuration = Number(generatedScript?.total_estimated_duration_sec || diagnostics.estimated_duration_sec || 0);
    const speakerCount = Number(generatedScript?.speakers.length || diagnostics.speaker_count || 0);
    const fallbackReason = scriptProviderStatus?.fallback_reason || scriptProviderStatus?.failure_type || null;
    const ready = Boolean(generatedScript && !generatedScriptHasHardWarnings && generatedScript.lines.length > 0);
    return {
      targetDuration,
      estimatedDuration,
      speakerCount,
      fallbackReason,
      ready,
      repaired: Boolean(scriptProviderStatus?.repair_attempted),
      normalized: scriptGenerationWarnings.length > 0,
      cacheHit: Boolean((diagnostics.cache as any)?.hit),
    };
  }, [generatedScript, generatedScriptHasHardWarnings, scriptGenerationWarnings.length, scriptProviderStatus, scriptTargetDuration]);
  const readinessProject = useMemo(
    () => project ? { ...project, latest_output: latestOutput } : null,
    [project, latestOutput]
  );
  const productionReadiness = useMemo(
    () => computeProductionReadiness({
      project: readinessProject,
      script,
      latestJob: generationJob,
      metadata,
      draftEstimate: renderReadiness,
      linkMode: 'anchor',
    }),
    [readinessProject, script, generationJob, metadata, renderReadiness]
  );
  const renderChangeSummary = useMemo(
    () => buildRenderChangeSummary({ scriptIsDirty, generationJob, previewSettings, renderReadiness }),
    [generationJob, previewSettings, renderReadiness, scriptIsDirty]
  );
  const renderCacheWarmth = useMemo(() => {
    const warmth = (renderReadiness?.cache_warmth || {}) as any;
    const hits = Number(warmth.tts_segment_hits || 0);
    const misses = Number(warmth.tts_segment_misses || 0);
    const total = hits + misses;
    return {
      hits,
      misses,
      total,
      cloneMisses: Number(warmth.clone_provider_misses || 0),
      percent: total ? Math.round((hits / total) * 100) : 0,
    };
  }, [renderReadiness]);
  const stepSummaries = useMemo(() => {
    const rowById = new Map(productionReadiness.rows.map((row) => [row.id, row]));
    const readyLike = (state?: string) => state === 'ready' || state === 'verified';
    return {
      Idea: project ? `${titleCase(project.status)} production` : 'Needs setup',
      Script: readyLike(rowById.get('script')?.state) ? `${scriptLines.length} lines ready` : 'Missing',
      'Cast & Voices': readyLike(rowById.get('voice-assignments')?.state) && readyLike(rowById.get('character-images')?.state)
        ? `${productionReadiness.speakers.length} speakers assigned`
        : 'Missing',
      Scene: readyLike(rowById.get('scene')?.state) ? 'Ready' : 'Missing',
      Preview: rowById.get('preview')?.state === 'verified' ? 'Verified' : rowById.get('preview')?.state === 'warning' ? 'Warning' : 'Missing',
      Render: generationJob?.status === 'failed' ? 'Failed' : generationJob?.status ? titleCase(generationJob.status) : latestOutput ? 'Ready' : 'Missing',
      Release: readyLike(rowById.get('release')?.state) ? 'Ready' : 'Missing',
    } as Record<Stage, string>;
  }, [generationJob?.status, latestOutput, productionReadiness, project, scriptLines.length]);

  const toUtcIso = (value: string) => (value ? new Date(value).toISOString() : null);
  const apiBase = apiBaseUrl;
  const toApiHref = (path: string | null | undefined) => {
    if (!path) {
      return '#';
    }
    if (/^https?:\/\//i.test(path)) {
      return path;
    }
    return `${apiBase}${path.startsWith('/') ? path : `/${path}`}`;
  };
  const persistPreviewLayout = async (nextSettings: ProjectPreviewSettings) => {
    const normalized = clampPreviewLayout(nextSettings);
    setPreviewSettings(normalized);
    try {
      const response = await apiClient.patch<ProjectPreviewSettings>(`/projects/${id}/preview-settings`, {
        layout: normalized.layout,
      });
      setPreviewSettings(clampPreviewLayout(response.data));
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save preview layout settings.');
    }
  };

  const adjustCharacterScale = (delta: number) => {
    const next = {
      ...previewSettings,
      layout: {
        ...previewSettings.layout,
        character_scale: Number((previewSettings.layout.character_scale + delta).toFixed(2)),
      },
    };
    void persistPreviewLayout(next);
  };

  const adjustChatFontSize = (delta: number) => {
    const next = {
      ...previewSettings,
      layout: {
        ...previewSettings.layout,
        chat_font_size_px: previewSettings.layout.chat_font_size_px + delta,
      },
    };
    void persistPreviewLayout(next);
  };

  const hydrateScriptState = (revision: ScriptRevision | null) => {
    setScript(revision);
    const nextDraft = revision?.raw_text || defaultScript;
    const nextLines = revision?.parsed_lines?.length ? revision.parsed_lines : parseDraftToLines(nextDraft);
    setScriptDraft(nextDraft);
    setScriptLines(nextLines);
    setGeneratedScript(revision?.generated_script || null);
  };

  const hydrateScriptGenerationSettings = (settings: ProjectScriptGenerationSettings | null | undefined) => {
    if (!settings) {
      return;
    }
    setScriptFormatId(settings.content_format_id || 'educational_short');
    setScriptPlatform(settings.platform || 'tiktok');
    setScriptTargetDuration(settings.target_duration_sec || 45);
    setScriptTone(settings.tone || 'explanatory');
    setScriptAudience(settings.audience || 'general short-form viewers');
    setScriptSpeakerNames((settings.speaker_names || []).join(', '));
  };

  const persistScriptGenerationSettings = async (patch: Partial<ProjectScriptGenerationSettings>) => {
    if (!id || Number.isNaN(id)) {
      return null;
    }
    const response = await apiClient.patch<ProjectScriptGenerationSettings>(`/projects/${id}/script-generation-settings`, patch);
    setProject((current) =>
      current
        ? {
            ...current,
            script_generation_settings: response.data,
          }
        : current
    );
    return response.data;
  };

  const selectScriptFormat = (format: ContentFormatPreset) => {
    const nextDuration =
      scriptTargetDuration < format.ideal_duration_range_sec[0] || scriptTargetDuration > format.ideal_duration_range_sec[1]
        ? formatMidpoint(format)
        : scriptTargetDuration;
    const nextTone = format.tone_options.includes(scriptTone) ? scriptTone : format.tone_options[0] || scriptTone;
    const nextSpeakerNames = speakerNamesForFormat(format);
    setScriptFormatId(format.id);
    setScriptTargetDuration(nextDuration);
    setScriptTone(nextTone);
    setScriptSpeakerNames(nextSpeakerNames);
    void persistScriptGenerationSettings({
      content_format_id: format.id,
      platform: scriptPlatform,
      target_duration_sec: nextDuration,
      tone: nextTone,
      audience: scriptAudience,
      speaker_names: format.default_speaker_roles,
    });
  };

  const loadAll = async () => {
    try {
      setLoading(true);
      const [
        projectResponse,
        formatsResponse,
        assetsResponse,
        presetsResponse,
        characterPresetsResponse,
        scriptResponse,
        revisionsResponse,
        outputsResponse,
        reviewsResponse,
        metadataResponse,
        accountsResponse,
        historyResponse,
        speakerBindingsResponse,
        generationJobsResponse,
        renderReadinessResponse,
      ] = await Promise.all([
        apiClient.get<Project>(`/projects/${id}`),
        apiClient
          .get<{ items: ContentFormatPreset[] }>('/script-generation/formats')
          .catch(() => ({ data: { items: FALLBACK_CONTENT_FORMATS } })),
        apiClient.get<Asset[]>(`/projects/${id}/assets`),
        apiClient.get<BackgroundPreset[]>('/background-presets'),
        apiClient.get<{ items: CharacterPreset[] }>('/character-presets'),
        apiClient.get<{ current_revision: ScriptRevision | null }>(`/projects/${id}/script`),
        apiClient.get<{ items: ScriptRevision[] }>(`/projects/${id}/script-revisions`),
        apiClient.get<{ items: OutputVideo[] }>(`/projects/${id}/outputs`),
        apiClient.get<{ items: ReviewQueueItem[] }>(`/projects/${id}/reviews`),
        apiClient.get<PlatformMetadata | null>(`/projects/${id}/metadata/youtube`),
        apiClient.get<{ items: SocialAccount[] }>('/social-accounts'),
        apiClient.get<{ jobs: PublishJob[]; posts: PublishedPost[] }>(`/projects/${id}/publish-history`),
        apiClient.get<{ items: SpeakerBinding[] }>(`/projects/${id}/speaker-bindings`),
        apiClient.get<{ items: GenerationJob[] }>(`/projects/${id}/generation-jobs?limit=1`),
        apiClient.get<RenderReadinessEstimate>(`/projects/${id}/render-readiness?output_kind=draft`).catch(() => ({ data: null as RenderReadinessEstimate | null })),
      ]);

      setProject(projectResponse.data);
      setContentFormats(formatsResponse.data.items?.length ? formatsResponse.data.items : FALLBACK_CONTENT_FORMATS);
      hydrateScriptGenerationSettings(projectResponse.data.script_generation_settings);
      setPreviewSettings(clampPreviewLayout(projectResponse.data.preview_settings || defaultPreviewSettings));
      setAssets(assetsResponse.data);
      setPresets(presetsResponse.data);
      setCharacterPresets(characterPresetsResponse.data.items);
      hydrateScriptState(scriptResponse.data.current_revision);
      setScriptRevisions(revisionsResponse.data.items);
      setOutputs(outputsResponse.data.items);
      setReviews(reviewsResponse.data.items);
      setMetadata(metadataResponse.data);
      setAccounts(accountsResponse.data.items);
      setHistory(historyResponse.data);
      setSpeakerBindings(speakerBindingsResponse.data.items);
      setGenerationJob(generationJobsResponse.data.items[0] || null);
      setRenderReadiness(renderReadinessResponse.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load project workspace.');
    } finally {
      setLoading(false);
    }
  };

  const refreshRenderState = async () => {
    const [projectResponse, outputsResponse, reviewsResponse, latestJobResponse, renderReadinessResponse] = await Promise.all([
      apiClient.get<Project>(`/projects/${id}`),
      apiClient.get<{ items: OutputVideo[] }>(`/projects/${id}/outputs`),
      apiClient.get<{ items: ReviewQueueItem[] }>(`/projects/${id}/reviews`),
      apiClient.get<GenerationJob>(`/projects/${id}/generation-jobs/latest`).catch(() => ({ data: null as GenerationJob | null })),
      apiClient.get<RenderReadinessEstimate>(`/projects/${id}/render-readiness?output_kind=draft`).catch(() => ({ data: null as RenderReadinessEstimate | null })),
    ]);
    setProject(projectResponse.data);
    setPreviewSettings(clampPreviewLayout(projectResponse.data.preview_settings || defaultPreviewSettings));
    setOutputs(outputsResponse.data.items);
    setReviews(reviewsResponse.data.items);
    setGenerationJob(latestJobResponse.data);
    setRenderReadiness(renderReadinessResponse.data);
  };

  useEffect(() => {
    if (!Number.isNaN(id)) {
      loadAll();
    }
  }, [id]);

  useEffect(() => {
    if (!generationJob || !['queued', 'processing'].includes(generationJob.status)) {
      return undefined;
    }

    const timer = window.setInterval(async () => {
      try {
        const response = await apiClient.get<GenerationJob>(`/generation-jobs/${generationJob.id}`);
        setGenerationJob(response.data);
        if (['completed', 'failed', 'canceled'].includes(response.data.status)) {
          await refreshRenderState();
          setStage('Preview');
        }
      } catch {
        window.clearInterval(timer);
      }
    }, generationJob.status === 'queued' ? 1800 : 1200);

    return () => window.clearInterval(timer);
  }, [generationJob]);

  useEffect(() => {
    if (!publishJob || !['queued', 'publishing', 'retrying', 'scheduled'].includes(publishJob.status)) {
      return undefined;
    }

    const timer = window.setInterval(async () => {
      try {
        const response = await apiClient.get<PublishJob>(`/publish-jobs/${publishJob.id}`);
        setPublishJob(response.data);
        if (['published', 'failed', 'canceled'].includes(response.data.status)) {
          await loadAll();
        }
      } catch {
        window.clearInterval(timer);
      }
    }, 2000);

    return () => window.clearInterval(timer);
  }, [publishJob]);

  const loadRoutingSuggestion = async () => {
    try {
      const response = await apiClient.post<RoutingSuggestion>(`/projects/${id}/routing/suggest`);
      setRouting(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to suggest routing.');
    }
  };

  const uploadBackground = async () => {
    if (!selectedFile) {
      return;
    }

    const formData = new FormData();
    formData.append('file', selectedFile);

    try {
      setBusy('upload');
      const response = await apiClient.post<Asset>(`/projects/${id}/assets/background`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setAssets((current) => [response.data, ...current.filter((asset) => asset.id !== response.data.id)]);
      setProject((current) =>
        current
          ? { ...current, background_asset_id: response.data.id, background_source_type: response.data.source_type }
          : current
      );
      setPreviewSettings((current) =>
        clampPreviewLayout({
          ...current,
          background_asset_id: response.data.id,
          background_preset_id: response.data.preset_key,
          background_source_type: response.data.source_type,
          background_url: response.data.content_url,
          background_metadata: response.data.metadata,
        })
      );
      setSelectedFile(null);
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Background upload failed.');
    } finally {
      setBusy(null);
    }
  };

  const choosePreset = async (presetKey: string) => {
    try {
      setBusy(`preset-${presetKey}`);
      const response = await apiClient.post<Asset>(`/projects/${id}/assets/background/preset/${presetKey}`);
      setAssets((current) => [response.data, ...current.filter((asset) => asset.id !== response.data.id)]);
      setProject((current) =>
        current
          ? { ...current, background_asset_id: response.data.id, background_source_type: response.data.source_type }
          : current
      );
      setPreviewSettings((current) =>
        clampPreviewLayout({
          ...current,
          background_asset_id: response.data.id,
          background_preset_id: response.data.preset_key,
          background_source_type: response.data.source_type,
          background_url: response.data.content_url,
          background_metadata: response.data.metadata,
        })
      );
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Scene selection failed.');
    } finally {
      setBusy(null);
    }
  };

  const syncDraftFromLines = (nextLines: ScriptLine[]) => {
    const normalized = nextLines.map((line, index) => ({ ...line, order: index }));
    setScriptLines(normalized);
    setScriptDraft(linesToDraft(normalized));
  };

  const persistScriptRevision = async () => {
    const response = await apiClient.put<{ current_revision: ScriptRevision }>(`/projects/${id}/script`, {
      parsed_lines: scriptLines.map((line, index) => ({ ...line, order: index })),
      source: 'manual',
      parent_revision_id: script?.id || null,
    });
    hydrateScriptState(response.data.current_revision);
    return response.data.current_revision;
  };

  const saveScript = async () => {
    try {
      setBusy('script');
      await persistScriptRevision();
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Script validation failed.');
    } finally {
      setBusy(null);
    }
  };

  const generateScript = async () => {
    try {
      setBusy('script-generate');
      const requestedSpeakerNames = scriptSpeakerNames
        .split(',')
        .map((name) => name.trim())
        .filter(Boolean);
      await persistScriptGenerationSettings({
        content_format_id: scriptFormatId,
        platform: scriptPlatform,
        target_duration_sec: scriptTargetDuration,
        tone: scriptTone,
        audience: scriptAudience,
        speaker_names: requestedSpeakerNames.length ? requestedSpeakerNames : selectedFormat?.default_speaker_roles || [],
      });
      const response = await apiClient.post<ScriptGenerationResponse>('/script-generation/generate', {
        idea: scriptPrompt,
        content_format_id: scriptFormatId,
        format_id: scriptFormatId,
        platform: scriptPlatform,
        platform_targets: [scriptPlatform],
        target_duration_sec: scriptTargetDuration,
        timing_target: {
          target_duration_sec: scriptTargetDuration,
        },
        tone: scriptTone,
        audience: scriptAudience,
        speaker_names: requestedSpeakerNames.length ? requestedSpeakerNames : selectedFormat?.default_speaker_roles || detectedSpeakers,
        speaker_roles: selectedFormat?.default_speaker_roles || [],
        quality_hints: {
          specificity: 'specific',
          retention_style: selectedFormat?.pacing_rules?.[0] || 'hook-driven',
        },
        debug: showScriptDebug,
      });
      setGeneratedScript(response.data.generated_script);
      setScriptProviderStatus(response.data.provider_metadata);
      setScriptGenerationWarnings(response.data.validation_warnings || []);
      const nextLines = response.data.generated_script.lines.map((line, index) => ({
        id: undefined,
        speaker: line.speaker_label,
        text: line.text,
        order: index,
      }));
      syncDraftFromLines(nextLines);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Script generation failed.');
    } finally {
      setBusy(null);
    }
  };

  const acceptGeneratedScript = async () => {
    if (!generatedScript || generatedScriptHasHardWarnings) {
      return;
    }
    try {
      setBusy('script');
      const parsedLines = generatedScript.lines.map((line, index) => ({
        speaker: line.speaker_label,
        text: line.text,
        caption_text: line.caption_text,
        section: line.section,
        line_id: line.id,
        order: index,
      }));
      const response = await apiClient.put<{ current_revision: ScriptRevision }>(`/projects/${id}/script`, {
        parsed_lines: parsedLines,
        generated_script: generatedScript,
        source: 'generated',
        parent_revision_id: script?.id || null,
      });
      hydrateScriptState(response.data.current_revision);
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to accept generated script.');
    } finally {
      setBusy(null);
    }
  };

  const restoreRevision = async (revisionId: number) => {
    try {
      setBusy(`restore-${revisionId}`);
      const response = await apiClient.post<{ current_revision: ScriptRevision }>(`/projects/${id}/script-revisions/${revisionId}/restore`);
      hydrateScriptState(response.data.current_revision);
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to restore revision.');
    } finally {
      setBusy(null);
    }
  };

  const saveSpeakerBindings = async (items: SpeakerBinding[]) => {
    const response = await apiClient.put<{ items: SpeakerBinding[] }>(`/projects/${id}/speaker-bindings`, {
      items: items.map((item) => ({
        speaker_name: item.speaker_name,
        character_preset_id: item.character_preset_id,
      })),
    });
    setSpeakerBindings(response.data.items);
    return response.data.items;
  };

  const updateSpeakerBinding = async (speakerName: string, characterPresetId: string) => {
    try {
      setBusy(`binding-${speakerName}`);
      const nextBindings = [...speakerBindings];
      const existing = nextBindings.find((item) => item.speaker_name === speakerName);
      const preset = characterPresets.find((item) => item.id === characterPresetId);
      if (!preset) {
        return;
      }
      if (existing) {
        existing.character_preset_id = characterPresetId;
        existing.character_display_name = preset.display_name;
        existing.voice_profile_id = preset.voice_profile_id;
        existing.provider = preset.tts_provider;
        existing.character_portrait_filename = preset.portrait_filename;
        existing.character_portrait_url = preset.portrait_url;
      } else {
        nextBindings.push({
          id: 0,
          speaker_name: speakerName,
          character_preset_id: characterPresetId,
          character_display_name: preset.display_name,
          voice_profile_id: preset.voice_profile_id,
          provider: preset.tts_provider,
          character_portrait_filename: preset.portrait_filename,
          character_portrait_url: preset.portrait_url,
        });
      }
      await saveSpeakerBindings(nextBindings);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save speaker binding.');
    } finally {
      setBusy(null);
    }
  };

  const generatePreview = async (outputKind: 'preview' | 'draft' | 'final' | 'debug' = 'preview') => {
    if (activeGeneration) {
      return;
    }
    try {
      setBusy('generation');
      let scriptRevisionId = script?.id || null;
      if (scriptIsDirty) {
        const savedRevision = await persistScriptRevision();
        scriptRevisionId = savedRevision.id;
      }
      if (detectedSpeakers.length > 0) {
        const ensuredBindings = detectedSpeakers.map((speakerName) => {
          // Queueing a render should snapshot every detected speaker, including newly typed script names.
          const existing = speakerBindings.find((item) => item.speaker_name === speakerName);
          if (existing) {
            return existing;
          }
          const suggestedPreset =
            characterPresets.find((item) => item.display_name.toLowerCase() === speakerName.toLowerCase()) ||
            characterPresets.find((item) => item.speaker_names.some((name) => name.toLowerCase() === speakerName.toLowerCase())) ||
            characterPresets[0];
          return {
            id: 0,
            speaker_name: speakerName,
            character_preset_id: suggestedPreset?.id || '',
            character_display_name: suggestedPreset?.display_name || '',
            voice_profile_id: suggestedPreset?.voice_profile_id || '',
            provider: suggestedPreset?.tts_provider || 'espeak',
            character_portrait_filename: suggestedPreset?.portrait_filename || null,
            character_portrait_url: suggestedPreset?.portrait_url || null,
          };
        });
        if (ensuredBindings.some((item) => !item.character_preset_id)) {
          setError('Assign a character preset to each detected speaker before rendering.');
          return;
        }
        await saveSpeakerBindings(ensuredBindings);
      }
      const response = await apiClient.post<GenerationJob>(`/projects/${id}/renders`, {
        background_style: project?.background_style || 'none',
        output_kind: outputKind,
        provider_name: 'local-compositor',
        script_revision_id: scriptRevisionId,
      });
      setGenerationJob(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Render queueing failed.');
    } finally {
      setBusy(null);
    }
  };

  const submitForReview = async () => {
    if (!latestOutput) {
      return;
    }
    try {
      setBusy('review-submit');
      await apiClient.post<ReviewQueueItem>(`/projects/${id}/review/submit`, {
        output_video_id: latestOutput.id,
        note: reviewNote || null,
      });
      setReviewNote('');
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to submit for review.');
    } finally {
      setBusy(null);
    }
  };

  const addReviewComment = async () => {
    if (!latestReview || !reviewComment.trim()) {
      return;
    }
    try {
      setBusy('review-comment');
      await apiClient.post(`/reviews/${latestReview.id}/comments`, {
        body: reviewComment.trim(),
        kind: 'note',
      });
      setReviewComment('');
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to add review comment.');
    } finally {
      setBusy(null);
    }
  };

  const approveReview = async () => {
    if (!latestReview) {
      return;
    }
    try {
      setBusy('review-approve');
      await apiClient.post(`/reviews/${latestReview.id}/approve`, {
        summary: decisionNote,
      });
      await loadAll();
      setStage('Release');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to approve review.');
    } finally {
      setBusy(null);
    }
  };

  const requestChanges = async () => {
    if (!latestReview) {
      return;
    }
    try {
      setBusy('review-changes');
      await apiClient.post(`/reviews/${latestReview.id}/request-changes`, {
        summary: 'Changes requested before publish.',
        rejection_reason: decisionNote,
      });
      await loadAll();
      setStage('Script');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to request changes.');
    } finally {
      setBusy(null);
    }
  };

  const saveMetadata = async () => {
    try {
      setBusy('metadata');
      const response = await apiClient.put<PlatformMetadata>(`/projects/${id}/metadata/youtube`, {
        title: metadata?.title || project?.name || 'Untitled Short',
        description: metadata?.description || '',
        tags: metadata?.tags || [],
        extras: metadata?.extras || {},
        source: 'manual',
      });
      setMetadata(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save metadata.');
    } finally {
      setBusy(null);
    }
  };

  const suggestMetadata = async () => {
    try {
      setBusy('metadata-suggest');
      const response = await apiClient.post<PlatformMetadata>(`/projects/${id}/metadata/youtube/suggest`);
      setMetadata(response.data);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to suggest metadata.');
    } finally {
      setBusy(null);
    }
  };

  const submitPublishJob = async (mode: 'assisted' | 'auto') => {
    if (!latestOutput || !metadata) {
      return;
    }

    const endpoint = mode === 'auto' ? `/projects/${id}/publish/auto` : `/projects/${id}/publish`;
    try {
      setBusy(`publish-${mode}`);
      const response = await apiClient.post<PublishJob>(endpoint, {
        platform: 'youtube',
        social_account_id: mode === 'auto' ? null : selectedAccount?.id || null,
        output_video_id: latestOutput.id,
        platform_metadata_id: metadata.id,
        publish_mode: publishMode,
        scheduled_for: publishMode === 'schedule' ? toUtcIso(scheduledFor) : null,
        automation_mode: mode,
      });
      setPublishJob(response.data);
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to create publish job.');
    } finally {
      setBusy(null);
    }
  };

  const renderGenerationJobPanel = () => {
    return <RenderDiagnosticsPanel job={generationJob} output={latestOutput} projectId={id || project?.id} />;
  };

  if (loading) {
    return (
      <StudioShell mainClassName="studio-detail-surface">
        <div className="mx-auto w-full max-w-7xl">
          <div className="studio-page-hero">Loading production...</div>
        </div>
      </StudioShell>
    );
  }

  return (
    <StudioShell currentProject={project} mainClassName="studio-detail-surface">
      <div className="max-w-7xl mx-auto w-full space-y-6">
          <div className="studio-page-hero flex items-center justify-between gap-4">
            <div>
              <div className="studio-page-kicker">Production Lab · {project?.status}</div>
              <h1 className="mt-2">{project?.name}</h1>
              <p className="mt-3 max-w-3xl text-slate-400">
                Stage the asset, refine the dialogue, render a preview, move it through human review, then publish in assisted or automatic mode.
              </p>
              <div className="studio-quick-links mt-4">
                <Link className="studio-link-pill" to="/">Command Room</Link>
                <Link className="studio-link-pill" to={`/voice-lab?productionId=${id}`}>Voice Lab</Link>
                <a className="studio-link-pill" href="#pre-render-preview">Preview Settings</a>
              </div>
            </div>
            <button
              onClick={loadAll}
              className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-4 py-2 text-sm hover:bg-white/10"
            >
              <RefreshCw size={16} />
              Refresh
            </button>
          </div>

          {error && <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-rose-200">{error}</div>}

          {stage !== 'Render' && generationJob && (
            <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
              <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Latest render job</div>
                  <div className="mt-1 text-sm text-slate-400">Segment WAV links stay available after completion for render debugging.</div>
                </div>
                <button
                  onClick={() => setStage('Render')}
                  className="rounded-full border border-white/10 px-4 py-2 text-sm hover:bg-white/10"
                >
                  Open Render Controls
                </button>
              </div>
              {renderGenerationJobPanel()}
            </section>
          )}

          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
            <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-7">
              {STAGES.map((item) => (
                <button
                  key={item}
                  onClick={() => {
                    setStage(item);
                    setSearchParams({ tab: item === 'Cast & Voices' ? 'cast' : item.toLowerCase() });
                  }}
                  className={`rounded-2xl px-4 py-3 text-left text-sm font-medium transition ${
                    stage === item ? 'bg-cyan-300 text-slate-950' : 'bg-slate-950/50 text-slate-300 hover:bg-white/10'
                  }`}
                >
                  <span className="block">{item}</span>
                  <span className={`mt-1 block text-xs ${stage === item ? 'text-slate-800' : 'text-slate-500'}`}>{stepSummaries[item]}</span>
                </button>
              ))}
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <section className="space-y-6">
              {stage === 'Idea' && (
                <div id="step-idea" className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Idea</h2>
                  <p className="mt-2 text-sm text-slate-400">Set the production direction before moving into script, cast, scene, preview, render, and release.</p>
                  <div className="mt-4 grid gap-3 md:grid-cols-2">
                    <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                      <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Production</div>
                      <div className="mt-2 text-lg font-semibold">{project?.name}</div>
                      <div className="mt-1 text-sm text-slate-400">{titleCase(project?.target_platform)} · {titleCase(project?.status)}</div>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                      <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Format</div>
                      <div className="mt-2 text-lg font-semibold">{selectedFormat?.display_name || titleCase(script?.generated_script?.content_format_id || 'Not selected')}</div>
                      <div className="mt-1 text-sm text-slate-400">{selectedFormat ? durationLabel(selectedFormat) : 'Choose a reusable format in Script.'}</div>
                    </div>
                  </div>
                  <div className="mt-4">
                    <ProductionReadinessPanel readiness={productionReadiness} />
                  </div>
                </div>
              )}

              {stage === 'Scene' && (
                <div id="step-scene" className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Scene</h2>
                  <p className="mt-2 text-sm text-slate-400">Upload a scene video or image, or pick a curated scene for this production.</p>
                  <div className="mt-4 flex flex-col gap-3 md:flex-row">
                    <input
                      type="file"
                      accept="video/mp4,video/webm,video/mpeg,image/png,image/jpeg,image/webp"
                      onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                      className="block w-full rounded-2xl border border-white/10 bg-slate-950/50 px-4 py-4 text-sm"
                    />
                    <button
                      onClick={uploadBackground}
                      disabled={!selectedFile || busy === 'upload'}
                      className="inline-flex items-center justify-center gap-2 rounded-2xl bg-cyan-300 px-5 py-4 font-medium text-slate-950 disabled:opacity-60"
                    >
                      <Upload size={18} />
                      {busy === 'upload' ? 'Uploading...' : 'Upload Scene'}
                    </button>
                  </div>

                  <div className="mt-6 grid gap-3 md:grid-cols-2">
                    {presets.length === 0 && (
                      <div className="rounded-2xl border border-dashed border-white/15 bg-slate-950/30 p-4 text-sm text-slate-400">
                        No bundled scenes are available yet. Add media under `backend/storage/presets`, then rebuild the Docker containers to refresh the gallery.
                      </div>
                    )}
                    {presets.map((preset) => (
                      <div key={preset.key} className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                        <div className="text-sm font-medium">{preset.name}</div>
                        <p className="mt-1 text-sm text-slate-400">{preset.description}</p>
                        <button
                          onClick={() => choosePreset(preset.key)}
                          disabled={busy === `preset-${preset.key}`}
                          className="mt-4 rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-60"
                        >
                          {busy === `preset-${preset.key}` ? 'Selecting...' : 'Use Scene'}
                        </button>
                      </div>
                    ))}
                  </div>

                  {backgroundAsset && (
                    <div className="mt-6 rounded-2xl border border-emerald-300/20 bg-emerald-400/10 p-4 text-sm text-emerald-100">
                      Selected scene: {backgroundAsset.original_filename} ({project?.background_source_type})
                    </div>
                  )}
                </div>
              )}

              {stage === 'Script' && (
                <div id="step-script" className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <h2 className="text-xl font-semibold">Dialogue Script</h2>
                      <p className="mt-2 text-sm text-slate-400">Generate a structured, speaker-separated script, then accept it into the render-ready project script.</p>
                    </div>
                    <button
                      onClick={generateScript}
                      disabled={busy === 'script-generate'}
                      className="inline-flex items-center gap-2 rounded-2xl bg-cyan-300 px-4 py-3 text-sm font-medium text-slate-950 hover:bg-cyan-200 disabled:opacity-60"
                    >
                      <Sparkles size={16} />
                      {busy === 'script-generate' ? 'Generating...' : generatedScript ? 'Regenerate' : 'Generate Script'}
                    </button>
                  </div>

                  {scriptIsDirty && (
                    <div className="mt-4 rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                      The dialogue has unsaved changes. Rendering will now save the latest speaker names and lines automatically before queueing a job.
                    </div>
                  )}

                  <div className="mt-4 space-y-3 rounded-2xl border border-white/10 bg-slate-950/30 p-4">
                    <FormatBrowser formats={contentFormats} selectedFormatId={scriptFormatId} onSelect={selectScriptFormat} />
                    <textarea
                      value={scriptPrompt}
                      onChange={(event) => setScriptPrompt(event.target.value)}
                      placeholder={selectedFormat ? `Idea for a ${selectedFormat.display_name.toLowerCase()}...` : 'Idea for structured script generation'}
                      rows={3}
                      className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                    />
                    {selectedFormat && (
                      <div className="rounded-2xl border border-cyan-300/20 bg-cyan-400/10 p-3 text-sm text-cyan-50">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="rounded-full bg-cyan-100 px-3 py-1 text-xs font-medium text-slate-950">{selectedFormat.display_name}</span>
                          <span>Ideal {durationLabel(selectedFormat)}</span>
                          <span>· {speakerCountLabel(selectedFormat)}</span>
                          <span>· {selectedFormat.section_structure.join(' -> ')}</span>
                        </div>
                        <div className="mt-2 text-xs text-cyan-100/80">{selectedFormat.best_use_case}</div>
                      </div>
                    )}
                    <div className="grid gap-3 lg:grid-cols-[0.9fr_0.8fr_1fr]">
                    <select
                      value={scriptFormatId}
                      onChange={(event) => {
                        const format = findFormat(contentFormats, event.target.value);
                        if (format) {
                          selectScriptFormat(format);
                        }
                      }}
                      className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                    >
                      {contentFormats.map((format) => (
                        <option key={format.id} value={format.id}>{format.display_name}</option>
                      ))}
                    </select>
                    <select
                      value={scriptPlatform}
                      onChange={(event) => setScriptPlatform(event.target.value as PlatformTarget)}
                      className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                    >
                      {platformTargets.map((platform) => (
                        <option key={platform.id} value={platform.id}>{platform.label}</option>
                      ))}
                    </select>
                      <div className="grid grid-cols-4 gap-2">
                        {[15, 30, 45, 60].map((duration) => (
                          <button
                            key={duration}
                            onClick={() => setScriptTargetDuration(duration)}
                            className={`rounded-2xl border px-3 py-3 text-sm ${
                              scriptTargetDuration === duration
                                ? 'border-cyan-300 bg-cyan-300/15 text-cyan-100'
                                : 'border-white/10 bg-slate-950/60 text-slate-300 hover:bg-white/10'
                            }`}
                          >
                            {duration}s
                          </button>
                        ))}
                      </div>
                    </div>
                    <div className="grid gap-3 md:grid-cols-3">
                      <input
                        value={scriptTone}
                        onChange={(event) => setScriptTone(event.target.value)}
                        placeholder="Tone"
                        className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                      />
                      <input
                        value={scriptAudience}
                        onChange={(event) => setScriptAudience(event.target.value)}
                        placeholder="Audience"
                        className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                      />
                      <input
                        value={scriptSpeakerNames}
                        onChange={(event) => setScriptSpeakerNames(event.target.value)}
                        placeholder={selectedFormat ? `${selectedFormat.default_speaker_roles.join(', ')}` : 'Optional speakers, comma-separated'}
                        className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                      />
                    </div>
                    <div className="flex flex-wrap items-center gap-3">
                      <button
                        onClick={generateScript}
                        disabled={busy === 'script-generate' || !scriptPrompt.trim()}
                        className="inline-flex items-center gap-2 rounded-2xl bg-cyan-300 px-4 py-3 text-sm font-medium text-slate-950 hover:bg-cyan-200 disabled:opacity-60"
                      >
                        <Sparkles size={16} />
                        {busy === 'script-generate' ? 'Generating...' : generatedScript ? 'Regenerate Script' : 'Generate Script'}
                      </button>
                      <label className="inline-flex items-center gap-2 text-sm text-slate-300">
                        <input
                          type="checkbox"
                          checked={showScriptDebug}
                          onChange={(event) => setShowScriptDebug(event.target.checked)}
                        />
                        Debug details
                      </label>
                    </div>
                  </div>

                  {(generatedScript || scriptProviderStatus) && (
                    <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-400/10 p-4 text-sm text-cyan-50">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-full px-3 py-1 text-xs font-medium ${
                            scriptProviderStatus?.fallback_used
                              ? 'bg-amber-300 text-slate-950'
                              : 'bg-emerald-300 text-slate-950'
                          }`}>
                            {scriptProviderLabel || 'Unknown'}
                          </span>
                          <span>
                            {scriptProviderStatus?.fallback_used
                              ? `Fallback script generated${scriptDiagnostics.fallbackReason ? `: ${scriptDiagnostics.fallbackReason}` : ''}`
                              : 'Generated with Ollama'}
                          </span>
                          {generatedScript ? <span>· {titleCase(generatedScript.format_id || generatedScript.content_format_id)}</span> : null}
                          {generatedScript ? <span>· {scriptDiagnostics.estimatedDuration.toFixed(1)}s / {scriptDiagnostics.targetDuration}s</span> : null}
                          {generatedScript ? <span>· {scriptDiagnostics.speakerCount} speaker{scriptDiagnostics.speakerCount === 1 ? '' : 's'}</span> : null}
                          {scriptDiagnostics.cacheHit ? <span>· cache hit</span> : null}
                          {scriptDiagnostics.repaired ? <span>· repaired</span> : null}
                          {scriptDiagnostics.normalized ? <span>· normalized</span> : null}
                          {generatedScript ? (
                            <span className={scriptDiagnostics.ready ? 'text-emerald-100' : 'text-amber-100'}>
                              · {scriptDiagnostics.ready ? 'ready to accept' : 'needs review'}
                            </span>
                          ) : null}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {generatedScript && (
                            <button
                              onClick={() => navigator.clipboard?.writeText(JSON.stringify(generatedScript, null, 2))}
                              className="rounded-2xl border border-white/10 px-4 py-2 font-medium text-cyan-50 hover:bg-white/10"
                            >
                              Copy JSON
                            </button>
                          )}
                          {generatedScript && (
                          <button
                            onClick={acceptGeneratedScript}
                            disabled={busy === 'script' || generatedScriptHasHardWarnings}
                            className="rounded-2xl bg-cyan-100 px-4 py-2 font-medium text-slate-950 disabled:opacity-60"
                          >
                            Accept Script
                          </button>
                          )}
                        </div>
                      </div>
                      {scriptGenerationWarnings.length > 0 && (
                        <div className="mt-2 text-xs text-amber-100">
                          {scriptGenerationWarnings.slice(0, 6).join(' · ')}
                        </div>
                      )}
                      {showScriptDebug && scriptProviderStatus && (
                        <pre className="mt-3 max-h-56 overflow-auto rounded-xl bg-slate-950/80 p-3 text-xs text-slate-300">
                          {JSON.stringify(scriptProviderStatus, null, 2)}
                        </pre>
                      )}
                    </div>
                  )}

                  <div className="mt-6 grid gap-4 xl:grid-cols-[1fr_0.8fr]">
                    <div className="space-y-3">
                      {scriptLines.map((line, index) => (
                        <div key={`${line.speaker}-${index}`} className="grid gap-3 rounded-2xl border border-white/10 bg-slate-950/40 p-4 md:grid-cols-[0.35fr_1fr]">
                          <input
                            value={line.speaker}
                            onChange={(event) => {
                              const nextLines = [...scriptLines];
                              nextLines[index] = { ...nextLines[index], speaker: event.target.value };
                              syncDraftFromLines(nextLines);
                            }}
                            className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
                          />
                          <textarea
                            value={line.text}
                            onChange={(event) => {
                              const nextLines = [...scriptLines];
                              nextLines[index] = { ...nextLines[index], text: event.target.value };
                              syncDraftFromLines(nextLines);
                            }}
                            rows={2}
                            className="rounded-xl border border-white/10 bg-white/5 px-3 py-2 text-sm"
                          />
                        </div>
                      ))}
                      <button
                        onClick={() => syncDraftFromLines([...scriptLines, { speaker: 'Host', text: '', order: scriptLines.length }])}
                        className="rounded-2xl border border-dashed border-white/15 px-4 py-3 text-sm hover:bg-white/10"
                      >
                        Add Dialogue Line
                      </button>
                      {generatedScript && (
                        <div className="space-y-2 rounded-2xl border border-white/10 bg-slate-950/30 p-4">
                          <div className="text-sm font-medium text-slate-200">Structured Lines</div>
                          {generatedScript.lines.slice(0, 8).map((line) => (
                            <div key={line.id} className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm">
                              <div className="flex flex-wrap items-center gap-2 text-xs uppercase tracking-wide text-cyan-200">
                                <span>{line.section}</span>
                                <span>·</span>
                                <span>{line.speaker_label}</span>
                                <span>·</span>
                                <span>{line.estimated_duration_sec.toFixed(1)}s</span>
                              </div>
                              <div className="mt-1 text-slate-100">{line.text}</div>
                              <div className="mt-1 text-xs text-slate-400">{line.caption_text}</div>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>

                    <div className="space-y-4">
                      <textarea
                        value={scriptDraft}
                        onChange={(event) => {
                          const nextDraft = event.target.value;
                          setScriptDraft(nextDraft);
                          setScriptLines(parseDraftToLines(nextDraft));
                        }}
                        rows={16}
                        className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 font-mono text-sm"
                      />
                      <button
                        onClick={saveScript}
                        disabled={busy === 'script'}
                        className="rounded-2xl bg-white px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                      >
                        {busy === 'script' ? 'Saving...' : 'Save Revision'}
                      </button>
                    </div>
                  </div>

                  <div className="mt-6 grid gap-3 md:grid-cols-2">
                    {scriptRevisions.slice(0, 6).map((revision) => (
                      <button
                        key={revision.id}
                        onClick={() => restoreRevision(revision.id)}
                        disabled={busy === `restore-${revision.id}`}
                        className="rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-left hover:border-cyan-300/40"
                      >
                        <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">
                          {revision.source} {revision.generation_provider ? `· ${revision.generation_provider}` : ''}
                        </div>
                        <div className="mt-2 font-medium">Revision #{revision.id}</div>
                        <div className="mt-2 text-sm text-slate-400">{revision.raw_text.slice(0, 100)}</div>
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {stage === 'Cast & Voices' && (
                <div id="step-cast" className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Cast & Voices</h2>
                  <p className="mt-2 text-sm text-slate-400">Assign each script speaker to a reusable character image and voice profile before rendering.</p>
                  <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
                    Detected cast: {(script?.characters || scriptLines.map((line) => line.speaker)).slice(0, 2).join(' vs ') || 'Add two dialogue speakers first'}.
                    The renderer uses these assignments to keep voices, captions, and active character images aligned.
                  </div>
                  <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-slate-100">Speaker assignments</div>
                        <div className="mt-1 text-sm text-slate-400">
                          Final generation uses these explicit preset bindings so Voice Lab previews and renders stay consistent.
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 space-y-3">
                      {detectedSpeakers.map((speakerName) => {
                        const binding = speakerBindings.find((item) => item.speaker_name === speakerName);
                        return (
                          <div key={speakerName} className="rounded-2xl border border-white/10 bg-black/20 p-3">
                            <div>
                              <div className="text-sm font-medium text-slate-200">{speakerName}</div>
                              <div className="mt-1 text-xs text-slate-500">
                                {binding ? `${binding.character_display_name} · ${binding.provider}` : 'No preset selected yet'}
                              </div>
                              {binding?.voice_profile_id && (
                                <Link
                                  to={`/voice-lab?profileId=${encodeURIComponent(binding.voice_profile_id)}&productionId=${id}&speakerId=${encodeURIComponent(speakerName)}`}
                                  className="mt-2 inline-flex text-xs text-cyan-200 hover:text-cyan-100"
                                >
                                  Edit selected voice in Voice Lab
                                </Link>
                              )}
                            </div>
                            <div className="mt-3 grid gap-2 sm:grid-cols-2">
                              {characterPresets.map((preset) => {
                                const selected = binding?.character_preset_id === preset.id;
                                return (
                                  <button
                                    key={preset.id}
                                    onClick={() => updateSpeakerBinding(speakerName, preset.id)}
                                    disabled={busy === `binding-${speakerName}`}
                                    className={`flex items-center gap-3 rounded-xl border p-3 text-left text-sm transition ${
                                      selected
                                        ? 'border-cyan-300/60 bg-cyan-300/10 text-cyan-100'
                                        : 'border-white/10 bg-slate-950/50 text-slate-300 hover:bg-white/10'
                                    } disabled:opacity-60`}
                                  >
                                    <div className="grid h-14 w-12 shrink-0 place-items-center overflow-hidden rounded-lg border border-white/10 bg-black/30 text-[10px] text-slate-500">
                                      {preset.portrait_url ? (
                                        <img
                                          src={toApiHref(preset.portrait_url)}
                                          alt={preset.display_name}
                                          className="h-full w-full object-cover"
                                        />
                                      ) : (
                                        <span>Image</span>
                                      )}
                                    </div>
                                    <span className="min-w-0">
                                      <span className="block truncate font-medium">{preset.display_name}</span>
                                      <span className="mt-1 block truncate text-xs text-slate-500">{preset.tts_provider}</span>
                                    </span>
                                  </button>
                                );
                              })}
                            </div>
                          </div>
                        );
                      })}
                      {detectedSpeakers.length === 0 && (
                        <div className="rounded-2xl border border-dashed border-white/10 px-3 py-4 text-sm text-slate-500">
                          Add named dialogue lines first so OmniPoster can bind each speaker to a saved preset.
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {stage === 'Render' && (
                <div id="step-render" className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Render</h2>
                  <p className="mt-2 text-sm text-slate-400">Queue a draft, preview, final, or debug render after the script, cast, and scene are ready.</p>
                  {renderReadiness && (
                    <div className={`mt-4 rounded-2xl border px-4 py-3 text-sm ${renderReadiness.draft_ready ? 'border-emerald-300/30 bg-emerald-400/10 text-emerald-100' : 'border-amber-300/30 bg-amber-400/10 text-amber-100'}`}>
                      <div className="font-medium">
                        60-second draft SLA: {renderReadiness.draft_ready ? 'Ready' : 'Warning'}
                      </div>
                      <div className="mt-1 opacity-90">
                        Estimate {Math.round(renderReadiness.estimated_seconds_low)}-{Math.round(renderReadiness.estimated_seconds_high)}s · cache dependency {renderReadiness.expected_cache_dependency}
                      </div>
                      {(renderReadiness.blocking_reasons[0] || renderReadiness.optimization_hints[0]) && (
                        <div className="mt-1 opacity-90">{renderReadiness.blocking_reasons[0] || renderReadiness.optimization_hints[0]}</div>
                      )}
                    </div>
                  )}
                  {renderReadiness && (
                    <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-300/10 p-4 text-sm text-cyan-50">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="font-medium">Render Cache Warmth</div>
                          <div className="mt-1 text-cyan-100/80">
                            {renderCacheWarmth.total
                              ? `${renderCacheWarmth.percent}% warm · ${renderCacheWarmth.hits} cached voice segment(s), ${renderCacheWarmth.misses} to regenerate`
                              : 'No voice segment cache keys available yet'}
                            {renderCacheWarmth.cloneMisses ? ` · ${renderCacheWarmth.cloneMisses} clone-provider miss(es)` : ''}
                          </div>
                        </div>
                        <span className={`op-badge ${renderCacheWarmth.misses ? 'op-badge-warning' : renderCacheWarmth.total ? 'op-badge-success' : 'op-badge-muted'}`}>
                          {renderCacheWarmth.misses ? 'Warning' : renderCacheWarmth.total ? 'Verified' : 'Missing'}
                        </span>
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                        <div className="h-full rounded-full bg-cyan-300" style={{ width: `${renderCacheWarmth.total ? renderCacheWarmth.percent : 0}%` }} />
                      </div>
                    </div>
                  )}
                  <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                    <div className="flex flex-wrap items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-slate-100">What Changed?</div>
                        <div className="mt-1 text-xs text-slate-400">Cache invalidation summary before queuing the next render.</div>
                      </div>
                      <span className={`op-badge ${renderChangeSummary.some((item) => item.state === 'Warning') ? 'op-badge-warning' : renderChangeSummary.some((item) => item.state === 'Missing') ? 'op-badge-muted' : 'op-badge-success'}`}>
                        {renderChangeSummary.some((item) => item.state === 'Warning') ? 'Warning' : renderChangeSummary.some((item) => item.state === 'Missing') ? 'Missing' : 'Verified'}
                      </span>
                    </div>
                    <div className="mt-3 grid gap-2 md:grid-cols-2">
                      {renderChangeSummary.map((item) => (
                        <div key={item.label} className="rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300">
                          <div className="flex items-center justify-between gap-3">
                            <span className="font-medium text-slate-100">{item.label}</span>
                            <span className={`op-badge ${stateBadgeClass(item.state)}`}>{item.state}</span>
                          </div>
                          <div className="mt-2 text-slate-400">{item.detail}</div>
                          {item.cacheKeys?.length ? (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {item.cacheKeys.map((cacheKey) => (
                                <span key={cacheKey} className="rounded-md border border-cyan-300/20 bg-cyan-300/10 px-2 py-1 font-mono text-[10px] text-cyan-100">
                                  {cacheKey}
                                </span>
                              ))}
                            </div>
                          ) : null}
                        </div>
                      ))}
                    </div>
                  </div>
                  {scriptIsDirty && (
                    <div className="mt-4 rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                      The script has unsaved speaker names or dialogue. Rendering will save this draft first.
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      onClick={() => generatePreview('draft')}
                      disabled={busy === 'generation' || !backgroundAsset || !script || activeGeneration}
                      className="inline-flex items-center gap-2 rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                    >
                      <PlayCircle size={18} />
                      {activeGeneration ? 'Render In Progress' : scriptIsDirty ? 'Save + Render Draft' : 'Render Draft'}
                    </button>
                    <button
                      onClick={() => generatePreview('preview')}
                      disabled={busy === 'generation' || !backgroundAsset || !script || activeGeneration}
                      className="inline-flex items-center gap-2 rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-60"
                    >
                      <PlayCircle size={18} />
                      {activeGeneration ? 'Await Active Render' : scriptIsDirty ? 'Save + Render Preview' : 'Render Preview'}
                    </button>
                    <button
                      onClick={() => generatePreview('final')}
                      disabled={busy === 'generation' || !backgroundAsset || !script || activeGeneration || !project?.approved_at}
                      className="inline-flex items-center gap-2 rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-60"
                    >
                      <Wand2 size={18} />
                      {activeGeneration ? 'Await Active Render' : scriptIsDirty ? 'Save + Final Render' : 'Final Render'}
                    </button>
                    <button
                      onClick={() => generatePreview('debug')}
                      disabled={busy === 'generation' || !backgroundAsset || !script || activeGeneration}
                      className="inline-flex items-center gap-2 rounded-2xl border border-cyan-300/30 px-4 py-3 text-sm text-cyan-100 hover:bg-cyan-300/10 disabled:opacity-60"
                    >
                      <CircleDashed size={18} />
                      {activeGeneration ? 'Await Active Render' : 'Debug Render'}
                    </button>
                  </div>

                  {generationJob && <div className="mt-4">{renderGenerationJobPanel()}</div>}

                  <div className="mt-6 space-y-3">
                    {outputs.map((output) => (
                      <div key={output.id} className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{output.output_kind}</div>
                            <div className="mt-2 font-medium">{output.asset.original_filename}</div>
                            <div className="mt-1 text-sm text-slate-400">{output.provider_name}</div>
                          </div>
                          <div className="text-sm text-slate-400">{output.duration_ms ? `${Math.round(output.duration_ms / 1000)}s` : 'Duration pending'}</div>
                        </div>
                      </div>
                    ))}
                    {!outputs.length && (
                      <div className="rounded-2xl border border-dashed border-white/10 px-4 py-5 text-sm text-slate-500">
                        No renders yet. Render a draft to create the first preview.
                      </div>
                    )}
                  </div>
                </div>
              )}

              {stage === 'Preview' && (
                <div id="step-preview" className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Preview</h2>
                  <p className="mt-2 text-sm text-slate-400">Review the 9:16 production frame, then approve the preview before final render and release.</p>

                  <div className="op-lab-preview-layout mt-5">
                    <ProductionPreviewFrame
                      previewSettings={previewSettings}
                      scriptLines={scriptLines}
                      outputUrl={latestOutput?.asset.content_url || null}
                      outputKind={latestOutput?.output_kind || null}
                      ariaLabel="approved production preview frame"
                    />
                    <div>
                      <ProductionReadinessPanel readiness={productionReadiness} compact />
                      <div className="mt-4 flex flex-wrap gap-3">
                        <button
                          onClick={() => setStage('Render')}
                          className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10"
                        >
                          Open Render
                        </button>
                        <button
                          onClick={approveReview}
                          disabled={!latestReview || busy === 'review-approve'}
                          className="inline-flex items-center gap-2 rounded-2xl bg-emerald-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                        >
                          <CheckCircle2 size={18} />
                          Approve preview
                        </button>
                      </div>
                    </div>
                  </div>

                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      onClick={submitForReview}
                      disabled={!latestOutput || busy === 'review-submit'}
                      className="inline-flex items-center gap-2 rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                    >
                      <MessageSquarePlus size={18} />
                      {busy === 'review-submit' ? 'Submitting...' : 'Submit For Review'}
                    </button>
                  </div>

                  <textarea
                    value={reviewNote}
                    onChange={(event) => setReviewNote(event.target.value)}
                    rows={3}
                    placeholder="Optional reviewer note"
                    className="mt-4 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                  />

                  {latestReview && (
                    <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                      <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{latestReview.status}</div>
                      <div className="mt-2 text-sm text-slate-300">{latestReview.decision_summary || latestReview.rejection_reason || 'Awaiting a review decision.'}</div>

                      <div className="mt-4 space-y-3">
                        {latestReview.comments.map((comment) => (
                          <div key={comment.id} className="rounded-2xl border border-white/10 bg-white/5 p-3 text-sm">
                            <div className="text-xs uppercase tracking-[0.2em] text-slate-400">{comment.kind}</div>
                            <div className="mt-2">{comment.body}</div>
                          </div>
                        ))}
                      </div>

                      <textarea
                        value={reviewComment}
                        onChange={(event) => setReviewComment(event.target.value)}
                        rows={3}
                        placeholder="Add a comment to this review thread"
                        className="mt-4 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
                      />
                      <div className="mt-3 flex flex-wrap gap-3">
                        <button
                          onClick={addReviewComment}
                          disabled={busy === 'review-comment' || !reviewComment.trim()}
                          className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-60"
                        >
                          Add Comment
                        </button>
                        <button
                          onClick={approveReview}
                          disabled={busy === 'review-approve'}
                          className="inline-flex items-center gap-2 rounded-2xl bg-emerald-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                        >
                          <CheckCircle2 size={18} />
                          Approve
                        </button>
                        <button
                          onClick={requestChanges}
                          disabled={busy === 'review-changes'}
                          className="inline-flex items-center gap-2 rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-amber-100 disabled:opacity-60"
                        >
                          <CircleDashed size={18} />
                          Request Changes
                        </button>
                      </div>
                      <textarea
                        value={decisionNote}
                        onChange={(event) => setDecisionNote(event.target.value)}
                        rows={3}
                        className="mt-4 w-full rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
                      />
                    </div>
                  )}
                </div>
              )}

              {stage === 'Release' && (
                <div id="step-release" className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <h2 className="text-xl font-semibold">Platform Metadata</h2>
                      <p className="mt-2 text-sm text-slate-400">Store YouTube-ready metadata now, with generic platform interfaces underneath.</p>
                    </div>
                    <button
                      onClick={suggestMetadata}
                      disabled={busy === 'metadata-suggest'}
                      className="rounded-full border border-white/10 px-4 py-2 text-sm hover:bg-white/10"
                    >
                      Suggest Metadata
                    </button>
                  </div>

                  <div className="mt-4 grid gap-4">
                    <input
                      value={metadata?.title || ''}
                      onChange={(event) =>
                        setMetadata((current) =>
                          current
                            ? { ...current, title: event.target.value }
                            : {
                                id: 0,
                                project_id: id,
                                platform: 'youtube',
                                title: event.target.value,
                                description: '',
                                tags: [],
                                extras: {},
                                validation_errors: [],
                                source: 'manual',
                                updated_at: new Date().toISOString(),
                              }
                        )
                      }
                      placeholder="Video title"
                      className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                    />
                    <textarea
                      value={metadata?.description || ''}
                      onChange={(event) =>
                        setMetadata((current) =>
                          current
                            ? { ...current, description: event.target.value }
                            : {
                                id: 0,
                                project_id: id,
                                platform: 'youtube',
                                title: project?.name || 'Untitled',
                                description: event.target.value,
                                tags: [],
                                extras: {},
                                validation_errors: [],
                                source: 'manual',
                                updated_at: new Date().toISOString(),
                              }
                        )
                      }
                      rows={5}
                      placeholder="Description"
                      className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                    />
                    <input
                      value={(metadata?.tags || []).join(', ')}
                      onChange={(event) =>
                        setMetadata((current) =>
                          current
                            ? { ...current, tags: event.target.value.split(',').map((tag) => tag.trim()).filter(Boolean) }
                            : {
                                id: 0,
                                project_id: id,
                                platform: 'youtube',
                                title: project?.name || 'Untitled',
                                description: '',
                                tags: event.target.value.split(',').map((tag) => tag.trim()).filter(Boolean),
                                extras: {},
                                validation_errors: [],
                                source: 'manual',
                                updated_at: new Date().toISOString(),
                              }
                        )
                      }
                      placeholder="comma, separated, tags"
                      className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                    />
                    <button
                      onClick={saveMetadata}
                      disabled={busy === 'metadata'}
                      className="rounded-2xl bg-white px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                    >
                      {busy === 'metadata' ? 'Saving...' : 'Save Metadata'}
                    </button>
                    {metadata?.validation_errors?.length ? (
                      <div className="rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                        {metadata.validation_errors.join(' ')}
                      </div>
                    ) : null}
                  </div>
                </div>
              )}

              {stage === 'Release' && (
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Destination Routing</h2>
                  <p className="mt-2 text-sm text-slate-400">Recommend the best destination account from project policy, account health, and metadata readiness.</p>
                  <button
                    onClick={loadRoutingSuggestion}
                    className="mt-4 rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950"
                  >
                    Suggest Destination
                  </button>

                  {routing && (
                    <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                      <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{routing.recommended_platform}</div>
                      <div className="mt-2 text-lg font-medium">
                        {routing.social_account_id
                          ? `Recommended account #${routing.social_account_id}`
                          : 'No eligible account available'}
                      </div>
                      <p className="mt-2 text-sm text-slate-400">{routing.reason}</p>
                      <div className="mt-4 grid gap-3 md:grid-cols-2">
                        {routing.eligible_accounts.map((account) => (
                          <div key={account.id} className="rounded-2xl border border-white/10 bg-white/5 p-4">
                            <div className="font-medium">{account.channel_title}</div>
                            <div className="mt-1 text-sm text-slate-400">
                              {account.platform} · {account.account_type} · {account.token_status}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {stage === 'Release' && (
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Publish</h2>
                  <p className="mt-2 text-sm text-slate-400">Choose assisted publish or let the platform auto-route using your saved project policy.</p>

                  <select
                    value={project?.selected_social_account_id || routing?.social_account_id || accounts[0]?.id || ''}
                    onChange={(event) =>
                      apiClient.patch<Project>(`/projects/${id}`, {
                        selected_social_account_id: Number(event.target.value),
                      }).then((response) => setProject(response.data))
                    }
                    className="mt-4 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                  >
                    {accounts.length === 0 && <option value="">Link a YouTube account first</option>}
                    {accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.channel_title} ({account.token_status})
                      </option>
                    ))}
                  </select>

                  <div className="mt-4 flex gap-3">
                    <button
                      onClick={() => setPublishMode('now')}
                      className={`rounded-full px-4 py-2 text-sm ${publishMode === 'now' ? 'bg-cyan-300 text-slate-950' : 'bg-white/5 text-slate-300'}`}
                    >
                      Publish Now
                    </button>
                    <button
                      onClick={() => setPublishMode('schedule')}
                      className={`rounded-full px-4 py-2 text-sm ${publishMode === 'schedule' ? 'bg-cyan-300 text-slate-950' : 'bg-white/5 text-slate-300'}`}
                    >
                      Schedule
                    </button>
                  </div>

                  {publishMode === 'schedule' && (
                    <input
                      type="datetime-local"
                      value={scheduledFor}
                      onChange={(event) => setScheduledFor(event.target.value)}
                      className="mt-4 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                    />
                  )}

                  <div className="mt-6 flex flex-wrap gap-3">
                    <button
                      onClick={() => submitPublishJob('assisted')}
                      disabled={!metadata || !latestOutput || !selectedAccount || project?.status !== 'approved' || busy === 'publish-assisted'}
                      className="rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                    >
                      {busy === 'publish-assisted' ? 'Submitting...' : 'Publish Assisted'}
                    </button>
                    <button
                      onClick={() => submitPublishJob('auto')}
                      disabled={!metadata || !latestOutput || project?.status !== 'approved' || busy === 'publish-auto'}
                      className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-60"
                    >
                      {busy === 'publish-auto' ? 'Submitting...' : 'Auto-Route + Publish'}
                    </button>
                  </div>

                  {publishJob && (
                    <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm text-slate-300">
                      Latest publish job #{publishJob.id}: {publishJob.status}
                      {publishJob.last_error && <div className="mt-2 text-rose-300">{publishJob.last_error}</div>}
                    </div>
                  )}
                </div>
              )}

              {stage === 'Release' && (
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Project History</h2>
                  <div className="mt-6 grid gap-6 lg:grid-cols-2">
                    <div className="space-y-3">
                      <h3 className="text-sm uppercase tracking-[0.3em] text-cyan-200/70">Publish Jobs</h3>
                      {history.jobs.map((job) => (
                        <div key={job.id} className="rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm">
                          <div className="font-medium">#{job.id} · {job.status}</div>
                          <div className="mt-1 text-slate-400">{job.routing_platform} · {job.automation_mode}</div>
                        </div>
                      ))}
                    </div>
                    <div className="space-y-3">
                      <h3 className="text-sm uppercase tracking-[0.3em] text-cyan-200/70">Published Posts</h3>
                      {history.posts.map((post) => (
                        <a
                          key={post.id}
                          href={post.external_url}
                          target="_blank"
                          rel="noreferrer"
                          className="block rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm transition hover:border-cyan-300/40"
                        >
                          <div className="font-medium">{post.external_url}</div>
                          <div className="mt-1 text-slate-400">{post.platform}</div>
                        </a>
                      ))}
                    </div>
                  </div>
                </div>
              )}
            </section>

            <section className="space-y-6">
              <div id="pre-render-preview" className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <div className="flex items-center justify-between gap-4">
                  <div>
                    <h2 className="text-xl font-semibold">Preview Frame</h2>
                    <p className="mt-2 text-sm text-slate-400">Selections update here before any render job is queued.</p>
                  </div>
                  <div className="text-right text-xs uppercase tracking-[0.2em] text-slate-500">
                    {previewSettings.background_source_type || project?.background_source_type || 'draft'}
                  </div>
                </div>

                <div className="mt-4 grid gap-4 lg:grid-cols-[minmax(0,1fr)_13rem]">
                  <ProductionPreviewFrame
                    previewSettings={previewSettings}
                    scriptLines={scriptLines}
                    ariaLabel="pre-render settings preview frame"
                  />

                  <div className="space-y-4">
                    <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                      <div className="text-sm font-medium text-slate-100">Character Size</div>
                      <div className="mt-2 text-2xl font-semibold text-cyan-100">
                        {previewSettings.layout.character_scale.toFixed(2)}x
                      </div>
                      <div className="mt-3 flex gap-2">
                        <button
                          onClick={() => adjustCharacterScale(-0.05)}
                          disabled={previewSettings.layout.character_scale <= 0.75}
                          className="rounded-xl border border-white/10 px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-40"
                        >
                          Smaller
                        </button>
                        <button
                          onClick={() => adjustCharacterScale(0.05)}
                          disabled={previewSettings.layout.character_scale >= 1.5}
                          className="rounded-xl border border-white/10 px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-40"
                        >
                          Larger
                        </button>
                      </div>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                      <div className="text-sm font-medium text-slate-100">Chat Font</div>
                      <div className="mt-2 text-2xl font-semibold text-cyan-100">
                        {previewSettings.layout.chat_font_size_px}px
                      </div>
                      <div className="mt-3 flex gap-2">
                        <button
                          onClick={() => adjustChatFontSize(-1)}
                          disabled={previewSettings.layout.chat_font_size_px <= 12}
                          className="rounded-xl border border-white/10 px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-40"
                        >
                          Smaller
                        </button>
                        <button
                          onClick={() => adjustChatFontSize(1)}
                          disabled={previewSettings.layout.chat_font_size_px >= 32}
                          className="rounded-xl border border-white/10 px-3 py-2 text-sm hover:bg-white/10 disabled:opacity-40"
                        >
                          Larger
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>

              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <h2 className="text-xl font-semibold">Current Output</h2>
                <p className="mt-2 text-sm text-slate-400">The latest render stays centered in a responsive phone-frame preview so review playback matches the rest of the workspace.</p>
                <div className="mt-4 rounded-3xl border border-white/10 bg-[radial-gradient(circle_at_top,_rgba(103,232,249,0.12),_transparent_48%),linear-gradient(180deg,rgba(15,23,42,0.92),rgba(2,6,23,0.96))] p-4 sm:p-5">
                  {latestOutput ? (
                    <div className="mx-auto w-full max-w-[22rem]">
                      <div className="overflow-hidden rounded-[2rem] border border-white/10 bg-black shadow-[0_24px_70px_rgba(2,6,23,0.55)]">
                        <video
                          src={`${apiBase}${latestOutput.asset.content_url}`}
                          controls
                          playsInline
                          preload="metadata"
                          className="aspect-[9/16] w-full bg-black object-contain"
                        />
                      </div>
                      <div className="mt-3 flex items-center justify-between gap-3 text-xs uppercase tracking-[0.24em] text-slate-400">
                        <span>{latestOutput.output_kind}</span>
                        <span>{latestOutput.duration_ms ? `${Math.round(latestOutput.duration_ms / 1000)}s` : 'Duration pending'}</span>
                      </div>
                    </div>
                  ) : (
                    <div className="mx-auto grid aspect-[9/16] w-full max-w-[22rem] place-items-center rounded-[2rem] border border-dashed border-white/10 bg-slate-950/70 text-slate-500">
                      No render output yet.
                    </div>
                  )}
                </div>
                {project?.latest_notifications?.length ? (
                  <div className="mt-4 space-y-2">
                    {project.latest_notifications.map((notification) => (
                      <div key={notification.id} className="rounded-2xl border border-white/10 bg-slate-950/40 p-3 text-sm text-slate-300">
                        {notification.message}
                      </div>
                    ))}
                  </div>
                ) : null}
              </div>

              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <h2 className="text-xl font-semibold">Workflow Snapshot</h2>
                <div className="mt-4 space-y-3 text-sm text-slate-300">
                  <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
                    <span>Status</span>
                    <span>{project?.status}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
                    <span>Automation</span>
                    <span>{project?.automation_mode}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
                    <span>Allowed Platforms</span>
                    <span>{project?.allowed_platforms.join(', ')}</span>
                  </div>
                  <div className="flex items-center justify-between rounded-2xl border border-white/10 bg-slate-950/40 px-4 py-3">
                    <span>Review State</span>
                    <span>{latestReview?.status || 'Not submitted'}</span>
                  </div>
                </div>
              </div>
            </section>
          </div>
        </div>
    </StudioShell>
  );
};

export default ProjectEditorPage;
