import React, { useEffect, useState } from 'react';
import { Download, ExternalLink, Play } from 'lucide-react';
import { Link } from 'react-router-dom';

import apiClient, { apiBaseUrl } from '../api/client';
import type { GeneratedMediaItem } from '../api/models';
import RenderDiagnosticsPanel from '../components/RenderDiagnosticsPanel';
import StudioShell from '../components/studio/StudioShell';

const toApiHref = (url: string | null | undefined) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${apiBaseUrl}${url}`;
};

const formatBytes = (bytes: number) => {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
};

const GeneratedMediaPage: React.FC = () => {
  const [items, setItems] = useState<GeneratedMediaItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewId, setPreviewId] = useState<number | null>(null);
  const [diagnosticsId, setDiagnosticsId] = useState<number | null>(null);

  const load = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get<{ items: GeneratedMediaItem[] }>('/generated-media?limit=20');
      setItems(response.data.items || []);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load generated media.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void load();
  }, []);

  return (
    <StudioShell mainClassName="studio-detail-surface">
      <div className="mx-auto w-full max-w-7xl space-y-6">
        <div className="studio-page-hero flex items-center justify-between gap-4">
          <div>
            <div className="studio-page-kicker">Generated Media Library</div>
            <h1 className="mt-2">Preview, audit, and export renders</h1>
            <p className="mt-3 max-w-3xl text-sm text-slate-400">
              Browser-facing MP4 outputs with their source production, provider diagnostics, segment audio, and render artifacts.
            </p>
          </div>
          <button onClick={load} className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10">Refresh</button>
        </div>

        {error && <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}
        {loading && <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-6 text-sm text-slate-400">Loading generated media...</div>}

        <div className="grid gap-4">
          {items.map((item) => {
            const output = item.output;
            const asset = output.asset;
            const assetUrl = toApiHref(asset.content_url);
            const isPreviewing = previewId === item.id;
            const diagnosticsOpen = diagnosticsId === item.id;
            return (
              <div key={item.id} className="rounded-3xl border border-white/10 bg-white/[0.04] p-5">
                <div className="grid gap-5 lg:grid-cols-[minmax(220px,320px)_1fr]">
                  <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/30">
                    {asset.mime_type.startsWith('video/') && isPreviewing ? (
                      <video src={assetUrl} controls preload="metadata" className="aspect-[9/16] h-full max-h-96 w-full object-contain" />
                    ) : (
                      <button
                        type="button"
                        onClick={() => setPreviewId(item.id)}
                        className="flex aspect-[9/16] w-full flex-col items-center justify-center gap-3 text-sm text-slate-500 hover:bg-white/5 hover:text-cyan-100"
                      >
                        <Play size={24} />
                        Preview
                      </button>
                    )}
                  </div>
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="text-xs uppercase tracking-[0.2em] text-cyan-200/70">{output.output_kind}</div>
                        <h2 className="mt-2 text-xl font-semibold">{asset.original_filename}</h2>
                        <div className="mt-1 text-sm text-slate-400">{item.project_name} · {item.project_status}</div>
                        <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
                          <span>{output.provider_name}</span>
                          <span>{output.duration_ms ? `${Math.round(output.duration_ms / 1000)}s` : 'Duration pending'}</span>
                          <span>{formatBytes(asset.size_bytes)}</span>
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <a href={assetUrl} className="inline-flex items-center gap-2 rounded-2xl bg-cyan-300 px-4 py-2 text-sm font-medium text-slate-950">
                          <Download size={16} /> Download
                        </a>
                        <Link to={`/projects/${item.project_id}`} className="inline-flex items-center gap-2 rounded-2xl border border-white/10 px-4 py-2 text-sm hover:bg-white/10">
                          <ExternalLink size={16} /> Open
                        </Link>
                        <button
                          type="button"
                          onClick={() => setDiagnosticsId(diagnosticsOpen ? null : item.id)}
                          className="inline-flex items-center gap-2 rounded-2xl border border-white/10 px-4 py-2 text-sm hover:bg-white/10"
                        >
                          {diagnosticsOpen ? 'Hide Logs' : 'View Logs'}
                        </button>
                      </div>
                    </div>
                    {diagnosticsOpen && <div className="mt-4">
                      <RenderDiagnosticsPanel job={item.generation_job} output={output} projectId={item.project_id} />
                    </div>}
                  </div>
                </div>
              </div>
            );
          })}
          {!loading && items.length === 0 && (
            <div className="rounded-3xl border border-dashed border-white/15 bg-slate-950/30 p-6 text-sm text-slate-400">
              No generated media yet. Render a draft or preview from a production to populate this library.
            </div>
          )}
        </div>
      </div>
    </StudioShell>
  );
};

export default GeneratedMediaPage;
