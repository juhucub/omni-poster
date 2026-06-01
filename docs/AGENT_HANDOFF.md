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

## Completed Migration Slices

### Phase 1.6 Slice 6Q — RVCProvider Migration (2026-05-28)

```md
## Handoff
Current task: Phase 1.6 Slice 6Q — Move RVCProvider to domains/voice/providers/rvc.py
Changed files:
  - backend/app/domains/voice/providers/rvc.py (new — canonical home for RVCProvider)
  - backend/app/services/tts.py (RVCProvider class body replaced with compatibility shim)
Do not touch:
  - OpenVoiceProvider, XTTSProvider, EspeakProvider, BaseTTSProvider, TTSOrchestrator,
    LocalSpeechService, ProviderRegistry — all remain in tts.py and domains/voice untouched
  - Any Celery task files, API route files, database models, frontend files, render pipeline
Compatibility surfaces:
  - app.services.tts.RVCProvider resolves via shim at tts.py:1543-1544
  - ProviderRegistry in tts.py still instantiates RVCProvider() — resolves through shim
  - shlex.split(command_template) is the only shell expansion point — preserved exactly
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - python3 -m pytest backend/app/tests/test_voice_domain.py -v → 34 passed
  - python3 -m pytest backend/app/tests/test_render_domain.py -v → 55 passed
  - python3 -m pytest backend/app/tests/test_script_generation.py -v → 39 passed
  - python3 -m pytest backend/app/tests/test_vertical_slice.py -v → 108 passed
Failures/skips: None
Next task: Phase 1.6 Slice 6R — Move OpenVoiceProvider to
  backend/app/domains/voice/providers/openvoice.py with a matching compatibility shim
  in tts.py, following the same rules as 6Q.
```

### Phase 1.6 Slice 6R — OpenVoiceProvider Migration (2026-05-28)

```md
## Handoff
Current task: Phase 1.6 Slice 6R — Move OpenVoiceProvider to domains/voice/providers/openvoice.py
Changed files:
  - backend/app/domains/voice/providers/openvoice.py (new — canonical home for OpenVoiceProvider)
  - backend/app/services/tts.py (OpenVoiceProvider class body removed; compatibility shim added at
    original class location, line 63)
Do not touch:
  - XTTSProvider, EspeakProvider, BaseTTSProvider, TTSOrchestrator, LocalSpeechService,
    ProviderRegistry, RVCProvider (shim at line 777) — all remain or resolve correctly
  - Any Celery task files, API route files, database models, frontend files, render pipeline
Compatibility surfaces:
  - app.services.tts.OpenVoiceProvider resolves via shim at tts.py:63-64
  - ProviderRegistry in tts.py still instantiates OpenVoiceProvider() — resolves through shim
  - Class-level threading.Lock() caches (_cache_lock, _melo_model_cache, _converter_cache,
    _source_embedding_cache, _target_embedding_cache, _silero_vad_ready_devices) preserved
    exactly as class attributes in the new file — singleton behavior unchanged
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - python3 -m pytest backend/app/tests/test_voice_domain.py -v → 34 passed
  - python3 -m pytest backend/app/tests/test_render_domain.py test_script_generation.py
    test_vertical_slice.py -v → 202 passed (55 + 39 + 108)
Failures/skips: None
Next task: Phase 1.6 Slice 6S — Move XTTSProvider (and its two supporting dataclasses
  _XTTSSelectedRecipeRuntime and _XTTSCheckpointDirectoryRecipe) to
  backend/app/domains/voice/providers/xtts.py with a matching compatibility shim in tts.py.
  Note: XTTSProvider defines its own _profile_stage (returns None, not nullcontext) — preserve
  this exactly. The two private dataclasses must move with the class.
```

### Phase 1.6 Slice 6S — XTTSProvider Migration (2026-05-28)

```md
## Handoff
Current task: Phase 1.6 Slice 6S — Move XTTSProvider (+ two private dataclasses) to
  domains/voice/providers/xtts.py
Changed files:
  - backend/app/domains/voice/providers/xtts.py (new — canonical home for XTTSProvider,
    _XTTSSelectedRecipeRuntime, _XTTSCheckpointDirectoryRecipe)
  - backend/app/services/tts.py (all three class bodies removed; compatibility shim added
    at original location, now line 67-68)
Do not touch:
  - OpenVoiceProvider (shim at tts.py:63), RVCProvider (shim at tts.py:71),
    EspeakProvider, BaseTTSProvider, TTSOrchestrator, LocalSpeechService, ProviderRegistry
  - Any Celery task files, API route files, database models, frontend files, render pipeline
Compatibility surfaces:
  - app.services.tts.XTTSProvider resolves via shim at tts.py:67-68
  - ProviderRegistry in tts.py still instantiates XTTSProvider() — resolves through shim
  - _profile_stage override (returns None, NOT nullcontext) preserved exactly in xtts.py:66-69
  - _runtime_cache_lock, _runtime_cache, _torch_runtime_lock, _torch_runtime_configured,
    _torch_runtime_metadata preserved as class-level attributes — singleton behavior unchanged
  - CharacterVoiceRecipeError and validate_selected_character_recipe imported directly from
    app.domains.voice.profiles.recipes (canonical source, not the service shim) — no circular
    import risk since recipes.py does not import from domains/voice/providers
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - python3 -m pytest backend/app/tests/test_voice_domain.py -v → 34 passed
  - python3 -m pytest test_render_domain + test_script_generation + test_vertical_slice -v
    → 202 passed (55 + 39 + 108)
Failures/skips: None
Next task: Phase 1.6 Slice 6T — tts.py is now only shims + ProviderRegistry subclass +
  TTSOrchestrator subclass + LocalSpeechService. The next natural step is to review what
  remains in tts.py and determine whether ProviderRegistry, TTSOrchestrator, and/or
  LocalSpeechService should be migrated to the domain, or whether tts.py should be declared
  the stable compatibility surface and left as-is. Recommend reading the current tts.py
  (~145 lines) and ARCHITECTURE_DECISIONS.md before deciding.
```

