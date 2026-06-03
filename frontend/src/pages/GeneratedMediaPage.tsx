import React, { useEffect, useMemo, useState } from 'react';
import { Download, ExternalLink, Play, RefreshCw, Waves } from 'lucide-react';
import { Link } from 'react-router-dom';

import apiClient, { apiBaseUrl } from '../api/client';
import type { GeneratedMediaItem } from '../api/models';
import RenderDiagnosticsPanel from '../components/RenderDiagnosticsPanel';
import StudioShell from '../components/studio/StudioShell';
import {
  StudioButton,
  StudioEmptyState,
  StudioErrorState,
  StudioLoadingState,
  StudioPageHeader,
  StudioPanel,
  StudioStatusBadge,
  StudioTabs,
} from '../components/studio/StudioPrimitives';

type LibraryTab = 'all' | 'finals' | 'drafts' | 'uploads' | 'segments' | 'backgrounds';

type SegmentArtifact = {
  item: GeneratedMediaItem;
  segmentId: string;
  segmentIndex: number | string;
  speaker: string;
  provider: string;
  voiceProfileId: string;
  artifactUrl: string;
  normalizedUrl: string;
  durationSeconds: number | null;
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

const formatBytes = (bytes: number) => {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
};

const statusTone = (status: string): 'ready' | 'warning' | 'failed' | 'info' => {
  if (['completed', 'approved', 'published'].includes(status)) return 'ready';
  if (['failed', 'blocked'].includes(status)) return 'failed';
  if (['queued', 'running', 'processing', 'retrying'].includes(status)) return 'warning';
  return 'info';
};

const extractSegments = (items: GeneratedMediaItem[]): SegmentArtifact[] =>
  items.flatMap((item) => {
    const segments = ((item.generation_job?.tts_result as any)?.segments || []) as Array<Record<string, any>>;
    return segments
      .filter((segment) => segment && (segment.artifact_url || segment.normalized_audio_artifact_url))
      .map((segment, index) => ({
        item,
        segmentId: String(segment.segment_id || `${item.id}-${index}`),
        segmentIndex: segment.segment_index ?? index,
        speaker: String(segment.speaker || 'Unknown speaker'),
        provider: String(segment.provider_used || segment.provider || 'tts'),
        voiceProfileId: String(segment.voice_profile_id || 'No voice profile recorded'),
        artifactUrl: String(segment.artifact_url || ''),
        normalizedUrl: String(segment.normalized_audio_artifact_url || ''),
        durationSeconds: segment.duration_seconds ? Number(segment.duration_seconds) : null,
      }));
  });

const GeneratedMediaPage: React.FC = () => {
  const [items, setItems] = useState<GeneratedMediaItem[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [previewId, setPreviewId] = useState<number | null>(null);
  const [diagnosticsId, setDiagnosticsId] = useState<number | null>(null);
  const [activeTab, setActiveTab] = useState<LibraryTab>('all');

  const load = async () => {
    try {
      setLoading(true);
      const response = await apiClient.get<{ items: GeneratedMediaItem[] }>('/generated-media?limit=50');
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

  const segments = useMemo(() => extractSegments(items), [items]);
  const finals = items.filter((item) => item.output.output_kind === 'final');
  const drafts = items.filter((item) => ['draft', 'preview', 'debug'].includes(item.output.output_kind));
  const visibleItems = activeTab === 'finals' ? finals : activeTab === 'drafts' ? drafts : activeTab === 'all' ? items : [];

  const tabs = [
    { key: 'all', label: 'All', count: items.length },
    { key: 'finals', label: 'Finals', count: finals.length },
    { key: 'drafts', label: 'Drafts', count: drafts.length },
    { key: 'uploads', label: 'Uploads', count: 0 },
    { key: 'segments', label: 'Segment WAVs', count: segments.length },
    { key: 'backgrounds', label: 'Backgrounds', count: 0 },
  ];
  const latestFeatured = activeTab === 'all' ? finals[0] || items[0] || null : null;

  const renderMediaCard = (item: GeneratedMediaItem, variant: 'latest' | 'tile' | 'standard' = 'standard') => {
    const output = item.output;
    const asset = output.asset;
    const assetUrl = toApiHref(asset.content_url);
    const isPreviewing = previewId === item.id;
    const diagnosticsOpen = diagnosticsId === item.id;
    const jobTone = statusTone(item.generation_job?.status || output.output_kind);

    return (
      <article key={`${variant}-${item.id}`} className={`studio-card studio-media-card studio-media-card-${variant}`}>
        <div className="studio-media-thumb">
          {asset.mime_type.startsWith('video/') && isPreviewing ? (
            <video src={assetUrl} controls preload="metadata" />
          ) : (
            <button type="button" onClick={() => setPreviewId(item.id)} aria-label={`Preview ${asset.original_filename}`}>
              <span className="inline-flex items-center gap-2"><Play size={24} /> Preview</span>
            </button>
          )}
        </div>
        <div className="studio-media-meta">
          <div className="studio-media-title-row">
            <div>
              <div className="studio-page-kicker">{titleCase(output.output_kind)}</div>
              <h2>{asset.original_filename}</h2>
              <p>{item.project_name} · {titleCase(item.project_status)}</p>
            </div>
            <StudioStatusBadge tone={jobTone}>{titleCase(item.generation_job?.status || output.output_kind)}</StudioStatusBadge>
          </div>
          <div className="studio-media-facts">
            <StudioStatusBadge tone="info">{output.provider_name}</StudioStatusBadge>
            <StudioStatusBadge tone={output.duration_ms ? 'ready' : 'muted'}>
              {output.duration_ms ? `${Math.round(output.duration_ms / 1000)}s` : 'Duration pending'}
            </StudioStatusBadge>
            <StudioStatusBadge tone="brand">{formatBytes(asset.size_bytes)}</StudioStatusBadge>
          </div>
          <div className="studio-media-actions">
            <div className="studio-artifact-list">
              <a href={assetUrl}><Download size={13} /> Download MP4</a>
              <Link to={`/projects/${item.project_id}`}><ExternalLink size={13} /> Open production</Link>
              <Link to={`/projects/${item.project_id}?tab=release#step-release`}>Release prep</Link>
            </div>
            {variant !== 'tile' && (
              <StudioButton size="sm" onClick={() => setDiagnosticsId(diagnosticsOpen ? null : item.id)}>
                {diagnosticsOpen ? 'Hide diagnostics' : 'Open diagnostics'}
              </StudioButton>
            )}
          </div>
          {diagnosticsOpen && variant !== 'tile' && <RenderDiagnosticsPanel job={item.generation_job} output={output} projectId={item.project_id} />}
        </div>
      </article>
    );
  };

  return (
    <StudioShell mainClassName="studio-detail-surface">
      <div className="mx-auto w-full max-w-7xl space-y-6">
        <StudioTabs tabs={tabs} activeKey={activeTab} onChange={(key) => setActiveTab(key as LibraryTab)} label="Generated media library tabs" />

        <StudioPageHeader
          eyebrow="Generated Media"
          title="Latest render, then the shelf."
          description="Every draft and final artifact reported by the backend lives in one local-first library with source production, diagnostics, segment WAVs, and release handoff."
          meta={
            <>
              <StudioStatusBadge tone="ready">{finals.length} final{finals.length === 1 ? '' : 's'}</StudioStatusBadge>
              <StudioStatusBadge tone="info">{drafts.length} draft{drafts.length === 1 ? '' : 's'}</StudioStatusBadge>
              <StudioStatusBadge tone={segments.length ? 'active' : 'muted'}>{segments.length} segment WAV{segments.length === 1 ? '' : 's'}</StudioStatusBadge>
            </>
          }
          actions={
            <StudioButton onClick={load}>
              <RefreshCw size={16} /> Refresh
            </StudioButton>
          }
        />

        {error && <StudioErrorState message={error} />}
        {loading && <StudioLoadingState label="Loading generated media from the local backend..." />}

        {activeTab === 'segments' && !loading && (
          <StudioPanel
            title="Segment WAVs"
            description="Segment WAVs help verify that final video audio matches the selected voice profiles."
            badge={<StudioStatusBadge tone={segments.length ? 'active' : 'muted'}>{segments.length} available</StudioStatusBadge>}
          >
            {segments.length ? (
              <div className="studio-generated-media-grid">
                {segments.map((segment) => (
                  <div key={`${segment.item.id}-${segment.segmentId}`} className="studio-card studio-tone-active">
                    <div className="studio-media-title-row">
                      <div>
                        <div className="studio-page-kicker">Segment #{segment.segmentIndex}</div>
                        <h2>{segment.speaker}</h2>
                        <p>{segment.item.project_name} · {segment.provider} · {segment.voiceProfileId}</p>
                      </div>
                      <StudioStatusBadge tone="ready">
                        <Waves size={12} /> WAV
                      </StudioStatusBadge>
                    </div>
                    <div className="studio-artifact-list">
                      {segment.artifactUrl && <a href={toApiHref(segment.artifactUrl)}>Original WAV</a>}
                      {segment.normalizedUrl && <a href={toApiHref(segment.normalizedUrl)}>Normalized WAV</a>}
                      <Link to={`/projects/${segment.item.project_id}?tab=render#step-render`}>Open render</Link>
                      <span>{segment.durationSeconds ? `${segment.durationSeconds.toFixed(2)}s` : 'Duration pending'}</span>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <StudioEmptyState
                title="No segment WAV artifacts reported yet."
                description="Render a draft or final production to expose persisted speaker audio segments here."
              />
            )}
          </StudioPanel>
        )}

        {(activeTab === 'uploads' || activeTab === 'backgrounds') && !loading && (
          <StudioEmptyState
            title={activeTab === 'uploads' ? 'No uploaded media is exposed by this library endpoint yet.' : 'No background library endpoint is wired here yet.'}
            description={
              activeTab === 'uploads'
                ? 'Uploads stay attached to their productions until a backend library endpoint reports them globally.'
                : 'Backgrounds are reusable scene assets for future productions, but this page will not invent them without backend data.'
            }
          />
        )}

        {['all', 'finals', 'drafts'].includes(activeTab) && (
          <div className={latestFeatured ? 'studio-media-library-layout' : 'studio-generated-media-grid'}>
            {latestFeatured && (
              <StudioPanel
                className="studio-latest-render-panel"
                title="Latest final render"
                description="Reuse its background, voices, and segments in one click."
                badge={<StudioStatusBadge tone="active">prod_{latestFeatured.project_id}</StudioStatusBadge>}
              >
                {renderMediaCard(latestFeatured, 'latest')}
              </StudioPanel>
            )}
            {visibleItems.length > 0 && (
              <StudioPanel
                className="studio-media-shelf-panel"
                title="Media library"
                description="Drafts, finals, segment WAVs and backgrounds stay reusable across productions."
                badge={<StudioStatusBadge tone="info">Local-first</StudioStatusBadge>}
              >
                <div className="studio-media-tile-grid">
                  {visibleItems.map((item) => renderMediaCard(item, latestFeatured ? 'tile' : 'standard'))}
                </div>
              </StudioPanel>
            )}
            {!loading && visibleItems.length === 0 && !error && (
              <StudioEmptyState
                title={activeTab === 'finals' ? 'No final renders yet.' : activeTab === 'drafts' ? 'No draft renders yet.' : 'No generated media yet.'}
                description={
                  activeTab === 'finals'
                    ? 'Complete a production to build your media library.'
                    : activeTab === 'drafts'
                      ? 'Drafts are useful for timing, captions, and voice checks before final export.'
                      : 'Render a draft or final production to populate this local media library.'
                }
              />
            )}
          </div>
        )}
      </div>
    </StudioShell>
  );
};

export default GeneratedMediaPage;
