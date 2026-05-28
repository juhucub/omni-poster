import React from 'react';

import type { ContentFormatPreset } from '../../api/models';
import { durationLabel, speakerCountLabel } from './formatBrowserData';

type Props = {
  formats: ContentFormatPreset[];
  selectedFormatId: string;
  onSelect: (format: ContentFormatPreset) => void;
  compact?: boolean;
};

export const FormatBrowser: React.FC<Props> = ({ formats, selectedFormatId, onSelect, compact = false }) => (
  <section id="browse-formats" className={compact ? 'space-y-3' : 'space-y-4'} aria-label="Browse content formats">
    <div className="flex flex-wrap items-end justify-between gap-3">
      <div>
        <h3 className="text-lg font-semibold text-slate-100">Browse Formats</h3>
        <p className="mt-1 text-sm text-slate-400">Reusable production shapes for script, speakers, captions, timing, and render readiness.</p>
      </div>
      <span className="rounded-full border border-cyan-300/30 px-3 py-1 text-xs font-medium text-cyan-100">
        {formats.length} presets
      </span>
    </div>
    <div className={`grid gap-3 ${compact ? 'lg:grid-cols-2' : 'md:grid-cols-2 xl:grid-cols-3'}`}>
      {formats.map((format) => {
        const selected = format.id === selectedFormatId;
        return (
          <button
            key={format.id}
            type="button"
            onClick={() => onSelect(format)}
            className={`min-h-64 rounded-lg border p-4 text-left transition ${
              selected
                ? 'border-cyan-300/70 bg-cyan-300/10 text-cyan-50'
                : 'border-white/10 bg-slate-950/45 text-slate-200 hover:border-cyan-300/40 hover:bg-white/10'
            }`}
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <div className="text-base font-semibold">{format.display_name}</div>
                <p className="mt-1 text-sm text-slate-400">{format.short_description}</p>
              </div>
              <span className="shrink-0 rounded-full border border-white/10 px-2 py-1 text-[11px] text-cyan-100">
                Use format
              </span>
            </div>
            <div className="mt-3 grid grid-cols-2 gap-2 text-xs text-slate-300">
              <span className="rounded-md bg-black/25 px-2 py-2">Ideal {durationLabel(format)}</span>
              <span className="rounded-md bg-black/25 px-2 py-2">{speakerCountLabel(format)}</span>
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-400">{format.best_use_case}</p>
            <div className="mt-3 flex flex-wrap gap-2">
              {format.tone_options.slice(0, 4).map((tone) => (
                <span key={tone} className="rounded-full bg-white/10 px-2 py-1 text-[11px] text-slate-200">
                  {tone}
                </span>
              ))}
            </div>
            <div className="mt-3 text-[11px] uppercase tracking-wide text-cyan-200/80">
              {format.section_structure.join(' -> ')}
            </div>
          </button>
        );
      })}
    </div>
  </section>
);

export default FormatBrowser;
