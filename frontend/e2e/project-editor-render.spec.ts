import { expect, test } from './fixtures/localhostOnly';
import type { Page, Route } from '@playwright/test';

const now = '2026-05-21T20:00:00.000Z';

const transparentPng = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=',
  'base64'
);

const basePreviewSettings = {
  background_asset_id: 11,
  background_preset_id: 'skyline',
  background_source_type: 'preset',
  background_url: '/assets/11/content',
  background_metadata: {
    original_filename: 'Skyline.png',
    mime_type: 'image/png',
  },
  speaker_mappings: [
    {
      speaker_name: 'Host',
      voice_profile_id: 'voice_host',
      character_preset_id: 'host',
      character_display_name: 'Host',
      character_portrait_filename: 'host.png',
      character_portrait_url: '/assets/201/content',
      display_label: 'Host',
      sample_text: 'A warm cache keeps draft loops fast.',
    },
    {
      speaker_name: 'Guest',
      voice_profile_id: 'voice_guest',
      character_preset_id: 'guest',
      character_display_name: 'Guest',
      character_portrait_filename: 'guest.png',
      character_portrait_url: '/assets/202/content',
      display_label: 'Guest',
      sample_text: 'Changed lines should be easy to spot.',
    },
  ],
  layout: { character_scale: 1, chat_font_size_px: 18 },
  layout_preset: 'left_right_locked',
  caption_style: 'bold_bubble',
  speaker_png_size: 'standard',
  render_preset: 'shorts_1080x1920',
};

const scriptRevision = {
  id: 7,
  parent_revision_id: null,
  raw_text: '<Host> A warm cache keeps draft loops fast.\n<Guest> Changed lines should be easy to spot.',
  parsed_lines: [
    {
      speaker: 'Host',
      text: 'A warm cache keeps draft loops fast.',
      caption_text: 'A warm cache keeps draft loops fast.',
      order: 0,
      line_id: 'line-host-1',
    },
    {
      speaker: 'Guest',
      text: 'Changed lines should be easy to spot.',
      caption_text: 'Changed lines should be easy to spot.',
      order: 1,
      line_id: 'line-guest-1',
    },
  ],
  characters: ['Host', 'Guest'],
  generated_script: null,
  source: 'manual',
  generation_provider: null,
  is_current: true,
  created_at: now,
};

const generatedScript = {
  id: 'generated-script-1',
  script_id: 'generated-script-1',
  idea: 'Dogs vs cats debate',
  content_format_id: 'educational_short',
  format_id: 'educational_short',
  platform: 'tiktok',
  platform_targets: ['tiktok'],
  target_duration_sec: 45,
  tone: 'playful',
  audience: 'pet owners',
  title: 'Dogs vs Cats',
  short_summary: 'A compact pet debate.',
  speakers: [
    {
      id: 'host',
      label: 'Host',
      role: 'host',
      voice_profile_id: null,
      speaker_image_id: null,
    },
    {
      id: 'guest',
      label: 'Guest',
      role: 'guest',
      voice_profile_id: null,
      speaker_image_id: null,
    },
  ],
  lines: [
    {
      id: 'line_001',
      section: 'hook',
      speaker_id: 'host',
      speaker_label: 'Host',
      text: 'Dogs celebrate every time you come home.',
      caption_text: 'Dogs celebrate every time you come home.',
      estimated_duration_sec: 4.2,
    },
    {
      id: 'line_002',
      section: 'body',
      speaker_id: 'guest',
      speaker_label: 'Guest',
      text: 'Cats are emotionally efficient.',
      caption_text: 'Cats are emotionally efficient.',
      estimated_duration_sec: 4.7,
    },
  ],
  sections: ['hook', 'body'],
  caption_blocks: [],
  metadata_suggestions: {},
  total_estimated_duration_sec: 8.9,
  estimated_total_duration_sec: 8.9,
  generation_provider: 'ollama',
  generation_model: 'llama3',
  fallback_used: false,
  provider_metadata: {},
  validation_warnings: [],
};

