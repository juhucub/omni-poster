# Omniposter Repo Map

Last updated: 2026-05-06

Use this map before broad scans. Inspect the smallest relevant area first, then expand only when evidence requires it.

## Backend

- `backend/app/main.py` - FastAPI app setup and router registration.
- `backend/app/routers/` - API routes for auth, assets, character presets, generation jobs, metadata, projects, publishing, reviews, routing, scripts, and social accounts.
- `backend/app/services/` - Business logic for storage, rendering, TTS, voice profiles, voice replication, character presets, scripts, script generation, generation helpers, publishing, auth, notifications, and project state.
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
