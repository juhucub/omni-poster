# Omniposter Project Manual

Last updated: 2026-05-13

## Product Vision

Omniposter is a creator workflow tool for generating repeatable video content from reusable assets.

It should support script-to-video generation, reusable characters, reusable backgrounds, accurate dialogue-driven speaker overlays, TTS generation with a Docker-safe local fallback, clone-capable reference-based voice profiles, licensed character voice replication, preview/export workflows, metadata preparation, job tracking, and future publishing integrations.

The product should become a system creators can use repeatedly, not a one-off renderer.

## Supporting Goals

Omniposter should support:

- Script-to-video generation.
- Dialogue-based accurate character speaker overlays.
- TTS generation with a reliable local fallback.
- Clone-capable and reference-based voice profiles.
- Licensed character voice replication from curated per-character datasets, attached trained models, calibration scoring, and render-path verification.
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

Generated scripts should be structured production data, not raw paragraphs. A generated script should preserve speaker definitions, sectioned lines, caption-ready text, optional visual cues, metadata suggestions, provider diagnostics, and validation warnings while still deriving speaker segments for rendering.

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

A reusable voice configuration. A voice profile may use local fallback TTS, OpenVoice V2, XTTS-style multi-reference cloning, RVC-style voice conversion, or a future provider. Character replication profiles should keep reference datasets, attached model/checkpoint paths, selected recipes, calibration scores, and render verification metadata separate from generic fallback voice settings.

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
- Script generation should prefer local Ollama when configured, but must return deterministic structured fallback output when Ollama is disabled or unavailable.

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
3. XTTS and RVC-style character voice providers when configured and available.
4. Future providers can be added without rewriting the video generation pipeline.

The app must not assume OpenVoice is installed or available. It should detect availability and expose status through health checks.

OpenVoice should be treated as an optional tone-color conversion layer for character replication, not as the whole near-identical voice stack. Licensed character voice replication should use curated reference datasets, prosody analysis, calibration scoring, attached trained models, and strict render-path verification.

### Rendering

The renderer should use the parsed speaker segment timeline as the source of truth for:

- Per-segment audio.
- Segment timing.
- Captions or text overlays.
- Active speaker portrait visibility.
- Final video assembly.

The renderer must not guess speaker identity from file ordering when explicit speaker mappings exist.

Render jobs should leave observable performance evidence without changing render correctness. Profiling output should be written as a generated job artifact at `MEDIA_DIR/generated/{job_id}/generation_profile.json` and exposed through the authenticated job artifact route. The profile should identify slow stages across provider health checks, TTS/profile resolution, XTTS load/conditioning/inference, persisted and normalized segment WAV handling, composite audio, FFmpeg visual assembly, encoding, and debug-only final audio extraction when available.

Runtime performance controls may cap preview/export resolution and FPS separately (`RENDER_PREVIEW_WIDTH`, `RENDER_PREVIEW_HEIGHT`, `RENDER_PREVIEW_FPS_CAP`, `RENDER_EXPORT_WIDTH`, `RENDER_EXPORT_HEIGHT`, `RENDER_EXPORT_FPS_CAP`) and may cap ffmpeg threads (`RENDER_FFMPEG_THREAD_CAP`). Profiling can be toggled with `RENDER_PROFILING_ENABLED`, defaulting on for development. XTTS selected-recipe render segments may reuse loaded runtime objects and conditioning latents inside a worker process with `XTTS_WORKER_CACHE_ENABLED` and `XTTS_WORKER_CACHE_MAX_ENTRIES`. Rendered XTTS/OpenVoice segment WAVs may be reused only through the strict content-addressed render cache when all content-affecting text, voice, provider, reference, recipe, and render settings inputs match; renders must still materialize distinct job-scoped segment WAV artifacts for auditability. Safe CPU inference controls may enable torch inference mode, set optional torch CPU thread caps, and apply an opt-in preview-only split-sentence override. Preview/export x264 preset and CRF may be configured separately while preserving existing defaults. For Docker/dev CPU-only XTTS runs, the measured default profile is `XTTS_CPU_NUM_THREADS=4`, `XTTS_CPU_INTEROP_THREADS=1`, and `CELERY_GENERATION_CONCURRENCY=1`; do not replace persisted render segment WAVs with hidden temp audio or Voice Lab/shared preview audio. Opt-in fast preview testing can also use `RENDER_PREVIEW_WIDTH=540`, `RENDER_PREVIEW_HEIGHT=960`, `RENDER_PREVIEW_FPS_CAP=12`, `RENDER_PREVIEW_ENCODE_PRESET=ultrafast`, `RENDER_PREVIEW_CRF=28`, and `RENDER_FFMPEG_THREAD_CAP=4`.

### Local Ollama Script Generation

Local script generation is configured with `OLLAMA_ENABLED`, `OLLAMA_BASE_URL`, `OLLAMA_MODEL`, `OLLAMA_TIMEOUT_SECONDS`, `OLLAMA_SCRIPT_TEMPERATURE`, `OLLAMA_NUM_PREDICT`, and `OLLAMA_NUM_CTX`.

Docker development can start Ollama with:

```sh
docker compose -f deploy/compose/docker-compose.yml --profile ollama up ollama
docker compose -f deploy/compose/docker-compose.yml exec ollama ollama pull llama3.1
```

When running the backend outside Docker, use a host Ollama service such as `OLLAMA_BASE_URL=http://localhost:11434` and pull the same model with `ollama pull llama3.1`.

If Ollama is not reachable, disabled, times out, or returns invalid output, script generation must return deterministic structured fallback output instead of failing app startup or blocking the script workflow. Provider metadata should expose whether Ollama or fallback produced the script, the failure type when applicable, and bounded generation diagnostics.

## Non-Goals for MVP

The MVP does not need to provide:

- Fully automated publishing to every platform.
- Production cloud storage.
- Production user billing.
- Enterprise-scale queue orchestration.
- In-app full XTTS/RVC training orchestration. The MVP may attach externally trained character model artifacts before adding full training jobs.
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