### Phase 1.6 Slice 6T — tts.py Import Cleanup and Close-out (2026-05-28)

```md
## Handoff
Current task: Phase 1.6 Slice 6T — Remove stale stdlib/domain imports from tts.py; confirm
  LocalSpeechService, ProviderRegistry, and TTSOrchestrator stay in tts.py
Changed files:
  - backend/app/services/tts.py (17 stale imports removed; now 214 lines)
  - backend/app/tests/test_vertical_slice.py (two monkeypatch targets corrected from
    "app.services.tts.shutil.which" → "app.domains.voice.providers.espeak.shutil.which")
Do not touch:
  - Any provider domain files, Celery tasks, API routes, database models, frontend, render pipeline
Compatibility surfaces:
  - All symbols tested by test_voice_domain.py remain importable from app.services.tts:
    BaseTTSProvider, EspeakProvider, ProviderCapability, SpeechSegment, SynthesisResult,
    TTSProviderError, TextToSpeechError, ProviderRegistry (subclass), TTSOrchestrator (subclass),
    _audio_stats, apply_voice_lab_overrides, LocalSpeechService
  - OpenVoiceProvider, XTTSProvider, RVCProvider shims remain (lines 43-52)
Architectural decision:
  - LocalSpeechService stays in tts.py: it has DB session dependencies (self.db),
    calls service-layer helpers (resolve_preset_for_project_speaker, etc.), and uses
    moviepy.AudioArrayClip + numpy — these are application-layer concerns outside a pure domain
  - ProviderRegistry and TTSOrchestrator stay in tts.py: they are concrete app-level wiring
    (5 lines each); no domain equivalent exists and creating one would be premature
  - tts.py is declared the stable compatibility surface for the voice service layer
Stale imports removed: hashlib, inspect, importlib.util, json, os, resource, shlex, shutil,
  subprocess, sys, threading, uuid, collections.OrderedDict, contextlib.nullcontext,
  dataclasses.dataclass, app.domains.voice.profiles.reference_audio_content_hash_from_paths,
  app.domains.voice.profiles.voice_embedding_artifact_path_for_reference,
  app.services.character_voice_recipes.CharacterVoiceRecipeError,
  app.services.character_voice_recipes.validate_selected_character_recipe
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - python3 -m pytest backend/app/tests/test_voice_domain.py -q → 34 passed
  - python3 -m pytest test_render_domain + test_script_generation + test_vertical_slice -q
    → 202 passed (55 + 39 + 108)
Failures/skips: None
Next task: Phase 1.6 is complete. tts.py is a clean compatibility surface (~214 lines).
  Recommended next step: review AGENTS.md and ARCHITECTURE_DECISIONS.md for Phase 1.7 or
  subsequent migration work, or declare Phase 1.6 done and checkpoint the branch.
```

### Phase 1.7A — Jobs Domain (2026-05-28)

