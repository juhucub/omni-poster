import React, { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import apiClient, { apiBaseUrl } from '../api/client';
import type {
  CharacterPreset,
  Project,
  TTSFailure,
  VoiceCalibrationBatch,
  VoiceCalibrationMatrix,
  VoiceLabPreview,
  VoiceOperationJob,
  VoiceProfile,
  VoiceProviderCapability,
} from '../api/models';
import StudioShell from '../components/studio/StudioShell';

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

const fixedTestPhrases = [
  "I need this line to sound calm, specific, and unmistakably like me.",
  "Wait, pause there. The rhythm matters more than the words.",
  "That is the difference between a generic voice and a real character.",
];

const VoiceLabPage: React.FC = () => {
  const [searchParams] = useSearchParams();
  const [presets, setPresets] = useState<CharacterPreset[]>([]);
  const [profiles, setProfiles] = useState<VoiceProfile[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [providerCapabilities, setProviderCapabilities] = useState<VoiceProviderCapability[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [previewProviderPreference, setPreviewProviderPreference] = useState<'auto' | 'openvoice' | 'xtts' | 'rvc' | 'espeak'>('auto');
  const [form, setForm] = useState(emptyForm);
  const [preview, setPreview] = useState<VoiceLabPreview | null>(null);
  const [calibrationItems, setCalibrationItems] = useState<VoiceLabPreview[]>([]);
  const [calibrationUnsupported, setCalibrationUnsupported] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [providerError, setProviderError] = useState<TTSFailure | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [referenceFile, setReferenceFile] = useState<File | null>(null);
  const [authorizationConfirmed, setAuthorizationConfirmed] = useState(false);
  const [authorizationNote, setAuthorizationNote] = useState('');
  const [characterSlug, setCharacterSlug] = useState('');
  const [modelPath, setModelPath] = useState('');
  const [characterBatch, setCharacterBatch] = useState<VoiceCalibrationBatch | null>(null);

  const apiBase = apiBaseUrl;
  const toApiHref = (path: string | null | undefined) => {
    if (!path) {
      return '#';
    }
    if (/^https?:\/\//i.test(path)) {
      return path;
    }
    return `${apiBase}${path.startsWith('/') ? path : `/${path}`}`;
  };

  const selectedPreset = useMemo(
    () => presets.find((preset) => preset.id === selectedId) || null,
    [presets, selectedId]
  );

  const selectedVoiceProfile = useMemo(
    () => profiles.find((profile) => profile.id === selectedPreset?.voice_profile_id) || null,
    [profiles, selectedPreset?.voice_profile_id]
  );

  const selectedProviderCapability = useMemo(
    () => providerCapabilities.find((capability) => capability.provider === form.provider) || null,
    [providerCapabilities, form.provider]
  );
  const selectedAssociatedImageUrl = selectedVoiceProfile?.associated_character_image_url || selectedPreset?.portrait_url || null;
  const linkedProductionId = searchParams.get('productionId');
  const linkedSpeakerId = searchParams.get('speakerId');

  const supportedControls = useMemo(
    () => new Set((selectedProviderCapability?.supported_controls || []).map((item) => String(item))),
    [selectedProviderCapability]
  );

  // Provider metadata is the bridge between Voice Lab prep and Video Lab render snapshots.
  const embeddingStatus = String(
    selectedVoiceProfile?.provider_metadata?.['embedding_status'] ||
      (selectedVoiceProfile?.embedding_path ? 'ready' : selectedVoiceProfile?.reference_audio_count ? 'not_prepared' : 'pending_reference_audio')
  );
  const embeddingReady = Boolean(
    selectedVoiceProfile?.provider_metadata?.['embedding_ready'] ?? selectedVoiceProfile?.embedding_path
  );
  const activeReferenceCount = Number(
    selectedVoiceProfile?.provider_metadata?.['active_reference_count'] ?? selectedVoiceProfile?.reference_audio_count ?? 0
  );
  const referenceAudioMode = String(
    selectedVoiceProfile?.provider_metadata?.['reference_audio_mode'] ||
      (activeReferenceCount > 1 ? 'average_all_clips' : activeReferenceCount === 1 ? 'single_clip' : 'none')
  );
  const unsupportedControls = Array.isArray(selectedVoiceProfile?.provider_metadata?.['unsupported_controls'])
    ? selectedVoiceProfile?.provider_metadata?.['unsupported_controls'].map((item) => String(item))
    : [];
  const selectedRecipeStatus = (selectedVoiceProfile?.provider_metadata?.['selected_recipe_status'] || {}) as Record<string, unknown>;
  const goldenPreviewUrl = String(selectedVoiceProfile?.provider_metadata?.['golden_preview_url'] || selectedRecipeStatus['golden_preview_url'] || '');
  const recipeReady = Boolean(selectedRecipeStatus['ready_for_test_render']);
  const recipeError = selectedRecipeStatus['error'] as { code?: string; message?: string } | undefined;
  const selectedProfileUsage = useMemo(
    () =>
      projects
        .flatMap((project) =>
          (project.speaker_bindings || [])
            .filter((binding) => binding.voice_profile_id === selectedVoiceProfile?.id)
            .map((binding) => ({ project, binding }))
        ),
    [projects, selectedVoiceProfile?.id]
  );

  const supportsControl = (controlName: string) => supportedControls.has(controlName);

  const calibrationRecipe = (item: VoiceLabPreview) =>
    (item.calibration?.['recipe'] || {}) as Record<string, unknown>;

  const calibrationUnsupportedControls = (item: VoiceLabPreview) =>
    Array.isArray(item.calibration?.['unsupported_controls'])
      ? (item.calibration['unsupported_controls'] as unknown[]).map((value) => String(value))
      : [];

  const calibrationSupportedControls = (item: VoiceLabPreview) =>
    Array.isArray(item.calibration?.['supported_controls'])
      ? (item.calibration['supported_controls'] as unknown[]).map((value) => String(value))
      : [];

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
        // Keep saved profile controls when returning from Video Lab while filling any new UI controls.
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

  const loadProjects = async () => {
    const response = await apiClient.get<{ items: Project[] }>('/projects');
    setProjects(response.data.items || []);
  };

  const loadAll = async () => {
    try {
      await Promise.all([loadCapabilities(), loadVoiceProfiles(), loadPresets(), loadProjects()]);
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
    const profileId = searchParams.get('profileId');
    if (!profileId || !presets.length) {
      return;
    }
    const matchingPreset = presets.find((preset) => preset.voice_profile_id === profileId);
    if (matchingPreset && selectedId !== matchingPreset.id) {
      setSelectedId(matchingPreset.id);
    }
  }, [presets, searchParams, selectedId]);

  useEffect(() => {
    hydrateForm(selectedPreset, selectedVoiceProfile);
    setCharacterSlug(selectedVoiceProfile?.character_slug || selectedPreset?.display_name?.toLowerCase().replace(/[^a-z0-9]+/g, '_') || '');
    setModelPath(selectedVoiceProfile?.model_checkpoint_path || '');
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
        character_slug: characterSlug.trim() || null,
        model_checkpoint_path: modelPath.trim() || null,
        selected_recipe: selectedVoiceProfile?.selected_recipe || {},
        voice: form.voice.trim(),
        rate: Number(form.rate),
        pitch: Number(form.pitch),
        word_gap: Number(form.word_gap),
        amplitude: Number(form.amplitude),
        controls: form.controls,
        style: {
          ...(selectedVoiceProfile?.style || {}),
          base_speaker: selectedVoiceProfile?.base_speaker || selectedVoiceProfile?.style?.['base_speaker'] || null,
          style_preset: selectedVoiceProfile?.style_preset || selectedVoiceProfile?.style?.['style_preset'] || 'default',
        },
        pace: Number(form.controls.speaking_rate || 1),
        energy: Number(form.controls.energy || 1),
        pause_bias: Number(form.controls.pause_length || 1),
        emotion: String(form.controls.emotion || 'neutral'),
        accent: String(form.controls.accent || 'default'),
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

  const voiceOperationMessage = (job: VoiceOperationJob, fallback: string) => {
    const detail = job.error?.detail;
    if (typeof detail === 'string') {
      return detail;
    }
    if (detail && typeof detail === 'object' && 'message' in detail) {
      return String((detail as Record<string, unknown>).message);
    }
    return typeof job.error?.message === 'string' ? job.error.message : fallback;
  };

  const pollVoiceOperation = async (job: VoiceOperationJob, successMessage: string) => {
    let current = job;
    setInfo(`${successMessage} Queued on the voice worker.`);
    for (let attempt = 0; attempt < 105; attempt += 1) {
      if (current.status === 'completed') {
        setInfo(successMessage);
        return current;
      }
      if (current.status === 'failed') {
        throw new Error(voiceOperationMessage(current, 'Voice operation failed.'));
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      const response = await apiClient.get<VoiceOperationJob>(`/voice-lab/operations/${current.id}`);
      current = response.data;
    }
    setInfo('Voice operation is still running on the worker.');
    return current;
  };

  const prepareVoice = async () => {
    if (!selectedPreset?.voice_profile_id) {
      setError('Save the preset before preparing a voice profile.');
      return;
    }
    try {
      setBusy('prepare');
      const response = await apiClient.post<VoiceOperationJob>(`/voice-profiles/${selectedPreset.voice_profile_id}/prepare`);
      await pollVoiceOperation(response.data, 'Voice preparation completed or is ready on demand.');
      await loadVoiceProfiles();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setProviderError(detail || null);
      setError(typeof detail === 'string' ? detail : detail?.message || err.message || 'Failed to prepare voice.');
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
      const response = await apiClient.post<VoiceOperationJob>('/voice-profiles/reference-audio', formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await pollVoiceOperation(response.data, 'Reference audio uploaded and processed.');
      setReferenceFile(null);
      setAuthorizationConfirmed(false);
      setAuthorizationNote('');
      await loadVoiceProfiles();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || err.message || 'Failed to upload reference audio.');
    } finally {
      setBusy(null);
    }
  };

  const ensureReferenceDataset = async () => {
    if (!selectedVoiceProfile) {
      throw new Error('Save the preset before creating a reference dataset.');
    }
    if (selectedVoiceProfile.reference_dataset_id && selectedVoiceProfile.reference_datasets?.length) {
      return selectedVoiceProfile.reference_dataset_id;
    }
    const response = await apiClient.post(`/voice-profiles/${selectedVoiceProfile.id}/reference-datasets`, {
      display_name: `${selectedVoiceProfile.display_name} reference dataset`,
      character_slug: characterSlug || selectedVoiceProfile.character_slug || selectedVoiceProfile.display_name,
    });
    await loadVoiceProfiles();
    return response.data.dataset.id as number;
  };

  const uploadDatasetClip = async () => {
    if (!selectedVoiceProfile) {
      setError('Save the preset before uploading dataset clips.');
      return;
    }
    if (!referenceFile) {
      setError('Choose an audio file first.');
      return;
    }
    try {
      setBusy('dataset-upload');
      const datasetId = await ensureReferenceDataset();
      const formData = new FormData();
      formData.append('authorization_confirmed', String(authorizationConfirmed));
      formData.append('authorization_note', authorizationNote);
      formData.append('file', referenceFile);
      const response = await apiClient.post<VoiceOperationJob>(`/voice-profiles/${selectedVoiceProfile.id}/reference-datasets/${datasetId}/clips`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      await pollVoiceOperation(response.data, 'Character dataset clip uploaded and processed.');
      setReferenceFile(null);
      setAuthorizationConfirmed(false);
      setAuthorizationNote('');
      await loadVoiceProfiles();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || err.message || 'Failed to upload dataset clip.');
    } finally {
      setBusy(null);
    }
  };

  const analyzeReferenceDataset = async () => {
    if (!selectedVoiceProfile?.reference_dataset_id) {
      setError('Create or upload a character dataset first.');
      return;
    }
    try {
      setBusy('dataset-analyze');
      const response = await apiClient.post<VoiceOperationJob>(`/voice-profiles/${selectedVoiceProfile.id}/reference-datasets/${selectedVoiceProfile.reference_dataset_id}/analyze`);
      await pollVoiceOperation(response.data, 'Reference dataset analyzed.');
      await loadVoiceProfiles();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || err.message || 'Failed to analyze reference dataset.');
    } finally {
      setBusy(null);
    }
  };

  const attachCharacterModel = async () => {
    if (!selectedVoiceProfile) {
      setError('Save the preset before attaching a model.');
      return;
    }
    if (!modelPath.trim()) {
      setError('Enter a model/checkpoint path first.');
      return;
    }
    try {
      setBusy('attach-model');
      const response = await apiClient.post<VoiceOperationJob>(`/voice-profiles/${selectedVoiceProfile.id}/models/attach`, {
        provider: form.provider === 'rvc' ? 'rvc' : form.provider === 'openvoice' ? 'openvoice' : 'xtts',
        character_slug: characterSlug.trim() || selectedVoiceProfile.character_slug || null,
        model_checkpoint_path: modelPath.trim(),
        reference_dataset_id: selectedVoiceProfile.reference_dataset_id,
        recipe: selectedVoiceProfile.selected_recipe || {},
      });
      await pollVoiceOperation(response.data, 'Character model attached.');
      await loadVoiceProfiles();
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || err.message || 'Failed to attach character model.');
    } finally {
      setBusy(null);
    }
  };

  const characterCalibrationCandidates = () => {
    const selectedProvider = form.provider === 'rvc' ? 'rvc' : form.provider === 'openvoice' ? 'openvoice' : 'xtts';
    const checkpointPath = modelPath || selectedVoiceProfile?.model_checkpoint_path || undefined;
    const baseRate = Number(form.controls.speaking_rate || 1);
    const pitchShift = Number((form.controls as Record<string, unknown>).pitch || 0);
    const pauseScale = Number(form.controls.pause_length || 1);
    const energyNormalization = Number(form.controls.energy || 1);

    if (selectedProvider === 'xtts') {
      const speedFactors = [0.92, 1.0, 1.08];
      const temperatures = [0.55, 0.7, 0.85];
      // XTTS calibration sweeps speed and temperature because those settings materially change character delivery.
      const xttsCandidates = speedFactors.flatMap((speedFactor) =>
        temperatures.map((temperature) => ({
          provider: 'xtts',
          rate: Number((baseRate * speedFactor).toFixed(2)),
          temperature,
          split_sentences: true,
          pitch_shift: pitchShift,
          pause_scale: pauseScale,
          energy_normalization: energyNormalization,
          model_checkpoint_path: checkpointPath,
          openvoice_tone_color: false,
        }))
      );
      return [
        ...xttsCandidates,
        { provider: 'openvoice', rate: 1, temperature: 0.7, split_sentences: true, openvoice_tone_color: true },
      ];
    }

    return [
      {
        provider: selectedProvider,
        rate: baseRate,
        temperature: 0.7,
        split_sentences: true,
        pitch_shift: pitchShift,
        pause_scale: pauseScale,
        energy_normalization: energyNormalization,
        model_checkpoint_path: checkpointPath,
        openvoice_tone_color: selectedProvider === 'openvoice',
      },
      { provider: 'openvoice', rate: 1, temperature: 0.7, split_sentences: true, openvoice_tone_color: true },
      { provider: 'rvc', rate: 1, rvc_index_rate: 0.75, model_checkpoint_path: checkpointPath },
    ];
  };

  const runCharacterCalibrationBatch = async () => {
    if (!selectedVoiceProfile) {
      setError('Save the preset before generating character calibration previews.');
      return;
    }
    try {
      setBusy('character-calibration');
      const response = await apiClient.post<VoiceCalibrationBatch>('/voice-lab/calibration-batches', {
        voice_profile_id: selectedVoiceProfile.id,
        reference_dataset_id: selectedVoiceProfile.reference_dataset_id,
        calibration_script: form.sample_text,
        candidates: characterCalibrationCandidates(),
      });
      setCharacterBatch(response.data);
      setInfo(`Character calibration batch ${response.data.id} queued on the voice worker.`);
      let current = response.data;
      for (let attempt = 0; attempt < 105; attempt += 1) {
        if (current.status === 'completed') {
          setCharacterBatch(current);
          setInfo(`Character calibration batch ${current.id} completed with ${current.rankings.length} ranked matches.`);
          return;
        }
        if (current.status === 'failed') {
          setCharacterBatch(current);
          const message = typeof current.error?.message === 'string' ? current.error.message : 'Failed to generate character calibration batch.';
          setError(message);
          return;
        }
        await new Promise((resolve) => window.setTimeout(resolve, 1000));
        const statusResponse = await apiClient.get<VoiceCalibrationBatch>(`/voice-lab/calibration-batches/${current.id}`);
        current = statusResponse.data;
        setCharacterBatch(current);
      }
      setInfo('Character calibration is still running on the voice worker.');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : detail?.message || 'Failed to generate character calibration batch.');
    } finally {
      setBusy(null);
    }
  };

  const saveCharacterRecipe = async (recipe: Record<string, unknown>) => {
    if (!selectedVoiceProfile) {
      return;
    }
    try {
      setBusy('save-character-recipe');
      await apiClient.post(`/voice-profiles/${selectedVoiceProfile.id}/calibration-recipe`, { recipe });
      setInfo('Character replication recipe saved.');
      await Promise.all([loadPresets(), loadVoiceProfiles()]);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save character recipe.');
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
        setInfo('Voice preview queued on the worker.');

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

  const pollPreviewJobs = async (items: VoiceLabPreview[]) => {
    let currentItems = items;
    for (let attempt = 0; attempt < 105; attempt += 1) {
      const pending = currentItems.filter((item) => item.job_id && ['queued', 'processing'].includes(item.status));
      if (pending.length === 0) {
        return currentItems;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
      const updates = await Promise.all(
        pending.map((item) => apiClient.get<VoiceLabPreview>(`/voice-lab/preview-jobs/${item.job_id}`))
      );
      const updateMap = new Map(updates.map((response) => [response.data.job_id, response.data]));
      currentItems = currentItems.map((item) => updateMap.get(item.job_id) || item);
      setCalibrationItems(currentItems);
    }
    return currentItems;
  };

  const runCalibrationMatrix = async () => {
    if (!selectedId) {
      setError('Save the preset first before generating a calibration matrix.');
      return;
    }
    try {
      setBusy('calibration');
      setProviderError(null);
      const response = await apiClient.post<VoiceCalibrationMatrix>('/voice-lab/calibration-matrix', {
        preset_id: selectedId,
        provider_preference: 'openvoice',
        fallback_allowed: false,
        phrases: fixedTestPhrases,
      });
      setCalibrationItems(response.data.items);
      setCalibrationUnsupported(response.data.unsupported_controls || []);
      setInfo(`Queued ${response.data.items.length} calibration previews.`);
      const settledItems = await pollPreviewJobs(response.data.items);
      const failed = settledItems.find((item) => item.status === 'failed');
      if (failed?.error) {
        setProviderError(failed.error);
        setError(failed.error.message || 'One or more calibration previews failed.');
        return;
      }
      setInfo('Calibration previews generated.');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      setCalibrationItems([]);
      setCalibrationUnsupported([]);
      setProviderError(typeof detail === 'object' ? detail : null);
      setError(typeof detail === 'string' ? detail : detail?.message || 'Failed to generate calibration matrix.');
    } finally {
      setBusy(null);
    }
  };

  const saveCalibrationRecipe = async (item: VoiceLabPreview) => {
    const recipe = calibrationRecipe(item);
    if (!item.voice_profile_id || Object.keys(recipe).length === 0) {
      setError('Calibration item is missing a recipe.');
      return;
    }
    try {
      setBusy(`save-calibration-${item.job_id || 'recipe'}`);
      await apiClient.post(`/voice-profiles/${item.voice_profile_id}/calibration-recipe`, { recipe });
      setInfo('Calibration recipe saved to the voice profile.');
      await Promise.all([loadPresets(), loadVoiceProfiles()]);
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to save calibration recipe.');
    } finally {
      setBusy(null);
    }
  };

  const providerState = Object.entries(preview?.provider_state || providerError?.provider_state || {});
  const attemptedProviders = providerError?.attempted_providers || [];
  const providerFailures = Object.entries(providerError?.provider_failures || {});

  return (
    <StudioShell mainClassName="studio-detail-surface">
      <div className="max-w-7xl mx-auto w-full space-y-6">
        <div className="studio-page-hero flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="studio-page-kicker">Voice Lab</div>
            <h1 className="mt-2">Voice cast profiles</h1>
            <p className="mt-3 max-w-3xl text-sm text-slate-400">
              Build reusable character voices, then bind them into productions without breaking render provenance.
            </p>
            <div className="studio-quick-links mt-4">
              <Link className="studio-link-pill" to="/">Command Room</Link>
              {linkedProductionId && <Link className="studio-link-pill" to={`/projects/${linkedProductionId}?tab=voices`}>Back to Production</Link>}
              {linkedSpeakerId && <span className="studio-link-pill">Speaker: {linkedSpeakerId}</span>}
            </div>
          </div>
          <button onClick={loadAll} className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10">
            Refresh
          </button>
        </div>
        <div className="grid gap-6 xl:grid-cols-[0.85fr_1.15fr]">
          <section className="rounded-3xl border border-white/10 bg-white/[0.04] p-6">
            <div className="text-xs uppercase tracking-[0.3em] text-cyan-200/70">Character presets</div>
            <h2 className="mt-2 text-3xl font-semibold">Profile library</h2>
            <p className="mt-3 text-slate-400">
              Build character voices with a clear split between voice identity and performance. Reference audio drives OpenVoice tone color cloning; performance controls only affect providers that actually support them today.
            </p>

            {info && <div className="mt-4 rounded-2xl border border-emerald-400/30 bg-emerald-500/10 px-4 py-3 text-emerald-200">{info}</div>}
            {error && <div className="mt-4 rounded-2xl border border-rose-400/30 bg-rose-500/10 px-4 py-3 text-rose-200">{error}</div>}

            <div className="mt-6 flex gap-3">
              <button
                onClick={() => {
                  setSelectedId(null);
                  setPreview(null);
                  setCalibrationItems([]);
                  setCalibrationUnsupported([]);
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
                    setCalibrationItems([]);
                    setCalibrationUnsupported([]);
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
                    {preset.portrait_url ? (
                      <img
                        src={toApiHref(preset.portrait_url)}
                        alt={preset.display_name}
                        className="h-20 w-16 rounded-xl border border-white/10 bg-slate-950/50 object-cover"
                      />
                    ) : (
                      <div className="grid h-20 w-16 place-items-center rounded-xl border border-dashed border-white/10 bg-slate-950/50 px-2 text-center text-[10px] text-slate-500">
                        No image
                      </div>
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
            <div className="text-xs uppercase tracking-[0.25em] text-cyan-200/70">Voice Identity</div>
            <div className="mt-4 flex items-center gap-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              {selectedAssociatedImageUrl ? (
                <img
                  src={toApiHref(selectedAssociatedImageUrl)}
                  alt={selectedVoiceProfile?.associated_character_display_name || selectedPreset?.display_name || 'Associated character'}
                  className="h-24 w-20 rounded-xl border border-white/10 bg-black/30 object-cover"
                />
              ) : (
                <div className="grid h-24 w-20 place-items-center rounded-xl border border-dashed border-white/10 bg-black/30 px-2 text-center text-xs text-slate-500">
                  No image
                </div>
              )}
              <div className="min-w-0">
                <div className="text-sm font-medium text-slate-100">
                  {selectedVoiceProfile?.associated_character_display_name || selectedPreset?.display_name || 'No preset selected'}
                </div>
                <div className="mt-1 text-sm text-slate-400">
                  {selectedVoiceProfile?.id || selectedPreset?.voice_profile_id || 'Save a preset to create a voice profile.'}
                </div>
              </div>
            </div>
            <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-slate-100">Production Usage</div>
                  <div className="mt-1 text-sm text-slate-400">
                    Profiles selected here are the same voice profile IDs used by Production Lab render snapshots.
                  </div>
                </div>
                {selectedVoiceProfile && <span className="rounded-full border border-cyan-300/30 px-3 py-1 text-xs text-cyan-200">{selectedProfileUsage.length} binding{selectedProfileUsage.length === 1 ? '' : 's'}</span>}
              </div>
              <div className="mt-3 space-y-2">
                {selectedProfileUsage.map(({ project, binding }) => (
                  <Link
                    key={`${project.id}-${binding.speaker_name}`}
                    to={`/projects/${project.id}?tab=voices`}
                    className="flex items-center justify-between gap-3 rounded-xl border border-white/10 bg-black/20 px-3 py-2 text-sm hover:border-cyan-300/40"
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-slate-100">{project.name}</span>
                      <span className="mt-1 block text-xs text-slate-500">{binding.speaker_name} · {binding.provider}</span>
                    </span>
                    <span className="text-xs text-cyan-200">Open</span>
                  </Link>
                ))}
                {selectedVoiceProfile && selectedProfileUsage.length === 0 && (
                  <div className="rounded-xl border border-dashed border-white/10 px-3 py-3 text-sm text-slate-500">
                    This profile is not bound to a production yet.
                  </div>
                )}
                {!selectedVoiceProfile && (
                  <div className="rounded-xl border border-dashed border-white/10 px-3 py-3 text-sm text-slate-500">
                    Select or create a profile to see production bindings.
                  </div>
                )}
              </div>
            </div>
            <div className="mt-4 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Embedding Status</div>
                  <div className="mt-2 text-lg font-medium text-slate-100">{embeddingStatus.replaceAll('_', ' ')}</div>
                  <div className="mt-1 text-sm text-slate-400">
                    {embeddingReady ? 'Cached speaker embedding is ready to reuse.' : 'Prepare Voice will build or refresh the cached speaker embedding.'}
                  </div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-[0.2em] text-slate-400">Reference Aggregation</div>
                  <div className="mt-2 text-lg font-medium text-slate-100">{referenceAudioMode.replaceAll('_', ' ')}</div>
                  <div className="mt-1 text-sm text-slate-400">
                    {activeReferenceCount > 1
                      ? `OpenVoice now averages ${activeReferenceCount} active reference clips for speaker identity.`
                      : activeReferenceCount === 1
                        ? 'OpenVoice is using 1 active reference clip for speaker identity.'
                        : 'No active reference clips yet.'}
                  </div>
                </div>
              </div>
              {unsupportedControls.length > 0 && (
                <div className="mt-4 rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 py-3 text-sm text-amber-100">
                  OpenVoice identity cloning is active, but these style controls are not implemented yet: {unsupportedControls.join(', ')}.
                </div>
              )}
            </div>

            <div className="mt-6 grid gap-4 md:grid-cols-2">
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
                  <option value="xtts">XTTS character clone</option>
                  <option value="rvc">RVC conversion</option>
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
                  <option value="xtts">XTTS</option>
                  <option value="rvc">RVC</option>
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
            </div>

            <div className="mt-6">
              <div className="text-xs uppercase tracking-[0.25em] text-cyan-200/70">Fallback Voice Settings</div>
              <p className="mt-2 text-sm text-slate-400">
                These settings are used by the espeak fallback path. They are not the same thing as OpenVoice speaker identity.
              </p>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
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

            <div className="mt-6">
              <div className="text-xs uppercase tracking-[0.25em] text-cyan-200/70">Performance</div>
              <p className="mt-2 text-sm text-slate-400">
                Performance controls change delivery only when the active provider supports them. Right now, OpenVoice only applies speaking rate from this panel.
              </p>
            </div>

            <div className="mt-4 grid gap-4 md:grid-cols-2">
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
                  disabled={!supportsControl('energy')}
                  className="mt-3 w-full"
                />
                {!supportsControl('energy') && <div className="mt-2 text-xs text-amber-300">Unavailable for {form.provider} previews right now.</div>}
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
                  disabled={!supportsControl('pause_length')}
                  className="mt-3 w-full"
                />
                {!supportsControl('pause_length') && <div className="mt-2 text-xs text-amber-300">Unavailable for {form.provider} previews right now.</div>}
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
                  disabled={!supportsControl('expressiveness')}
                  className="mt-3 w-full"
                />
                {!supportsControl('expressiveness') && <div className="mt-2 text-xs text-amber-300">Unavailable for {form.provider} previews right now.</div>}
              </label>
              <label className="text-sm text-slate-300">
                Emotion
                <select
                  value={String(form.controls.emotion)}
                  onChange={(event) => setControl('emotion', event.target.value)}
                  disabled={!supportsControl('emotion')}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                >
                  <option value="neutral">Neutral</option>
                  <option value="warm">Warm</option>
                  <option value="serious">Serious</option>
                  <option value="upbeat">Upbeat</option>
                </select>
                {!supportsControl('emotion') && <div className="mt-2 text-xs text-amber-300">Unavailable for {form.provider} previews right now.</div>}
              </label>
              <label className="text-sm text-slate-300">
                Accent
                <input
                  value={String(form.controls.accent)}
                  onChange={(event) => setControl('accent', event.target.value)}
                  disabled={!supportsControl('accent')}
                  className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
                />
                {!supportsControl('accent') && <div className="mt-2 text-xs text-amber-300">Unavailable for {form.provider} previews right now.</div>}
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
            <div className="mt-3 flex flex-wrap gap-2">
              {fixedTestPhrases.map((phrase) => (
                <button
                  key={phrase}
                  type="button"
                  onClick={() => setForm((current) => ({ ...current, sample_text: phrase }))}
                  className="rounded-full border border-white/10 px-3 py-2 text-xs text-slate-300 hover:bg-white/10"
                >
                  {phrase}
                </button>
              ))}
            </div>

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
                    <div>{(clip.processed_storage_path || clip.storage_path).split('/').pop()}</div>
                    <div className="mt-1 text-xs text-slate-500">
                      {clip.mime_type} · {clip.duration_ms ? `${(clip.duration_ms / 1000).toFixed(2)}s` : 'duration unknown'} · {clip.validation_status}
                    </div>
                    {Array.isArray((clip.validation as any)?.warnings) && (clip.validation as any).warnings.length > 0 && (
                      <div className="mt-2 text-xs text-amber-200">
                        {(clip.validation as any).warnings.map((warning: any) => warning.code || 'warning').join(', ')}
                      </div>
                    )}
                    <div className="mt-2 flex flex-wrap gap-2 text-xs">
                      {clip.original_content_url && (
                        <a href={`${apiBase}${clip.original_content_url}`} className="text-cyan-200 hover:text-cyan-100">
                          Original
                        </a>
                      )}
                      {clip.processed_content_url && (
                        <a href={`${apiBase}${clip.processed_content_url}`} className="text-cyan-200 hover:text-cyan-100">
                          Processed WAV
                        </a>
                      )}
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

            <div className="mt-5 rounded-2xl border border-cyan-300/20 bg-cyan-300/[0.04] p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <div className="text-sm font-medium text-cyan-100">Character calibration</div>
                  <div className="mt-1 text-sm text-slate-400">
                    Dataset-backed matching with exact provider, model path, recipe, and render verification metadata.
                  </div>
                </div>
                {selectedVoiceProfile?.calibration_score != null && (
                  <div className="rounded-xl border border-emerald-300/30 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-100">
                    Saved score {Number(selectedVoiceProfile.calibration_score).toFixed(3)}
                  </div>
                )}
              </div>
              <div className="mt-4 grid gap-3 md:grid-cols-2">
                <label className="text-sm text-slate-300">
                  Character slug
                  <input
                    value={characterSlug}
                    onChange={(event) => setCharacterSlug(event.target.value)}
                    className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm"
                    placeholder="peter_griffin"
                  />
                </label>
                <label className="text-sm text-slate-300">
                  Model/checkpoint path
                  <input
                    value={modelPath}
                    onChange={(event) => setModelPath(event.target.value)}
                    className="mt-2 w-full rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3 text-sm"
                    placeholder="backend/storage/voice_models/name/xtts/model.pth"
                  />
                </label>
              </div>
              {selectedVoiceProfile?.character_slug === 'stewie_griffin' && (
                <div className={`mt-4 rounded-xl border p-3 text-sm ${recipeReady ? 'border-emerald-300/30 bg-emerald-500/10 text-emerald-100' : 'border-amber-300/30 bg-amber-500/10 text-amber-100'}`}>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="font-medium">Stewie selected recipe</div>
                      <div className="mt-1 text-xs opacity-80">
                        {recipeReady ? 'Golden preview selected · Ready for test render' : `Missing files · ${recipeError?.message || 'Recipe validation failed'}`}
                      </div>
                      {!Boolean(selectedRecipeStatus['render_verified']) && (
                        <div className="mt-1 text-xs opacity-80">Recipe not render verified</div>
                      )}
                    </div>
                    <div className="text-xs">
                      Provider {String(selectedRecipeStatus['provider'] || selectedVoiceProfile.provider)}
                    </div>
                  </div>
                  {goldenPreviewUrl && (
                    <div className="mt-3 space-y-2">
                      <audio controls src={`${apiBase}${goldenPreviewUrl}`} className="w-full" />
                      <a href={`${apiBase}${goldenPreviewUrl}`} className="text-xs text-cyan-100 hover:text-white">
                        Golden preview WAV
                      </a>
                    </div>
                  )}
                  {recipeReady && (
                    <pre className="mt-3 max-h-36 overflow-auto rounded-lg bg-black/30 p-3 text-xs text-slate-200">
                      {JSON.stringify(selectedVoiceProfile.selected_recipe, null, 2)}
                    </pre>
                  )}
                </div>
              )}
              <div className="mt-4 flex flex-wrap gap-3">
                <button
                  onClick={uploadDatasetClip}
                  disabled={!selectedVoiceProfile || busy === 'dataset-upload'}
                  className="rounded-2xl border border-cyan-300/40 px-4 py-3 text-sm text-cyan-100 hover:bg-cyan-300/10 disabled:opacity-50"
                >
                  {busy === 'dataset-upload' ? 'Processing...' : 'Upload/Manage Dataset'}
                </button>
                <button
                  onClick={analyzeReferenceDataset}
                  disabled={!selectedVoiceProfile?.reference_dataset_id || busy === 'dataset-analyze'}
                  className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-50"
                >
                  {busy === 'dataset-analyze' ? 'Analyzing...' : 'Analyze References'}
                </button>
                <button
                  onClick={attachCharacterModel}
                  disabled={!selectedVoiceProfile || busy === 'attach-model'}
                  className="rounded-2xl border border-white/10 px-4 py-3 text-sm hover:bg-white/10 disabled:opacity-50"
                >
                  {busy === 'attach-model' ? 'Attaching...' : 'Train/Attach Character Model'}
                </button>
                <button
                  onClick={runCharacterCalibrationBatch}
                  disabled={!selectedVoiceProfile || busy === 'character-calibration'}
                  className="rounded-2xl bg-cyan-300 px-4 py-3 text-sm font-medium text-slate-950 disabled:opacity-50"
                >
                  {busy === 'character-calibration' ? 'Scoring...' : 'Generate Calibration Previews'}
                </button>
              </div>
              {selectedVoiceProfile?.reference_datasets?.length ? (
                <div className="mt-4 grid gap-3">
                  {selectedVoiceProfile.reference_datasets.map((dataset) => (
                    <div key={dataset.id} className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-slate-300">
                      <div className="flex flex-wrap items-center justify-between gap-3">
                        <div>
                          <div className="font-medium text-slate-100">{dataset.display_name}</div>
                          <div className="mt-1 text-xs text-slate-500">
                            {dataset.character_slug} · {dataset.status} · {dataset.accepted_clip_count} accepted · {dataset.rejected_clip_count} rejected
                          </div>
                        </div>
                        <div className="text-xs text-cyan-200">
                          {Number(dataset.clean_speech_duration_seconds || 0).toFixed(2)}s clean speech
                        </div>
                      </div>
                      <pre className="mt-3 max-h-36 overflow-auto rounded-lg bg-slate-950/60 p-3 text-xs text-slate-400">
                        {JSON.stringify({ metrics: dataset.metrics, prosody: dataset.prosody_metrics }, null, 2)}
                      </pre>
                    </div>
                  ))}
                </div>
              ) : (
                <div className="mt-4 rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-slate-500">
                  No character reference dataset yet. Uploading a dataset clip will create one for this profile.
                </div>
              )}
              {characterBatch && (
                <div className="mt-4 rounded-xl border border-white/10 bg-black/20 p-3">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <div className="text-sm font-medium text-slate-100">Top matches</div>
                      <div className="mt-1 text-xs text-slate-500">Batch {characterBatch.id} · {characterBatch.status}</div>
                    </div>
                  </div>
                  <div className="mt-3 grid gap-3">
                    {characterBatch.rankings.map((ranking, index) => {
                      const recipe = (ranking.recipe || {}) as Record<string, unknown>;
                      return (
                        <div key={`${characterBatch.id}-${index}`} className="rounded-xl border border-white/10 p-3 text-sm text-slate-300">
                          <div className="flex flex-wrap items-start justify-between gap-3">
                            <div>
                              <div className="font-medium text-slate-100">#{index + 1} score {Number(ranking.score || 0).toFixed(3)}</div>
                              <div className="mt-1 text-xs text-slate-500">
                                {String(ranking.provider || recipe.provider || 'provider')} · speed {String(recipe['speaking_rate'] || 1)} · temp {String(recipe['temperature'] ?? 'default')} · pitch {Number(ranking.pitch_score || 0).toFixed(3)} · rhythm {Number(ranking.rhythm_score || 0).toFixed(3)} · pause {Number(ranking.pause_score || 0).toFixed(3)}
                              </div>
                            </div>
                            <button
                              onClick={() => saveCharacterRecipe({ ...recipe, calibration_score: ranking.score })}
                              disabled={busy === 'save-character-recipe'}
                              className="rounded-xl border border-emerald-300/30 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/10 disabled:opacity-50"
                            >
                              Use this recipe
                            </button>
                          </div>
                          {ranking.content_url && (
                            <audio controls src={`${apiBase}${ranking.content_url}`} className="mt-3 w-full" />
                          )}
                        </div>
                      );
                    })}
                    {characterBatch.rankings.length === 0 && (
                      <div className="rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-slate-500">
                        No ranked previews completed. Provider diagnostics are available in the batch payload.
                      </div>
                    )}
                  </div>
                </div>
              )}
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
                onChange={(event) => setPreviewProviderPreference(event.target.value as 'auto' | 'openvoice' | 'xtts' | 'rvc' | 'espeak')}
                className="rounded-2xl border border-white/10 bg-slate-950/60 px-4 py-3"
              >
                <option value="auto">Preview: Auto</option>
                <option value="openvoice">Preview: OpenVoice</option>
                <option value="xtts">Preview: XTTS</option>
                <option value="rvc">Preview: RVC</option>
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
                onClick={runCalibrationMatrix}
                disabled={busy === 'calibration' || !selectedId}
                className="rounded-2xl border border-cyan-300/40 px-4 py-3 text-sm text-cyan-100 hover:bg-cyan-300/10 disabled:opacity-60"
              >
                {busy === 'calibration' ? 'Generating Matrix...' : 'Generate Calibration Matrix'}
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
                    <div className="space-y-2">
                      <audio controls src={`${apiBase}${preview.content_url}`} className="w-full" />
                      <a href={`${apiBase}${preview.content_url}`} className="text-xs text-cyan-200 hover:text-cyan-100">
                        Voice Lab preview WAV
                      </a>
                    </div>
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

            <div className="mt-6 rounded-2xl border border-white/10 bg-slate-950/40 p-4">
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="text-sm font-medium text-slate-100">Calibration matrix</div>
                  <div className="mt-1 text-sm text-slate-400">
                    Audition fixed phrases across the persisted OpenVoice reference artifacts, base speakers, and explicit style controls.
                  </div>
                </div>
                {calibrationUnsupported.length > 0 && (
                  <div className="rounded-xl border border-amber-300/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                    Unsupported: {calibrationUnsupported.join(', ')}
                  </div>
                )}
              </div>
              {calibrationItems.length > 0 ? (
                <div className="mt-4 grid gap-3">
                  {calibrationItems.map((item, index) => {
                    const recipe = calibrationRecipe(item);
                    const unsupported = calibrationUnsupportedControls(item);
                    const supported = calibrationSupportedControls(item);
                    const processedPaths = Array.isArray(item.calibration?.['processed_reference_paths'])
                      ? (item.calibration['processed_reference_paths'] as unknown[]).map((value) => String(value))
                      : [];
                    return (
                      <div key={`${item.job_id || index}-${item.sample_text}`} className="rounded-xl border border-white/10 bg-black/20 p-3 text-sm text-slate-300">
                        <div className="flex flex-wrap items-start justify-between gap-3">
                          <div>
                            <div className="text-xs uppercase tracking-[0.2em] text-slate-500">
                              Recipe {String(item.calibration?.['recipe_index'] ?? index)} · Phrase {String(item.calibration?.['phrase_index'] ?? 0)}
                            </div>
                            <div className="mt-1 font-medium text-slate-100">{item.sample_text}</div>
                            <div className="mt-2 text-xs text-slate-400">
                              Base {String(recipe['base_speaker'] || 'default')} · Style {String(recipe['style_preset'] || 'default')} · Rate {String(recipe['speaking_rate'] || 1)} · Pause {String(recipe['pause_bias'] || 'default')}
                            </div>
                            <div className="mt-1 text-xs text-slate-500">
                              Pitch {String(recipe['pitch'] ?? 'stored only')} · Energy {String(recipe['energy'] ?? 'stored only')} · Embedding {String(item.calibration?.['embedding_path'] || 'not prepared')}
                            </div>
                          </div>
                          <button
                            onClick={() => saveCalibrationRecipe(item)}
                            disabled={item.status !== 'completed' || Boolean(busy?.startsWith('save-calibration'))}
                            className="rounded-xl border border-emerald-300/30 px-3 py-2 text-xs text-emerald-100 hover:bg-emerald-500/10 disabled:opacity-50"
                          >
                            Save Recipe
                          </button>
                        </div>
                        <div className="mt-3 grid gap-2 md:grid-cols-3">
                          <div>Status: <span className="text-cyan-200">{item.status}</span></div>
                          <div>Provider: <span className="text-cyan-200">{item.provider_used || 'pending'}</span></div>
                          <div>Supported: <span className="text-cyan-200">{supported.join(', ') || 'none'}</span></div>
                        </div>
                        {unsupported.length > 0 && (
                          <div className="mt-2 rounded-lg border border-amber-300/20 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                            Stored but ignored by this provider: {unsupported.join(', ')}
                          </div>
                        )}
                        {processedPaths.length > 0 && (
                          <div className="mt-2 text-xs text-slate-500">Processed refs: {processedPaths.join(', ')}</div>
                        )}
                        {item.content_url ? (
                          <div className="mt-3 space-y-2">
                            <audio controls src={`${apiBase}${item.content_url}`} className="w-full" />
                            <a href={`${apiBase}${item.content_url}`} className="text-xs text-cyan-200 hover:text-cyan-100">
                              Calibration preview WAV
                            </a>
                          </div>
                        ) : (
                          <div className="mt-3 rounded-lg border border-dashed border-white/10 px-3 py-3 text-xs text-slate-500">
                            Audio pending from worker.
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div className="mt-3 rounded-xl border border-dashed border-white/10 px-3 py-4 text-sm text-slate-500">
                  Generate a calibration matrix to compare style recipes for this profile.
                </div>
              )}
            </div>
          </section>
        </div>
      </div>
    </StudioShell>
  );
};

export default VoiceLabPage;
