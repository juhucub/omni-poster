import React, { useEffect, useMemo, useState } from 'react';
import { ImagePlus, Mic2, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';

import apiClient, { apiBaseUrl } from '../api/client';
import type { CharacterPreset, VoiceProfile } from '../api/models';
import StudioShell from '../components/studio/StudioShell';

const toApiHref = (url: string | null | undefined) => {
  if (!url) return '';
  if (/^https?:\/\//i.test(url)) return url;
  return `${apiBaseUrl}${url}`;
};

const CharacterLibraryPage: React.FC = () => {
  const [characters, setCharacters] = useState<CharacterPreset[]>([]);
  const [voices, setVoices] = useState<VoiceProfile[]>([]);
  const [selectedFiles, setSelectedFiles] = useState<Record<string, File | null>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const voiceById = useMemo(() => new Map(voices.map((voice) => [voice.id, voice])), [voices]);

  const load = async () => {
    try {
      const [charactersResponse, voicesResponse] = await Promise.all([
        apiClient.get<{ items: CharacterPreset[] }>('/character-presets'),
        apiClient.get<{ items: VoiceProfile[] }>('/voice-profiles'),
      ]);
      setCharacters(charactersResponse.data.items || []);
      setVoices(voicesResponse.data.items || []);
      setError(null);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load character library.');
    }
  };

  useEffect(() => {
    void load();
  }, []);

  const uploadPortrait = async (character: CharacterPreset) => {
    const file = selectedFiles[character.id];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    try {
      setBusy(character.id);
      await apiClient.post(`/character-presets/${character.id}/portrait`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setSelectedFiles((current) => ({ ...current, [character.id]: null }));
      await load();
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to upload character portrait.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <StudioShell mainClassName="studio-detail-surface">
      <div className="mx-auto w-full max-w-7xl space-y-6">
        <div className="studio-page-hero flex items-center justify-between gap-4">
          <div>
            <div className="studio-page-kicker">Character Library</div>
            <h1 className="mt-2">Visual speakers and voice links</h1>
            <p className="mt-3 max-w-3xl text-sm text-slate-400">
              Character portraits are visual speaker assets. Voice profiles stay managed in Voice Lab and are only linked for render mapping.
            </p>
          </div>
          <Link to="/voice-lab" className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10">Open Voice Lab</Link>
        </div>

        {error && <div className="rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-sm text-rose-200">{error}</div>}

        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {characters.map((character) => {
            const voice = voiceById.get(character.voice_profile_id);
            const portraitUrl = toApiHref(character.portrait_url);
            const file = selectedFiles[character.id];
            return (
              <div key={character.id} className="rounded-3xl border border-white/10 bg-white/[0.04] p-5">
                <div className="overflow-hidden rounded-2xl border border-white/10 bg-black/30">
                  {portraitUrl ? (
                    <img src={portraitUrl} alt={`${character.display_name} portrait`} className="aspect-square w-full object-contain" />
                  ) : (
                    <div className="flex aspect-square items-center justify-center text-slate-500"><UserRound size={44} /></div>
                  )}
                </div>
                <div className="mt-4">
                  <div className="text-xs uppercase tracking-[0.2em] text-cyan-200/70">{character.source}</div>
                  <h2 className="mt-2 text-xl font-semibold">{character.display_name}</h2>
                  <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-400">
                    {character.speaker_names.map((speaker) => <span key={speaker} className="rounded-full border border-white/10 px-2 py-1">{speaker}</span>)}
                  </div>
                  <div className="mt-4 rounded-2xl border border-white/10 bg-black/20 p-3 text-sm">
                    <div className="flex items-center gap-2 text-slate-100"><Mic2 size={16} /> {voice?.display_name || character.voice_profile_id}</div>
                    <div className="mt-1 text-xs text-slate-400">{character.tts_provider} provider · fallback {character.fallback_provider || 'none'}</div>
                  </div>
                  <div className="mt-4 space-y-2">
                    <label className="block text-xs uppercase tracking-[0.2em] text-slate-500">Character image / portrait</label>
                    <input
                      type="file"
                      accept="image/png,image/jpeg,image/webp"
                      onChange={(event) => setSelectedFiles((current) => ({ ...current, [character.id]: event.target.files?.[0] || null }))}
                      className="w-full rounded-2xl border border-white/10 bg-slate-950/60 px-3 py-2 text-sm"
                    />
                    <button
                      type="button"
                      onClick={() => uploadPortrait(character)}
                      disabled={!file || busy === character.id}
                      className="inline-flex w-full items-center justify-center gap-2 rounded-2xl bg-cyan-300 px-4 py-3 text-sm font-medium text-slate-950 disabled:opacity-60"
                    >
                      <ImagePlus size={16} /> {busy === character.id ? 'Uploading...' : 'Save Portrait'}
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
          {characters.length === 0 && (
            <div className="rounded-3xl border border-dashed border-white/15 bg-slate-950/30 p-6 text-sm text-slate-400">
              No characters are available yet. Create a voice profile or character preset to begin speaker mapping.
            </div>
          )}
        </div>
      </div>
    </StudioShell>
  );
};

export default CharacterLibraryPage;
