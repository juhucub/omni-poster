# Omniposter Architecture Decisions

Last updated: 2026-05-26

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

## ADR-012: Use A Content Format Registry And Script Generation Cache

Status: Accepted
Date: 2026-05-19

### Context

Script generation was format-aware in name but still relied on scattered frontend lists, compact generic prompts, and deterministic templates that were difficult to browse, validate, or reuse. Repeated identical Ollama requests also re-entered the slow path even when the generation settings had not changed.

### Decision

Omniposter uses a backend content format preset registry as the durable source of truth for reusable short-form content formats.

Each preset defines:

- Stable format ID, display name, purpose, best use case, and description.
- Ideal duration range, supported speaker count, default speaker roles, tone options, pacing rules, section structure, caption hints, metadata hints, prompt guidance, and validation rules.

The registry is exposed through `GET /script-generation/formats` and `GET /script-generation/formats/{format_id}`. Frontend format browsers should load this API and use local constants only as an API-failure fallback.

Script generation also uses a local JSON cache under generated storage. Cache keys include the user scope, selected format, normalized idea, target duration, platform targets, tone/audience/quality hints, speaker roles/context, provider/model, and relevant generation settings. Debug requests and transient provider-failure fallbacks are not cached.

### Consequences

- New content formats should be added to the backend registry first, with tests proving the preset is exposed and validates.
- Prompt construction, fallback generation, validation, and UI browsing should consume preset fields instead of duplicating format rules.
- Cache-hit diagnostics can support measured speed claims; no performance improvement should be claimed from cache work without command output, logs, or provider diagnostics.
- Synchronous script generation remains acceptable for this slice; moving script generation into Celery should be decided from measured Ollama timing diagnostics.

### Files/Areas Affected

- `backend/app/services/script_generation/formats.py`
- `backend/app/services/script_generation/cache.py`
- `backend/app/services/script_generation/prompt_builder.py`
- `backend/app/services/script_generation/providers.py`
- `backend/app/services/script_generation/validator.py`
- `backend/app/routers/script_generation.py`
- `frontend/src/components/script-generation/FormatBrowser.tsx`
- `frontend/src/pages/ProjectEditorPage.tsx`
- `frontend/src/components/command-room/CommandRoom.tsx`

## ADR-013: Use Domain, Infra, Worker, Runtime, And Seed-Asset Boundaries

Status: Accepted
Date: 2026-05-25

### Context

Omniposter needs to stay maintainable for one-engineer development while separating product behavior from runtime artifacts and low-level adapters. The previous `services/`-heavy layout made source ownership harder to see and allowed generated/runtime files to drift into tracked paths.

### Decision

The repository uses explicit modular boundaries:

- `backend/app/domains/` owns product-domain behavior.
- `backend/app/infra/` owns low-level runtime adapters such as storage, FFmpeg, Redis, and Ollama.
- `backend/app/api/` is the future home for thin API routes.
- `backend/app/workers/` is the future home for thin Celery wrappers.
- `seed_assets/` is the future tracked home for small curated seed assets.
- `runtime/` and existing generated storage paths remain ignored homes for local/generated artifacts.

Script generation is the first migrated domain. Old `backend/app/services/script_generation/*` imports remain compatibility shims.

### Consequences

- Generated media, local DBs, render cache, voice datasets, and model/checkpoint artifacts must not be tracked.
- New product behavior should be placed under the closest domain owner.
- Routers and workers should delegate to domain services rather than accumulating business logic.
- Future migrations should proceed in small tested slices with compatibility imports until callers are updated.

### Files/Areas Affected

- `backend/app/domains/script_generation/`
- `backend/app/services/script_generation/`
- `backend/app/api/`
- `backend/app/infra/`
- `backend/app/workers/`
- `seed_assets/`
- `runtime/`
- `docs/REPO_STRUCTURE.md`

## ADR-014: Stop Phase 5 Render Micro-Extraction Before Voice/TTS Migration

Status: Accepted
Date: 2026-05-26

### Context

Phase 5 moved pure render-domain decisions out of `backend/app/services/rendering.py` in narrow tested slices: cache keys, planning, readiness, geometry, audio timeline and mixdown payloads, video command payloads, overlay payloads, artifact/result metadata, progress labels, diagnostics, and cache report metadata shaping.

The remaining renderer code is mostly orchestration and runtime side effects: FFmpeg/MoviePy execution, `RenderCache` materialization and stores, TTS synthesis and persisted segment WAV writes, PIL drawing/saving, generated artifact paths/URLs, profile/cache report file writes, character portrait lookup, and final result file stats.

### Decision

Phase 5 render-domain migration stops here. Do not keep extracting small helpers from `backend/app/services/rendering.py` before Phase 6.

Keep these responsibilities in `rendering.py` until their owning domains are clearer:

- FFmpeg/MoviePy orchestration and `_run_ffmpeg(...)`.
- `RenderCache` path/materialize/store calls.
- TTS synthesis/cache orchestration and persisted segment WAV writes.
- PIL image creation/drawing/saving for portraits, captions, and overlays.
- Generated job artifact directories, URLs, profile/cache report file writes, and final file stats.
- Character portrait lookup and fallback generated portrait creation.

Future render cleanup may still extract artifact path metadata builders, normalized segment metadata enrichment, render plan/cache report artifact metadata envelopes, or MIME/background classification helpers, but those should wait until voice, media, and jobs ownership is clearer.

Phase 6 should begin with a voice/TTS audit and move map for `tts.py`, `voice_profiles.py`, `voice_replication.py`, `voice_operation_jobs.py`, `voice_preview_jobs.py`, `character_voice_recipes.py`, related tests, and provider/runtime paths.

### Consequences

- `rendering.py` may remain large while it owns orchestration and runtime side effects.
- The next high-value modular boundary is voice/TTS, not more render micro-extraction.
- Final render must continue using persisted segment WAV artifacts, and provider behavior must remain fail-closed for selected clone providers.

### Files/Areas Affected

- `backend/app/services/rendering.py`
- `backend/app/domains/render/`
- Future `backend/app/domains/voice/`
- Voice/TTS services and tests
