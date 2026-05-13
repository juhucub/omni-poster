# Omniposter Current Status

Last updated: 2026-05-13

## Working

- Codex context document structure is defined:
  - `AGENTS.md`
  - `docs/AGENT_BRIEF.md`
  - `docs/CONTEXT_INDEX.md`
  - `docs/TASK_ROUTING.md`
  - `docs/REPO_MAP.md`
  - `docs/PROJECT_MANUAL.md`
  - `docs/CURRENT_STATUS.md`
  - `docs/KNOWN_MISTAKES.md`
  - `docs/ARCHITECTURE_DECISIONS.md`
  - `docs/MVP_CHECKLIST.md`
  - `docs/CODEX_WORKFLOW.md`
- Codex context loading now uses a tiered strategy: agents always read `AGENTS.md`, `docs/AGENT_BRIEF.md`, and `docs/CONTEXT_INDEX.md`, then use `docs/TASK_ROUTING.md` and `docs/REPO_MAP.md` for targeted full-doc and code inspection.
- Video generation jobs now snapshot per-speaker voice profile/provider selections into the job payload and expose TTS provider status in job responses.
- OpenVoice-selected render jobs fail closed with structured provider diagnostics instead of silently falling back to local TTS.
- Render jobs now persist per-segment WAV artifacts under generated job storage and expose safe artifact URLs in job metadata for audio comparison.
- Final MP4 assembly now builds a persisted per-job dialogue composite WAV from the same render segment WAV artifacts and uses that composite WAV as the final video audio source.
- Generation renders now write a structured performance profile artifact at `MEDIA_DIR/generated/{job_id}/generation_profile.json`, expose its URL in job/output metadata, and log per-stage timing/RSS summaries for TTS, segment WAV validation/normalization, composite audio, FFmpeg visual assembly, encoding, and debug-only final audio extraction.
- Video renders now use an FFmpeg-first render plan and strict content-addressed render cache for TTS segment WAVs, normalized WAVs, dialogue composite audio, normalized backgrounds, overlay layers, and final MP4s. Job artifacts include `render_plan.json`, `cache_report.json`, normalized segment WAV links, the composite dialogue WAV, and cache/timing metadata.
- Format-aware script generation now returns structured `GeneratedScript` objects through `POST /script-generation/generate`, supports local Ollama via bounded configurable `OLLAMA_*` settings, normalizes Ollama JSON into render-compatible lines, exposes provider/fallback diagnostics, and falls back to deterministic hardcoded templates for reddit stories, character dialogue, podcast clips, debate, meme news reaction, educational shorts, and multi-speaker skits. Generated scripts persist on script revisions while derived speaker lines continue to feed TTS/render jobs.
- Render modes now include `preview`, `draft`, `final`, and `debug`; final MP4 audio extraction runs only for debug renders.
- Background uploads and presets now accept static images (`png`, `jpg/jpeg`, `webp`) as well as videos, and the pre-render preview displays image backgrounds with an image element.
- XTTS selected-recipe render segments now reuse loaded config/model/checkpoint runtime objects and conditioning latents inside each worker process, keyed by checkpoint/config/vocab/device/reference recipe identity. This keeps each segment inference and persisted segment WAV distinct while reducing repeated setup work visible as `xtts.runtime_cache_hit` and `xtts.conditioning_latents_cache_hit` in `generation_profile.json`.
- Render profiles now include OpenVoice provider substage timings for health reuse/checks, runtime import, Melo model/cache use, base TTS inference, converter load/cache use, target/source embedding work, and voice conversion when a render profiler is active. XTTS cache profile stages now include worker-local cache size/max-entry/eviction metadata so Docker RSS behavior is easier to explain without caching rendered audio.
- XTTS selected-recipe CPU inference now records effective torch thread settings, inference-mode status, and effective inference kwargs in render profiles. Docker/dev CPU-only defaults use `XTTS_CPU_NUM_THREADS=4`, `XTTS_CPU_INTEROP_THREADS=1`, and `CELERY_GENERATION_CONCURRENCY=1` based on render-profile benchmarking; safe runtime controls also include torch inference mode, job-local provider health reuse, preview-only split-sentence override, and configurable preview/export x264 preset/CRF defaults.
- Project-scoped pre-render preview settings now persist selected background metadata, speaker/profile portrait mappings, and bounded layout controls. Generation jobs snapshot those settings into render metadata, and the renderer consumes character scale and chat font size without changing provider selection, persisted segment WAVs, dialogue composite assembly, or `generation_profile.json`.
- Voice profile and character preset summaries now expose associated character portrait URLs when a portrait exists in character storage, while background presets remain sourced only from configured background preset storage.
- Voice profiles now persist original reference uploads, processed mono 16 kHz WAV references, validation metadata, processed-reference OpenVoice embedding metadata, style/prosody settings, render segment WAVs, dialogue composite WAVs, and extracted final-video audio artifacts for comparison.
- Voice Lab can queue a calibration matrix for a profile, recording per-preview base speaker, style preset, speaking rate, pause bias, supported/unsupported controls, processed reference paths, and embedding path; XTTS profiles now send a multi-candidate XTTS speed/temperature matrix plus an OpenVoice comparison candidate, and selected recipes can be saved back to the profile and snapshotted into video render voice manifests.
- Project Editor now fetches the latest project generation job when there is no active job, so completed render status and segment WAV links remain visible after refresh or stage changes.
- Character voice replication now has backend support for per-profile reference datasets, dataset aggregate metrics, prosody analysis, attached model/checkpoint paths, selected recipe JSON, calibration scores, optional XTTS/RVC provider adapters, calibration batch scoring, and render verification.
- Generic XTTS character calibration now loads checkpoint directories through explicit `config.json` plus `Xtts.load_checkpoint(checkpoint_dir=...)`, matching the selected-recipe loader pattern. A live Peter Griffin calibration rerun saved an XTTS recipe with score `0.7295` over OpenVoice `0.6185` using `/data/uploads/voice_models/shared/xtts_v2`.
- The bundled Voice Lab preset manifest is currently empty. Extra local runtime test presets, including Peter and Stewie Griffin, were removed from the live dev database without deleting voice-model workspace files.
- Stewie Griffin has a narrow golden-recipe integration: `backend/storage/voice_models/stewie_griffin/selected_recipe.json` validates its XTTS checkpoint directory, reference WAV glob, golden preview WAV, language, and recipe settings; Voice Lab exposes the golden preview/status; XTTS synthesis and render metadata use that selected recipe as the source of truth when the Stewie profile is selected.
- Docker API/worker images now enable XTTS by default in compose, mount `backend/storage/voice_models` at `/data/uploads/voice_models`, and can import Coqui XTTS. A Docker API smoke synthesis produced `/data/uploads/voice_models/stewie_griffin/previews/render_smoke/stewie_recipe_smoke_container.wav` from the selected Stewie recipe with `provider_used='xtts'`, 6 reference WAVs, and no fallback.
- Automated XTTS render-path regression coverage verifies that multi-speaker video renders synthesize each exact parsed script segment through XTTS into per-job segment WAV artifacts, expose XTTS metadata, build the dialogue composite from those WAVs in script order, use that composite for MP4 assembly, bypass shared XTTS voice-cache reads/writes, and fail closed with persisted diagnostics when XTTS is unavailable.
- Heavy Voice Lab work now uses `voice_worker` job processing instead of synchronous API execution: reference upload processing/validation, dataset clip processing, dataset analysis, model attach, voice profile preparation, OpenVoice/XTTS/RVC previews, and calibration batch synthesis are queued to the `voice_preview` worker queue. `GET /voice-lab/operations/{job_id}` exposes non-preview Voice Lab operation status, and calibration batch polling remains available at `GET /voice-lab/calibration-batches/{batch_id}`.
- Voice Lab reference upload jobs now process staged upload files by streaming/copying from disk in the worker instead of reading the full staged file into memory before normalization.
- Command Room dashboard route now exists at `/` with a reusable React component shell matching the local/auth-paused dashboard references, unauthenticated local workspace messaging, frontend-controlled Studio Sync paused/active state, production/project loading, start-production script generation, preview setting controls, scene/voice/job panels, and disabled release controls for local or paused sync states.
- Project preview settings now persist additional UI controls for `layout_preset`, `caption_style`, `speaker_png_size`, and `render_preset`; generation jobs snapshot these settings along with the existing background, speaker mappings, character scale, and chat font size.
- Thin production aliases now wrap the existing project model through `/productions`, `/productions/{id}`, `/productions/{id}/preview-settings`, `/productions/{id}/approve-preview`, and `/productions/{id}/render`, while `GET /generation-jobs/{id}/artifacts` exposes a metadata summary of segment WAVs, composite audio, debug audio, render plan/cache/profile URLs, timing, cache statistics, and mismatch-debug context.