```md
## Handoff
Current task: Phase 1.7A — Create backend/app/domains/jobs/ with job status constants,
  transition predicates, stale recovery, quota rules, polling helpers, and diagnostics.
Changed files:
  - backend/app/domains/jobs/__init__.py (new)
  - backend/app/domains/jobs/statuses.py (new — ACTIVE_GENERATION_STATUSES, STALE_GENERATION_MINUTES,
    STALE_GENERATION_ERROR, TERMINAL_GENERATION_STATUSES, CANCELABLE_GENERATION_STATUSES)
  - backend/app/domains/jobs/transitions.py (new — is_active_status, is_terminal_status, can_cancel)
  - backend/app/domains/jobs/recovery.py (new — reconcile_stale_generation_jobs, moved from tasks)
  - backend/app/domains/jobs/quotas.py (new — check_generation_queue_limits, no HTTP deps)
  - backend/app/domains/jobs/polling.py (new — find_active_generation_job,
    find_latest_generation_job, find_latest_active_generation_job)
  - backend/app/domains/jobs/diagnostics.py (new — is_job_stale, job_age_seconds)
  - backend/app/tasks/generation.py (constants + reconcile_stale replaced with shim re-exports)
  - backend/app/routers/generation.py (_enforce_generation_queue_limits delegated to
    check_generation_queue_limits; active job dedup and active-job endpoint use polling helpers)
Do not touch:
  - Celery task function bodies (process_generation_job, reconcile_stale_generation_jobs_task)
  - API URL paths or response schemas
  - DB schema (models.py, schemas.py, migrations)
  - render, voice, script-generation behavior
  - frontend
Compatibility surfaces:
  - app.tasks.generation.ACTIVE_GENERATION_STATUSES re-exports from domains/jobs/statuses
  - app.tasks.generation.STALE_GENERATION_ERROR re-exports from domains/jobs/statuses
  - app.tasks.generation.STALE_GENERATION_MINUTES re-exports from domains/jobs/statuses
  - app.tasks.generation.reconcile_stale_generation_jobs re-exports from domains/jobs/recovery
  - test_vertical_slice.py imports STALE_GENERATION_ERROR + reconcile_stale from tasks — still works
  - routers/generation.py imports ACTIVE_GENERATION_STATUSES removed (no longer needed there);
    check_generation_queue_limits and polling helpers imported from domains/jobs directly
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - all four pytest suites → 236 passed (34 + 55 + 39 + 108)
Failures/skips: None
Next task: Phase 1.7B — Media domain. Move media/artifact helpers (generated video serving,
  output video metadata, artifact path resolution) into backend/app/domains/media/.
  Candidate sources: app.services.storage (resolve_generated_job_artifact, project_media_dir,
  store_generated_file), app.services.project_state (to_output_video_summary), and
  app.services.render_performance (build_performance_summary).
```

### Phase 1.7C — Projects Domain (2026-05-28)

```md
## Handoff
Current task: Phase 1.7C — Create backend/app/domains/projects/ with project readiness predicates,
  diagnostic helpers, workflow state machine, preview settings normalization, URL aliases,
  ownership queries, and speaker-binding utilities.
Changed files:
  - backend/app/domains/projects/__init__.py (new)
  - backend/app/domains/projects/readiness.py (new — project_has_background_asset, project_has_script,
    project_has_output, project_can_render)
  - backend/app/domains/projects/diagnostics.py (new — latest_preview_asset, latest_review,
    project_is_archived)
  - backend/app/domains/projects/workflow.py (new — sync_project_state: 35-line status machine)
  - backend/app/domains/projects/preview_settings.py (new — DEFAULT_CHARACTER_SCALE,
    DEFAULT_CHAT_FONT_SIZE_PX, clamp_float, clamp_int, normalize_preview_layout)
  - backend/app/domains/projects/aliases.py (new — asset_content_url)
  - backend/app/domains/projects/ownership.py (new — find_owned_project)
  - backend/app/domains/projects/speaker_bindings.py (new — extract_script_speaker_samples)
  - backend/app/services/project_state.py (old function bodies removed; domain imports added as
    compatibility re-exports; to_*_summary projection functions remain here)
  - backend/app/routers/projects.py (get_owned_project now delegates to find_owned_project domain
    function; domain import added)
Do not touch:
  - API URL paths or response schemas
  - DB schema (models.py, schemas.py, migrations)
  - Celery tasks, render pipeline, voice/TTS, script generation
  - frontend
Compatibility surfaces:
  - app.services.project_state.asset_content_url re-exports from domains/projects/aliases (noqa: F401)
  - app.services.project_state.latest_preview_asset re-exports from domains/projects/diagnostics (noqa: F401)
  - app.services.project_state.latest_review re-exports from domains/projects/diagnostics (noqa: F401)
  - app.services.project_state.sync_project_state re-exports from domains/projects/workflow (noqa: F401)
  - app.services.project_state.DEFAULT_CHARACTER_SCALE re-exports via preview_settings import (noqa: F401)
  - app.services.project_state.DEFAULT_CHAT_FONT_SIZE_PX re-exports via preview_settings import (noqa: F401)
  - app.services.project_state.normalize_preview_layout re-exports from domains/projects/preview_settings (noqa: F401)
  - _clamp_float/_clamp_int removed from project_state.py (private helpers, not API surface);
    renamed to clamp_float/clamp_int (public) in domain
  - All to_*_summary, update_*_settings, sync_project_preview_background remain in project_state.py
Naming note:
  - Domain uses clamp_float/clamp_int (public, no underscore) vs old private _clamp_float/_clamp_int
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - all four pytest suites → 236 passed (34 + 55 + 39 + 108)
Failures/skips: None
Next task: Phase 1.7D — Publishing domain. Move publish workflow rules, window scheduling predicates,
  and social account validation into backend/app/domains/publishing/. Candidate sources:
  app.tasks.publish, app.routers.publish (publish window evaluation, social account selection),
  app.services.social_accounts (if it exists).
```

### Phase 1.7D — Publishing Domain (2026-05-28)

