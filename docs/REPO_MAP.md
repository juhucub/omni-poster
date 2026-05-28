# Omniposter Repo Map

Last updated: 2026-05-06

Use this map before broad scans. Inspect the smallest relevant area first, then expand only when evidence requires it.

## Backend

- `backend/app/main.py` - FastAPI app setup and router registration.
- `backend/app/api/` - Future home for thin API route modules; existing routes are still under `backend/app/routers/` until moved safely.
- `backend/app/domains/` - Product-domain logic. `backend/app/domains/script_generation/` now owns script generation behavior, `backend/app/domains/render/` owns render cache-key, preset/layout, pure geometry, audio timeline and mixdown payloads, background/video concat and command payloads, planning, readiness, artifact metadata, cache report, and diagnostics decisions, and `backend/app/domains/voice/` owns initial voice/TTS provider contracts, provider registry/capability selection helpers, provider capability/health metadata payload helpers, Docker-safe espeak fallback behavior, Voice Lab override helpers, TTS synthesis orchestration, pure audio metadata helpers, pure Voice Lab preview provider-selection, manifest profile normalization, ephemeral profile payload decisions, DB voice-profile-to-preview payload projection, pure TTS cache-key and provider failure/result metadata payload helpers, provider artifact path/hash helpers, voice runtime path helpers, and selected character recipe validation. Phase 5 render extraction is stopped; remaining renderer orchestration/runtime side effects stay in `backend/app/services/rendering.py`.
- `backend/app/infra/` - Low-level runtime adapters. `backend/app/infra/ffmpeg/` centralizes reusable FFmpeg/ffprobe helpers, `backend/app/infra/storage/` centralizes local filesystem/path helpers, `backend/app/infra/redis/` centralizes Redis client/rate-limit primitives, and `backend/app/infra/ollama/` centralizes generic Ollama HTTP transport.
- `backend/app/workers/` - Future home for thin worker wrappers around domain services.
- `backend/app/routers/` - API routes for auth, assets, character presets, generation jobs, metadata, projects, publishing, reviews, routing, scripts, and social accounts.
- `backend/app/services/` - Compatibility and still-unmigrated service modules for storage, rendering, TTS, voice profiles, voice replication, character presets, scripts, generation helpers, publishing, auth, notifications, and project state. Script-generation, render-decision, and initial voice/TTS service imports are compatibility surfaces to domain packages. `app.services.tts` still owns concrete OpenVoice, XTTS, and RVC provider bodies plus `LocalSpeechService`; `rendering.py` intentionally still owns FFmpeg/MoviePy orchestration, render cache materialization/stores, TTS handoff, PIL drawing/saving, generated artifact writes, and final file-stat assembly until later domain migrations.
- `backend/app/tasks/` - Celery tasks for generation, voice preview, publishing, and scheduler work.
- `backend/app/models.py` and `backend/app/schemas.py` - Database models and API schemas.
- `backend/app/core/` - Shared configuration and request utilities.
- `backend/alembic/versions/` - Database migrations.
- `backend/app/tests/` - Backend regression and vertical-slice tests.

## Frontend

- `frontend/src/App.tsx` - Frontend route shell.
- `frontend/src/pages/ProjectEditorPage.tsx` - Project editor, video generation workflow, job status, and render diagnostics.
- `frontend/src/pages/VoiceLabPage.tsx` - Voice profiles, reference audio, calibration, recipes, and voice diagnostics.
- `frontend/src/pages/ProjectsPage.tsx` - Project listing and project entry points.
- `frontend/src/pages/AccountManager.tsx` and `frontend/src/pages/PublishHistoryPage.tsx` - Account and publishing surfaces.
- `frontend/src/components/` - Shared navigation and protected-route components.
- `frontend/src/api/` - API client and frontend data models.
- `frontend/src/utils/` - Security and file validation helpers.

## Runtime And Deployment

- `deploy/compose/docker-compose.yml` - API, worker, scheduler, Redis, Postgres, and runtime mounts.
- `deploy/compose/Dockerfile` - Backend/runtime image dependencies.
- `backend/requirements.txt` - Python dependencies.
- `frontend/package.json` - Frontend scripts and dependencies.
- `scripts/voice/` - Voice and XTTS smoke scripts.

## Storage And Generated Artifacts

- `backend/storage/` - Local uploaded assets, voice profiles, voice models, generated job artifacts, and other runtime storage. Do not commit generated media or model artifacts.
- `backend/generated_videos/` and `generated_videos/` - Generated video/media outputs. Do not commit generated outputs.
- `runtime/` - Future ignored local runtime home for generated outputs as storage paths migrate.
- `seed_assets/` - Future tracked home for small curated seed assets and manifests.
- `vendor/OpenVoice/` - Optional OpenVoice runtime source/checkpoints mount area. Do not assume availability without health/runtime checks.

## Tests

- `backend/app/tests/test_vertical_slice.py` - Main backend regression coverage for generation jobs, TTS/provider behavior, voice profiles, render artifacts, and related vertical slices.
- `backend/app/tests/conftest.py` - Backend test fixtures.
- `frontend/package.json` scripts - Frontend build/test entry points.

## Fast Routing Hints

- TTS/provider issues: start with `backend/app/services/tts.py`, `backend/app/services/voice_profiles.py`, `backend/app/services/voice_replication.py`, and Voice Lab UI.
- Rendering/job issues: start with `backend/app/services/rendering.py`, `backend/app/tasks/generation.py`, `backend/app/routers/generation.py`, and Project Editor UI.
- Background presets: start with `backend/app/services/storage.py`, `backend/app/services/character_presets.py` if speaker presets are involved, asset/generation routes, and Project Editor selectors.
- Character/speaker mapping: start with script parsing, generation payload schemas, character preset services, rendering, and Project Editor mappings.