const providerMetadata = {
  provider_name: 'ollama',
  model: 'llama3',
  fallback_used: false,
  fallback_reason: null,
  generation_duration_ms: 480,
  repair_attempted: false,
  prompt_char_count: 200,
  response_char_count: 800,
  timeout_seconds: 60,
  num_predict: null,
  num_ctx: null,
  ollama_total_duration: null,
  ollama_load_duration: null,
  ollama_prompt_eval_count: null,
  ollama_eval_count: null,
  failure_type: null,
  diagnostics: {
    target_duration_sec: 45,
    estimated_duration_sec: 8.9,
    speaker_count: 2,
  },
};

const backgroundAsset = {
  id: 11,
  kind: 'background_image',
  source_type: 'preset',
  preset_key: 'skyline',
  provider_name: null,
  mime_type: 'image/png',
  original_filename: 'Skyline.png',
  size_bytes: 1200,
  duration_ms: null,
  width: 1080,
  height: 1920,
  content_url: '/assets/11/content',
  metadata: { original_filename: 'Skyline.png', mime_type: 'image/png' },
  created_at: now,
};

const output = {
  id: 88,
  project_id: 42,
  output_kind: 'draft',
  provider_name: 'local',
  is_preview: true,
  duration_ms: 9000,
  asset: {
    id: 88,
    kind: 'generated_video',
    source_type: 'generated',
    preset_key: null,
    provider_name: 'local',
    mime_type: 'video/mp4',
    original_filename: 'draft.mp4',
    size_bytes: 4096,
    duration_ms: 9000,
    width: 1080,
    height: 1920,
    content_url: '/assets/88/content',
    metadata: {},
    created_at: now,
  },
  created_at: now,
};

const makeProject = (previewSettings: typeof basePreviewSettings, currentScript: Record<string, unknown> | null = scriptRevision) => ({
  id: 42,
  name: 'Render Coverage Production',
  status: 'draft',
  target_platform: 'youtube_shorts',
  background_style: 'none',
  background_source_type: previewSettings.background_source_type,
  background_asset_id: previewSettings.background_asset_id,
  selected_social_account_id: null,
  current_script_revision_id: currentScript ? Number(currentScript.id || scriptRevision.id) : null,
  current_output_video_id: output.id,
  automation_mode: 'manual',
  preferred_account_type: null,
  allowed_platforms: ['youtube_shorts'],
  publish_windows: [],
  approved_at: null,
  created_at: now,
  updated_at: now,
  current_script: currentScript,
  latest_preview: output.asset,
  latest_output: output,
  latest_review: null,
  latest_notifications: [],
  speaker_bindings: [],
  preview_settings: previewSettings,
  script_generation_settings: {
    content_format_id: 'educational_short',
    platform: 'youtube_shorts',
    target_duration_sec: 45,
    tone: 'explanatory',
    audience: 'creators',
    speaker_names: ['Host', 'Guest'],
  },
});

const makeGenerationJob = (previewSettings: typeof basePreviewSettings) => ({
  id: 123,
  project_id: 42,
  status: 'completed',
  progress: 100,
  style_preset: 'default',
  output_kind: 'draft',
  provider_name: 'local',
  error_message: null,
  voice_manifest: {
    speakers: {
      Host: { voice_profile_id: 'voice_host', requested_provider: 'espeak' },
      Guest: { voice_profile_id: 'voice_guest', requested_provider: 'espeak' },
    },
  },
  preview_settings: previewSettings,
  tts_result: {},
  provider_state: {},
  current_phase: null,
  cache_statistics: { tts_segment_hits: 1, tts_segment_misses: 1 },
  timing_breakdown: {},
  performance_summary: {},
  artifact_urls: {},
  debug_artifacts: {},
  output_video_id: output.id,
  started_at: now,
  finished_at: now,
  created_at: now,
});

