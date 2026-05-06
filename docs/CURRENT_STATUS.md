# Omniposter Current Status

Last updated: 2026-05-05

## Working

- Codex context document structure is defined:
  - `AGENTS.md`
  - `docs/PROJECT_MANUAL.md`
  - `docs/CURRENT_STATUS.md`
  - `docs/KNOWN_MISTAKES.md`
  - `docs/ARCHITECTURE_DECISIONS.md`
  - `docs/MVP_CHECKLIST.md`
  - `docs/CODEX_WORKFLOW.md`
- Video generation jobs now snapshot per-speaker voice profile/provider selections into the job payload and expose TTS provider status in job responses.
- OpenVoice-selected render jobs fail closed with structured provider diagnostics instead of silently falling back to local TTS.
- Render jobs now persist per-segment WAV artifacts under generated job storage and expose safe artifact URLs in job metadata for audio comparison.
- Final MP4 assembly now builds a persisted per-job dialogue composite WAV from the same render segment WAV artifacts and uses that composite WAV as the final video audio source.
- Voice profiles now persist original reference uploads, processed mono 16 kHz WAV references, validation metadata, processed-reference OpenVoice embedding metadata, style/prosody settings, render segment WAVs, dialogue composite WAVs, and extracted final-video audio artifacts for comparison.
- Voice Lab can queue a calibration matrix for a profile, recording per-preview base speaker, style preset, speaking rate, pause bias, supported/unsupported controls, processed reference paths, and embedding path; selected recipes can be saved back to the profile and are snapshotted into video render voice manifests.
- Project Editor now fetches the latest project generation job when there is no active job, so completed render status and segment WAV links remain visible after refresh or stage changes.
- Character voice replication now has backend support for per-profile reference datasets, dataset aggregate metrics, prosody analysis, attached model/checkpoint paths, selected recipe JSON, calibration scores, optional XTTS/RVC provider adapters, calibration batch scoring, and render verification.
- Peter Griffin and Stewie Griffin are seeded as generic character replication profiles/directories without reference audio or model checkpoints committed.
- Stewie Griffin has a narrow golden-recipe integration: `backend/storage/voice_models/stewie_griffin/selected_recipe.json` validates its XTTS checkpoint directory, reference WAV glob, golden preview WAV, language, and recipe settings; Voice Lab exposes the golden preview/status; XTTS synthesis and render metadata use that selected recipe as the source of truth when the Stewie profile is selected.
- Docker API/worker images now enable XTTS by default in compose, mount `backend/storage/voice_models` at `/data/uploads/voice_models`, and can import Coqui XTTS. A Docker API smoke synthesis produced `/data/uploads/voice_models/stewie_griffin/previews/render_smoke/stewie_recipe_smoke_container.wav` from the selected Stewie recipe with `provider_used='xtts'`, 6 reference WAVs, and no fallback.

## Partially Working

- Product and MVP goals are documented, but implementation status must be verified against the repository before marking any app feature complete.
- The intended architecture is documented, but exact current code alignment is not verified in this file yet.
- TTS architecture intent is documented as provider-based with Docker-safe fallback and OpenVoice V2 as the clone-capable provider when configured.
- Voice profile propagation from Voice Lab and Video Generator to render/TTS is covered by backend regression tests, including processed reference audio and style metadata, but real OpenVoice runtime rendering still needs manual Docker/runtime verification with checkpoints installed.
- XTTS and RVC providers are optional runtime adapters and report unavailable unless dependencies/model paths are configured. Stewie XTTS is verified in the Docker API runtime; RVC and full video-job use of the Stewie recipe still need manual runtime verification.
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

## Open Questions

- Which MVP features are already implemented in the current repository?
- Which tests currently pass?
- Which exact endpoints exist for scripts, characters, backgrounds, voices, jobs, health, and generated media?
- Is OpenVoice V2 currently installed in the runtime image or only planned/configurable?
- Are XTTS/RVC dependencies and trained Peter/Stewie model artifacts available in the target runtime?
- Are generated assets correctly excluded from git?
- Are background presets and character assets stored and loaded from separate paths?