## Partially Working

- Product and MVP goals are documented, but implementation status must be verified against the repository before marking any app feature complete.
- The intended architecture is documented, but exact current code alignment is not verified in this file yet.
- TTS architecture intent is documented as provider-based with Docker-safe fallback and OpenVoice V2 as the clone-capable provider when configured.
- Voice profile propagation from Voice Lab and Video Generator to render/TTS is covered by backend regression tests, including processed reference audio and style metadata, but real OpenVoice runtime rendering still needs manual Docker/runtime verification with checkpoints installed.
- XTTS and RVC providers are optional runtime adapters and report unavailable unless dependencies/model paths are configured. Stewie XTTS is verified in the Docker API runtime, and the automated video render path contract is verified with mocked XTTS synthesis; RVC and real full video-job use of the Stewie recipe still need manual runtime verification.
- The local host Python runtime still does not have the Coqui `TTS` package installed, so run real Stewie XTTS smoke synthesis through Docker unless a local XTTS environment is activated.

## Broken / Needs Fix

- Not verified from repository audit yet.
- Any current bugs must be confirmed against code, tests, logs, or manual reproduction before being listed as fixed or complete.

## Current MVP Priority

P0:
- Verify the full script-to-video path from UI/API request through Celery job to generated video output.
- Verify character image selection and active speaker overlay mapping.
- Verify background preset discovery and selection.
- Verify Docker-safe fallback TTS.
- Verify job status, error, and log visibility.
- Verify exportable generated video output.

