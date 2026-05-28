# OmniPoster

OmniPoster is a local-first AI short-form video production studio.

The current MVP is centered on a repeatable creator workflow:

```text
Script -> speaker-separated dialogue -> voice profile assignment -> preview -> render -> downloadable/releasable video
```

It is a production command room for reusable projects, scripts, characters, voice profiles, scenes, render jobs, artifacts, and release prep.

## Current Product Surface

- **Command Room**: primary dashboard at `/` with production state, start-production flow, preview/render controls, queues, studio health, channels, and release gating.
- **Production Lab**: detailed project view at `/projects/:projectId` for scripts, backgrounds, voice mappings, preview settings, renders, review, metadata, routing, publishing, and history.
- **Voice Lab**: detailed voice/profile workspace at `/voice-lab` for character presets, reference audio, provider checks, calibration, datasets, and voice preview jobs.
- **Productions**: project list/create surface at `/projects`.
- **Channels / Release History**: connected account and publish-history surfaces for the existing publishing support.

## Stack

- Frontend: React, TypeScript, Tailwind, Vite, CRACO/Jest
- Backend: FastAPI, SQLAlchemy, Alembic
- Jobs: Celery workers for generation, publishing, and voice operations
- Queue/cache: Redis
- Database: PostgreSQL
- Media/runtime: local filesystem storage, FFmpeg, Docker-safe fallback TTS, optional OpenVoice, optional XTTS/RVC, optional Ollama

## Local Setup

1. Create local environment config:

```bash
cp .env.example .env.dev
```

2. Start backend services:

```bash
docker compose -f deploy/compose/docker-compose.yml --profile ollama up --build
```

The API container runs `alembic upgrade head` before starting Uvicorn.

3. Start the frontend in another terminal:

```bash
cd frontend
npm install
npm start
```

Default local URLs:

- Frontend: `http://localhost:3000`
- API: `http://localhost:8000`
- API health: `http://localhost:8000/health`
- Postgres: `localhost:5432`
- Redis: `localhost:6379`

The frontend dev server binds to `127.0.0.1:3000`. Browser API, artifact, and media requests should stay on the frontend origin and are forwarded to the backend through the Vite dev proxy.

## Docker Services

The compose stack includes:

- `api`: FastAPI app and authenticated artifact serving
- `worker`: Celery generation/publish worker
- `voice_worker`: single-concurrency Voice Lab worker for heavier reference/audio/calibration operations
- `beat`: Celery scheduler
- `postgres`: local dev database
- `redis`: queue broker
- `ollama`: local script-generation service included by the recommended run command

After first startup, pull the default local generation model:

```bash
docker compose -f deploy/compose/docker-compose.yml exec ollama ollama pull llama3.1
```

To shut the Docker stack down:
```bash
docker compose -f deploy/compose/docker-compose.yml --profile ollama down
```

If Ollama is unreachable or disabled, script generation still falls back to deterministic structured templates.

## Important Runtime Notes

- `espeak` is the Docker-safe fallback TTS path.
- OpenVoice, XTTS, and RVC are optional providers and should be treated as unavailable unless configured and reported healthy.
- OpenVoice/XTTS-selected render jobs are expected to fail closed with diagnostics rather than silently falling back.
- Render jobs persist segment WAV artifacts, normalized WAVs, dialogue composite audio, render plans, cache reports, timing profiles, and final MP4 links where available.
- Voice Lab reference processing, dataset analysis, model attach, profile preparation, and calibration jobs run through `voice_worker`, not inside FastAPI request handlers.
- Generated media, model checkpoints, Docker volumes, virtualenvs, and dependency caches should not be committed.

## Key Environment Settings

Core:

```text
FRONTEND_URL=http://localhost:3000
REACT_APP_API_URL=http://localhost:8000
DATABASE_URL=postgresql+psycopg://omni:omni@localhost:5432/omni_dev
REDIS_URL=redis://localhost:6379/0
MEDIA_DIR=backend/storage
SECRET_KEY=replace-me
OAUTH_TOKEN_ENCRYPTION_KEY=replace-with-dedicated-key
```

Optional script generation:

```text
OLLAMA_ENABLED=true
OLLAMA_BASE_URL=http://host.docker.internal:11434
OLLAMA_MODEL=llama3.1
```

Optional publishing:

```text
YOUTUBE_CLIENT_ID=
YOUTUBE_CLIENT_SECRET=
YOUTUBE_REDIRECT_URI=http://localhost:8000/social-accounts/youtube/callback
YOUTUBE_CONNECT_ENABLED=true
```

Optional voice providers and render tuning are documented in `.env.example`.

## Useful Commands

Frontend build:

```bash
cd frontend
npm run build
```

Frontend browser smoke:

```bash
cd frontend
npm run test:e2e
```

Backend regression suites:

```bash
python3 -m pytest backend/app/tests/test_script_generation.py
python3 -m pytest backend/app/tests/test_vertical_slice.py
```

Backend compile check:

```bash
python3 -m compileall backend/app
```

Docker status:

```bash
docker compose -f deploy/compose/docker-compose.yml ps -a
```

## API Areas

Commonly used API surfaces include:

- `/projects` and `/productions`
- `/projects/{id}/script`
- `/script-generation/generate`
- `/projects/{id}/speaker-bindings`
- `/voice-profiles`
- `/character-presets`
- `/background-presets`
- `/projects/{id}/preview-settings`
- `/projects/{id}/renders`
- `/generation-jobs/{id}`
- `/generation-jobs/{id}/artifacts`
- `/projects/{id}/outputs`
- `/social-accounts`
- `/publish-history`

`Project` records currently serve as durable product “Productions.” The `/productions` routes are thin aliases for the existing project model.

## Current Scope

In scope for the MVP:

- create/load productions
- generate or enter speaker-separated scripts
- assign voice profiles to script speakers
- select backgrounds/scenes
- preview with persisted layout/caption/speaker settings
- render preview/draft/final/debug jobs
- inspect/download render artifacts
- prepare release metadata and use existing publish support where configured

Not in scope yet:

- full multi-platform publishing automation
- production cloud storage
- billing/team management
- full timeline editor
- in-app end-to-end model training orchestration

## Repo Structure

backend/app/domains/    Product behavior
backend/app/infra/      Technical adapters
backend/app/api/        API routes
backend/app/workers/    Background workers
frontend/src/features/  Frontend product features
runtime/                Ignored generated artifacts
seed_assets/            Platform-provided presets
docs/                   Architecture and operating docs

## Project Memory

Before broad changes, read:

- `AGENTS.md`
- `docs/AGENT_BRIEF.md`
- `docs/CONTEXT_INDEX.md`
- `docs/TASK_ROUTING.md`
- `docs/REPO_MAP.md`

Product scope and current implementation status live in:

- `docs/PROJECT_MANUAL.md`
- `docs/CURRENT_STATUS.md`
- `docs/MVP_CHECKLIST.md`
- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md`
