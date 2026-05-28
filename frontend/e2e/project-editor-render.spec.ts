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

const makeProject = (previewSettings: typeof basePreviewSettings) => ({
  id: 42,
  name: 'Render Coverage Production',
  status: 'draft',
  target_platform: 'youtube_shorts',
  background_style: 'none',
  background_source_type: previewSettings.background_source_type,
  background_asset_id: previewSettings.background_asset_id,
  selected_social_account_id: null,
  current_script_revision_id: scriptRevision.id,
  current_output_video_id: output.id,
  automation_mode: 'manual',
  preferred_account_type: null,
  allowed_platforms: ['youtube_shorts'],
  publish_windows: [],
  approved_at: null,
  created_at: now,
  updated_at: now,
  current_script: scriptRevision,
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

const installProjectEditorMocks = async (page: Page) => {
  let previewSettings = structuredClone(basePreviewSettings);
  const originalRenderSnapshot = structuredClone(basePreviewSettings);

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
      await json(route, makeProject(previewSettings));
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

    if (path === '/projects/42/script') {
      await json(route, { current_revision: scriptRevision });
      return;
    }

    if (path === '/projects/42/script-revisions') {
      await json(route, { items: [scriptRevision] });
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

test('authenticated Project Editor render surfaces cache warmth, changes, labels, badges, and preview updates', async ({ page }) => {
  await installProjectEditorMocks(page);

  await page.goto('/projects/42?tab=render#step-render');

  await expect(page).toHaveURL('http://localhost:3000/projects/42?tab=render#step-render');
  await expect(page.getByRole('heading', { name: 'Render Coverage Production' })).toBeVisible();

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
  await expect(page.locator('[aria-label="pre-render settings preview frame"]')).toBeVisible();
  await expect(page.locator('[aria-label="9:16 production preview"]')).toHaveCount(0);
});