const renderReadiness = {
  target_seconds: 60,
  estimated_seconds_low: 8,
  estimated_seconds_high: 18,
  draft_ready: true,
  blocking_reasons: [],
  optimization_hints: ['Draft mode is ready for local iteration.'],
  recommended_mode: 'draft',
  max_recommended_lines: 8,
  max_recommended_speakers: 2,
  max_recommended_words_per_line: 24,
  expected_cache_dependency: 'medium',
  cache_warmth: {
    tts_segment_hits: 1,
    tts_segment_misses: 1,
    clone_provider_misses: 0,
    tts_segments: [
      {
        line_index: 0,
        line_id: 'line-host-1',
        speaker: 'Host',
        voice_profile_id: 'voice_host',
        provider: 'espeak',
        cache_key_prefix: 'host-cache-hit',
        cached: true,
        text_preview: 'A warm cache keeps draft loops fast.',
      },
      {
        line_index: 1,
        line_id: 'line-guest-1',
        speaker: 'Guest',
        voice_profile_id: 'voice_guest',
        provider: 'espeak',
        cache_key_prefix: 'guest-cache-miss',
        cached: false,
        text_preview: 'Changed lines should be easy to spot.',
      },
    ],
  },
};

const json = async (route: Route, body: unknown, status = 200) => {
  await route.fulfill({
    status,
    contentType: 'application/json',
    body: JSON.stringify(body),
  });
};

type ProjectEditorMockOptions = {
  scriptRevision?: Record<string, unknown> | null;
  generationDelayMs?: number;
  generationShouldFail?: boolean;
  onAcceptedPayload?: (body: Record<string, unknown>) => void;
};

const lineDraft = (lines: Array<Record<string, unknown>>) =>
  lines.map((line) => `<${String(line.speaker || line.speaker_label || 'Speaker')}> ${String(line.text || '')}`).join('\n');

const makeRevisionFromPayload = (body: Record<string, unknown>, id: number, source: string) => {
  const parsedLines = Array.isArray(body.parsed_lines) ? body.parsed_lines as Array<Record<string, unknown>> : [];
  const scriptPayload = body.generated_script as Record<string, unknown> | undefined;
  return {
    id,
    parent_revision_id: body.parent_revision_id || null,
    raw_text: parsedLines.length ? lineDraft(parsedLines) : String(body.raw_text || ''),
    parsed_lines: parsedLines,
    characters: Array.from(new Set(parsedLines.map((line) => String(line.speaker || '')).filter(Boolean))),
    generated_script: scriptPayload || null,
    source,
    generation_provider: scriptPayload ? 'ollama' : null,
    is_current: true,
    created_at: now,
  };
};

