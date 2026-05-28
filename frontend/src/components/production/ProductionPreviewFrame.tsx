import React from 'react';

import { apiBaseUrl } from '../../api/client';
import type { ProjectPreviewSettings, ProjectPreviewSpeakerMapping, ScriptLine } from '../../api/models';
import { normalizePreviewSettings } from './ProductionReadinessPanel';

const toApiHref = (url: string | null | undefined) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${apiBaseUrl}${url.startsWith('/') ? url : `/${url}`}`;
};

const initials = (value: string | null | undefined) =>
  String(value || 'OP')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'OP';

export const ProductionPreviewFrame: React.FC<{
  previewSettings: ProjectPreviewSettings | null | undefined;
  scriptLines?: ScriptLine[];
  outputUrl?: string | null;
  outputKind?: string | null;
  className?: string;
  ariaLabel?: string;
}> = ({ previewSettings, scriptLines = [], outputUrl = null, outputKind = null, className = '', ariaLabel = '9:16 production preview' }) => {
  const preview = normalizePreviewSettings(previewSettings);
  const placeholderMapping: ProjectPreviewSpeakerMapping = {
    speaker_name: 'Speaker',
    voice_profile_id: null,
    character_preset_id: null,
    character_display_name: null,
    character_portrait_filename: null,
    character_portrait_url: null,
    display_label: null,
    sample_text: 'Dialogue text will appear here.',
  };
  const mappings = preview.speaker_mappings.length
    ? preview.speaker_mappings
    : [placeholderMapping];
  const firstMapping = mappings[0];
  const bgUrl = toApiHref(preview.background_url);
  const playableUrl = toApiHref(outputUrl);
  const mimeType = String(preview.background_metadata?.mime_type || '');
  const isVideo = mimeType.startsWith('video/');
  const missingScene = !bgUrl;
  const missingScript = scriptLines.length === 0;
  const missingVoice = mappings.some((mapping) => !mapping.voice_profile_id);
  const missingImage = mappings.some((mapping) => !mapping.character_portrait_url && !mapping.character_portrait_filename);
  const scale = preview.speaker_png_size === 'large' ? 1.16 : preview.speaker_png_size === 'compact' ? 0.84 : 1;
  const caption = firstMapping.sample_text || scriptLines[0]?.caption_text || scriptLines[0]?.text || 'Preview captions follow the speaker timeline.';

  return (
    <div className={`op-preview-frame-shell ${className}`}>
      <div className="op-video-frame op-video-frame-large" aria-label={ariaLabel}>
        {playableUrl ? (
          <>
            <video
              className="op-render-playback"
              src={playableUrl}
              controls
              playsInline
              preload="metadata"
              aria-label={`${outputKind || 'render'} playback`}
            />
            <div className="op-render-ready-badge">Playable {outputKind || 'render'}</div>
          </>
        ) : (
          <>
            {bgUrl ? (
              isVideo ? (
                <video className="op-scene-bg" src={bgUrl} muted playsInline preload="metadata" />
              ) : (
                <img className="op-scene-bg" src={bgUrl} alt="" />
              )
            ) : (
              <div className="op-scene-bg" />
            )}
            <div className="op-scene-split-left" />
            <div className="op-scene-split-right" />
            <div className="op-scene-label">
              {String(preview.background_metadata?.original_filename || preview.background_preset_id || 'Select a Scene')}
            </div>
            <div className="op-frame-badge-top">9:16 PREVIEW</div>
            {mappings.slice(0, 2).map((mapping, index) => (
              <div key={mapping.speaker_name} className={`op-speaker-zone ${index === 0 ? 'left' : 'right'}`}>
                <div
                  className={`op-speaker-avatar ${mapping.character_portrait_url ? '' : 'needs-asset'}`}
                  style={{
                    width: `${68 * scale * preview.layout.character_scale}px`,
                    height: `${102 * scale * preview.layout.character_scale}px`,
                  }}
                >
                  {mapping.character_portrait_url ? (
                    <img src={toApiHref(mapping.character_portrait_url)} alt={mapping.character_display_name || mapping.speaker_name} />
                  ) : (
                    <span className="op-speaker-initials">{initials(mapping.character_display_name || mapping.speaker_name)}</span>
                  )}
                </div>
                <div className="op-speaker-label-tag">
                  {mapping.speaker_name.toUpperCase()} · {mapping.voice_profile_id ? 'VOICE READY' : 'VOICE NEEDS ASSIGNMENT'}
                </div>
              </div>
            ))}
            <div className={`op-caption-overlay ${preview.caption_style}`}>
              <div className="op-caption-speaker-tag">{(firstMapping.display_label || firstMapping.speaker_name).toUpperCase()}</div>
              <div className="op-caption-text" style={{ fontSize: `${Math.max(9, Math.round(preview.layout.chat_font_size_px / 1.85))}px` }}>
                {caption}
              </div>
            </div>
            <div className="op-preview-missing-stack">
              {missingScript && <span>Script Missing</span>}
              {missingScene && <span>Scene Missing</span>}
              {missingVoice && <span>Voice Missing</span>}
              {missingImage && <span>Character Image Missing</span>}
            </div>
            <div className="op-frame-timecode">00:00:08:04 · PREVIEW DRAFT</div>
          </>
        )}
      </div>
    </div>
  );
};

export default ProductionPreviewFrame;
