# Omniposter Project Manual

Last updated: 2026-05-01

## Product Vision

Omniposter is a creator workflow tool for generating repeatable video content from reusable assets.

It should support script-to-video generation, reusable characters, reusable backgrounds, accurate dialogue-driven speaker overlays, TTS generation with a Docker-safe local fallback, clone-capable reference-based voice profiles, preview/export workflows, metadata preparation, job tracking, and future publishing integrations.

The product should become a system creators can use repeatedly, not a one-off renderer.

## Supporting Goals

Omniposter should support:

- Script-to-video generation.
- Dialogue-based accurate character speaker overlays.
- TTS generation with a reliable local fallback.
- Clone-capable and reference-based voice profiles.
- Background preset management.
- Upload metadata preparation.
- Job tracking and preview generation.
- Future platform integrations for automated publishing.

## Functional MVP Goals

The MVP should allow the user to:

1. Upload or select character images.
2. Upload or select background videos from presets.
3. Write a two-speaker or multi-speaker dialogue script.
4. Parse script lines into speaker segments.
5. Map each speaker to a character image.
6. Map each speaker to a voice profile.
7. Generate TTS audio per line or per segment.
8. Assemble audio, background, captions or basic text overlays, and active speaker portraits into a video.
9. Preview generated output.
10. Export the generated video file.
11. View job status, errors, and generation logs from the UI.

## Technical MVP Goals

The MVP should provide:

1. A FastAPI backend with clear REST endpoints.
2. A React + Tailwind frontend with simple generation forms and preview panels.
3. A Celery worker for long-running generation jobs.
4. A local storage structure for uploaded assets, generated files, voice profiles, and presets.
5. A provider abstraction for TTS engines.
6. A reliable fallback TTS provider that works inside Docker.
7. OpenVoice V2 integration as the main clone-capable provider when configured.
8. Health checks for API, worker, storage, ffmpeg, TTS providers, and OpenVoice availability.
9. Regression tests for critical rendering and TTS behavior.

## Product Modules

Omniposter should be organized around clear product modules:

- Dashboard
- Script Studio
- Character Library
- Voice Lab
- Background Presets
- Video Generator
- Job Monitor
- Generated Media Library
- Upload / Publishing Prep
- System Health and Settings

Each module should have a clear boundary so the project remains maintainable.

## Core Domain Model

These domain concepts should remain distinct:

### Script

A user-authored dialogue script. It may contain two speakers or many speakers.

### Speaker Segment

A parsed unit of dialogue with:

- Speaker name or id.
- Text.
- Segment order.
- Expected timing after TTS generation.
- Links to character image and voice profile after mapping.

Speaker segments should become the canonical timeline for audio, captions, and active speaker overlays.

### Character

A reusable visual speaker identity. Character assets should not be loaded from background preset directories.

### Voice Profile

A reusable voice configuration. A voice profile may use local fallback TTS, OpenVoice V2, or a future provider.

### Background Preset

A reusable video background source. Background presets should not be treated as speaker images.

### Generation Job

A long-running video generation task managed by the backend and worker. The UI should be able to show status, errors, logs, preview output, and export output.

### Generated Media

The output video and any intermediate artifacts worth exposing or debugging.

## Architecture Expectations

### Backend

- FastAPI should expose clear REST endpoints.
- Long-running video generation should be queued through Celery.
- Backend code should separate API routes, services, providers, storage, and rendering concerns.
- Health checks should report provider availability and common runtime dependencies.

### Frontend

- React + Tailwind should provide simple, visible generation controls.
- The UI should expose job status, preview, errors, and logs.
- Frontend modules should map to product modules when practical.

### Worker

- Celery should perform long-running video generation work.
- Worker tasks should report status and errors.
- Worker tasks should avoid blocking API request handlers.

### Storage

The MVP may use local filesystem storage. Storage paths should keep asset classes separate:

- Character images
- Background presets
- Uploaded source media
- Voice profiles and reference audio
- Generated audio
- Generated videos
- Job logs or metadata

Generated media, model checkpoints, and large uploaded assets should not be committed to git.

### TTS

TTS must use a provider abstraction.

Required provider tiers:

1. Docker-safe local fallback provider.
2. OpenVoice V2 provider when configured and available.
3. Future providers can be added without rewriting the video generation pipeline.

The app must not assume OpenVoice is installed or available. It should detect availability and expose status through health checks.

### Rendering

The renderer should use the parsed speaker segment timeline as the source of truth for:

- Per-segment audio.
- Segment timing.
- Captions or text overlays.
- Active speaker portrait visibility.
- Final video assembly.

The renderer must not guess speaker identity from file ordering when explicit speaker mappings exist.

## Non-Goals for MVP

The MVP does not need to provide:

- Fully automated publishing to every platform.
- Production cloud storage.
- Production user billing.
- Enterprise-scale queue orchestration.
- Perfect voice cloning quality.
- Full video editor functionality.
- Complex timeline editing UI.

These can be added later after the core generation loop is reliable.

## MVP Acceptance Standard

A feature is MVP-ready only when:

- The user can access it from the UI or documented API.
- It has a clear implementation location.
- It has a test, manual verification, or command result.
- Its status is reflected in `docs/MVP_CHECKLIST.md`.
- Any bug fixes or known risks are reflected in `docs/CURRENT_STATUS.md` or `docs/KNOWN_MISTAKES.md`.