```md
## Handoff
Current task: Phase 1.7D — Create backend/app/domains/publishing/ with platform capability rules,
  publish job lifecycle predicates, scheduling helpers, account routing logic, history projections,
  release metadata helpers, and publishing diagnostics.
Changed files:
  - backend/app/domains/publishing/__init__.py (new)
  - backend/app/domains/publishing/platforms.py (new — PlatformCapability, PLATFORM_CAPABILITIES,
    capability_for, supported_platforms, validate_platform_metadata; canonical home for platforms logic)
  - backend/app/domains/publishing/lifecycle.py (new — PUBLISH_*_STATUSES constants,
    is_publish_job_processable, is_publish_job_cancelable, is_publish_job_retryable,
    publish_job_public_status)
  - backend/app/domains/publishing/scheduling.py (new — is_scheduled_job_due predicate)
  - backend/app/domains/publishing/accounts.py (new — is_account_routing_eligible,
    to_social_account_summary, choose_social_account, suggest_destination; all moved from routing.py)
  - backend/app/domains/publishing/history.py (new — to_post_summary; moved from routers/history.py)
  - backend/app/domains/publishing/diagnostics.py (new — account_requires_reconnect,
    account_token_is_healthy, project_is_publishable)
  - backend/app/domains/publishing/metadata.py (new — normalize_tags; re-exports validate_platform_metadata)
  - backend/app/services/platforms.py (converted to full re-export shim from domains/publishing/platforms)
  - backend/app/services/routing.py (converted to full re-export shim from domains/publishing/accounts)
  - backend/app/routers/history.py (removed local to_post_summary; imports from domain instead)
  - backend/app/routers/publish.py (retry/cancel checks now use is_publish_job_retryable/cancelable)
  - backend/app/services/project_state.py (to_publish_job_summary uses publish_job_public_status from domain)
Do not touch:
  - API URL paths or response schemas
  - DB schema (models.py, schemas.py, migrations)
  - Celery tasks (tasks/publish.py, tasks/scheduler.py) — not moved yet (Phase 1.8)
  - YouTube OAuth/upload services (youtube_accounts.py, youtube_publish.py) — stay as integration surfaces
  - render pipeline, voice/TTS, script generation, project behavior, jobs behavior, media behavior
  - frontend
Compatibility surfaces:
  - app.services.platforms.{PlatformCapability, PLATFORM_CAPABILITIES, capability_for,
    supported_platforms, validate_platform_metadata} re-export from domains/publishing/platforms (noqa: F401)
  - app.services.routing.{is_account_routing_eligible, to_social_account_summary,
    choose_social_account, suggest_destination} re-export from domains/publishing/accounts (noqa: F401)
  - All callers of app.services.platforms.* and app.services.routing.* continue to work unchanged
  - to_post_summary no longer defined in routers/history.py (was never part of public API surface)
Celery task names preserved:
  - app.tasks.publish.process_publish_job (unchanged)
  - app.tasks.scheduler.dispatch_due_publish_jobs (unchanged)
YouTube behavior preserved:
  - youtube_accounts.py and youtube_publish.py untouched — OAuth, token refresh, upload unchanged
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - all four pytest suites → 236 passed (34 + 55 + 39 + 108)
Failures/skips: None
Next task: Phase 1.7E — Optional assets/auth cleanup, or Phase 1.7F Closeout if no
  cleanup is needed. Recommended: review backend/app/services/ for any remaining
  service files that have purely domain-level helpers not yet extracted, then decide
  whether a 1.7E slice is warranted before closing out the migration.
```

### Phase 1.7F — Smaller Domains Closeout (2026-05-28)

