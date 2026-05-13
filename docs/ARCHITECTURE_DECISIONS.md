# Omniposter Architecture Decisions

Last updated: 2026-05-13

This file records architectural decisions that future Codex agents should not reverse casually.

## ADR-001: Use Tiered Context Docs As Living Project Memory

Status: Accepted
Date: 2026-05-01, updated 2026-05-06

### Context

Codex agents need durable project memory to avoid repeating mistakes, ignoring current status, or reversing prior decisions. Reading every full context doc for every narrow task wastes context tokens and makes focused work harder.

### Decision

Omniposter uses a tiered `/docs` context system plus root `AGENTS.md`.

Always-read tier:

- `AGENTS.md`
- `docs/AGENT_BRIEF.md`
- `docs/CONTEXT_INDEX.md`

Routing/map tier:

- `docs/TASK_ROUTING.md`
- `docs/REPO_MAP.md`

Full context tier, read selectively based on task scope:

- `docs/PROJECT_MANUAL.md`
- `docs/CURRENT_STATUS.md`
- `docs/KNOWN_MISTAKES.md`
- `docs/ARCHITECTURE_DECISIONS.md`
- `docs/MVP_CHECKLIST.md`
- `docs/CODEX_WORKFLOW.md`

Agents must use `docs/CONTEXT_INDEX.md`, `docs/TASK_ROUTING.md`, and `docs/REPO_MAP.md` to decide which full docs and code areas to inspect. Full-doc reading remains required for broad audits, MVP-wide verification, architecture changes, or explicit user requests.

### Consequences

- Project knowledge is maintained in-repo.
- Completion claims require evidence.
- Documentation updates must be small and factual.
- Context-token usage is reduced for narrow tasks without weakening evidence rules, regression memory, or architecture protection.

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

## ADR-007: Persist Render Segment Audio As Scoped Job Artifacts

Status: Accepted
Date: 2026-05-02

### Context

Voice Lab previews and final video renders can differ in audible quality. Debugging that difference requires access to the exact per-segment WAV files used during final assembly without exposing arbitrary filesystem paths.

### Decision

Video render TTS segment WAVs are persisted under generated job artifact storage and served only through authenticated, job-scoped artifact routes:

- Storage path shape: `MEDIA_DIR/generated/{job_id}/segments/*.wav`
- URL shape: `/generation-jobs/{job_id}/artifacts/segments/{filename}.wav`

Final video assembly must use these persisted segment WAV files rather than a separate hidden temp copy.

### Consequences

- Job metadata can compare Voice Lab preview audio, render segment audio, and final video audio.
- Generated segment WAVs remain local generated artifacts and must not be committed.
- Artifact routes must validate project ownership and reject path traversal.

### Files/Areas Affected

- Render pipeline.
- Generation job metadata.
- Generated artifact storage.
- Job artifact serving routes.
- Job Monitor UI.

## ADR-008: Treat Voice Reference Processing As Durable Profile State

Status: Accepted
Date: 2026-05-05

### Context

OpenVoice reference audio primarily provides tone color. Debugging voice quality requires knowing which original upload, processed reference WAV, embedding artifact, profile settings, preview WAV, render segment WAV, composite WAV, and final video audio were used.

### Decision

Voice profiles persist reference processing and validation state:

- Original reference uploads and processed mono 16 kHz WAVs are stored as profile-scoped Voice Lab artifacts.
- Validation status, validation metrics, and warning metadata are stored on each reference audio row.
- OpenVoice embeddings are derived from processed reference artifacts and persisted under Voice Lab embedding storage.
- Render job metadata records the profile settings, processed references, embedding identifiers, segment WAVs, dialogue composite WAV, and extracted final-video audio used for assembly.

### Consequences

- Voice Lab previews and render jobs can be compared against the same persisted profile state.
- Unsupported provider style controls must be reported and ignored safely.
- Reference artifact routes must remain scoped to the owning/editable voice profile.

### Files/Areas Affected

- Voice profile models, schemas, services, and routes.
- TTS/OpenVoice provider integration.
- Render metadata and generated job artifact storage.
- Voice Lab and Project Editor comparison UI.

