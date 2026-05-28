import {
  computeProductionReadiness,
  defaultPreviewSettings,
} from './ProductionReadinessPanel';

const baseProject = {
  id: 10,
  name: 'Test Production',
  status: 'draft',
  target_platform: 'youtube_shorts',
  background_style: 'none',
  background_source_type: 'preset',
  background_asset_id: 1,
  selected_social_account_id: null,
  current_script_revision_id: 1,
  current_output_video_id: null,
  automation_mode: 'manual',
  preferred_account_type: null,
  allowed_platforms: ['youtube_shorts'],
  publish_windows: [],
  approved_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
  current_script: null,
  latest_preview: null,
  latest_output: null,
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
    content_format_id: 'educational_short',
    platform: 'youtube_shorts',
    target_duration_sec: 45,
    tone: 'sharp',
    audience: 'creators',
    speaker_names: ['Host'],
  },
};

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
  created_at: new Date().toISOString(),
};

describe('computeProductionReadiness', () => {
  it('returns a scene action when the scene is not selected', () => {
    const project = {
      ...baseProject,
      background_asset_id: null,
      preview_settings: { ...baseProject.preview_settings, background_url: null, background_asset_id: null },
    };

    const readiness = computeProductionReadiness({ project, script });

    expect(readiness.nextAction.label).toBe('Select a background or scene before rendering');
  });

  it('returns a voice action for the speaker that needs assignment', () => {
    const project = {
      ...baseProject,
      preview_settings: {
        ...baseProject.preview_settings,
        speaker_mappings: [{ ...baseProject.preview_settings.speaker_mappings[0], speaker_name: 'Narrator', voice_profile_id: null }],
      },
    };
    const narratorScript = { ...script, parsed_lines: [{ speaker: 'Narrator', text: 'Listen.', order: 0 }], characters: ['Narrator'] };

    const readiness = computeProductionReadiness({ project, script: narratorScript });

    expect(readiness.nextAction.label).toBe('Assign a voice profile to Narrator');
  });

  it('returns a character image action for the speaker that needs assignment', () => {
    const project = {
      ...baseProject,
      preview_settings: {
        ...baseProject.preview_settings,
        speaker_mappings: [
          {
            ...baseProject.preview_settings.speaker_mappings[0],
            character_portrait_filename: null,
            character_portrait_url: null,
          },
        ],
      },
    };

    const readiness = computeProductionReadiness({ project, script });

    expect(readiness.nextAction.label).toBe('Choose a character image for Host');
  });

  it('asks for preview approval when output exists but is not approved', () => {
    const project = {
      ...baseProject,
      current_output_video_id: 22,
      latest_output: { id: 22, project_id: 10, output_kind: 'draft', provider_name: 'local', is_preview: true, duration_ms: 1000, asset: {}, created_at: '' },
    };

    const readiness = computeProductionReadiness({ project, script });

    expect(readiness.nextAction.label).toBe('Approve preview before final render');
    expect(readiness.rows.find((row) => row.id === 'preview').state).toBe('warning');
    expect(readiness.rows.find((row) => row.id === 'preview').needsText).toBe('Preview output needs verification');
  });

  it('marks preview approval as verified after approval', () => {
    const project = {
      ...baseProject,
      approved_at: new Date().toISOString(),
      current_output_video_id: 22,
      latest_output: { id: 22, project_id: 10, output_kind: 'draft', provider_name: 'local', is_preview: true, duration_ms: 1000, asset: {}, created_at: '' },
    };

    const readiness = computeProductionReadiness({ project, script });

    expect(readiness.rows.find((row) => row.id === 'preview').state).toBe('verified');
  });

  it('asks for a draft render before release when no output exists', () => {
    const readiness = computeProductionReadiness({ project: baseProject, script });

    expect(readiness.nextAction.label).toBe('Render a draft before preparing release');
    expect(readiness.rows.find((row) => row.id === 'preview').state).toBe('missing');
    expect(readiness.rows.find((row) => row.id === 'render').state).toBe('ready');
  });

  it('uses failed and warning states for render job readiness', () => {
    const failedJob = { id: 'job-1', status: 'failed', progress: 100 };
    const activeJob = { id: 'job-2', status: 'processing', progress: 40 };

    const failedReadiness = computeProductionReadiness({ project: baseProject, script, latestJob: failedJob });
    const activeReadiness = computeProductionReadiness({ project: baseProject, script, latestJob: activeJob });

    expect(failedReadiness.rows.find((row) => row.id === 'render').state).toBe('failed');
    expect(failedReadiness.rows.find((row) => row.id === 'render').needsText).toBe('Latest render failed');
    expect(activeReadiness.rows.find((row) => row.id === 'render').state).toBe('warning');
    expect(activeReadiness.rows.find((row) => row.id === 'render').needsText).toBe('Render is running');
  });
});