```md
## Handoff
Current task: Phase 1.7F — Verification and documentation closeout for Phase 1.7 smaller backend domains.
Changed files:
  - docs/AGENT_HANDOFF.md (this record)
  - docs/REPO_MAP.md (updated to reflect domains/jobs, media, projects, publishing)
  - docs/REPO_STRUCTURE.md (updated domains section to include all four new domains)
Do not touch:
  - Any source code — no code changes in this phase; verification and docs only
Domains verified (files + ownership):
  - backend/app/domains/jobs/ — statuses, transitions, recovery, quotas, polling, diagnostics
  - backend/app/domains/media/ — validators, uploads, quotas, assets, artifacts, generated_media, diagnostics
  - backend/app/domains/projects/ — readiness, diagnostics, workflow, preview_settings, aliases, ownership, speaker_bindings
  - backend/app/domains/publishing/ — platforms, lifecycle, scheduling, accounts, history, metadata, diagnostics
  - backend/app/domains/voice/ — pre-existing (Phase 1.6); providers, synthesis, previews, profiles, etc.
  - backend/app/domains/render/ — pre-existing (Phase 1.5); cache keys, geometry, planning, readiness, etc.
  - backend/app/domains/script_generation/ — pre-existing; formats, prompts, providers, validators, etc.
Routers verified: all in backend/app/routers/ — not moved
Celery tasks verified: all in backend/app/tasks/ — not moved
Celery task names verified unchanged:
  - app.tasks.generation.process_generation_job
  - app.tasks.generation.reconcile_stale_generation_jobs
  - app.tasks.publish.process_publish_job
  - app.tasks.scheduler.dispatch_due_publish_jobs
API routes verified unchanged (spot check on publish, projects, history)
Compatibility shims verified:
  - app.services.platforms.* → re-exports from domains/publishing/platforms
  - app.services.routing.* → re-exports from domains/publishing/accounts
  - app.services.project_state.{asset_content_url, latest_preview_asset, latest_review,
    sync_project_state, DEFAULT_CHARACTER_SCALE, DEFAULT_CHAT_FONT_SIZE_PX, normalize_preview_layout}
    → re-exported from domains/projects/*
  - app.tasks.generation.{ACTIVE_GENERATION_STATUSES, STALE_GENERATION_ERROR, STALE_GENERATION_MINUTES,
    reconcile_stale_generation_jobs} → re-exported from domains/jobs/*
  - app.services.{draft_readiness, render_cache_keys, render_performance} → re-export from render domain
  - app.services.character_presets → re-exports from voice_profiles service
Intentional non-migrations (services remaining as application services or integration surfaces):
  - backend/app/services/rendering.py — FFmpeg/MoviePy orchestration, runtime side effects (Phase 1.8+)
  - backend/app/services/tts.py — LocalSpeechService, ProviderRegistry, TTSOrchestrator; provider shims
  - backend/app/services/voice_profiles.py — 1801 lines of DB/schema logic (Phase 1.8+)
  - backend/app/services/voice_replication.py — 897 lines of model training / file I/O (not domain logic)
  - backend/app/services/storage.py — filesystem + S3 I/O; calls domain validators internally
  - backend/app/services/youtube_accounts.py — OAuth, JWT, encryption, external HTTP (integration surface)
  - backend/app/services/youtube_publish.py — external HTTP upload (integration surface)
  - backend/app/services/scripts.py — script CRUD with DB (application service)
  - backend/app/services/crypto.py — settings.SECRET_KEY crypto (core-adjacent infrastructure)
  - backend/app/services/audit.py + notifications.py — cross-cutting DB write helpers
Phase 1.7E decision: intentionally skipped — no remaining services/ file passed the extraction bar
  (pure business logic not yet in a domain, with sufficient mass to justify a new domain file)
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - all four pytest suites → 236 passed (34 + 55 + 39 + 108), 0 failures
Phase 1.7 status: COMPLETE
Next task: Phase 1.8 — API / worker boundary cleanup. Move routers from backend/app/routers/
  to backend/app/api/ and Celery task wrappers from backend/app/tasks/ to backend/app/workers/,
  making routes and workers thin delegation layers that call domain services directly.
```

### Phase 1.8A — Move Tasks to Workers (2026-05-28)

```md
## Handoff
Current task: Phase 1.8A — Move all Celery task implementations from backend/app/tasks/ to
  backend/app/workers/ and update celery_app.py to load from the new location.
Changed files:
  - backend/app/workers/__init__.py (new — empty package marker)
  - backend/app/workers/generation.py (new — canonical home for process_generation_job,
    reconcile_stale_generation_jobs_task, plus domain compatibility re-exports)
  - backend/app/workers/publish.py (new — canonical home for process_publish_job)
  - backend/app/workers/scheduler.py (new — canonical home for dispatch_due_publish_jobs;
    imports process_publish_job from app.workers.publish, not app.tasks.publish)
  - backend/app/workers/voice_operations.py (new — canonical home for process_voice_operation_job,
    process_voice_calibration_batch; acks_late=False/reject_on_worker_lost=False preserved)
  - backend/app/workers/voice_preview.py (new — canonical home for process_voice_lab_preview,
    reconcile_stale_voice_preview_jobs_task; acks_late=False/reject_on_worker_lost=False preserved)
  - backend/app/celery_app.py (include list updated: app.tasks.* → app.workers.*)
  - backend/app/tasks/generation.py (now a 1-line re-export shim: from app.workers.generation import *)
  - backend/app/tasks/publish.py (now a 1-line re-export shim: from app.workers.publish import *)
  - backend/app/tasks/scheduler.py (now a 1-line re-export shim: from app.workers.scheduler import *)
  - backend/app/tasks/voice_operations.py (now a 1-line re-export shim)
  - backend/app/tasks/voice_preview.py (now a 1-line re-export shim)
  - backend/app/tests/test_vertical_slice.py (4 monkeypatch targets corrected:
    "app.tasks.publish.upload_short" → "app.workers.publish.upload_short")
Do not touch:
  - API route files (backend/app/routers/) — not moved yet (Phase 1.8B)
  - Domain files, service files, model/schema files, frontend, runtime artifacts
Celery task names: ALL preserved exactly (name="app.tasks.X.Y" stays on all @celery.task decorators)
Celery task_routes, task_annotations, beat_schedule: ALL unchanged (reference task names not module paths)
celery_app.py autodiscovery: Changed from explicit app.tasks.* include list to app.workers.*
  Task registration is identical because task names are hardcoded in @celery.task(name=...) decorators.
Compatibility shims (tasks/ re-exports):
  - app.tasks.generation.{process_generation_job, ACTIVE_GENERATION_STATUSES, STALE_GENERATION_ERROR,
    STALE_GENERATION_MINUTES, reconcile_stale_generation_jobs} → via shim → app.workers.generation
  - app.tasks.publish.process_publish_job → via shim → app.workers.publish
  - app.tasks.scheduler.dispatch_due_publish_jobs → via shim → app.workers.scheduler
  - app.tasks.voice_operations.{process_voice_operation_job, process_voice_calibration_batch}
    → via shim → app.workers.voice_operations
  - app.tasks.voice_preview.{process_voice_lab_preview, reconcile_stale_voice_preview_jobs_task}
    → via shim → app.workers.voice_preview
Monkeypatch fix: tests patched "app.tasks.publish.upload_short" which was the import point in the
  old task file. The new worker file imports upload_short at "app.workers.publish.upload_short" —
  four monkeypatch targets updated accordingly.
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - all four pytest suites → 236 passed (34 + 55 + 39 + 108), 0 failures
Failures/skips: None (4 test failures on first run due to stale monkeypatch targets; fixed immediately)
Next task: Phase 1.8B — Move routers from backend/app/routers/ to backend/app/api/. Update main.py
  to import from app.api.*. Make routers/ files 1-line re-export shims. Fix any cross-module imports
  (publish.py and history.py import get_owned_project from projects.py — both move together so update
  those two import lines atomically). Validate full test suite.
```