const installProjectEditorMocks = async (page: Page, options: ProjectEditorMockOptions = {}) => {
  let previewSettings = structuredClone(basePreviewSettings);
  const originalRenderSnapshot = structuredClone(basePreviewSettings);
  let activeScriptRevision: Record<string, unknown> | null =
    options.scriptRevision === undefined ? scriptRevision : options.scriptRevision;
  let nextRevisionId = 80;
  let scriptGenerationSettings = {
    content_format_id: 'educational_short',
    platform: 'youtube_shorts',
    target_duration_sec: 45,
    tone: 'explanatory',
    audience: 'creators',
    speaker_names: ['Host', 'Guest'],
  };

  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (url.origin !== 'http://localhost:3000' || request.resourceType() === 'document') {
      await route.fallback();
      return;
    }

    if (path.startsWith('/assets/') && path.endsWith('/content')) {
      await route.fulfill({
        status: 200,
        contentType: path.includes('/88/') ? 'video/mp4' : 'image/png',
        body: path.includes('/88/') ? Buffer.from('') : transparentPng,
      });
      return;
    }

    if (path === '/auth/me') {
      await json(route, {
        id: 1,
        username: 'playwright',
        preferences_summary: {
          default_platform: 'youtube_shorts',
          default_social_account_id: null,
          metadata_style: 'default',
          auto_select_default_account: true,
          automation_mode: 'assisted',
          preferred_account_type: null,
          allowed_platforms: ['youtube_shorts'],
          publish_windows: [],
        },
      });
      return;
    }

    if (path === '/projects/42' && request.method() === 'GET') {
      await json(route, {
        ...makeProject(previewSettings, activeScriptRevision),
        script_generation_settings: scriptGenerationSettings,
      });
      return;
    }

    if (path === '/projects/42/assets') {
      await json(route, [backgroundAsset]);
      return;
    }

    if (path === '/background-presets') {
      await json(route, [
        {
          key: 'skyline',
          name: 'Skyline',
          description: 'Static test scene',
          filename: 'skyline.png',
          content_url: '/assets/11/content',
          mime_type: 'image/png',
        },
      ]);
      return;
    }

    if (path === '/character-presets') {
      await json(route, {
        items: [
          {
            id: 'host',
            display_name: 'Host',
            speaker_names: ['Host'],
            portrait_filename: 'host.png',
            portrait_url: '/assets/201/content',
            voice_profile_id: 'voice_host',
            tts_provider: 'espeak',
            provider_preference: 'espeak',
            fallback_provider: null,
            voice: 'en',
            rate: 165,
          },
          {
            id: 'guest',
            display_name: 'Guest',
            speaker_names: ['Guest'],
            portrait_filename: 'guest.png',
            portrait_url: '/assets/202/content',
            voice_profile_id: 'voice_guest',
            tts_provider: 'espeak',
            provider_preference: 'espeak',
            fallback_provider: null,
            voice: 'en',
            rate: 165,
          },
        ],
      });
      return;
    }

    if (path === '/projects/42/script' && request.method() === 'GET') {
      await json(route, { current_revision: activeScriptRevision });
      return;
    }

    if (path === '/projects/42/script' && request.method() === 'PUT') {
      const body = JSON.parse(request.postData() || '{}');
      options.onAcceptedPayload?.(body);
      activeScriptRevision = makeRevisionFromPayload(body, nextRevisionId++, body.generated_script ? 'generated' : 'manual');
      await json(route, { current_revision: activeScriptRevision });
      return;
    }

    if (path === '/projects/42/script/import' && request.method() === 'POST') {
      activeScriptRevision = {
        id: nextRevisionId++,
        parent_revision_id: null,
        raw_text: '<Host> Imported script keeps the production moving.',
        parsed_lines: [
          {
            speaker: 'Host',
            text: 'Imported script keeps the production moving.',
            caption_text: 'Imported script keeps the production moving.',
            section: 'hook',
            line_id: 'imported_line_001',
            order: 0,
          },
        ],
        characters: ['Host'],
        generated_script: null,
        source: 'upload:.txt',
        generation_provider: null,
        is_current: true,
        created_at: now,
      };
      await json(route, { current_revision: activeScriptRevision }, 201);
      return;
    }

    if (path === '/projects/42/script-revisions') {
      await json(route, { items: activeScriptRevision ? [activeScriptRevision] : [] });
      return;
    }

    if (path === '/projects/42/outputs') {
      await json(route, { items: [output] });
      return;
    }

    if (path === '/projects/42/reviews') {
      await json(route, { items: [] });
      return;
    }

    if (path === '/projects/42/metadata/youtube') {
      await json(route, null);
      return;
    }

    if (path === '/social-accounts') {
      await json(route, { items: [] });
      return;
    }

    if (path === '/projects/42/publish-history') {
      await json(route, { jobs: [], posts: [] });
      return;
    }

    if (path === '/projects/42/speaker-bindings') {
      await json(route, {
        items: [
          {
            id: 1,
            speaker_name: 'Host',
            character_preset_id: 'host',
            character_display_name: 'Host',
            voice_profile_id: 'voice_host',
            provider: 'espeak',
            character_portrait_filename: 'host.png',
            character_portrait_url: '/assets/201/content',
          },
          {
            id: 2,
            speaker_name: 'Guest',
            character_preset_id: 'guest',
            character_display_name: 'Guest',
            voice_profile_id: 'voice_guest',
            provider: 'espeak',
            character_portrait_filename: 'guest.png',
            character_portrait_url: '/assets/202/content',
          },
        ],
      });
      return;
    }

    if (path === '/projects/42/generation-jobs') {
      await json(route, { items: [makeGenerationJob(originalRenderSnapshot)] });
      return;
    }

    if (path === '/projects/42/generation-jobs/latest') {
      await json(route, makeGenerationJob(originalRenderSnapshot));
      return;
    }

    if (path === '/projects/42/render-readiness') {
      await json(route, renderReadiness);
      return;
    }

    if (path === '/script-generation/formats') {
      await json(route, { items: [] });
      return;
    }

    if (path === '/projects/42/script-generation-settings' && request.method() === 'PATCH') {
      const body = JSON.parse(request.postData() || '{}');
      scriptGenerationSettings = {
        ...scriptGenerationSettings,
        ...body,
      };
      await json(route, scriptGenerationSettings);
      return;
    }

    if (path === '/script-generation/generate' && request.method() === 'POST') {
      if (options.generationDelayMs) {
        await new Promise((resolve) => setTimeout(resolve, options.generationDelayMs));
      }
      if (options.generationShouldFail) {
        await json(route, { detail: 'Parser error on line_006. Speaker tag missing.' }, 500);
        return;
      }
      await json(route, {
        generated_script: generatedScript,
        provider_metadata: providerMetadata,
        validation_warnings: [],
        fallback_used: false,
      });
      return;
    }

    if (path === '/projects/42/preview-settings' && request.method() === 'PATCH') {
      const body = JSON.parse(request.postData() || '{}');
      previewSettings = {
        ...previewSettings,
        ...body,
        layout: {
          ...previewSettings.layout,
          ...(body.layout || {}),
        },
      };
      await json(route, previewSettings);
      return;
    }

    await route.fallback();
  });
};