P1:
- Verify OpenVoice V2 availability checks and provider fallback behavior.
- Add or strengthen regression tests for speaker mapping, background preset loading, TTS fallback, and render timing.
- Manually audition Voice Lab calibration recipes against real OpenVoice checkpoints and confirm saved recipes sound distinctive in generated video.

P2:
- Improve generated media library.
- Improve upload / publishing prep.
- Prepare future platform publishing integrations.

## Recent Changes

- Added Codex context docs as living project memory.
- Defined required read-first order for Codex tasks.
- Added documentation maintenance rules for status, checklist, known mistakes, architecture decisions, workflow, and product manual updates.
- Added generation-job voice manifests, TTS result diagnostics, OpenVoice fail-closed render behavior, and regression tests for selected voice profile propagation.
- Added persisted render segment WAV artifacts, scoped job artifact serving, and UI links for comparing Voice Lab previews, render segment WAVs, and final video audio.
- Added project generation-job listing and a persistent latest render job panel so completed render diagnostics do not disappear when the active-job endpoint returns 404.
- Fixed final MP4 audio assembly to concatenate the persisted segment WAV artifacts into `audio/dialogue_composite.wav` before muxing, with assembly paths recorded in job metadata.
- Added reference-audio validation with hard rejects for unreadable, too-short, mostly silent, and clipped clips; soft validation warnings are persisted for quality heuristics.
- Added scoped original/processed reference audio artifact routes, processed-reference OpenVoice preparation tests, Voice Lab fixed comparison phrases, and render metadata links for dialogue composite/final extracted audio.
- Added Voice Profile Calibration Matrix endpoints/UI, persisted calibration recipe metadata on preview jobs, recipe save-back to voice profiles, and tests proving saved recipes are included in generation voice manifests.
- Added Character Voice Replication Pipeline foundation: reference dataset APIs, prosody analyzer, model attach API, optional XTTS/RVC provider registry entries, scored calibration batch API/UI, saved recipe/model-path snapshots, render verification API, storage/gitignore guards, and backend tests.
- Wired the Stewie Griffin XTTS golden recipe into provider execution, Voice Lab status/golden-preview display, render metadata, fail-closed recipe validation, and `scripts/voice/render_stewie_recipe_smoke.py`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` and `npm run build` passed on 2026-05-05.
- Enabled XTTS in the Docker compose runtime, mounted voice model artifacts into API/worker containers, pinned CPU `torch==2.8.0`/`torchaudio==2.8.0`, restored `transformers==4.57.6` after OpenVoice/Melo installs, pinned `setuptools==80.9.0` for `pkg_resources`, and verified real Stewie XTTS synthesis inside the API container.
- Added the canonical short context brief, context index, task routing, and repo map so narrow Codex tasks can preserve project memory while reading fewer full docs by default.
- Hardened XTTS render jobs so shared voice-cache entries are not used for XTTS segment synthesis, XTTS/RVC local profile resolution fails closed by default, and backend regressions prove exact-script XTTS segment WAVs feed the persisted dialogue composite and final MP4 assembly; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-06.
- Added render profiling and safe performance knobs for preview/export resolution/FPS and ffmpeg thread caps. XTTS instrumentation now measures config load, checkpoint/model load, device move, conditioning latent computation, inference, and WAV save per render segment, making repeated per-segment XTTS loading/latent work visible without changing provider selection or render audio caching behavior.
- Added bounded worker-process XTTS selected-recipe runtime reuse (`XTTS_WORKER_CACHE_ENABLED`, `XTTS_WORKER_CACHE_MAX_ENTRIES`) so same-profile render segments avoid repeated model/checkpoint/latent setup while still running per-segment inference and writing unique persisted WAVs.
- Added safe XTTS CPU inference controls (`XTTS_TORCH_INFERENCE_MODE_ENABLED`, `XTTS_CPU_NUM_THREADS`, `XTTS_CPU_INTEROP_THREADS`, `XTTS_PREVIEW_SPLIT_SENTENCES_OVERRIDE`) plus configurable render encode knobs (`RENDER_PREVIEW_ENCODE_PRESET`, `RENDER_PREVIEW_CRF`, `RENDER_EXPORT_ENCODE_PRESET`, `RENDER_EXPORT_CRF`). A Docker/dev CPU benchmark on project 9 found `XTTS_CPU_NUM_THREADS=4`, `XTTS_CPU_INTEROP_THREADS=1`, and one generation worker process fastest among the tested settings, so the Docker/dev profile now uses those values by default.
- Added persistent customizable pre-render preview settings across backend, Project Editor, Voice Lab, generation job snapshots, render planning, and backend regression coverage. `python3 -m pytest backend/app/tests/test_vertical_slice.py` and `npm run build` passed on 2026-05-08.
- Cleared bundled Voice Lab presets, added an Alembic data migration to remove prior bundled seed rows from migrated databases, and removed all local runtime Voice Lab presets from the live dev database.
- Fixed generic XTTS calibration for directory-based checkpoints, rebuilt/restarted the Docker API/workers, reran Peter Griffin calibration, and saved the top XTTS recipe. `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-09.
- Updated Generate Calibration Previews so XTTS profiles submit a 3x3 XTTS candidate matrix across speed and temperature, plus a single OpenVoice comparison candidate; saved XTTS recipes preserve temperature and sentence-splitting settings. `python3 -m pytest backend/app/tests/test_vertical_slice.py` and `npm run build` passed on 2026-05-09.
- Moved memory-heavy Voice Lab operations out of FastAPI request handlers and into `voice_worker` Celery jobs. Added `voice_operation_jobs`, worker-side reference audio validation failure reporting with `http_status=400`, RSS/peak RSS memory logging around voice enqueue/worker stages, and `--max-tasks-per-child=${CELERY_VOICE_MAX_TASKS_PER_CHILD:-1}` for `voice_worker`. `python3 -m pytest backend/app/tests/test_vertical_slice.py`, `python3 -m compileall backend/app`, and `npm run build` passed on 2026-05-11; Docker compose `ps -a` still showed the prior `api` container as `Exited (137)` before restart/runtime replay.
- Reduced Docker Voice Lab upload memory pressure by removing `pending_path.read_bytes()` from worker reference-audio processing; added OpenVoice render-profile substages, XTTS cache occupancy/eviction metadata, and per-render portrait path reuse. `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `93 passed`, and `python3 -m compileall backend/app` passed on 2026-05-11.
- Added the FFmpeg-first cached render pipeline, strict render-cache TTS reuse for XTTS/OpenVoice exact matches, normalized segment WAV artifacts, render plan/cache report artifacts, draft/debug render modes, debug-only final audio extraction, direct final MP4 output handling, image background support, and Project Editor cache/timing links. `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `96 passed`, `python3 -m compileall backend/app` passed, and `npm run build` passed on 2026-05-13.
- Hardened local-first Ollama script generation with JSON-safe temperature/`num_predict`/`num_ctx` bounds, typed provider failure diagnostics, compact prompts, stronger normalization, character dialogue fallback name inference/alternation, and a clearer Project Editor generation panel with provider status, warnings, debug JSON, and accept gating. `python3 -m pytest backend/app/tests/test_script_generation.py` passed with `15 passed`, `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `96 passed`, `python3 -m compileall backend/app` passed, and `npm run build` passed on 2026-05-13.
- Added the Command Room dashboard integration, production aliases, expanded preview settings, and generation-job artifact summary endpoint. `python3 -m pytest backend/app/tests/test_script_generation.py` passed with `15 passed`, `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `98 passed`, `python3 -m compileall backend/app` passed, and `npm run build` passed on 2026-05-13.
- Added a shared Studio shell/sidebar/style layer for Command Room, Productions, Production Lab, Voice Lab, Channels, and Release History. The detailed Production Lab and Voice Lab now keep their existing MVP actions while matching the Command Room visual system and linking production voice bindings to Voice Lab profiles; `npm run build` passed on 2026-05-13.

## Open Questions

- Which MVP features are already implemented in the current repository?
- Which tests currently pass?
- Which exact endpoints exist for scripts, characters, backgrounds, voices, jobs, health, and generated media?
- Is OpenVoice V2 currently installed in the runtime image or only planned/configurable?
- Are XTTS/RVC dependencies and trained Peter/Stewie model artifacts available in the target runtime?
- Are generated assets correctly excluded from git?
- Are background presets and character assets stored and loaded from separate paths?