### Phase 1.8B — Move Routers to api/ (2026-05-28)

```md
## Handoff
Current task: Phase 1.8B — Move all 14 FastAPI router files from backend/app/routers/ to
  backend/app/api/ and make backend/app/routers/ a compatibility shim layer.
Changed files:
  - backend/app/api/__init__.py (new — empty package marker)
  - backend/app/api/assets.py (new — canonical home, copy of routers/assets.py)
  - backend/app/api/auth.py (new — canonical home, copy of routers/auth.py)
  - backend/app/api/character_presets.py (new — canonical home, copy of routers/character_presets.py)
  - backend/app/api/generation.py (new — canonical home, copy of routers/generation.py)
  - backend/app/api/history.py (new — canonical home, copy of routers/history.py)
  - backend/app/api/metadata.py (new — canonical home, copy of routers/metadata.py)
  - backend/app/api/productions.py (new — canonical home, copy of routers/productions.py)
  - backend/app/api/projects.py (new — canonical home, copy of routers/projects.py)
  - backend/app/api/publish.py (new — canonical home, copy of routers/publish.py)
  - backend/app/api/reviews.py (new — canonical home, copy of routers/reviews.py)
  - backend/app/api/routing.py (new — canonical home, copy of routers/routing.py)
  - backend/app/api/script_generation.py (new — canonical home, copy of routers/script_generation.py)
  - backend/app/api/scripts.py (new — canonical home, copy of routers/scripts.py)
  - backend/app/api/social_accounts.py (new — canonical home, copy of routers/social_accounts.py)
  - backend/app/main.py (updated: all router imports changed from app.routers.* to app.api.*)
  - backend/app/routers/assets.py (now a 1-line shim: from app.api.assets import *)
  - backend/app/routers/auth.py (now a 1-line shim)
  - backend/app/routers/character_presets.py (now a 1-line shim)
  - backend/app/routers/generation.py (now a 1-line shim)
  - backend/app/routers/history.py (now a 1-line shim)
  - backend/app/routers/metadata.py (now a 1-line shim)
  - backend/app/routers/productions.py (now a 1-line shim)
  - backend/app/routers/projects.py (now a 1-line shim)
  - backend/app/routers/publish.py (now a 1-line shim)
  - backend/app/routers/reviews.py (now a 1-line shim)
  - backend/app/routers/routing.py (now a 1-line shim)
  - backend/app/routers/script_generation.py (now a 1-line shim)
  - backend/app/routers/scripts.py (now a 1-line shim)
  - backend/app/routers/social_accounts.py (now a 1-line shim)
Do not touch:
  - Domain files, service files, model/schema files, worker files, frontend, runtime artifacts
Cross-import fix (wider than originally estimated):
  grep discovered 10 cross-import lines across 9 files (not 2). All "from app.routers.X import Y"
  in api/ copies were updated to "from app.api.X import Y" via sed in one pass.
  Files with get_owned_project: assets, generation, history, metadata, productions, publish,
    reviews, routing, scripts (9 files — all fixed)
  Files with create_generation_job: productions only (1 file — fixed)
Compatibility shims (routers/ re-exports):
  - app.routers.X.{router, ...} → via shim → app.api.X (all 14 routers)
URL paths: All FastAPI route paths unchanged (no frontend impact)
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - python3 -m pytest app/tests/ → 236 passed, 0 failures
Failures/skips: None
Next task: Phase 1.8C (optional) — Thin api/publish.py by extracting _create_publish_job
  and scheduling helpers to service/domain layer. Or begin Phase 1.9 — database/migration
  boundary cleanup.
```

