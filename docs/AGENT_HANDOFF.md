# Omniposter Agent Handoff Protocol

Last updated: 2026-05-28

Use this protocol when switching work between Codex, Claude Code, or any other coding agent. The goal is a clean trade-off: one agent can stop, another can continue, and project memory, runtime safety, and verification evidence stay intact.

## Core Rule

Only one agent should actively edit a scope at a time. Parallel work is acceptable only when file ownership is disjoint and each agent has a clearly bounded task.

Do not let two agents edit the same large orchestration files, migration files, frontend page, or docs section at the same time.

## Required Pre-Flight

Before starting work, the active agent must read:

1. `AGENTS.md`
2. `docs/AGENT_BRIEF.md`
3. `docs/CONTEXT_INDEX.md`
4. `docs/TASK_ROUTING.md`
5. `docs/REPO_MAP.md`
6. This file

Then inspect the smallest relevant code area for the task. Do not perform a broad rewrite or broad scan unless the task requires it.

## Handoff Packet

Every handoff between agents should include:

- Current phase or task name.
- Files intentionally changed.
- Files intentionally not touched.
- Compatibility imports or shims that must remain.
- Runtime/generated paths that must not be moved, deleted, or committed.
- Tests run and exact result.
- Known failures, skipped checks, or local-only assumptions.
- Next recommended scoped task.

Use this compact format:

```md
## Handoff
Current task:
Changed files:
Do not touch:
Compatibility surfaces:
Runtime paths protected:
Tests run:
Failures/skips:
Next task:
```

## Checkpoint Rules

Create a Git checkpoint when:

- A migration phase or provider/render/storage boundary slice is complete and tests pass.
- The worktree is broad enough that the next agent could confuse baseline changes with new edits.
- A second agent will continue from the current state.

Before checkpointing:

1. Run `git status --short`.
2. Run `bash scripts/dev/check_repo_hygiene.sh`.
3. Run the targeted compile/tests for the changed area.
4. Confirm no generated media, local DBs, model checkpoints, dependency caches, or runtime outputs are staged.
5. Use a clear commit message that names the phase or boundary.

Do not checkpoint a failing or partially verified state unless the commit message clearly says it is an intentionally incomplete WIP checkpoint.

## Conflict Avoidance

Avoid overlapping edits in these high-risk files unless the previous agent has fully stopped and checkpointed:

- `backend/app/services/rendering.py`
- `backend/app/services/tts.py`
- `backend/app/services/voice_profiles.py`
- `backend/app/tasks/generation.py`
- `backend/app/models.py`
- `backend/app/schemas.py`
- `frontend/src/pages/ProjectEditorPage.tsx`
- `frontend/src/pages/VoiceLabPage.tsx`
- living context docs under `docs/`

Prefer handing off one bounded phase at a time, such as `Phase 6Q: move RVCProvider`, rather than a broad instruction like "continue voice migration."

## Safety Invariants

Every agent must preserve these invariants unless the user explicitly approves a new architecture decision:

- Public API routes remain stable.
- Celery task names remain stable.
- Database schema does not change unless the task explicitly requires a migration.
- TTS provider abstraction remains intact.
- OpenVoice, XTTS, and RVC selections fail closed when unavailable.
- Docker-safe fallback TTS remains available only when fallback is allowed.
- Final MP4 audio uses persisted per-job segment WAV artifacts.
- Voice Lab preview audio is never reused as final render audio.
- Runtime media, generated videos, local DBs, voice datasets, model checkpoints, and Docker volumes stay out of source control.

## Recommended Validation Baseline

For backend architecture migration slices, run:

```bash
bash scripts/dev/check_repo_hygiene.sh
python3 -m compileall backend/app
python3 -m pytest backend/app/tests/test_voice_domain.py -q
python3 -m pytest backend/app/tests/test_render_domain.py -q
python3 -m pytest backend/app/tests/test_script_generation.py -q
python3 -m pytest backend/app/tests/test_vertical_slice.py -q
```

For frontend route or behavior changes, also run:

```bash
cd frontend && npm test -- --watchAll=false
cd frontend && npm run build
cd frontend && npm run test:e2e
```

Run frontend E2E only when the frontend dev server/runtime assumptions are safe for the task.

## Stop Conditions

Stop and report instead of continuing when:

- More than ten files need non-mechanical changes for a migration slice.
- A provider move changes fallback or fail-closed behavior.
- A render move changes artifact paths, cache keys, persisted WAV usage, or output behavior.
- A test failure touches persisted segment WAVs, Voice Lab preview isolation, provider fallback, XTTS selected recipes, or generated artifact serving.
- The agent cannot tell whether a dirty worktree change belongs to the current task.

