# Omniposter Repo Map

Last updated: 2026-06-01

Use this map before broad scans. Inspect the smallest relevant area first, then expand only when evidence requires it.

## Backend

- `backend/app/main.py` - FastAPI app setup and router registration.
- `backend/app/api/` - Thin FastAPI route modules — canonical home for all 14 API route files (assets, auth, character_presets, generation, history, metadata, productions, projects, publish, reviews, routing, script_generation, scripts, social_accounts).
- `backend/app/domains/` - Product-domain logic. Seven domains now exist: `domains/script_generation/` owns script generation behavior; `domains/render/` owns render cache-keys, preset/layout, pure geometry, audio timeline and mixdown payloads, planning, readiness, artifact metadata, cache report, and diagnostics; `domains/voice/` owns voice/TTS provider contracts, provider capability helpers, Docker-safe espeak fallback, Voice Lab override helpers, TTS synthesis orchestration, pure audio helpers, manifest profile normalization, ephemeral profile payloads, provider artifact paths, and selected character recipe validation; `domains/jobs/` owns generation job status constants, transition predicates, stale recovery, quota rules, polling helpers, and diagnostics; `domains/media/` owns background media validators, upload helpers, quota predicates, asset classification, artifact URL building, and storage diagnostics; `domains/projects/` owns project readiness predicates, diagnostic helpers, workflow state machine, preview settings normalization, URL aliases, ownership queries, and speaker-binding utilities; `domains/publishing/` owns platform capability rules, publish job lifecycle predicates, scheduling helpers, account routing logic, history projections, metadata helpers, and publishing diagnostics. Renderer orchestration/runtime side effects remain in `backend/app/services/rendering.py` until Phase 1.8+.
- `backend/app/infra/` - Low-level runtime adapters. `backend/app/infra/ffmpeg/` centralizes reusable FFmpeg/ffprobe helpers, `backend/app/infra/storage/` centralizes local filesystem/path helpers, `backend/app/infra/redis/` centralizes Redis client/rate-limit primitives, and `backend/app/infra/ollama/` centralizes generic Ollama HTTP transport.
- `backend/app/workers/` - Thin Celery worker wrappers — canonical home for all 5 task implementations (generation, publish, scheduler, voice_operations, voice_preview).
- `backend/app/routers/` - Compatibility re-export shims only (`from app.api.X import *`). All route logic lives in `backend/app/api/`. Import paths `app.routers.*` remain valid for backward compat.
- `backend/app/services/` - Application services, integration surfaces, and compatibility re-export shims. `services/platforms.py` and `services/routing.py` are now full re-export shims to domains/publishing. `services/project_state.py` re-exports domain symbols and retains projection functions (to_*_summary). `services/tts.py` retains `LocalSpeechService`, `ProviderRegistry`, and `TTSOrchestrator` as application-layer wiring; OpenVoice/XTTS/RVC provider bodies are shims to domains/voice. `services/rendering.py` intentionally retains FFmpeg/MoviePy orchestration, render cache materialization, TTS handoff, PIL drawing/saving, generated artifact writes, and final file-stat assembly until Phase 1.8+. `services/youtube_accounts.py` and `services/youtube_publish.py` are OAuth/HTTP integration surfaces that stay in services. `services/crypto.py`, `services/audit.py`, and `services/notifications.py` are cross-cutting infrastructure helpers.
- `backend/app/tasks/` - Compatibility re-export shims only (`from app.workers.X import *`). All task logic lives in `backend/app/workers/`. Task name strings (`app.tasks.*`) are preserved in worker decorators for wire-protocol backward compat.
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
- Rendering/job issues: start with `backend/app/services/rendering.py`, `backend/app/workers/generation.py`, `backend/app/api/generation.py`, and Project Editor UI.
- Background presets: start with `backend/app/services/storage.py`, `backend/app/services/character_presets.py` if speaker presets are involved, asset/generation routes, and Project Editor selectors.
- Character/speaker mapping: start with script parsing, generation payload schemas, character preset services, rendering, and Project Editor mappings.