### Phase 1.9 — DB/Migration Boundary Cleanup (2026-05-28)

```md
## Handoff
Current task: Phase 1.9 — Audit the DB/migration boundary and fix session lifecycle bugs.
Sub-phases executed: 1.9A (session lifecycle fix) and 1.9C (comment). 1.9B was skipped (see below).

### 1.9A — Fix process_voice_lab_preview session lifecycle
Changed files:
  - backend/app/workers/voice_preview.py (rewritten)
Problem fixed: The original function opened a session, manually closed it mid-function via
  db.close(), then reassigned db = SessionLocal() up to three more times in the happy path and
  both exception handlers. The outer finally: db.close() only closed whichever session db
  pointed to at function exit. Any exception after the second db = SessionLocal() (line 107)
  but before returning left the second session unreferenced and unclosed (true session leak).
  Exception handlers also called db.rollback() on the already-closed first session.
Fix applied: Extracted the three DB-touching phases into four focused helpers:
  - _load_preview_job_data(preview_job_id) — read phase; one session, own try/finally
  - _write_preview_success(preview_job_id, *, result, profile_payload, orchestrator) — one session
  - _write_preview_provider_error(preview_job_id, exc) — one session
  - _write_preview_error(preview_job_id, exc) — one session
  The main task process_voice_lab_preview has NO direct DB access; it calls helpers sequentially.
  Each helper: opens SessionLocal(), does its work, closes in finally. No reassignment ever.
  Invariant verified: 6 SessionLocal() calls, 6 paired finally: db.close() — confirmed by grep.
Celery task decorators: unchanged (name=, acks_late=, reject_on_worker_lost= all preserved)
_update_voice_preview_job_stage: already had correct single-session lifecycle — not changed.

### 1.9B — Remove _session_scope from voice_profiles.py
SKIPPED. Planning agent incorrectly reported all callers pass db= explicitly. grep revealed:
  - app/services/tts.py:145: resolve_character_preset_for_speaker(speaker) — no db
  - app/services/tts.py:147: get_character_preset_model(preset["id"], None) — explicit None
  - app/services/rendering.py:1891: resolve_character_preset_for_speaker(speaker) — no db
  - app/tests/test_vertical_slice.py:388: get_character_preset(created_id) — no db
  TTSOrchestrator and the renderer can be instantiated without a DB session; _session_scope is
  genuinely needed. Removing it would require a broad refactor of TTSOrchestrator and the
  rendering pipeline — out of scope for a boundary cleanup pass.

### 1.9C — Document task name divergence in celery_app.py
Changed files:
  - backend/app/celery_app.py (comment added above task_routes)
Comment explains: include= lists app.workers.* module paths; name= strings on @celery.task
  decorators retain app.tasks.* namespace for wire-protocol backward compat.
  task_routes, task_annotations, beat_schedule use the registered name strings, not module paths.
Do not touch:
  - app/db.py, app/dependencies.py, alembic/env.py, alembic/versions/ — all correct
  - app/tests/conftest.py — Base.metadata.create_all() is correct test infrastructure
  - app/main.py — execute(text(...)) calls are read-only health-check pattern, approved
  - Domain packages — no DB construction in any domain file
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall → all files compiled clean
  - python3 -m pytest app/tests/ → 236 passed, 0 failures
Failures/skips: None
Next task: Phase 2.0 planning — evaluate whether to begin the worker/service consolidation
  (thin api/ handlers calling domain services directly) or move to a different structural
  concern (e.g. typing improvements, test coverage expansion, or frontend integration).
```

### Phase 1.9D — Migrated Runtime Verification Checkpoint (2026-06-01)

