import React from 'react';
import { Link } from 'react-router-dom';

import { apiBaseUrl } from '../api/client';
import type { GenerationJob, OutputVideo } from '../api/models';

const toApiHref = (url: string | null | undefined) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${apiBaseUrl}${url}`;
};

const titleCase = (value: string | null | undefined) =>
  String(value || '')
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase());

const objectValues = (value: unknown): any[] => {
  if (!value || typeof value !== 'object') return [];
  return Object.values(value as Record<string, unknown>) as any[];
};

export const RenderDiagnosticsPanel: React.FC<{
  job: GenerationJob | null;
  output?: OutputVideo | null;
  projectId?: number | string | null;
  compact?: boolean;
}> = ({ job, output = null, projectId = null, compact = false }) => {
  if (!job) return null;

  const ttsResult = (job.tts_result || {}) as any;
  const assembly = (ttsResult.assembly || {}) as any;
  const segments = ((ttsResult.segments || []) as any[]).filter(Boolean);
  const ttsError = ttsResult.error || null;
  const artifactUrls = (job.artifact_urls || {}) as any;
  const cacheStats = (job.cache_statistics || {}) as any;
  const performance = (job.performance_summary || (ttsResult.performance_summary || {})) as any;
  const voiceEntries = objectValues((job.voice_manifest as any)?.speakers);
  const mp4Url = output?.asset?.content_url ? toApiHref(output.asset.content_url) : '';

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-950/40 p-4 text-sm text-slate-300">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="font-medium text-slate-100">Render job #{job.id}</div>
          <div className="mt-1 text-xs text-slate-400">
            {titleCase(job.status)} · {job.progress}% · {job.current_phase || job.output_kind}
          </div>
        </div>
        {projectId && (
          <Link to={`/projects/${projectId}`} className="text-xs text-cyan-200 hover:text-cyan-100">
            Open production
          </Link>
        )}
      </div>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-cyan-300 transition-[width] duration-500" style={{ width: `${Math.max(0, Math.min(100, job.progress || 0))}%` }} />
      </div>
      {job.error_message && <div className="mt-3 rounded-xl border border-rose-300/30 bg-rose-950/30 p-3 text-rose-100">{job.error_message}</div>}
      {ttsError && (
        <div className="mt-3 rounded-xl border border-rose-300/30 bg-rose-950/30 p-3 text-rose-100">
          <div className="font-medium">{ttsError.message || ttsError.code || 'TTS provider failed.'}</div>
          {ttsError.suggested_action && <div className="mt-1 text-rose-200/80">{ttsError.suggested_action}</div>}
        </div>
      )}

      <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3 text-xs text-slate-300">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>Cache: {Number(cacheStats.hits || 0)} hits · {Number(cacheStats.misses || 0)} misses</div>
          <div className="flex flex-wrap gap-3">
            {artifactUrls.render_plan && <a href={toApiHref(String(artifactUrls.render_plan))} className="text-cyan-200 hover:text-cyan-100">Render plan</a>}
            {artifactUrls.cache_report && <a href={toApiHref(String(artifactUrls.cache_report))} className="text-cyan-200 hover:text-cyan-100">Cache report</a>}
            {artifactUrls.render_profile && <a href={toApiHref(String(artifactUrls.render_profile))} className="text-cyan-200 hover:text-cyan-100">Timing profile</a>}
            {assembly.composite_audio_artifact_url && <a href={toApiHref(assembly.composite_audio_artifact_url)} className="text-cyan-200 hover:text-cyan-100">Composite WAV</a>}
            {assembly.final_video_audio_artifact_url && <a href={toApiHref(assembly.final_video_audio_artifact_url)} className="text-cyan-200 hover:text-cyan-100">Final audio WAV</a>}
            {mp4Url && <a href={mp4Url} className="text-cyan-200 hover:text-cyan-100">Download MP4</a>}
          </div>
        </div>
      </div>

      {Object.keys(performance).length > 0 && (
        <div className="mt-3 rounded-xl border border-cyan-300/20 bg-cyan-300/10 p-3 text-xs text-cyan-50">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <div className="font-medium">Draft performance summary</div>
              <div className="mt-1 text-cyan-100/80">
                {performance.total_seconds ? `${Number(performance.total_seconds).toFixed(1)}s total` : 'Timing pending'}
                {performance.exceeded_60s_target === true ? ' · exceeded 60s draft target' : performance.exceeded_60s_target === false ? ' · within 60s draft target' : ''}
                {performance.top_bottleneck ? ` · bottleneck: ${titleCase(performance.top_bottleneck)}` : ''}
              </div>
            </div>
            {performance.peak_rss_mb && <div>{Number(performance.peak_rss_mb).toFixed(0)} MB peak RSS</div>}
          </div>
          {performance.next_optimization_hint && <div className="mt-2 text-cyan-100/80">{String(performance.next_optimization_hint)}</div>}
        </div>
      )}

      {!compact && (
        <details className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
          <summary className="cursor-pointer text-xs font-medium uppercase tracking-[0.2em] text-cyan-200">
            Advanced render diagnostics
          </summary>
          {voiceEntries.length > 0 && (
            <div className="mt-3 grid gap-2 md:grid-cols-2">
              {voiceEntries.map((entry: any) => (
                <div key={entry.speaker} className="rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="font-medium text-slate-100">{entry.speaker}</div>
                  <div className="mt-1 text-xs text-slate-400">{entry.character_display_name || 'Unmapped visual'} · {entry.provider || 'tts'}</div>
                  <div className="mt-1 text-xs text-cyan-200">{entry.voice_profile_id || 'ephemeral fallback voice'}</div>
                </div>
              ))}
            </div>
          )}

          {segments.length > 0 && (
            <div className="mt-3 rounded-xl border border-white/10 bg-black/20 p-3">
              <div className="text-xs uppercase tracking-[0.2em] text-slate-500">Provider segments</div>
              <div className="mt-2 grid gap-2 md:grid-cols-2">
                {segments.map((segment: any) => (
                  <a
                    key={segment.segment_id || `${segment.segment_index}-${segment.speaker}`}
                    href={toApiHref(segment.artifact_url)}
                    className="rounded-lg border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/10"
                  >
                    <div className="font-medium text-slate-100">#{segment.segment_index} {segment.speaker} · {segment.provider_used}</div>
                    <div className="mt-1 text-cyan-200">{segment.voice_profile_id || 'fallback profile'}</div>
                    <div className="mt-1 text-slate-500">
                      {segment.duration_seconds ? `${Number(segment.duration_seconds).toFixed(2)}s` : 'duration unknown'}
                      {segment.fallback_used ? ' · fallback used' : ''}
                      {segment.tts_cache_hit ? ' · cache hit' : ''}
                    </div>
                    {segment.normalized_audio_artifact_url && <div className="mt-1 text-cyan-200">Normalized WAV available</div>}
                  </a>
                ))}
              </div>
            </div>
          )}

          <pre className="mt-3 max-h-64 overflow-auto rounded-xl border border-white/10 bg-slate-950/70 p-3 text-xs text-slate-400">
            {JSON.stringify(
              {
                provider_state: job.provider_state,
                voice_manifest: job.voice_manifest,
                timing_breakdown: job.timing_breakdown,
                performance_summary: job.performance_summary,
                debug_artifacts: job.debug_artifacts,
              },
              null,
              2
            )}
          </pre>
        </details>
      )}
    </div>
  );
};

export default RenderDiagnosticsPanel;