## ADR-009: Use Dataset-Backed Character Voice Replication With Fail-Closed Verification

Status: Accepted
Date: 2026-05-05

### Context

OpenVoice reference audio is useful for tone-color conversion, but licensed near-identical character voice replication needs curated datasets, prosody targets, stronger provider options, attached trained artifacts, calibration scoring, and render-path verification.

### Decision

Character voice replication is a generic Voice Lab pipeline:

- Voice profiles may have a reference dataset, character slug, attached model/checkpoint path, selected recipe JSON, calibration score, and last verified render job ID.
- Reference datasets live under `VOICE_MODELS_DIR/{character_slug}` with separate `dataset`, `processed`, `xtts`, and `rvc` areas.
- OpenVoice, XTTS, and RVC are provider adapters behind the TTS abstraction. XTTS/RVC are optional and report unavailable until configured.
- Calibration batches synthesize candidate previews, analyze prosody, score similarity, and persist ranked recipes.
- Render verification must fail closed for selected character recipes when provider, fallback, model path, segment audio, composite audio, or final extracted audio do not match expectations.

### Consequences

- OpenVoice must not be treated as the whole character replication stack.
- Trained model artifacts and generated media remain local storage and must not be committed.
- Full in-app XTTS/RVC training is deferred; the first supported flow attaches externally trained artifacts.

### Files/Areas Affected

- Voice profile and dataset models, migrations, schemas, and routes.
- TTS provider registry and render metadata.
- Voice Lab calibration UI.
- Generated storage and `.gitignore`.

## ADR-010: Use FFmpeg-First Render Planning With Strict Content-Addressed Cache

Status: Accepted
Date: 2026-05-13

### Context

The MoviePy-heavy final render path scaled poorly because every dialogue line created active portrait and caption clips. The renderer also needed repeatable artifact reuse without losing the existing persisted segment-WAV audit contract.

### Decision

Video renders use a render plan plus a strict content-addressed render cache for TTS segment WAVs, normalized WAVs, composite audio, normalized backgrounds, overlay layers, and final videos.

The normal render path is FFmpeg-first:

- Segment audio remains persisted under job-scoped generated artifact storage.
- Cached TTS audio may be reused for XTTS/OpenVoice only when all content-affecting voice, text, recipe, reference, provider, and settings inputs match.
- Segment WAVs are normalized to a canonical PCM format before composition.
- Final MP4 assembly uses normalized background, cached overlay layers, and dialogue composite WAV through FFmpeg.
- Final-video audio extraction runs only for debug renders.

### Consequences

- Render jobs expose `render_plan.json`, `cache_report.json`, `generation_profile.json`, normalized segment WAVs, composite WAV, and final MP4 metadata.
- Future renderer changes must update cache schema/version inputs when output-affecting behavior changes.
- Voice Lab preview/shared audio caches remain separate and must not be used as loose substitutes for render segment artifacts.

### Files/Areas Affected

- `backend/app/services/rendering.py`
- `backend/app/services/render_cache.py`
- `backend/app/services/render_planning.py`
- Generation job API/UI metadata
- Render regression tests

## ADR-011: Treat GeneratedScript As The Canonical Structured Script Artifact

Status: Accepted
Date: 2026-05-13

### Context

Format-aware script generation needs richer production data than the legacy manual `<Speaker> dialogue` format can carry. At the same time, rendering and TTS already rely on parsed speaker segments as the canonical timeline.

### Decision

Script generation produces a `GeneratedScript` object with speakers, sectioned lines, caption text, visual cues, metadata suggestions, provider diagnostics, and validation warnings.

Generated scripts are persisted on script revisions as structured JSON. The existing parsed speaker segment list remains the render/TTS bridge and is derived from `GeneratedScript.lines` for generated scripts.

### Consequences

- Manual scripts keep working through the legacy dialogue-line path.
- Generated scripts can feed captions, preview, metadata, future Content Format Presets, and publishing prep without reparsing raw paragraphs.
- Render/TTS correctness still depends on speaker segment order, text, and explicit speaker mapping.

### Files/Areas Affected

- Script generation schemas, route, services, and migration.
- Project Editor Script UI.
- Script revision serialization.
- TTS/render caption display.