```md
## Handoff
Current task: Verify and checkpoint the migrated API/worker/domain runtime in Docker.
Changed files:
  - docs/CURRENT_STATUS.md (fresh runtime verification evidence)
  - docs/MVP_CHECKLIST.md (stale endpoint/Celery/Docker evidence refreshed)
  - docs/AGENT_HANDOFF.md (this handoff record)
Do not touch:
  - Runtime media, generated MP4/WAV files, render cache, local DBs, voice model/checkpoint files,
    Docker volumes, and `.claude/` unless explicitly requested
Compatibility surfaces:
  - `backend/app/routers/*` remains a compatibility shim layer to `backend/app/api/*`
  - `backend/app/tasks/*` remains a compatibility shim layer to `backend/app/workers/*`
  - Celery task names remain `app.tasks.*` even though `celery_app.py` includes `app.workers.*`
Runtime paths protected:
  - Docker smoke generated runtime artifacts only inside Docker volumes/temp dirs; no generated
    media/model artifacts were staged
Tests run:
  - `bash scripts/dev/check_repo_hygiene.sh` → repo hygiene ok
  - `python3 -m compileall backend/app` → all files compiled clean
  - `python3 -m pytest app/tests/ -q` from `backend/` → 236 passed
  - `docker compose -f deploy/compose/docker-compose.yml build` → passed
  - `docker compose -f deploy/compose/docker-compose.yml up -d` → passed
  - `docker compose -f deploy/compose/docker-compose.yml ps -a` → API healthy; worker,
    voice_worker, beat, Redis, and Postgres running
  - `docker compose -f deploy/compose/docker-compose.yml exec worker sh -lc 'celery -A app.celery_app.celery inspect registered'`
    → 2 nodes online, all expected `app.tasks.*` tasks registered
  - `docker compose -f deploy/compose/docker-compose.yml exec api sh -lc 'curl -fsS http://localhost:8000/health/deep'`
    → required checks ok; OpenVoice/XTTS available; overall degraded only because optional RVC disabled
  - `scripts/mvp_smoke_verify.sh` → passed with project `36`, generation job `78`, output
    `/assets/84/content`, `Host=espeak, Guest=espeak`, ffprobe duration `9.166667`,
    `1` video stream, and `1` audio stream
Failures/skips:
  - Host `curl http://localhost:8000/health/deep` inside Codex sandbox failed with connection
    refused, but the same endpoint succeeded inside the API container and the escalated smoke
    script succeeded from the host.
  - Real OpenVoice/XTTS full generation-job audio remains unverified; smoke render intentionally
    used Docker-safe espeak.
Next task: Browser-verify real Generated Media, Character Library, Command Room diagnostics,
  and Project Editor diagnostics against the rebuilt Docker runtime, including manual visual
  inspection of active speaker portrait/caption alignment in the generated MP4.
```

## Stop Conditions

Stop and report instead of continuing when:

- More than ten files need non-mechanical changes for a migration slice.
- A provider move changes fallback or fail-closed behavior.
- A render move changes artifact paths, cache keys, persisted WAV usage, or output behavior.
- A test failure touches persisted segment WAVs, Voice Lab preview isolation, provider fallback, XTTS selected recipes, or generated artifact serving.
- The agent cannot tell whether a dirty worktree change belongs to the current task.

### Phase 1.7B — Media Domain (2026-05-28)

```md
## Handoff
Current task: Phase 1.7B — Create backend/app/domains/media/ with media validation rules,
  upload helpers, quota predicates, asset classification, artifact URL building, and diagnostics.
Changed files:
  - backend/app/domains/media/__init__.py (new)
  - backend/app/domains/media/validators.py (new — ALLOWED_BACKGROUND_*_TYPES, detect_background_mime_type,
    background_duration_exceeds_limit)
  - backend/app/domains/media/uploads.py (new — declared_upload_mime_type, mime_types_match)
  - backend/app/domains/media/quotas.py (new — upload_exceeds_size_limit, project_storage_quota_exceeded)
  - backend/app/domains/media/assets.py (new — BACKGROUND_PRESET_EXTENSIONS, upload_asset_kind,
    preset_asset_kind)
  - backend/app/domains/media/artifacts.py (new — artifact_url_path)
  - backend/app/domains/media/generated_media.py (new — is_video_mime, is_image_mime,
    is_preview_output_kind)
  - backend/app/domains/media/diagnostics.py (new — asset_file_exists, asset_file_missing)
  - backend/app/services/storage.py (updated to call domain internals; public API unchanged)
Do not touch:
  - API route files (assets.py, generation.py, etc.) — not moved yet (Phase 1.8)
  - infra/storage/ — storage adapter mechanics unchanged
  - Any Celery task files, DB models, frontend
Compatibility surfaces:
  - ALLOWED_BACKGROUND_VIDEO_TYPES, ALLOWED_BACKGROUND_IMAGE_TYPES, ALLOWED_BACKGROUND_TYPES
    re-exported from services/storage.py (noqa: F401) for any callers
  - All existing imports from app.services.storage remain stable (public API unchanged):
    guess_mime_type, resolve_generated_job_artifact, generated_job_artifact_url,
    list_background_presets, save_background_asset, copy_preset_to_project, store_generated_file,
    project_media_dir, generated_job_segment_dir, generated_job_artifact_dir, delete_storage_key
  - Private storage helpers removed: _detect_background_mime_type, _declared_upload_mime_type
    replaced with domain calls; _verify_background_duration uses domain predicate internally
Storage paths preserved:
  - All storage paths, artifact URLs, download routes unchanged
  - No path traversal behavior changes; resolve_generated_job_artifact still enforces ownership
  - generated_job_artifact_url still produces /generation-jobs/{id}/artifacts/{path} URLs
Runtime paths protected:
  - No runtime media, model dirs, generated videos, or local DBs were touched
Tests run:
  - bash scripts/dev/check_repo_hygiene.sh → repo hygiene ok
  - python3 -m compileall backend/app → all files compiled clean
  - all four pytest suites → 236 passed (34 + 55 + 39 + 108)
Failures/skips: None
Next task: Phase 1.7C — Projects domain. Move project state helpers, project summary building,
  and project status transition rules into backend/app/domains/projects/.
  Candidate sources: app.services.project_state (sync_project_state, to_project_summary,
  to_generation_summary, to_output_video_summary, sync_project_preview_background, etc.)
  and any project-specific business rules currently in routers/projects.py.
```
