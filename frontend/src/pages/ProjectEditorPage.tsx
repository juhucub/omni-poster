import React, { useEffect, useMemo, useState } from 'react';
import { useParams } from 'react-router-dom';
import { CheckCircle2, PlayCircle, RefreshCw, Upload } from 'lucide-react';

import apiClient from '../api/client';
import type { Asset, GenerationJob, PlatformMetadata, Project, PublishJob, ScriptRevision, SocialAccount } from '../api/models';
import Sidebar from '../components/Sidebar';

const ProjectEditorPage: React.FC = () => {
  const { projectId } = useParams();
  const id = Number(projectId);

  const [project, setProject] = useState<Project | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [script, setScript] = useState<ScriptRevision | null>(null);
  const [scriptDraft, setScriptDraft] = useState('<Host> Welcome to Omni-poster\n<Guest> We keep the script editable all the way through.');
  const [metadata, setMetadata] = useState<PlatformMetadata | null>(null);
  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [generationJob, setGenerationJob] = useState<GenerationJob | null>(null);
  const [publishJob, setPublishJob] = useState<PublishJob | null>(null);
  const [publishMode, setPublishMode] = useState<'now' | 'schedule'>('now');
  const [scheduledFor, setScheduledFor] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const backgroundAsset = useMemo(
    () => assets.find((asset) => asset.kind === 'background_video') || null,
    [assets]
  );
  const selectedAccount = useMemo(
    () => accounts.find((account) => account.id === (project?.selected_social_account_id || accounts[0]?.id)) || null,
    [accounts, project?.selected_social_account_id]
  );

  const toUtcIso = (value: string) => (value ? new Date(value).toISOString() : null);

  const loadAll = async () => {
    try {
      setLoading(true);
      const [projectResponse, assetsResponse, scriptResponse, metadataResponse, accountsResponse] = await Promise.all([
        apiClient.get<Project>(`/projects/${id}`),
        apiClient.get<Asset[]>(`/projects/${id}/assets`),
        apiClient.get<{ current_revision: ScriptRevision | null }>(`/projects/${id}/script`),
        apiClient.get<PlatformMetadata | null>(`/projects/${id}/metadata/youtube`),
        apiClient.get<{ items: SocialAccount[] }>('/social-accounts'),
      ]);
      setProject(projectResponse.data);
      setAssets(assetsResponse.data);
      setScript(scriptResponse.data.current_revision);
      setScriptDraft(scriptResponse.data.current_revision?.raw_text || scriptDraft);
      setMetadata(metadataResponse.data);
      setAccounts(accountsResponse.data.items);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load project editor.');
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

  const saveScript = async () => {
    try {
      setBusy('script');
      const response = await apiClient.put<{ current_revision: ScriptRevision }>(`/projects/${id}/script`, {
        raw_text: scriptDraft,
        source: 'manual',
      });
      setScript(response.data.current_revision);
      await loadAll();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Script validation failed.');
    } finally {
      setBusy(null);
    }
  };

  const generatePreview = async () => {
    try {
      setBusy('generation');
      const response = await apiClient.post<GenerationJob>(`/projects/${id}/generation-jobs`, {
        background_style: project?.background_style || 'none',
      });
      setGenerationJob(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Preview generation failed.');
    } finally {
      setBusy(null);
    }
  };

  const approvePreview = async () => {
    try {
      setBusy('approve');
      const response = await apiClient.post<Project>(`/projects/${id}/approve-preview`);
      setProject(response.data);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Approval failed.');
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

  const submitPublishJob = async () => {
    if (!project?.current_output_video_id || !metadata || !accounts.length) {
      return;
    }
    const selectedAccountId = project.selected_social_account_id || accounts[0].id;
    try {
      setBusy('publish');
      const response = await apiClient.post<PublishJob>(`/projects/${id}/publish-jobs`, {
        social_account_id: selectedAccountId,
        output_video_id: project.current_output_video_id,
        platform_metadata_id: metadata.id,
        publish_mode: publishMode,
        scheduled_for: publishMode === 'schedule' ? toUtcIso(scheduledFor) : null,
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
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">{project?.status}</div>
              <h1 className="mt-2 text-4xl font-semibold">{project?.name}</h1>
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

          <div className="grid gap-6 xl:grid-cols-[1.1fr_0.9fr]">
            <section className="space-y-6">
              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <h2 className="text-xl font-semibold">1. Background Video</h2>
                <p className="mt-2 text-sm text-slate-400">Upload one background video for the current Shorts project.</p>
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
                    {busy === 'upload' ? 'Uploading...' : 'Upload'}
                  </button>
                </div>
                {backgroundAsset && (
                  <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm text-slate-300">
                    Current background: {backgroundAsset.original_filename}
                  </div>
                )}
              </div>

              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <h2 className="text-xl font-semibold">2. Editable Dialogue Script</h2>
                <p className="mt-2 text-sm text-slate-400">Each non-empty line must follow the format `{`<Character> dialogue`}`.</p>
                <textarea
                  value={scriptDraft}
                  onChange={(event) => setScriptDraft(event.target.value)}
                  rows={12}
                  className="mt-4 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-4 font-mono text-sm text-slate-100 focus:border-cyan-300 focus:outline-none"
                />
                <div className="mt-4 flex items-center gap-3">
                  <button
                    onClick={saveScript}
                    disabled={busy === 'script'}
                    className="rounded-2xl bg-white px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                  >
                    {busy === 'script' ? 'Saving...' : 'Save Script'}
                  </button>
                  {script && <span className="text-sm text-slate-400">Current revision #{script.id}</span>}
                </div>
              </div>

              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <h2 className="text-xl font-semibold">3. Metadata</h2>
                    <p className="mt-2 text-sm text-slate-400">Save manual metadata or generate a draft from the script.</p>
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
                              source: 'manual',
                              updated_at: new Date().toISOString(),
                            }
                      )
                    }
                    placeholder="Shorts title"
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
                              source: 'manual',
                              updated_at: new Date().toISOString(),
                            }
                      )
                    }
                    rows={4}
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
                              source: 'manual',
                              updated_at: new Date().toISOString(),
                            }
                      )
                    }
                    placeholder="comma,separated,tags"
                    className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                  />
                  <button
                    onClick={saveMetadata}
                    disabled={busy === 'metadata'}
                    className="rounded-2xl bg-white px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                  >
                    {busy === 'metadata' ? 'Saving...' : 'Save Metadata'}
                  </button>
                </div>
              </div>
            </section>

            <section className="space-y-6">
              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <h2 className="text-xl font-semibold">4. Preview</h2>
                <p className="mt-2 text-sm text-slate-400">Render a project preview after the background and script are ready.</p>
                <div className="mt-4 flex flex-wrap gap-3">
                  <button
                    onClick={generatePreview}
                    disabled={busy === 'generation' || !backgroundAsset || !script}
                    className="inline-flex items-center gap-2 rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                  >
                    <PlayCircle size={18} />
                    {busy === 'generation' ? 'Queueing...' : 'Generate Preview'}
                  </button>
                  <button
                    onClick={approvePreview}
                    disabled={!project?.latest_preview || busy === 'approve'}
                    className="inline-flex items-center gap-2 rounded-2xl border border-emerald-300/40 bg-emerald-400/10 px-4 py-3 font-medium text-emerald-200 disabled:opacity-60"
                  >
                    <CheckCircle2 size={18} />
                    {busy === 'approve' ? 'Approving...' : 'Approve Preview'}
                  </button>
                </div>
                {generationJob && (
                  <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm text-slate-300">
                    Generation job #{generationJob.id}: {generationJob.status} ({generationJob.progress}%)
                    {generationJob.error_message && <div className="mt-2 text-rose-300">{generationJob.error_message}</div>}
                  </div>
                )}
                <div className="mt-4 rounded-3xl overflow-hidden border border-white/10 bg-slate-950/70">
                  {project?.latest_preview ? (
                    <video
                      src={`${process.env.REACT_APP_API_URL || 'http://localhost:8000'}${project.latest_preview.content_url}`}
                      controls
                      className="aspect-[9/16] w-full bg-black object-contain"
                    />
                  ) : (
                    <div className="aspect-[9/16] w-full grid place-items-center text-slate-500">
                      No preview generated yet.
                    </div>
                  )}
                </div>
              </div>

              <div className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
                <h2 className="text-xl font-semibold">5. Publishing</h2>
                <p className="mt-2 text-sm text-slate-400">Select a linked YouTube destination, then publish now or schedule later.</p>
                <div className="mt-4 grid gap-4">
                  <select
                    value={project?.selected_social_account_id || accounts[0]?.id || ''}
                    onChange={(event) =>
                      apiClient.patch<Project>(`/projects/${id}`, {
                        selected_social_account_id: Number(event.target.value),
                      }).then((response) => setProject(response.data))
                    }
                    className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                  >
                    {accounts.length === 0 && <option value="">Link a YouTube account first</option>}
                    {accounts.map((account) => (
                      <option key={account.id} value={account.id}>
                        {account.channel_title} ({account.status})
                      </option>
                    ))}
                  </select>

                  {selectedAccount?.status === 'reconnect_required' && (
                    <div className="rounded-2xl border border-amber-300/30 bg-amber-400/10 px-4 py-3 text-sm text-amber-100">
                      This account needs to reconnect before it can publish.
                    </div>
                  )}

                  <div className="flex gap-3">
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
                      className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                    />
                  )}

                  <button
                    onClick={submitPublishJob}
                    disabled={
                      !project?.current_output_video_id ||
                      !metadata ||
                      accounts.length === 0 ||
                      selectedAccount?.status !== 'linked' ||
                      busy === 'publish'
                    }
                    className="rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
                  >
                    {busy === 'publish' ? 'Submitting...' : publishMode === 'now' ? 'Create Publish Job' : 'Schedule Publish Job'}
                  </button>
                </div>

                {publishJob && (
                  <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm text-slate-300">
                    Latest publish job #{publishJob.id}: {publishJob.status}
                    {publishJob.last_error && <div className="mt-2 text-rose-300">{publishJob.last_error}</div>}
                  </div>
                )}
              </div>
            </section>
          </div>
        </div>
      </main>
    </div>
  );
};

export default ProjectEditorPage;
