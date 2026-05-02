# Omniposter MVP Checklist

Last updated: 2026-05-01

Allowed statuses:

- Complete
- Partial
- Missing
- Not Verified

Do not mark an item `Complete` without evidence from code, tests, endpoint behavior, command output, or manual verification.

## Functional MVP

| Requirement | Status | Evidence | Notes |
|---|---:|---|---|
| Upload or select character images | Not Verified | Needs repository audit | Verify Character Library UI, backend storage, and API behavior. |
| Upload or select background videos from presets | Not Verified | Needs repository audit | Verify preset storage path, endpoint, frontend choices, and file extension filtering. |
| Write a two-speaker or multi-speaker dialogue script | Not Verified | Needs repository audit | Verify Script Studio or generation form. |
| Parse script lines into speaker segments | Not Verified | Needs repository audit | Verify parser behavior with two and multi-speaker scripts. |
| Map each speaker to a character image | Not Verified | Needs repository audit | Must not use background presets as character portraits. |
| Map each speaker to a voice profile | Not Verified | Needs repository audit | Verify Voice Lab and generation job payload. |
| Generate TTS audio per line or segment | Not Verified | Needs repository audit | Verify provider abstraction and generated audio files. |
| Assemble audio, background, captions/text overlays, and active speaker portraits into video | Not Verified | Needs repository audit | Verify render planner and ffmpeg output. |
| Preview generated output | Not Verified | Needs repository audit | Verify UI and generated media serving. |
| Export generated video file | Not Verified | Needs repository audit | Verify generated video path and download/export behavior. |
| View job status, errors, and generation logs from UI | Not Verified | Needs repository audit | Verify Job Monitor and backend job status endpoints. |

## Technical MVP

| Requirement | Status | Evidence | Notes |
|---|---:|---|---|
| FastAPI backend with clear REST endpoints | Not Verified | Needs repository audit | List endpoints and verify health/generation routes. |
| React + Tailwind frontend with generation forms and preview panels | Not Verified | Needs repository audit | Verify screens and components. |
| Celery worker for long-running generation jobs | Not Verified | Needs repository audit | Verify queue config, worker startup, task execution, and status reporting. |
| Local storage structure for uploaded assets, generated files, voice profiles, and presets | Not Verified | Needs repository audit | Verify storage service and `.gitignore`. |
| TTS provider abstraction | Not Verified | Needs repository audit | Verify interface and provider selection. |
| Reliable fallback TTS provider that works inside Docker | Not Verified | Needs Docker/runtime verification | Must test inside app runtime. |
| OpenVoice V2 integration as clone-capable provider when configured | Not Verified | Needs repository and runtime audit | Must handle disabled/unavailable/available states. |
| Health checks for API, worker, storage, ffmpeg, TTS providers, and OpenVoice availability | Not Verified | Needs repository audit | Verify endpoint response includes each dependency. |
| Regression tests for critical rendering and TTS behavior | Not Verified | Needs test audit | Add tests where missing. |

## Product Modules

| Module | Status | Evidence | Notes |
|---|---:|---|---|
| Dashboard | Not Verified | Needs repository audit | Verify route/component. |
| Script Studio | Not Verified | Needs repository audit | Verify script entry and parsing feedback. |
| Character Library | Not Verified | Needs repository audit | Verify upload/select flow. |
| Voice Lab | Not Verified | Needs repository audit | Verify profile creation, preview, and mapping. |
| Background Presets | Not Verified | Needs repository audit | Verify preset discovery and selection. |
| Video Generator | Not Verified | Needs repository audit | Verify generation form and job creation. |
| Job Monitor | Not Verified | Needs repository audit | Verify status/errors/logs. |
| Generated Media Library | Not Verified | Needs repository audit | Verify list/preview/export. |
| Upload / Publishing Prep | Not Verified | Needs repository audit | Verify metadata preparation. |
| System Health and Settings | Not Verified | Needs repository audit | Verify health and provider status UI. |

## Context System

| Requirement | Status | Evidence | Notes |
|---|---:|---|---|
| Root `AGENTS.md` exists | Complete | `AGENTS.md` | Codex read-first and behavior rules generated. |
| `docs/PROJECT_MANUAL.md` exists | Complete | `docs/PROJECT_MANUAL.md` | Product intent and MVP scope generated. |
| `docs/CURRENT_STATUS.md` exists | Complete | `docs/CURRENT_STATUS.md` | Conservative status generated; app behavior still needs audit. |
| `docs/KNOWN_MISTAKES.md` exists | Complete | `docs/KNOWN_MISTAKES.md` | Regression memory generated. |
| `docs/ARCHITECTURE_DECISIONS.md` exists | Complete | `docs/ARCHITECTURE_DECISIONS.md` | ADRs generated. |
| `docs/MVP_CHECKLIST.md` exists | Complete | `docs/MVP_CHECKLIST.md` | Checklist generated with evidence rules. |
| `docs/CODEX_WORKFLOW.md` exists | Complete | `docs/CODEX_WORKFLOW.md` | Audit/implementation/verification workflow generated. |

## Next Verification Targets

1. Run backend tests and identify current failures.
2. Run frontend build/tests and identify current failures.
3. Verify Docker compose startup.
4. Verify health endpoint output.
5. Verify background presets are discoverable.
6. Verify character image mapping.
7. Verify fallback TTS generation inside Docker.
8. Verify generated video output from a minimal two-speaker script.
