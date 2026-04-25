import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
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
  GenerationJob,
  OutputVideo,
  PlatformMetadata,
  Project,
  PublishJob,
  PublishedPost,
  ReviewQueueItem,
  RoutingSuggestion,
  SpeakerBinding,
  ScriptLine,
  ScriptRevision,
  SocialAccount,
} from '../api/models';
import Sidebar from '../components/Sidebar';

const STAGES = ['Assets', 'Script', 'Generate', 'Review', 'Metadata', 'Routing', 'Publish', 'History'] as const;
type Stage = (typeof STAGES)[number];

const defaultScript = '<Host> Welcome to Omni-poster.\n<Guest> We can keep revising this conversation before it ships.';

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

const ProjectEditorPage: React.FC = () => {
  const { projectId } = useParams();
  const id = Number(projectId);

  const [stage, setStage] = useState<Stage>('Assets');
  const [project, setProject] = useState<Project | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [presets, setPresets] = useState<BackgroundPreset[]>([]);
  const [characterPresets, setCharacterPresets] = useState<CharacterPreset[]>([]);
  const [script, setScript] = useState<ScriptRevision | null>(null);
  const [scriptRevisions, setScriptRevisions] = useState<ScriptRevision[]>([]);
  const [scriptDraft, setScriptDraft] = useState(defaultScript);
  const [scriptLines, setScriptLines] = useState<ScriptLine[]>(parseDraftToLines(defaultScript));
  const [scriptPrompt, setScriptPrompt] = useState('an explainer about why short-form distribution pipelines need review');
  const [metadata, setMetadata] = useState<PlatformMetadata | null>(null);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [outputs, setOutputs] = useState<OutputVideo[]>([]);
  const [reviews, setReviews] = useState<ReviewQueueItem[]>([]);
  const [routing, setRouting] = useState<RoutingSuggestion | null>(null);
  const [history, setHistory] = useState<{ jobs: PublishJob[]; posts: PublishedPost[] }>({ jobs: [], posts: [] });
  const [speakerBindings, setSpeakerBindings] = useState<SpeakerBinding[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(null);
  const [publishJob, setPublishJob] = useState<PublishJob | null>(null);
  const [publishMode, setPublishMode] = useState<'now' | 'schedule'>('now');
  const [scheduledFor, setScheduledFor] = useState('');
  const [reviewNote, setReviewNote] = useState('');
  const [reviewComment, setReviewComment] = useState('');
  const [decisionNote, setDecisionNote] = useState('Looks good for publish.');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

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
  const savedDraft = useMemo(() => normalizeDraft(script?.raw_text || defaultScript), [script?.raw_text]);
  const scriptIsDirty = useMemo(() => normalizeDraft(scriptDraft) !== savedDraft, [scriptDraft, savedDraft]);
  const detectedSpeakers = useMemo(() => {
    const names = (scriptLines.length ? scriptLines : script?.parsed_lines || []).map((line) => line.speaker.trim()).filter(Boolean);
    return Array.from(new Set(names));
  }, [script?.parsed_lines, scriptLines]);

  const toUtcIso = (value: string) => (value ? new Date(value).toISOString() : null);
  const apiBase = apiBaseUrl;

  const hydrateScriptState = (revision: ScriptRevision | null) => {
    setScript(revision);
    const nextDraft = revision?.raw_text || defaultScript;
    const nextLines = revision?.parsed_lines?.length ? revision.parsed_lines : parseDraftToLines(nextDraft);
    setScriptDraft(nextDraft);
    setScriptLines(nextLines);
  };

  const loadAll = async () => {
    try {
      setLoading(true);
      const [
        projectResponse,
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
      ] = await Promise.all([
        apiClient.get<Project>(`/projects/${id}`),
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
      ]);

      setProject(projectResponse.data);
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
      try {
        const activeGenerationResponse = await apiClient.get<GenerationJob>(`/projects/${id}/generation-jobs/active`);
        setGenerationJob(activeGenerationResponse.data);
      } catch (activeErr: any) {
        if (activeErr.response?.status === 404) {
          setGenerationJob(null);
        } else {
          throw activeErr;
        }
      }
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load project workspace.');
    } finally {
      setLoading(false);
    }
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
          await loadAll();
          setStage('Review');
        }
      } catch {
        window.clearInterval(timer);
      }
    }, 1500);

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
      await apiClient.post(`/projects/${id}/assets/background`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
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
      await apiClient.post(`/projects/${id}/assets/background/preset/${presetKey}`);
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Background preset selection failed.');
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
      const response = await apiClient.post<{ current_revision: ScriptRevision }>(`/projects/${id}/script/generate`, {
        prompt: scriptPrompt,
        character_names: scriptLines.slice(0, 2).map((line) => line.speaker).filter(Boolean),
        tone: 'explanatory',
      });
      hydrateScriptState(response.data.current_revision);
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Script generation failed.');
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
      } else {
        nextBindings.push({
          id: 0,
          speaker_name: speakerName,
          character_preset_id: characterPresetId,
          character_display_name: preset.display_name,
          voice_profile_id: preset.voice_profile_id,
          provider: preset.tts_provider,
        });
      }
      await saveSpeakerBindings(nextBindings);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save speaker binding.');
    } finally {
      setBusy(null);
    }
  };

  const generatePreview = async (outputKind: 'preview' | 'final' = 'preview') => {
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
      setStage('Publish');
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

  if (loading) {
    return (
      <div className="min-h-screen bg-[#08111f] text-white flex">
        <Sidebar />
        <main className="flex-1 p-8">Loading project...</main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="max-w-7xl mx-auto space-y-6">
          <div className="flex items-center justify-between gap-4">
            <div>
              <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{project?.status}</div>
              <h1 className="mt-2 text-4xl font-semibold">{project?.name}</h1>
              <p className="mt-3 max-w-3xl text-slate-400">
                Stage the asset, refine the dialogue, render a preview, move it through human review, then publish in assisted or automatic mode.
              </p>
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

          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-4">
            <div className="grid gap-3 md:grid-cols-4 xl:grid-cols-8">
              {STAGES.map((item) => (
                <button
                  key={item}
                  onClick={() => setStage(item)}
                  className={`rounded-2xl px-4 py-3 text-sm font-medium transition ${
                    stage === item ? 'bg-cyan-300 text-slate-950' : 'bg-slate-950/50 text-slate-300 hover:bg-white/10'
                  }`}
                >
                  {item}
                </button>
              ))}
            </div>
          </section>

          <div className="grid gap-6 xl:grid-cols-[1.15fr_0.85fr]">
            <section className="space-y-6">
              {stage === 'Assets' && (
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Background Source</h2>
                  <p className="mt-2 text-sm text-slate-400">Upload a background video or pick a curated preset for the current project.</p>
                  <div className="mt-4 flex flex-col gap-3 md:flex-row">
                    <input
                      type="file"
                      accept="video/mp4,video/webm,video/mpeg"
                      onChange={(event) => setSelectedFile(event.target.files?.[0] || null)}
                      className="block w-full rounded-2xl border border-white/10 bg-slate-950/50 px-4 py-4 text-sm"
                    />
                    <button
                      onClick={uploadBackground}
                      disabled={!selectedFile || busy === 'upload'}
                      className="inline-flex items-center justify-center gap-2 rounded-2xl bg-cyan-300 px-5 py-4 font-medium text-slate-950 disabled:opacity-60"
                    >
                      <Upload size={18} />
                      {busy === 'upload' ? 'Uploading...' : 'Upload Background'}
                    </button>
                  </div>

                  <div className="mt-6 grid gap-3 md:grid-cols-2">
                    {presets.length === 0 && (
                      <div className="rounded-2xl border border-dashed border-white/15 bg-slate-950/30 p-4 text-sm text-slate-400">
                        No bundled presets are available yet. Add `.mp4` files under `backend/storage/presets`, then rebuild the Docker containers to refresh the gallery.
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
                          {busy === `preset-${preset.key}` ? 'Selecting...' : 'Use Preset'}
                        </button>
                      </div>
                    ))}
                  </div>

                  {backgroundAsset && (
                    <div className="mt-6 rounded-2xl border border-emerald-300/20 bg-emerald-400/10 p-4 text-sm text-emerald-100">
                      Selected background: {backgroundAsset.original_filename} ({project?.background_source_type})
                    </div>
                  )}
                </div>
              )}

              {stage === 'Script' && (
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <h2 className="text-xl font-semibold">Dialogue Script</h2>
                      <p className="mt-2 text-sm text-slate-400">Keep the canonical format <code>&lt;Character&gt; dialogue</code>, with line-level edits and revision history.</p>
                    </div>
                    <button
                      onClick={generateScript}
                      disabled={busy === 'script-generate'}
                      className="inline-flex items-center gap-2 rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10"
                    >
                      <Sparkles size={16} />
                      {busy === 'script-generate' ? 'Generating...' : 'Generate Draft'}
                    </button>
                  </div>

                  {scriptIsDirty && (
                    <div className="mt-4 rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                      The dialogue has unsaved changes. Rendering will now save the latest speaker names and lines automatically before queueing a job.
                    </div>
                  )}

                  <input
                    value={scriptPrompt}
                    onChange={(event) => setScriptPrompt(event.target.value)}
                    placeholder="Prompt for AI-assisted script generation"
                    className="mt-4 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                  />

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

              {stage === 'Generate' && (
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Render Outputs</h2>
                  <p className="mt-2 text-sm text-slate-400">Queue a preview render for review or a higher-confidence final output once the draft is stable.</p>
                  <div className="mt-4 rounded-2xl border border-cyan-300/20 bg-cyan-400/10 p-4 text-sm text-cyan-100">
                    Detected cast: {(script?.characters || scriptLines.map((line) => line.speaker)).slice(0, 2).join(' vs ') || 'Add two dialogue speakers first'}.
                    The local renderer now voices each line and pops the active speaker portrait. It checks bundled character PNGs in <code>backend/storage/characters</code> first using <code>&lt;speaker&gt;.png</code> or <code>speaker_1.png</code> and <code>speaker_2.png</code>, then falls back to runtime overrides and finally generated portraits.
                  </div>
                  <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                    <div className="flex items-center justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-slate-100">Speaker Voice Bindings</div>
                        <div className="mt-1 text-sm text-slate-400">
                          Final generation uses these explicit preset bindings so Voice Lab previews and renders stay consistent.
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 space-y-3">
                      {detectedSpeakers.map((speakerName) => {
                        const binding = speakerBindings.find((item) => item.speaker_name === speakerName);
                        return (
                          <div key={speakerName} className="grid gap-3 rounded-2xl border border-white/10 bg-black/20 p-3 md:grid-cols-[0.4fr_0.6fr]">
                            <div>
                              <div className="text-sm font-medium text-slate-200">{speakerName}</div>
                              <div className="mt-1 text-xs text-slate-500">
                                {binding ? `${binding.character_display_name} · ${binding.provider}` : 'No preset selected yet'}
                              </div>
                            </div>
                            <select
                              value={binding?.character_preset_id || ''}
                              onChange={(event) => updateSpeakerBinding(speakerName, event.target.value)}
                              className="rounded-xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm"
                            >
                              <option value="" disabled>
                                Select a character preset
                              </option>
                              {characterPresets.map((preset) => (
                                <option key={preset.id} value={preset.id}>
                                  {preset.display_name} · {preset.tts_provider}
                                </option>
                              ))}
                            </select>
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
                  {scriptIsDirty && (
                    <div className="mt-4 rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                      The script editor has unsaved character names or dialogue. Generate will save this draft first so preset matching uses the latest speaker names.
                    </div>
                  )}
                  <div className="mt-4 flex flex-wrap gap-3">
                    <button
                      onClick={() => generatePreview('preview')}
                      disabled={busy === 'generation' || !backgroundAsset || !script || activeGeneration}
                      className="inline-flex items-center gap-2 rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                    >
                      <PlayCircle size={18} />
                      {activeGeneration ? 'Render In Progress' : busy === 'generation' ? 'Saving + Queueing...' : scriptIsDirty ? 'Save + Generate Preview' : 'Generate Preview'}
                    </button>
                    <button
                      onClick={() => generatePreview('final')}
                      disabled={busy === 'generation' || !backgroundAsset || !script || activeGeneration}
                      className="inline-flex items-center gap-2 rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-60"
                    >
                      <Wand2 size={18} />
                      {activeGeneration ? 'Await Active Render' : scriptIsDirty ? 'Save + Generate Final Pass' : 'Generate Final Pass'}
                    </button>
                  </div>

                  {generationJob && (
                    <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm text-slate-300">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <span>
                          Render job #{generationJob.id}: {generationJob.status} ({generationJob.progress}%)
                        </span>
                        {generationStage ? <span className="text-cyan-200">{generationStage}</span> : null}
                      </div>
                      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
                        <div className="h-full rounded-full bg-cyan-300 transition-[width] duration-500" style={{ width: `${generationJob.progress}%` }} />
                      </div>
                      {generationJob.error_message && <div className="mt-2 text-rose-300">{generationJob.error_message}</div>}
                    </div>
                  )}

                  <div className="mt-6 space-y-3">
                    {outputs.map((output) => (
                      <div key={output.id} className="rounded-2xl border border-white/10 bg-slate-950/40 p-4">
                        <div className="flex items-center justify-between gap-4">
                          <div>
                            <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{output.output_kind}</div>
                            <div className="mt-2 font-medium">{output.asset.original_filename}</div>
                            <div className="mt-1 text-sm text-slate-400">{output.provider_name}</div>
                          </div>
                          <div className="text-sm text-slate-400">{output.duration_ms ? `${Math.round(output.duration_ms / 1000)}s` : 'Unknown duration'}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {stage === 'Review' && (
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                  <h2 className="text-xl font-semibold">Human Review Queue</h2>
                  <p className="mt-2 text-sm text-slate-400">Submit the latest output for human review, discuss changes, and explicitly approve or request revisions.</p>

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

              {stage === 'Metadata' && (
                <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
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

              {stage === 'Routing' && (
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

              {stage === 'Publish' && (
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

              {stage === 'History' && (
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
      </main>
    </div>
  );
};

export default ProjectEditorPage;
