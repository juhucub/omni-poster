# Omniposter Task Routing

Last updated: 2026-05-06

Use this file after the always-read docs. Read only the relevant full docs and inspect the smallest code area that can answer the task.

## TTS / Voice Lab / OpenVoice / XTTS / RVC

Read:

- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md` ADR-004, ADR-008, ADR-009
- `docs/CURRENT_STATUS.md` when changing behavior or reporting status
- `docs/MVP_CHECKLIST.md` when verifying MVP TTS/provider requirements

Inspect:

- `backend/app/services/tts.py`
- `backend/app/services/voice_profiles.py`
- `backend/app/services/voice_replication.py`
- `backend/app/services/voice_preview_jobs.py`
- `backend/app/routers/generation.py`
- `backend/app/tasks/voice_preview.py`
- `backend/app/tests/test_vertical_slice.py`
- `frontend/src/pages/VoiceLabPage.tsx`
- `frontend/src/pages/ProjectEditorPage.tsx`
- `deploy/compose/docker-compose.yml` for Docker/runtime provider availability
- `scripts/voice/` for smoke checks

## Rendering / Speaker Segment Timeline

Read:

- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md` ADR-005 and ADR-007
- `docs/PROJECT_MANUAL.md` Rendering section when product requirements are in question
- `docs/MVP_CHECKLIST.md` when verifying assembly, preview, export, or speaker overlays

Inspect:

- `backend/app/services/rendering.py`
- `backend/app/services/tts.py`
- `backend/app/services/scripts.py`
- `backend/app/tasks/generation.py`
- `backend/app/routers/generation.py`
- `backend/app/tests/test_vertical_slice.py`
- `frontend/src/pages/ProjectEditorPage.tsx`

## Background Presets

Read:

- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md` ADR-006
- `docs/MVP_CHECKLIST.md` rows for Background Presets and Video Generator
- `docs/CURRENT_STATUS.md` when changing or verifying behavior

Inspect:

- `backend/app/services/storage.py`
- `backend/app/routers/assets.py`
- `backend/app/routers/generation.py`
- `backend/app/services/vid_gen.py`
- `frontend/src/pages/ProjectEditorPage.tsx`
- Tests that mention background, preset, assets, or generation

## Character Assets / Speaker Mapping

Read:

- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md` ADR-005 and ADR-006
- `docs/MVP_CHECKLIST.md` rows for character images, speaker mapping, and active speaker overlays
- `docs/PROJECT_MANUAL.md` Core Domain Model if boundaries are unclear

Inspect:

- `backend/app/services/scripts.py`
- `backend/app/services/character_presets.py`
- `backend/app/services/rendering.py`
- `backend/app/services/tts.py`
- `backend/app/routers/character_presets.py`
- `backend/app/routers/scripts.py`
- `backend/app/routers/generation.py`
- `backend/app/tests/test_vertical_slice.py`
- `frontend/src/pages/ProjectEditorPage.tsx`

## Job Status / Logs / Generated Artifacts

Read:

- `docs/CURRENT_STATUS.md`
- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md` ADR-003 and ADR-007
- `docs/MVP_CHECKLIST.md` rows for job status, preview, export, generated media, and Celery

Inspect:

- `backend/app/models.py`
- `backend/app/schemas.py`
- `backend/app/routers/generation.py`
- `backend/app/tasks/generation.py`
- `backend/app/services/rendering.py`
- `backend/app/services/storage.py`
- `backend/app/tests/test_vertical_slice.py`
- `frontend/src/pages/ProjectEditorPage.tsx`

## Docker / Runtime / Health

Read:

- `docs/CURRENT_STATUS.md`
- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md` ADR-003, ADR-004, ADR-006, ADR-009
- `docs/MVP_CHECKLIST.md` Technical MVP rows for Docker-safe fallback TTS, OpenVoice, health checks, Celery, and storage

Inspect:

- `deploy/compose/docker-compose.yml`
- `deploy/compose/Dockerfile`
- `backend/requirements.txt`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/app/celery_app.py`
- `backend/app/services/tts.py`
- `backend/app/services/storage.py`
- Health route implementation in `backend/app/routers/` or `backend/app/main.py`
- `scripts/voice/`

## MVP Audit / Full Verification

Read:

- `docs/PROJECT_MANUAL.md`
- `docs/CURRENT_STATUS.md`
- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/MVP_CHECKLIST.md`
- `docs/CODEX_WORKFLOW.md`
- `docs/REPO_MAP.md`

Inspect:

- Backend routes, services, tasks, models, schemas, tests, Docker config, frontend pages, generated media serving, storage boundaries, and `.gitignore`.
- Use broad scans only after consulting `docs/REPO_MAP.md`.

## Documentation / Context-System Changes

Read:

- `docs/CODEX_WORKFLOW.md`
- `docs/REPO_STRUCTURE.md` when changing permanent directories, repo hygiene, or source/runtime ownership
- `docs/CURRENT_STATUS.md`
- `docs/MVP_CHECKLIST.md`
- `docs/ARCHITECTURE_DECISIONS.md` if read strategy or memory architecture changes
- `docs/PROJECT_MANUAL.md` only if product scope or architecture source of truth changes

Inspect:

- `AGENTS.md`
- `docs/AGENT_BRIEF.md`
- `docs/CONTEXT_INDEX.md`
- `docs/TASK_ROUTING.md`
- `docs/REPO_MAP.md`
- Other living context docs only when the routing conditions require them
