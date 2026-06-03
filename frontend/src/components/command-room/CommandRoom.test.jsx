jest.mock('react-router-dom', () => ({
  Link: ({ children, to, ...props }) => <a href={String(to)} {...props}>{children}</a>,
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock('lucide-react', () => ({
  ChevronDown: () => null,
  ExternalLink: () => null,
  FileUp: () => null,
  Play: () => null,
  RefreshCw: () => null,
  Sparkles: () => null,
}));

import { deriveCommandRoomViewModel } from './CommandRoom';
import { defaultPreviewSettings } from '../production/ProductionReadinessPanel';

const now = '2026-06-02T12:00:00.000Z';

const script = {
  id: 1,
  parent_revision_id: null,
  raw_text: '<Host> Hello.',
  parsed_lines: [{ speaker: 'Host', text: 'Hello.', order: 0 }],
  characters: ['Host'],
  generated_script: null,
  source: 'manual',
  generation_provider: null,
  is_current: true,
  created_at: now,
};

const output = {
  id: 44,
  project_id: 10,
  output_kind: 'draft',
  provider_name: 'local-compositor',
  is_preview: true,
  duration_ms: 42000,
  created_at: now,
  asset: {
    id: 88,
    kind: 'generated_video',
    source_type: 'generated',
    preset_key: null,
    provider_name: 'local-compositor',
    mime_type: 'video/mp4',
    original_filename: 'draft.mp4',
    size_bytes: 1000,
    duration_ms: 42000,
    width: 1080,
    height: 1920,
    content_url: '/assets/88/content',
    metadata: {},
    created_at: now,
  },
};

const metadata = {
  id: 5,
  project_id: 10,
  platform: 'youtube',
  title: 'Ready title',
  description: 'Ready description',
  tags: [],
  extras: {},
  validation_errors: [],
  source: 'manual',
  updated_at: now,
};

const makeProject = (overrides = {}) => ({
  id: 10,
  name: 'Dogs vs Cats Debate',
  status: 'approved',
  target_platform: 'youtube_shorts',
  background_style: 'none',
  background_source_type: 'preset',
  background_asset_id: 1,
  selected_social_account_id: null,
  current_script_revision_id: 1,
  current_output_video_id: output.id,
  automation_mode: 'manual',
  preferred_account_type: null,
  allowed_platforms: ['youtube_shorts'],
  publish_windows: [],
  approved_at: now,
  created_at: now,
  updated_at: now,
  current_script: script,
  latest_preview: null,
  latest_output: output,
  latest_review: null,
  latest_notifications: [],
  speaker_bindings: [],
  preview_settings: {
    ...defaultPreviewSettings,
    background_asset_id: 1,
    background_preset_id: 'studio',
    background_source_type: 'preset',
    background_url: '/assets/1/content',
    speaker_mappings: [
      {
        speaker_name: 'Host',
        voice_profile_id: 'voice_host',
        character_preset_id: 'host',
        character_display_name: 'Host',
        character_portrait_filename: 'host.png',
        character_portrait_url: '/characters/host.png',
        display_label: 'Host',
        sample_text: 'Hello.',
      },
    ],
  },
  script_generation_settings: {
    content_format_id: 'debate_format',
    platform: 'youtube_shorts',
    target_duration_sec: 45,
    tone: 'sharp',
    audience: 'creators',
    speaker_names: ['Host'],
  },
  ...overrides,
});

const makeJob = (overrides = {}) => ({
  id: 77,
  project_id: 10,
  status: 'completed',
  progress: 100,
  style_preset: 'none',
  output_kind: 'draft',
  provider_name: 'local-compositor',
  error_message: null,
  voice_manifest: {},
  preview_settings: defaultPreviewSettings,
  tts_result: {},
  provider_state: {},
  current_phase: 'completed',
  cache_statistics: { hits: 3 },
  timing_breakdown: {},
  performance_summary: {},
  artifact_urls: {},
  debug_artifacts: {},
  output_video_id: output.id,
  started_at: now,
  finished_at: now,
  created_at: now,
  ...overrides,
});

describe('deriveCommandRoomViewModel', () => {
  it('returns firstRun when there is no meaningful activity', () => {
    const viewModel = deriveCommandRoomViewModel();

    expect(viewModel.mode).toBe('firstRun');
    expect(viewModel.counts.blocked).toBe(0);
    expect(viewModel.productionRows).toHaveLength(0);
  });

  it('returns active for attention, ready, and failed mixed rows', () => {
    const attentionProject = makeProject({
      id: 11,
      name: 'Cats Run the Internet',
      approved_at: null,
      current_output_video_id: null,
      latest_output: null,
      preview_settings: {
        ...defaultPreviewSettings,
        background_asset_id: 1,
        background_url: '/assets/1/content',
        speaker_mappings: [{ ...makeProject().preview_settings.speaker_mappings[0], voice_profile_id: null }],
      },
    });
    const readyProject = makeProject({ id: 12, name: 'Dogs vs Cats Debate' });
    const failedProject = makeProject({ id: 13, name: 'Why I Quit Editing' });

    const viewModel = deriveCommandRoomViewModel({
      projects: [attentionProject, readyProject, failedProject],
      currentProject: attentionProject,
      script,
      jobs: [makeJob({ project_id: failedProject.id, status: 'failed', error_message: 'XTTS reference mismatch' })],
      metadataByProjectId: {
        [readyProject.id]: { ...metadata, project_id: readyProject.id },
        [failedProject.id]: { ...metadata, project_id: failedProject.id },
      },
    });

    expect(viewModel.mode).toBe('active');
    expect(viewModel.counts.attention).toBeGreaterThan(0);
    expect(viewModel.counts.failed).toBe(1);
    expect(viewModel.productionRows.map((row) => row.family)).toEqual(expect.arrayContaining(['attention', 'ready', 'failed']));
  });

  it('returns allClear when production activity is healthy and verified', () => {
    const project = makeProject();

    const viewModel = deriveCommandRoomViewModel({
      projects: [project],
      currentProject: project,
      script,
      outputs: [output],
      metadata,
      metadataByProjectId: { [project.id]: metadata },
    });

    expect(viewModel.mode).toBe('allClear');
    expect(viewModel.counts.failed).toBe(0);
    expect(viewModel.counts.attention).toBe(0);
    expect(viewModel.productionRows[0].family).toBe('ready');
  });

  it('does not hide failed jobs behind allClear', () => {
    const project = makeProject();

    const viewModel = deriveCommandRoomViewModel({
      projects: [project],
      currentProject: project,
      script,
      outputs: [output],
      metadata,
      metadataByProjectId: { [project.id]: metadata },
      jobs: [makeJob({ status: 'failed', error_message: 'ffmpeg failed' })],
    });

    expect(viewModel.mode).toBe('active');
    expect(viewModel.counts.failed).toBe(1);
    expect(viewModel.productionRows[0].family).toBe('failed');
  });
});
