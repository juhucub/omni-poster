import { expect, test } from './fixtures/localhostOnly';
import type { Page, Route } from '@playwright/test';

const now = '2026-05-21T20:00:00.000Z';

const emptyMp4 = Buffer.from('');

const generatedMediaItems = [
  {
    id: 88,
    project_id: 42,
    project_name: 'Render Coverage Production',
    project_status: 'approved',
    generation_job: {
      id: 123,
      project_id: 42,
      status: 'completed',
      progress: 100,
      style_preset: 'default',
      output_kind: 'draft',
      provider_name: 'local',
      error_message: null,
      voice_manifest: { speakers: { Host: { speaker: 'Host', provider: 'espeak', voice_profile_id: 'voice_host' } } },
      preview_settings: { speaker_mappings: [], background_metadata: {}, layout: { character_scale: 1, chat_font_size_px: 18 } },
      tts_result: {
        segments: [
          {
            segment_id: 'seg-host-1',
            segment_index: 0,
            speaker: 'Host',
            provider_used: 'espeak',
            voice_profile_id: 'voice_host',
            artifact_url: '/generation-jobs/123/artifacts/segments/seg-host-1.wav',
            normalized_audio_artifact_url: '/generation-jobs/123/artifacts/segments/seg-host-1.normalized.wav',
            duration_seconds: 1.2,
          },
        ],
      },
      provider_state: {},
      current_phase: null,
      cache_statistics: { hits: 1, misses: 0 },
      timing_breakdown: {},
      performance_summary: {},
      artifact_urls: {},
      debug_artifacts: {},
      output_video_id: 88,
      started_at: now,
      finished_at: now,
      created_at: now,
    },
    output: {
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
    },
    artifact_urls: {},
    provider_state: {},
    created_at: now,
  },
  {
    id: 89,
    project_id: 42,
    project_name: 'Render Coverage Production',
    project_status: 'approved',
    generation_job: null,
    output: {
      id: 89,
      project_id: 42,
      output_kind: 'final',
      provider_name: 'local',
      is_preview: false,
      duration_ms: 11000,
      asset: {
        id: 89,
        kind: 'generated_video',
        source_type: 'generated',
        preset_key: null,
        provider_name: 'local',
        mime_type: 'video/mp4',
        original_filename: 'final.mp4',
        size_bytes: 8192,
        duration_ms: 11000,
        width: 1080,
        height: 1920,
        content_url: '/assets/89/content',
        metadata: {},
        created_at: now,
      },
      created_at: now,
    },
    artifact_urls: {},
    provider_state: {},
    created_at: now,
  },
];

const json = async (route: Route, body: unknown, status = 200) => {
  await route.fulfill({ status, contentType: 'application/json', body: JSON.stringify(body) });
};

const installGeneratedMediaMocks = async (page: Page) => {
  await page.route('**/*', async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (url.origin !== 'http://localhost:3000' || request.resourceType() === 'document') {
      await route.fallback();
      return;
    }

    if (path === '/auth/me') {
      await json(route, { id: 1, username: 'playwright', preferences_summary: {} });
      return;
    }

    if (path === '/generated-media') {
      await json(route, { items: generatedMediaItems });
      return;
    }

    if (path.startsWith('/assets/') && path.endsWith('/content')) {
      await route.fulfill({ status: 200, contentType: 'video/mp4', body: emptyMp4 });
      return;
    }

    if (path.startsWith('/generation-jobs/') && path.includes('/artifacts/')) {
      await route.fulfill({ status: 200, contentType: 'audio/wav', body: Buffer.from('RIFF') });
      return;
    }

    await route.fallback();
  });
};

test('Generated Media route renders real library tabs and honest empty states', async ({ page }) => {
  await installGeneratedMediaMocks(page);

  await page.goto('/generated-media');
  await expect(page).toHaveURL('http://localhost:3000/generated-media');
  await expect(page.getByRole('heading', { name: 'Latest render, then the shelf.' })).toBeVisible();
  await expect(page.getByRole('tab', { name: /All/ })).toBeVisible();
  await expect(page.getByText('draft.mp4')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'final.mp4' }).first()).toBeVisible();

  await page.getByRole('tab', { name: /Finals/ }).click();
  await expect(page.getByRole('heading', { name: 'final.mp4' }).first()).toBeVisible();
  await expect(page.getByText('draft.mp4')).toHaveCount(0);

  await page.getByRole('tab', { name: /Drafts/ }).click();
  await expect(page.getByText('draft.mp4')).toBeVisible();

  await page.getByRole('tab', { name: /Segment WAVs/ }).click();
  await expect(page.getByRole('heading', { name: 'Segment WAVs' })).toBeVisible();
  await expect(page.getByText('voice_host')).toBeVisible();
  await expect(page.getByRole('link', { name: 'Original WAV' })).toBeVisible();

  await page.getByRole('tab', { name: /Uploads/ }).click();
  await expect(page.getByText('No uploaded media is exposed by this library endpoint yet.')).toBeVisible();

  await page.getByRole('tab', { name: /Backgrounds/ }).click();
  await expect(page.getByText('No background library endpoint is wired here yet.')).toBeVisible();
});