test('Production Builder Script shows true empty state, expandable controls, and import recovery', async ({ page }) => {
  await installProjectEditorMocks(page, { scriptRevision: null });

  await page.goto('/projects/42?tab=script#step-script');

  const scriptSection = page.locator('#step-script');
  await expect(scriptSection.getByRole('heading', { name: 'Generate the script.' })).toBeVisible();
  await expect(scriptSection.getByText('No dialogue yet')).toBeVisible();
  await expect(scriptSection.getByText('Timeline is empty')).toBeVisible();
  await expect(scriptSection.getByRole('button', { name: /Continue to Cast & Voices/ })).toBeDisabled();

  const accordion = scriptSection.getByTestId('script-controls-accordion');
  await expect(accordion.getByRole('heading', { name: 'Generation controls' })).toHaveCount(0);
  await accordion.getByRole('button', { name: /Generation controls/ }).click();
  await expect(accordion.getByRole('heading', { name: 'Generation controls' })).toBeVisible();
  await expect(accordion.getByRole('heading', { name: 'Script budget' })).toBeVisible();
  await expect(accordion.getByRole('heading', { name: 'Advanced diagnostics' })).toBeVisible();

  await scriptSection.locator('input[type="file"]').first().setInputFiles({
    name: 'script.txt',
    mimeType: 'text/plain',
    buffer: Buffer.from('<Host> Imported script keeps the production moving.'),
  });

  await expect(scriptSection.getByRole('heading', { name: 'Editor and timeline, side by side.' })).toBeVisible();
  await expect(scriptSection.locator('.script-timeline-panel').getByText('imported_line_001', { exact: true })).toBeVisible();
  await expect(scriptSection.getByRole('button', { name: /Continue to Cast & Voices/ })).toBeEnabled();
});

