# Omniposter Current Status

Last updated: 2026-05-01

## Working

- Codex context document structure is defined:
  - `AGENTS.md`
  - `docs/PROJECT_MANUAL.md`
  - `docs/CURRENT_STATUS.md`
  - `docs/KNOWN_MISTAKES.md`
  - `docs/ARCHITECTURE_DECISIONS.md`
  - `docs/MVP_CHECKLIST.md`
  - `docs/CODEX_WORKFLOW.md`

## Partially Working

- Product and MVP goals are documented, but implementation status must be verified against the repository before marking any app feature complete.
- The intended architecture is documented, but exact current code alignment is not verified in this file yet.
- TTS architecture intent is documented as provider-based with Docker-safe fallback and OpenVoice V2 as the clone-capable provider when configured.

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
- Improve Voice Lab so voice profiles map predictably to generation jobs.

P2:
- Improve generated media library.
- Improve upload / publishing prep.
- Prepare future platform publishing integrations.

## Recent Changes

- Added Codex context docs as living project memory.
- Defined required read-first order for Codex tasks.
- Added documentation maintenance rules for status, checklist, known mistakes, architecture decisions, workflow, and product manual updates.

## Open Questions

- Which MVP features are already implemented in the current repository?
- Which tests currently pass?
- Which exact endpoints exist for scripts, characters, backgrounds, voices, jobs, health, and generated media?
- Is OpenVoice V2 currently installed in the runtime image or only planned/configurable?
- Are generated assets correctly excluded from git?
- Are background presets and character assets stored and loaded from separate paths?
