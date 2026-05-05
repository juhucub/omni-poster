# Omniposter MVP Checklist

Last updated: 2026-05-05

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
| Map each speaker to a voice profile | Partial | `backend/app/tests/test_vertical_slice.py::test_generation_job_snapshots_selected_voice_profiles`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-05 | Generation jobs snapshot selected speaker voice profile/provider payloads; real UI/runtime verification still needed. |
| Generate TTS audio per line or segment | Partial | `backend/app/tests/test_vertical_slice.py::test_local_speech_service_prefers_generation_voice_manifest`; `test_render_segment_metadata_exposes_safe_artifact_url`; `test_openvoice_prepare_voice_profile_prefers_processed_reference_path`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-05 | TTS layer uses persisted per-speaker voice manifest, processed reference WAV metadata, and exposes per-segment render WAV metadata; manual OpenVoice segment artifact comparison confirmed OpenVoice segment WAVs are correct. |
| Assemble audio, background, captions/text overlays, and active speaker portraits into video | Partial | `backend/app/tests/test_vertical_slice.py::test_render_preview_final_mp4_uses_persisted_segment_wavs`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-05 | Final MP4 audio now uses a persisted dialogue composite WAV built from the same segment WAV artifacts and exposes extracted final-video audio metadata; real rendered MP4 still needs manual audio extraction verification. |
| Preview generated output | Not Verified | Needs repository audit | Verify UI and generated media serving. |
| Export generated video file | Not Verified | Needs repository audit | Verify generated video path and download/export behavior. |
| View job status, errors, and generation logs from UI | Partial | `backend/app/tests/test_vertical_slice.py::test_generation_job_list_exposes_latest_completed_job`; `backend/app/tests/test_vertical_slice.py::test_generation_job_artifact_endpoint_serves_scoped_segment_wav`; `npm run build` passed on 2026-05-05 | Project Editor loads the latest completed generation job and shows voice/provider status plus render segment, dialogue composite, final extracted audio, and MP4 artifact URLs; full Job Monitor UX still needs manual verification. |

## Technical MVP

| Requirement | Status | Evidence | Notes |
|---|---:|---|---|
| FastAPI backend with clear REST endpoints | Not Verified | Needs repository audit | List endpoints and verify health/generation routes. |
| React + Tailwind frontend with generation forms and preview panels | Not Verified | Needs repository audit | Verify screens and components. |
| Celery worker for long-running generation jobs | Not Verified | Needs repository audit | Verify queue config, worker startup, task execution, and status reporting. |
| Local storage structure for uploaded assets, generated files, voice profiles, and presets | Not Verified | Needs repository audit | Verify storage service and `.gitignore`. |
| TTS provider abstraction | Partial | `backend/app/tests/test_vertical_slice.py::test_tts_orchestrator_does_not_fallback_when_openvoice_selected_but_unavailable` | Provider selection honors explicit OpenVoice fail-closed policy and records provider diagnostics. |
| Reliable fallback TTS provider that works inside Docker | Not Verified | Needs Docker/runtime verification | Must test inside app runtime. |
| OpenVoice V2 integration as clone-capable provider when configured | Not Verified | Needs repository and runtime audit | Must handle disabled/unavailable/available states. |
| Health checks for API, worker, storage, ffmpeg, TTS providers, and OpenVoice availability | Not Verified | Needs repository audit | Verify endpoint response includes each dependency. |
| Regression tests for critical rendering and TTS behavior | Partial | `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-05 | Added coverage for voice manifest propagation, reference audio validation, processed reference artifacts, OpenVoice fail-closed behavior, render TTS error handling, TTS metadata exposure, persisted segment WAV artifact URLs, dialogue composite WAVs, final extracted audio metadata, and final MP4 audio assembly from segment WAVs. |

## Product Modules

| Module | Status | Evidence | Notes |
|---|---:|---|---|
| Dashboard | Not Verified | Needs repository audit | Verify route/component. |
| Script Studio | Not Verified | Needs repository audit | Verify script entry and parsing feedback. |
| Character Library | Not Verified | Needs repository audit | Verify upload/select flow. |
| Voice Lab | Partial | `backend/app/tests/test_vertical_slice.py::test_reference_audio_upload_normalizes_audio_and_invalidates_embedding`; `test_reference_audio_upload_accepts_soft_warning_metadata`; `test_openvoice_prepare_voice_profile_prefers_processed_reference_path`; `npm run build` passed on 2026-05-05 | Voice Lab persists original/processed reference artifacts, validation metadata, fixed test phrase controls, and preview WAV links; full manual runtime UX verification still needed. |
| Background Presets | Not Verified | Needs repository audit | Verify preset discovery and selection. |
| Video Generator | Not Verified | Needs repository audit | Verify generation form and job creation. |
| Job Monitor | Partial | `backend/app/tests/test_vertical_slice.py::test_generation_job_list_exposes_latest_completed_job`; `npm run build` passed on 2026-05-05 | Project Editor exposes latest render status plus segment WAV, dialogue composite WAV, final extracted audio, and MP4 diagnostics, but a dedicated monitor view and manual UX verification are still needed. |
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