test('Production Builder Script reflects delayed generation and preserves generated payload on accept', async ({ page }) => {
  let acceptedPayload: Record<string, unknown> | null = null;
  await installProjectEditorMocks(page, {
    scriptRevision: null,
    generationDelayMs: 500,
    onAcceptedPayload: (body) => {
      acceptedPayload = body;
    },
  });

  await page.goto('/projects/42?tab=script#step-script');
  await page.locator('#step-script').getByRole('button', { name: /Generate with Ollama/ }).first().click();
  await expect(page.locator('#step-script').getByRole('heading', { name: 'Writing the script...' })).toBeVisible();
  await expect(page.locator('#step-script .script-line-row.pending').first()).toContainText('Generation pending');

  await expect(page.locator('#step-script').getByRole('heading', { name: 'Editor and timeline, side by side.' })).toBeVisible();
  await expect(page.locator('#step-script .script-timeline-panel').getByText('line_001', { exact: true })).toBeVisible();

  await page.locator('#step-script').getByRole('button', { name: /Accept & Continue/ }).click();
  await expect(page.locator('#step-cast').getByRole('heading', { name: 'Cast & Voices' })).toBeVisible();
  expect(acceptedPayload?.generated_script).toBeTruthy();
  expect((acceptedPayload?.parsed_lines as Array<Record<string, unknown>>)[0].line_id).toBe('line_001');
});

test('Production Builder Script shows failed state from real generation errors', async ({ page }) => {
  await installProjectEditorMocks(page, { scriptRevision: null, generationShouldFail: true });

  await page.goto('/projects/42?tab=script#step-script');
  await page.locator('#step-script').getByRole('button', { name: /Generate with Ollama/ }).first().click();

  const scriptSection = page.locator('#step-script');
  await expect(scriptSection.getByRole('heading', { name: 'Generation failed - repair to continue.' })).toBeVisible();
  await expect(scriptSection.getByText('Parser error on line_006. Speaker tag missing.')).toBeVisible();
  await expect(scriptSection.getByRole('button', { name: /Retry generation/ })).toBeVisible();
  await expect(scriptSection.getByRole('button', { name: /Continue to Cast & Voices/ })).toBeDisabled();
});

test('Production Builder Script remains usable without horizontal overflow on mobile', async ({ page }) => {
  await installProjectEditorMocks(page, { scriptRevision: null });
  await page.setViewportSize({ width: 390, height: 844 });

  await page.goto('/projects/42?tab=script#step-script');
  await page.setViewportSize({ width: 390, height: 844 });
  await page.locator('#step-script').getByRole('button', { name: /Generation controls/ }).click();
  await expect(page.locator('#step-script').getByRole('heading', { name: 'Advanced diagnostics' })).toBeVisible();

  const overflow = await page.evaluate(() => document.documentElement.scrollWidth > document.documentElement.clientWidth + 1);
  expect(overflow).toBe(false);
});

