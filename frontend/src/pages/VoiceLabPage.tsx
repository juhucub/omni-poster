import React, { useEffect, useMemo, useState } from 'react';

import apiClient, { apiBaseUrl } from '../api/client';
import type {
  CharacterPreset,
  TTSFailure,
  VoiceLabPreview,
  VoiceProfile,
  VoiceProviderCapability,
} from '../api/models';
import Sidebar from '../components/Sidebar';

const emptyForm = {
  display_name: '',
  speaker_names: 'Host',
  portrait_filename: 'speaker_1.png',
  provider: 'espeak',
  fallback_provider: 'espeak',
  voice: 'en-us+f3',
  rate: 155,
  pitch: 45,
  word_gap: 1,
  amplitude: 140,
  language: 'en',
  notes: '',
  sample_text: "Hey, welcome back. Today we're testing a new character voice.",
  controls: {
    speaking_rate: 1,
    energy: 1,
    pause_length: 1,
    expressiveness: 0.5,
    rhythm: 0.5,
    intonation: 0.5,
    emotion: 'neutral',
    accent: 'default',
  },
};

const VoiceLabPage: React.FC = () => {
  const [presets, setPresets] = useState<CharacterPreset[]>([]);
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [providerCapabilities, setProviderCapabilities] = useState<VoiceProviderCapability[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewProviderPreference, setPreviewProviderPreference] = useState<'auto' | 'openvoice' | 'espeak'>('auto');
  const [form, setForm] = useState(emptyForm);
  const [preview, setPreview] = useState<VoiceLabPreview | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [providerError, setProviderError] = useState<TTSFailure | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [authorizationConfirmed, setAuthorizationConfirmed] = useState(false);
  const [authorizationNote, setAuthorizationNote] = useState('');

  const apiBase = apiBaseUrl;

  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === selectedId) || null,
    [presets, selectedId]
  );

  const selectedVoiceProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedPreset?.voice_profile_id) || null,
    [profiles, selectedPreset?.voice_profile_id]
  );

  const hydrateForm = (preset: CharacterPreset | null, profile: VoiceProfile | null) => {
    if (!preset) {
      setForm(emptyForm);
      return;
    }
    setForm({
      display_name: preset.display_name,
      speaker_names: preset.speaker_names.join(', '),
      portrait_filename: preset.portrait_filename || '',
      provider: preset.tts_provider || 'espeak',
      fallback_provider: preset.fallback_provider || 'espeak',
      voice: preset.voice,
      rate: preset.rate,
      pitch: preset.pitch,
      word_gap: preset.word_gap,
      amplitude: preset.amplitude,
      language: preset.language || profile?.language || 'en',
      notes: preset.notes || '',
      sample_text: preset.sample_text || emptyForm.sample_text,
      controls: {
        ...emptyForm.controls,
        ...(profile?.controls || {}),
        ...(preset.controls || {}),
      },
    });
  };

  const loadCapabilities = async () => {
    const response = await apiClient.get<{ items: VoiceProviderCapability[] }>('/tts/providers');
    setProviderCapabilities(response.data.items);
  };

  const loadVoiceProfiles = async () => {
    const response = await apiClient.get<{ items: VoiceProfile[] }>('/voice-profiles');
    setProfiles(response.data.items);
  };

  const loadPresets = async () => {
    const response = await apiClient.get<{ items: CharacterPreset[] }>('/character-presets');
    setPresets(response.data.items);
    if (!selectedId && response.data.items.length > 0) {
      setSelectedId(response.data.items[0].id);
    }
  };

  const loadAll = async () => {
    try {
      await Promise.all([loadCapabilities(), loadVoiceProfiles(), loadPresets()]);
      setError(null);
      setProviderError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load Voice Lab.');
    }
  };

  useEffect(() => {
    loadAll();
  }, []);

  useEffect(() => {
    hydrateForm(selectedPreset, selectedVoiceProfile);
  }, [selectedPreset, selectedVoiceProfile]);

  const setControl = (key: string, value: string | number) => {
    setForm((current) => ({
      ...current,
      controls: {
        ...current.controls,
        [key]: value,
      },
    }));
  };

  const savePreset = async () => {
    try {
      setBusy('save');
      setProviderError(null);
      const payload = {
        display_name: form.display_name.trim(),
        speaker_names: form.speaker_names
          .split(',')
          .map((value) => value.trim())
          .filter(Boolean),
        portrait_filename: form.portrait_filename.trim() || null,
        tts_provider: form.provider,
        fallback_provider: form.fallback_provider || null,
        model_id: form.provider === 'openvoice' ? 'openvoice_v2' : null,
        language: form.language,
        voice_profile_id: selectedPreset?.voice_profile_id || null,
        voice: form.voice.trim(),
        rate: Number(form.rate),
        pitch: Number(form.pitch),
        word_gap: Number(form.word_gap),
        amplitude: Number(form.amplitude),
        controls: form.controls,
        fallback_voice_settings: {
          voice: form.voice.trim(),
          rate: Number(form.rate),
          pitch: Number(form.pitch),
          word_gap: Number(form.word_gap),
          amplitude: Number(form.amplitude),
        },
        notes: form.notes,
        sample_text: form.sample_text,
      };
      const response = selectedId
        ? await apiClient.put<CharacterPreset>(`/character-presets/${selectedId}`, payload)
        : await apiClient.post<CharacterPreset>('/character-presets', payload);
      setSelectedId(response.data.id);
      setInfo(selectedId ? 'Preset updated.' : 'Preset created.');
      await Promise.all([loadPresets(), loadVoiceProfiles()]);
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
      setInfo('Preset removed.');
      await Promise.all([loadPresets(), loadVoiceProfiles()]);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to delete preset.');
    } finally {
      setBusy(null);
    }
  };

  const prepareVoice = async () => {
    if (!selectedPreset?.voice_profile_id) {
      setError('Save the preset before preparing a voice profile.');
      return;
    }
    try {
      setBusy('prepare');
      await apiClient.post(`/voice-profiles/${selectedPreset.voice_profile_id}/prepare`);
      setInfo('Voice preparation completed or is ready on demand.');
      await loadVoiceProfiles();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setProviderError(detail || null);
      setError(typeof detail === 'string' ? detail : detail?.message || 'Failed to prepare voice.');
    } finally {
      setBusy(null);
    }
  };

  const uploadReferenceAudio = async () => {
    if (!selectedPreset?.voice_profile_id) {
      setError('Save the preset before uploading reference audio.');
      return;
    }
    if (!referenceFile) {
      setError('Choose an audio file first.');
      return;
    }
    try {
      setBusy('upload');
      const formData = new FormData();
      formData.append('voice_profile_id', selectedPreset.voice_profile_id);
      formData.append('authorization_confirmed', String(authorizationConfirmed));
      formData.append('authorization_note', authorizationNote);
      formData.append('file', referenceFile);
      await apiClient.post('/voice-profiles/reference-audio', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setReferenceFile(null);
      setAuthorizationConfirmed(false);
      setAuthorizationNote('');
      setInfo('Reference audio uploaded.');
      await loadVoiceProfiles();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload reference audio.');
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
      setProviderError(null);
      const response = await apiClient.post<VoiceLabPreview>('/voice-lab/preview', {
        preset_id: selectedId,
        provider_preference: previewProviderPreference,
        fallback_allowed: true,
        text: form.sample_text,
        rate: Number(form.rate),
        pitch: Number(form.pitch),
        word_gap: Number(form.word_gap),
        amplitude: Number(form.amplitude),
        controls: form.controls,
      });
      if (response.data.status === 'queued' && response.data.job_id) {
        setPreview(response.data);
        setError(null);
        setInfo('OpenVoice preview queued on the worker.');

        for (let attempt = 0; attempt < 105; attempt += 1) {
          await new Promise((resolve) => window.setTimeout(resolve, 1000));
          const statusResponse = await apiClient.get<VoiceLabPreview>(`/voice-lab/preview-jobs/${response.data.job_id}`);
          setPreview(statusResponse.data);
          if (statusResponse.data.status === 'completed') {
            setInfo('Voice preview generated.');
            return;
          }
          if (statusResponse.data.status === 'failed') {
            const detail = statusResponse.data.error;
            setProviderError(detail || null);
            setError(detail?.message || 'Failed to generate voice preview.');
            return;
          }
        }

        setError('Voice preview is taking unusually long. If the worker does not finish, this preview should be marked failed shortly.');
        setInfo('Preview is still running, but the app will fail it soon if the worker is stuck.');
        return;
      }

      setPreview(response.data);
      setError(null);
      setInfo('Voice preview generated.');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setPreview(null);
      setInfo(null);
      setProviderError(typeof detail === 'object' ? detail : null);
      setError(typeof detail === 'string' ? detail : detail?.message || 'Failed to generate voice preview.');
    } finally {
      setBusy(null);
    }
  };

  const providerState = Object.entries(preview?.provider_state || providerError?.provider_state || {});
  const attemptedProviders = providerError?.attempted_providers || [];
  const providerFailures = Object.entries(providerError?.provider_failures || {});

  return (
    <div className="min-h-screen bg-[#08111f] text-slate-100 flex">
      <Sidebar />
      <main className="flex-1 p-8">
        <div className="max-w-7xl mx-auto grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Character presets</div>
            <h1 className="mt-2 text-4xl font-semibold">Voice Lab</h1>
            <p className="mt-3 text-slate-400">
              Build provider-backed character voices with authorized reference audio, provider-aware previews, and reusable fallback settings for final renders.
            </p>

            {info && <div className="mt-4 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-emerald-200">{info}</div>}
            {error && <div className="mt-4 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-rose-200">{error}</div>}

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => {
                  setSelectedId(null);
                  setPreview(null);
                  setProviderError(null);
                  setInfo(null);
                  hydrateForm(null, null);
                }}
                className="rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950"
              >
                New Preset
              </button>
              <button
                onClick={loadAll}
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
                    setProviderError(null);
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
                        {preset.tts_provider} primary · fallback {preset.fallback_provider || 'none'}
                      </div>
                      <div className="mt-1 text-sm text-slate-500">
                        {preset.voice} · {preset.reference_audio_count} reference clip{preset.reference_audio_count === 1 ? '' : 's'}
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
            </div>

            <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="text-sm font-medium text-slate-200">Provider readiness</div>
              <div className="mt-3 space-y-2">
                {providerCapabilities.map((capability) => (
                  <div key={capability.provider} className="rounded-xl border border-white/10 px-3 py-2 text-sm">
                    <div className="flex items-center justify-between">
                      <span className="font-medium capitalize">{capability.provider}</span>
                      <span className={capability.available ? 'text-emerald-300' : 'text-amber-300'}>
                        {capability.available ? 'Available' : capability.reason || 'Unavailable'}
                      </span>
                    </div>
                    <div className="mt-1 text-xs text-slate-400">
                      {capability.supported_controls.join(', ') || 'No normalized controls reported'}
                    </div>
                  </div>
                ))}
              </div>
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
                Primary Provider
                <select
                  value={form.provider}
                  onChange={(event) => setForm((current) => ({ ...current, provider: event.target.value }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                >
                  <option value="espeak">espeak fallback</option>
                  <option value="openvoice">OpenVoice</option>
                </select>
              </label>
              <label className="text-sm text-slate-300">
                Fallback Provider
                <select
                  value={form.fallback_provider}
                  onChange={(event) => setForm((current) => ({ ...current, fallback_provider: event.target.value }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                >
                  <option value="espeak">espeak</option>
                  <option value="openvoice">OpenVoice</option>
                </select>
              </label>
              <label className="text-sm text-slate-300">
                Language
                <input
                  value={form.language}
                  onChange={(event) => setForm((current) => ({ ...current, language: event.target.value }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                Fallback Voice
                <input
                  value={form.voice}
                  onChange={(event) => setForm((current) => ({ ...current, voice: event.target.value }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                espeak Rate
                <input
                  type="number"
                  value={form.rate}
                  onChange={(event) => setForm((current) => ({ ...current, rate: Number(event.target.value) }))}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
              </label>
              <label className="text-sm text-slate-300">
                espeak Pitch
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

            <div className="mt-6 grid gap-4 md:grid-cols-2">
              <label className="text-sm text-slate-300">
                Speaking Rate
                <input
                  type="range"
                  min="0.6"
                  max="1.4"
                  step="0.05"
                  value={Number(form.controls.speaking_rate)}
                  onChange={(event) => setControl('speaking_rate', Number(event.target.value))}
                  className="mt-3 w-full"
                />
              </label>
              <label className="text-sm text-slate-300">
                Energy
                <input
                  type="range"
                  min="0.4"
                  max="1.6"
                  step="0.05"
                  value={Number(form.controls.energy)}
                  onChange={(event) => setControl('energy', Number(event.target.value))}
                  className="mt-3 w-full"
                />
              </label>
              <label className="text-sm text-slate-300">
                Pause Length
                <input
                  type="range"
                  min="0"
                  max="5"
                  step="0.25"
                  value={Number(form.controls.pause_length)}
                  onChange={(event) => setControl('pause_length', Number(event.target.value))}
                  className="mt-3 w-full"
                />
              </label>
              <label className="text-sm text-slate-300">
                Expressiveness
                <input
                  type="range"
                  min="0"
                  max="1"
                  step="0.05"
                  value={Number(form.controls.expressiveness)}
                  onChange={(event) => setControl('expressiveness', Number(event.target.value))}
                  className="mt-3 w-full"
                />
              </label>
              <label className="text-sm text-slate-300">
                Emotion
                <select
                  value={String(form.controls.emotion)}
                  onChange={(event) => setControl('emotion', event.target.value)}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                >
                  <option value="neutral">Neutral</option>
                  <option value="warm">Warm</option>
                  <option value="serious">Serious</option>
                  <option value="upbeat">Upbeat</option>
                </select>
              </label>
              <label className="text-sm text-slate-300">
                Accent
                <input
                  value={String(form.controls.accent)}
                  onChange={(event) => setControl('accent', event.target.value)}
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
              Preview Text
              <textarea
                value={form.sample_text}
                onChange={(event) => setForm((current) => ({ ...current, sample_text: event.target.value }))}
                rows={4}
                className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
              />
            </label>

            <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="flex items-center justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-slate-100">Reference audio</div>
                  <div className="mt-1 text-sm text-slate-400">
                    Only upload original or explicitly authorized clips. Character-inspired presets are fine; direct copyrighted impersonation workflows are not.
                  </div>
                </div>
                <button
                  onClick={prepareVoice}
                  disabled={!selectedPreset || busy === 'prepare'}
                  className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-50"
                >
                  {busy === 'prepare' ? 'Preparing...' : 'Prepare Voice'}
                </button>
              </div>

              <div className="mt-4 grid gap-4 md:grid-cols-[1fr_auto]">
                <div>
                  <input
                    type="file"
                    accept="audio/*"
                    onChange={(event) => setReferenceFile(event.target.files?.[0] || null)}
                    className="block w-full text-sm text-slate-300"
                  />
                  <label className="mt-3 flex items-center gap-3 text-sm text-slate-300">
                    <input
                      type="checkbox"
                      checked={authorizationConfirmed}
                      onChange={(event) => setAuthorizationConfirmed(event.target.checked)}
                    />
                    I confirm this reference audio is original or explicitly authorized.
                  </label>
                  <input
                    value={authorizationNote}
                    onChange={(event) => setAuthorizationNote(event.target.value)}
                    placeholder="Authorization note or source context"
                    className="mt-3 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm"
                  />
                </div>
                <button
                  onClick={uploadReferenceAudio}
                  disabled={!selectedPreset || busy === 'upload'}
                  className="rounded-2xl bg-sky-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-50"
                >
                  {busy === 'upload' ? 'Uploading...' : 'Upload Clip'}
                </button>
              </div>

              <div className="mt-4 space-y-2">
                {(selectedVoiceProfile?.reference_audios || []).map((clip) => (
                  <div key={clip.id} className="rounded-xl border border-white/10 px-3 py-2 text-sm text-slate-300">
                    <div>{clip.storage_path.split('/').pop()}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {clip.mime_type} · {clip.duration_ms ? `${(clip.duration_ms / 1000).toFixed(2)}s` : 'duration unknown'}
                    </div>
                  </div>
                ))}
                {!selectedVoiceProfile?.reference_audios?.length && (
                  <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-slate-500">
                    No reference clips yet for this voice profile.
                  </div>
                )}
              </div>
            </div>

            <div className="mt-5 flex flex-wrap gap-3">
              <button
                onClick={savePreset}
                disabled={busy === 'save'}
                className="rounded-2xl bg-cyan-300 px-4 py-3 font-medium text-slate-950 disabled:opacity-60"
              >
                {busy === 'save' ? 'Saving...' : selectedId ? 'Save Changes' : 'Create Preset'}
              </button>
              <select
                value={previewProviderPreference}
                onChange={(event) => setPreviewProviderPreference(event.target.value as 'auto' | 'openvoice' | 'espeak')}
                className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
              >
                <option value="auto">Preview: Auto</option>
                <option value="openvoice">Preview: OpenVoice</option>
                <option value="espeak">Preview: espeak fallback</option>
              </select>
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
                {busy === 'delete' ? 'Removing...' : 'Delete Runtime Preset'}
              </button>
            </div>

            <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="text-sm font-medium text-slate-100">Preview response</div>
              {preview ? (
                <div className="mt-4 space-y-3 text-sm text-slate-300">
                  <div>Status: <span className="text-cyan-200">{preview.status}</span></div>
                  {preview.job_id && <div>Job: <span className="text-cyan-200">{preview.job_id}</span></div>}
                  <div className="grid gap-2 md:grid-cols-2">
                    <div>Provider used: <span className="text-cyan-200">{preview.provider_used || 'pending'}</span></div>
                    <div>Fallback used: <span className="text-cyan-200">{preview.fallback_used ? 'Yes' : 'No'}</span></div>
                    <div>Voice profile: <span className="text-cyan-200">{preview.voice_profile_id}</span></div>
                    <div>Reference clips: <span className="text-cyan-200">{preview.reference_audio_count}</span></div>
                  </div>
                  <div className="rounded-xl border border-white/10 bg-black/20 p-3">
                    <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Applied controls</div>
                    <pre className="mt-2 overflow-x-auto text-xs text-slate-300">{JSON.stringify(preview.controls_applied, null, 2)}</pre>
                  </div>
                  {preview.content_url ? (
                    <audio controls src={`${apiBase}${preview.content_url}`} className="w-full" />
                  ) : (
                    <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-slate-500">
                      Audio will appear here once the worker finishes the preview.
                    </div>
                  )}
                </div>
              ) : (
                <div className="mt-3 text-sm text-slate-500">Generate a preview to inspect provider metadata and hear the current profile.</div>
              )}

              {providerError && (
                <div className="mt-4 rounded-xl border border-rose-400/30 bg-rose-500/10 p-3 text-sm text-rose-100">
                  <div className="text-xs uppercase tracking-[0.2em] text-rose-200/80">Preview failure</div>
                  <div className="mt-2 grid gap-2 md:grid-cols-2">
                    <div>Failure code: <span className="text-rose-200">{providerError.code}</span></div>
                    <div>Fallback attempted: <span className="text-rose-200">{providerError.fallback_attempted ? 'Yes' : 'No'}</span></div>
                  </div>
                  {attemptedProviders.length > 0 && (
                    <div className="mt-3">
                      <div className="text-xs uppercase tracking-[0.2em] text-rose-200/80">Attempted providers</div>
                      <div className="mt-2 text-sm text-rose-100">{attemptedProviders.join(' -> ')}</div>
                    </div>
                  )}
                  {providerFailures.length > 0 && (
                    <div className="mt-3">
                      <div className="text-xs uppercase tracking-[0.2em] text-rose-200/80">Provider failures</div>
                      <div className="mt-2 space-y-2">
                        {providerFailures.map(([provider, failure]) => (
                          <div key={provider} className="rounded-xl border border-rose-300/20 bg-black/20 px-3 py-2">
                            <div className="font-medium capitalize text-rose-100">{provider}</div>
                            <pre className="mt-1 overflow-x-auto text-xs text-rose-100/90">{JSON.stringify(failure, null, 2)}</pre>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}

              {providerState.length > 0 && (
                <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Provider state</div>
                  <div className="mt-3 space-y-2 text-sm">
                    {providerState.map(([provider, state]) => (
                      <div key={provider} className="rounded-xl border border-white/10 px-3 py-2">
                        <div className="font-medium capitalize text-slate-200">{provider}</div>
                        <pre className="mt-1 overflow-x-auto text-xs text-slate-400">{JSON.stringify(state, null, 2)}</pre>
                      </div>
                    ))}
                  </div>
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
