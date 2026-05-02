# Omniposter Architecture Decisions

Last updated: 2026-05-01

This file records architectural decisions that future Codex agents should not reverse casually.

## ADR-001: Use Context Docs As Living Project Memory

Status: Accepted
Date: 2026-05-01

### Context

Codex agents need durable project memory to avoid repeating mistakes, ignoring current status, or reversing prior decisions.

### Decision

Omniposter uses a `/docs` level context system plus root `AGENTS.md`:

- `AGENTS.md`
- `docs/PROJECT_MANUAL.md`
- `docs/CURRENT_STATUS.md`
- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/MVP_CHECKLIST.md`
- `docs/CODEX_WORKFLOW.md`

Agents must read these before implementation and update them only when necessary.

### Consequences

- Project knowledge is maintained in-repo.
- Completion claims require evidence.
- Documentation updates must be small and factual.

### Files/Areas Affected

- `AGENTS.md`
- `docs/*`

## ADR-002: Organize Omniposter Around Product Modules

Status: Accepted
Date: 2026-05-01

### Context

The product needs to grow from MVP video generation into a maintainable creator workflow tool.

### Decision

Omniposter is organized around these product modules:

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

### Consequences

- UI and backend changes should preserve module boundaries.
- Broad cross-module refactors should be justified.
- New features should be placed in the closest matching module.

### Files/Areas Affected

- Frontend route and component organization.
- Backend route and service organization.
- Documentation and MVP checklist.

## ADR-003: Use Celery For Long-Running Generation Jobs

Status: Accepted
Date: 2026-05-01

### Context

Script-to-video generation can involve TTS, ffmpeg, audio processing, overlays, and exporting. These tasks can exceed normal HTTP request timing.

### Decision

Long-running generation work should run through Celery workers. FastAPI should enqueue jobs, expose job status, and return quickly.

### Consequences

- API handlers should not perform full video generation inline.
- Job state, errors, logs, preview output, and export output must be observable.
- Worker health matters for system health.

### Files/Areas Affected

- FastAPI job endpoints.
- Celery tasks.
- Job status storage.
- Job Monitor UI.
- Health checks.

## ADR-004: Use TTS Provider Abstraction With Docker-Safe Fallback

Status: Accepted
Date: 2026-05-01

### Context

The product needs local fallback TTS, clone-capable voice profiles, and future provider flexibility. Host-specific TTS is fragile inside Docker.

### Decision

TTS must be implemented behind a provider abstraction.

Required tiers:

1. Docker-safe local fallback provider.
2. OpenVoice V2 provider when configured and available.
3. Future provider implementations behind the same interface.

### Consequences

- Video generation should request speech through provider interfaces, not provider-specific code.
- Provider availability must be exposed through health checks.
- Fallback TTS must continue working if OpenVoice is disabled or unavailable.

### Files/Areas Affected

- TTS services.
- Voice Lab.
- Video generation tasks.
- Health endpoints.
- Docker image dependencies.

## ADR-005: Treat Speaker Segments As The Canonical Timeline

Status: Accepted
Date: 2026-05-01

### Context

Dialogue-based videos require accurate mapping between script lines, generated audio, captions, and active speaker portraits.

### Decision

Parsed speaker segments are the canonical timeline for:

- Speaker identity.
- Text.
- Per-segment TTS audio.
- Segment duration.
- Captions or text overlays.
- Active speaker portrait visibility.

### Consequences

- Do not guess overlay timing independently from script order.
- Do not infer character identity from file ordering when explicit mappings exist.
- Rendering tests should verify that speaker overlay intervals match segment audio intervals.

### Files/Areas Affected

- Script parser.
- Speaker mapping services.
- TTS generation.
- Render planner.
- ffmpeg composition.
- Regression tests.

## ADR-006: Keep Asset Classes In Separate Storage Areas

Status: Accepted
Date: 2026-05-01

### Context

A repeated risk is mixing background videos, character images, voice profiles, uploaded media, and generated outputs.

### Decision

Local MVP storage must keep asset classes separate:

- Character images
- Background presets
- Uploaded source media
- Voice profiles and reference audio
- Generated audio
- Generated videos
- Job logs or metadata

### Consequences

- Character selectors should not read background preset directories.
- Background preset selectors should not read character directories.
- Generated outputs should not be committed to git.
- Storage path changes should be treated as architecture changes.

### Files/Areas Affected

- Backend storage services.
- Upload endpoints.
- Background preset endpoints.
- Character library endpoints.
- Video generation tasks.
- `.gitignore`.