test('authenticated Project Editor render surfaces cache warmth, changes, labels, badges, and preview updates', async ({ page }) => {
  await installProjectEditorMocks(page);

  await page.goto('/projects/42?tab=render#step-render');

  await expect(page).toHaveURL('http://localhost:3000/projects/42?tab=render#step-render');

  const renderSection = page.locator('#step-render');
  await expect(renderSection.getByRole('heading', { name: 'Render' })).toBeVisible();
  await expect(renderSection.getByText('Render Cache Warmth')).toBeVisible();
  await expect(renderSection.getByText('50% warm · 1 cached voice segment(s), 1 to regenerate')).toBeVisible();
  await expect(renderSection.getByText('What Changed?')).toBeVisible();
  await expect(renderSection.getByText('1 line(s) need fresh voice WAVs.')).toBeVisible();
  await expect(renderSection.getByText('guest-cache-miss')).toBeVisible();
  await expect(renderSection.getByText('Voice profile assignments match the latest render snapshot.')).toBeVisible();
  await expect(renderSection.getByText('Layout and overlay settings match the latest render snapshot.')).toBeVisible();
  await expect(renderSection.locator('.op-badge').filter({ hasText: 'Warning' }).first()).toBeVisible();
  await expect(renderSection.locator('.op-badge').filter({ hasText: 'Verified' }).first()).toBeVisible();

  const previewSettingsPanel = page.locator('#pre-render-preview');
  await expect(previewSettingsPanel.locator('[aria-label="pre-render settings preview frame"]')).toBeVisible();
  await expect(previewSettingsPanel.getByText('1.00x')).toBeVisible();

  const patchRequest = page.waitForRequest((request) =>
    request.url() === 'http://localhost:3000/projects/42/preview-settings' && request.method() === 'PATCH'
  );
  await previewSettingsPanel.getByRole('button', { name: 'Larger' }).first().click();
  const request = await patchRequest;
  expect(JSON.parse(request.postData() || '{}')).toEqual({
    layout: { character_scale: 1.05, chat_font_size_px: 18 },
  });

  await expect(previewSettingsPanel.getByText('1.05x')).toBeVisible();
  await expect(renderSection.getByText('Layout, caption, speaker PNG size, or render preset changed; overlay/final MP4 cache may invalidate.')).toBeVisible();
  await expect(renderSection.getByText('overlay layer')).toBeVisible();
  await expect(renderSection.getByText('final mp4', { exact: true })).toBeVisible();

  await page.goto('/projects/42?tab=preview#step-preview');
  await expect(page.locator('[aria-label="approved production preview frame"]')).toBeVisible();
  await expect(page.locator('[aria-label="pre-render settings preview frame"]')).toHaveCount(0);
  await expect(page.locator('[aria-label="9:16 production preview"]')).toHaveCount(0);
});

test('authenticated Project Editor exposes approved builder stages and generated media handoff', async ({ page }) => {
  await installProjectEditorMocks(page);

  await page.goto('/projects/42?tab=script#step-script');

  const stageStrip = page.locator('[aria-label="Production builder stages"]');
  await expect(stageStrip.getByRole('button', { name: /Script/ })).toBeVisible();
  await expect(stageStrip.getByRole('button', { name: /Cast & Voices/ })).toBeVisible();
  await expect(stageStrip.getByRole('button', { name: /Preview/ })).toBeVisible();
  await expect(stageStrip.getByRole('button', { name: /Render/ })).toBeVisible();
  await expect(stageStrip.getByRole('button', { name: /Generated Media/ })).toBeVisible();
  await expect(stageStrip.getByRole('button', { name: /Release/ })).toBeVisible();

  await stageStrip.getByRole('button', { name: /Cast & Voices/ }).click();
  await expect(page.locator('#step-cast').getByRole('heading', { name: 'Cast & Voices' })).toBeVisible();

  await stageStrip.getByRole('button', { name: /Preview/ }).click();
  await expect(page.locator('#step-preview').getByRole('heading', { name: 'Preview' })).toBeVisible();
  await expect(page.locator('[aria-label="approved production preview frame"]')).toHaveCount(1);
  await expect(page.locator('[aria-label="pre-render settings preview frame"]')).toHaveCount(0);
  await expect(page.locator('[aria-label="9:16 production preview"]')).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Scene and layout controls' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Preview readiness and diagnostics' })).toBeVisible();

  await stageStrip.getByRole('button', { name: /Render/ }).click();
  await expect(page.locator('#step-render').getByRole('heading', { name: 'Render' })).toBeVisible();

  await stageStrip.getByRole('button', { name: /Generated Media/ }).click();
  await expect(page.locator('#step-generated-media').getByRole('heading', { name: 'Generated Media' })).toBeVisible();
  await expect(page.locator('#step-generated-media').getByText('draft.mp4')).toBeVisible();
});
