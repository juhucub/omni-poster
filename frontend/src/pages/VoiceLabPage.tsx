import React, { useEffect, useMemo, useState } from 'react';

import apiClient, { apiBaseUrl } from '../api/client';
import type { CharacterPreset, VoiceLabPreview } from '../api/models';
import Sidebar from '../components/Sidebar';

const emptyPreset = {
  display_name: '',
  speaker_names: 'Host',
  portrait_filename: 'speaker_1.png',
  voice: 'en-us+f3',
  rate: 155,
  pitch: 45,
  word_gap: 1,
  amplitude: 140,
  notes: '',
  sample_text: "Hey, welcome back. Today we're testing a new character voice.",
};

const VoiceLabPage: React.FC = () => {
  const [presets, setPresets] = useState<CharacterPreset[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [form, setForm] = useState(emptyPreset);
  const [preview, setPreview] = useState<VoiceLabPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const apiBase = apiBaseUrl;

  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === selectedId) || null,
    [presets, selectedId]
  );

  const hydrateForm = (preset: CharacterPreset | null) => {
    if (!preset) {
      setForm(emptyPreset);
      return;
    }
    setForm({
      display_name: preset.display_name,
      speaker_names: preset.speaker_names.join(', '),
      portrait_filename: preset.portrait_filename || '',
      voice: preset.voice,
      rate: preset.rate,
      pitch: preset.pitch,
      word_gap: preset.word_gap,
      amplitude: preset.amplitude,
      notes: preset.notes || '',
      sample_text: preset.sample_text || emptyPreset.sample_text,
    });
  };

  const loadPresets = async () => {
    try {
      const response = await apiClient.get<{ items: CharacterPreset[] }>('/character-presets');
      setPresets(response.data.items);
      setError(null);
      if (!selectedId && response.data.items.length > 0) {
        setSelectedId(response.data.items[0].id);
        hydrateForm(response.data.items[0]);
      } else if (selectedId) {
        const next = response.data.items.find((preset) => preset.id === selectedId) || null;
        hydrateForm(next);
      }
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load character presets.');
    }
  };

  useEffect(() => {
    loadPresets();
  }, []);

  useEffect(() => {
    hydrateForm(selectedPreset);
  }, [selectedPreset]);

  const savePreset = async () => {
    try {
      setBusy('save');
      const payload = {
        display_name: form.display_name.trim(),
        speaker_names: form.speaker_names
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
        portrait_filename: form.portrait_filename.trim() || null,
        tts_provider: 'espeak',
        voice: form.voice.trim(),
        rate: Number(form.rate),
        pitch: Number(form.pitch),
        word_gap: Number(form.word_gap),
        amplitude: Number(form.amplitude),
        notes: form.notes,
        sample_text: form.sample_text,
      };
      const response = selectedId
        ? await apiClient.put<CharacterPreset>(`/character-presets/${selectedId}`, payload)
        : await apiClient.post<CharacterPreset>('/character-presets', payload);
      setSelectedId(response.data.id);
      setInfo(selectedId ? 'Preset updated.' : 'Preset created.');
      await loadPresets();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save preset.');
    } finally {
      setBusy(null);
    }
  };

  const deletePreset = async () => {
    if (!selectedPreset) {
      return;
    }
    try {
      setBusy('delete');
      await apiClient.delete(`/character-presets/${selectedPreset.id}`);
      setSelectedId(null);
      setPreview(null);
      setInfo('Preset removed from runtime overrides.');
      await loadPresets();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete preset.');
    } finally {
      setBusy(null);
    }
  };

  const runPreview = async () => {
    if (!selectedId) {
      setError('Save the preset first before generating a preview.');
      return;
    }
    try {
      setBusy('preview');
      const response = await apiClient.post<VoiceLabPreview>('/voice-lab/preview', {
        preset_id: selectedId,
        text: form.sample_text,
        rate: Number(form.rate),
        pitch: Number(form.pitch),
        word_gap: Number(form.word_gap),
        amplitude: Number(form.amplitude),
      });
      setPreview(response.data);
      setInfo('Voice preview generated.');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to generate voice preview.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="max-w-7xl mx-auto grid gap-6 xl:grid-cols-[0.95fr_1.05fr]">
          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Character presets</div>
            <h1 className="mt-2 text-4xl font-semibold">Voice Lab</h1>
            <p className="mt-3 text-slate-400">
              Tune reusable character voices beside the main app flow, pair them with speaker portraits, and test short lines before using them in renders.
            </p>

            {info && <div className="mt-4 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-emerald-200">{info}</div>}
            {error && <div className="mt-4 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-rose-200">{error}</div>}

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => {
                  setSelectedId(null);
                  setPreview(null);
                  setInfo(null);
                  hydrateForm(null);
                }}
                className="rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950"
              >
                New Preset
              </button>
              <button
                onClick={loadPresets}
                className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10"
              >
                Refresh
              </button>
            </div>

            <div className="mt-6 space-y-3">
              {presets.map((preset) => (
                <button
                  key={preset.id}
                  onClick={() => {
                    setSelectedId(preset.id);
                    setPreview(null);
                    setInfo(null);
                  }}
                  className={`w-full rounded-2xl border p-4 text-left transition ${
                    selectedId === preset.id
                      ? 'border-cyan-300/60 bg-cyan-300/10'
                      : 'border-white/10 bg-slate-950/40 hover:bg-white/10'
                  }`}
                >
                  <div className="flex items-center justify-between gap-4">
                    <div>
                      <div className="text-xs uppercase tracking-[0.25em] text-cyan-200/70">{preset.source}</div>
                      <div className="mt-2 text-lg font-medium">{preset.display_name}</div>
                      <div className="mt-1 text-sm text-slate-400">
                        {preset.voice} · rate {preset.rate} · pitch {preset.pitch}
                      </div>
                    </div>
                    {preset.portrait_url && (
                      <img
                        src={`${apiBase}${preset.portrait_url}`}
                        alt={preset.display_name}
                        className="h-20 w-16 rounded-xl border border-white/10 bg-slate-950/50 object-cover"
                      />
                    )}
                  </div>
                </button>
              ))}
              {presets.length === 0 && (
                <div className="rounded-2xl border border-dashed border-white/15 bg-slate-950/30 p-4 text-sm text-slate-400">
                  No character presets yet. Create one here or seed bundled defaults in <code>backend/storage/character_presets.json</code>.
                </div>
              )}
            </div>
          </section>

          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <div className="grid gap-4 md:grid-cols-2">
              <label className="text-sm text-slate-300">
                Display Name
                <input
                  value={form.display_name}
                  onChange={(event) => setForm((current) => ({ ...current, display_name: event.target.value }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                Speaker Aliases
                <input
                  value={form.speaker_names}
                  onChange={(event) => setForm((current) => ({ ...current, speaker_names: event.target.value }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                Portrait Filename
                <input
                  value={form.portrait_filename}
                  onChange={(event) => setForm((current) => ({ ...current, portrait_filename: event.target.value }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                Voice
                <input
                  value={form.voice}
                  onChange={(event) => setForm((current) => ({ ...current, voice: event.target.value }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                Rate
                <input
                  type="number"
                  value={form.rate}
                  onChange={(event) => setForm((current) => ({ ...current, rate: Number(event.target.value) }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                Pitch
                <input
                  type="number"
                  value={form.pitch}
                  onChange={(event) => setForm((current) => ({ ...current, pitch: Number(event.target.value) }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                Word Gap
                <input
                  type="number"
                  value={form.word_gap}
                  onChange={(event) => setForm((current) => ({ ...current, word_gap: Number(event.target.value) }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                Amplitude
                <input
                  type="number"
                  value={form.amplitude}
                  onChange={(event) => setForm((current) => ({ ...current, amplitude: Number(event.target.value) }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
            </div>

            <label className="mt-4 block text-sm text-slate-300">
              Notes
              <textarea
                value={form.notes}
                onChange={(event) => setForm((current) => ({ ...current, notes: event.target.value }))}
                rows={3}
                className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
              />
            </label>

            <label className="mt-4 block text-sm text-slate-300">
              Sample Text
              <textarea
                value={form.sample_text}
                onChange={(event) => setForm((current) => ({ ...current, sample_text: event.target.value }))}
                rows={5}
                className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
              />
            </label>

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                onClick={savePreset}
                disabled={busy === 'save'}
                className="rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
              >
                {busy === 'save' ? 'Saving...' : selectedId ? 'Save Changes' : 'Create Preset'}
              </button>
              <button
                onClick={runPreview}
                disabled={busy === 'preview' || !selectedId}
                className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-60"
              >
                {busy === 'preview' ? 'Generating Preview...' : 'Generate Voice Preview'}
              </button>
              <button
                onClick={deletePreset}
                disabled={busy === 'delete' || !selectedPreset || selectedPreset.source === 'bundled'}
                className="rounded-2xl border border-rose-400/30 px-4 py-3 text-sm text-rose-200 hover:bg-rose-500/10 disabled:opacity-40"
              >
                {busy === 'delete' ? 'Removing...' : selectedPreset?.source === 'bundled' ? 'Bundled Preset' : 'Delete Runtime Preset'}
              </button>
            </div>

            <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/40 p-5">
              <div className="text-xs uppercase tracking-[0.25em] text-cyan-200/70">Testing loop</div>
              <p className="mt-2 text-sm text-slate-400">
                Keep a stable sample line here, tweak one parameter at a time, and compare short previews before promoting a preset into real project renders.
              </p>
              {preview && (
                <div className="mt-4 space-y-3">
                  <div className="text-sm text-slate-300">
                    Preview voice: {preview.voice} · {preview.duration_seconds.toFixed(2)}s
                  </div>
                  <audio controls className="w-full" src={`${apiBase}${preview.content_url}`}>
                    Your browser does not support audio preview.
                  </audio>
                </div>
              )}
            </div>
          </section>
        </div>
      </main>
    </div>
  );
};

export default VoiceLabPage;
