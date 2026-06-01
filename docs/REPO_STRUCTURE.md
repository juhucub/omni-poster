# Omniposter Repo Structure

Last updated: 2026-06-01

Omniposter is moving toward a lean modular monorepo layout. Keep source code, seed assets, deployment config, local scripts, docs, and runtime outputs in separate homes.

## Source Directories

- `backend/app/api/` - thin FastAPI route modules — canonical home for all API route files. `backend/app/routers/` is a compatibility shim layer (`from app.api.X import *`).
- `backend/app/core/` - shared configuration and process-wide app utilities.
- `backend/app/db/` - future database/session helpers. Current DB entrypoint remains `backend/app/db.py` until migrated.
- `backend/app/domains/` - product-domain logic. Seven domain packages now exist:
  - `domains/script_generation/` — script generation formats, prompts, providers, normalizers, validators, platform helpers, and caption utilities.
  - `domains/render/` — render cache keys, preset/layout decisions, pure geometry helpers, audio timeline and mixdown payload helpers, background/video concat and command payload helpers, render planning metadata, readiness estimates, artifact metadata shaping, cache report summaries, and diagnostics summaries.
  - `domains/voice/` — voice/TTS provider contracts, provider registry and capability selection, Docker-safe espeak fallback, Voice Lab override payloads, TTS synthesis orchestration, pure audio metadata helpers, Voice Lab preview provider selection, manifest profile normalization, ephemeral profile payload decisions, DB voice-profile-to-preview payload projection, pure TTS cache-key and provider failure/result metadata helpers, provider artifact path/hash helpers, voice runtime path helpers, and selected character recipe validation.
  - `domains/jobs/` — generation job status constants, transition predicates, stale job recovery, queue quota rules, polling helpers, and diagnostics.
  - `domains/media/` — background media MIME validators, upload helpers, size/storage quota predicates, asset kind classification, artifact URL building, and storage file diagnostics.
  - `domains/projects/` — project readiness predicates, diagnostic helpers (latest preview, latest review), workflow state machine (sync_project_state), preview settings normalization, asset URL aliases, ownership queries, and speaker-binding sample extraction.
  - `domains/publishing/` — platform capability rules, publish job lifecycle status predicates, schedule-due helpers, account routing logic (is_account_routing_eligible, choose_social_account, suggest_destination), history projections (to_post_summary), metadata helpers, and account/project publishing diagnostics.
  Full video composition, cache materialization, concrete renderer orchestration, and generated artifact writes remain in `backend/app/services/rendering.py`.
- `backend/app/infra/` - low-level adapters for storage, FFmpeg, Redis, Ollama, and similar runtime dependencies. Storage path/filesystem helpers belong under `backend/app/infra/storage/`; Redis client/rate-limit primitives belong under `backend/app/infra/redis/`; generic Ollama HTTP transport belongs under `backend/app/infra/ollama/`.
- `backend/app/workers/` - thin Celery worker wrappers — canonical home for all Celery task implementations. `backend/app/tasks/` is a compatibility shim layer (`from app.workers.X import *`). Task name strings (`app.tasks.*`) are preserved in `@celery.task(name=...)` decorators for wire-protocol backward compat.
- `frontend/src/features/` - future feature-oriented frontend modules. Existing frontend pages/components remain in place until moved safely.
- `deploy/` - Docker and deployment configuration.
- `docs/` - project memory, product docs, architecture decisions, and repo structure docs.
- `scripts/` - local development and verification scripts.

## Runtime Directories

- `runtime/` - local generated runtime data for future migrations. It is ignored by Git.
- `backend/storage/` - current local runtime storage for uploads, generated artifacts, voice profiles, voice models, render cache, and generated job artifacts.
- `backend/generated_videos/` and `generated_videos/` - legacy/generated video output folders. They are ignored and should not receive new source files.

Generated artifacts must stay out of source directories. This includes generated MP4/WAV files, local databases, Celery schedule files, render cache, Playwright reports, frontend build output, voice datasets, and model/checkpoint files.

## Seed Assets

- `seed_assets/` is the future tracked home for small curated seed assets and manifests.
- Large preset videos, voice datasets, checkpoints, and generated media should not be committed directly. Use external storage or an intentional large-file strategy before adding them.
- Do not mix seed assets with runtime outputs.

## What Belongs In Git

- Source code, tests, docs, migrations, deployment config, small manifests, placeholders, and local scripts.
- `.gitkeep` or README files that preserve expected empty directories.
- Small seed metadata only when it is intentionally part of the app.

## What Must Stay Ignored

- Local DBs and SQLite files.
- Celery schedule DBs and worker PID/runtime files.
- Generated videos, generated audio, render cache, and generated job artifacts.
- Uploaded user media and project-specific media.
- Voice datasets, processed reference audio, previews, embeddings, selected local recipes, and model checkpoints.
- Frontend `build/`, `dist/`, Playwright reports, test results, and dependency caches.
- Docker volumes, virtual environments, `node_modules`, Python caches, and OS/editor caches.

## Adding New Files

- Search first before creating a new module; prefer the existing owner.
- Add domain behavior under the closest `backend/app/domains/<domain>/` owner.
- Add low-level runtime adapters under `backend/app/infra/<adapter>/`.
- Keep routers and workers thin; route handlers and Celery tasks should delegate to domain services.
- Update this document when adding a permanent top-level directory or changing source/runtime ownership.
