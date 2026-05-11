# Omniposter Context Index

Last updated: 2026-05-06

Use this file to reduce context-token usage. Always read the short core first, then read full context docs only when the task calls for them.

## Always Read

- `AGENTS.md`
- `docs/AGENT_BRIEF.md`
- `docs/CONTEXT_INDEX.md`

Also read `docs/TASK_ROUTING.md` when the task touches code, tests, runtime behavior, MVP verification, or any repeated risk area.

## Read Full Docs When Needed

### `docs/PROJECT_MANUAL.md`

Read when the task changes product intent, MVP scope, non-goals, product modules, architecture expectations, or asks what Omniposter should become.

Do not update for routine implementation progress.

### `docs/CURRENT_STATUS.md`

Read when the task asks what currently works, changes app behavior, fixes a bug, verifies runtime behavior, changes priority, or may alter Working/Partial/Broken status.

Update only with evidence from code, tests, endpoint behavior, manual verification, or command output.

### `docs/KNOWN_MISTAKES.md`

Read when the task touches TTS, rendering, voice profiles, generated media, Docker/runtime, storage paths, `.gitignore`, background presets, character assets, speaker mapping, job artifacts, or prior failures.

Read `docs/archive/KNOWN_MISTAKES_ARCHIVE.md` only when the active file points there or historical details are needed.

### `docs/ARCHITECTURE_DECISIONS.md`

Read when the task changes or questions FastAPI/Celery boundaries, storage layout, rendering architecture, TTS provider abstraction, Docker/runtime assumptions, health checks, voice replication, artifact serving, or any cross-module pattern.

Update only when a new architectural decision is made.

### `docs/MVP_CHECKLIST.md`

Read when the task verifies, changes, or reports MVP readiness; touches a Product Manual requirement; or needs evidence-backed status.

Do not mark `Complete` without specific evidence.

### `docs/CODEX_WORKFLOW.md`

Read when the task changes agent workflow, documentation maintenance rules, final response requirements, or prompt/process guidance.

Update only for workflow changes that should apply to future Codex tasks.

## Broad-Context Exceptions

Read all full context docs only when the user explicitly asks for a full audit, broad architecture review, MVP-wide verification, project-memory refresh, or a change that spans most of backend, frontend, runtime, and docs.
