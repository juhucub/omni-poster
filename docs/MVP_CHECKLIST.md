# Omniposter MVP Checklist

Last updated: 2026-05-06

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
| Map each speaker to a voice profile | Partial | `backend/app/tests/test_vertical_slice.py::test_generation_job_snapshots_selected_voice_profiles`; `test_saved_calibration_recipe_is_snapshotted_for_video_render`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-05 | Generation jobs snapshot selected speaker voice profile/provider payloads, including saved calibration recipes; real UI/runtime verification still needed. |
| Generate TTS audio per line or segment | Partial | `backend/app/tests/test_vertical_slice.py::test_local_speech_service_prefers_generation_voice_manifest`; `test_render_segment_metadata_exposes_safe_artifact_url`; `test_xtts_provider_uses_stewie_selected_recipe_exactly`; `test_xtts_render_job_synthesizes_exact_script_segments_to_persisted_wavs`; `test_tts_orchestrator_does_not_use_xtts_voice_cache_for_render_segments`; Docker API `XTTSProvider().synthesize_line(...)` wrote `/data/uploads/voice_models/stewie_griffin/previews/render_smoke/stewie_recipe_smoke_container.wav` with `provider_used='xtts'` and 6 reference WAVs; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-06 | TTS layer uses persisted per-speaker voice manifest, processed reference WAV metadata, calibration recipe controls, optional XTTS/RVC provider adapters, and exposes per-segment render WAV metadata. Automated tests verify XTTS render jobs synthesize exact parsed script text to per-job segment WAVs and bypass shared XTTS cache; real full video-job XTTS runtime verification is still needed. |
| Assemble audio, background, captions/text overlays, and active speaker portraits into video | Partial | `backend/app/tests/test_vertical_slice.py::test_render_preview_final_mp4_uses_persisted_segment_wavs`; `test_xtts_render_job_synthesizes_exact_script_segments_to_persisted_wavs`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-06 | Final MP4 audio now uses a persisted dialogue composite WAV built from the same segment WAV artifacts and exposes extracted final-video audio metadata; automated XTTS render-path tests verify the composite is built from persisted XTTS segment WAVs in script order and used for MP4 assembly. Real rendered MP4 still needs manual audio extraction verification. |
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
| TTS provider abstraction | Partial | `backend/app/tests/test_vertical_slice.py::test_tts_orchestrator_does_not_fallback_when_openvoice_selected_but_unavailable`; `test_tts_orchestrator_does_not_fallback_when_xtts_selected_but_unavailable`; `test_generation_worker_persists_xtts_provider_failure`; `test_tts_provider_capabilities_route_returns_registry_state`; `test_stewie_selected_recipe_validates_required_paths`; `test_xtts_provider_uses_stewie_selected_recipe_exactly`; Docker API/worker import checks passed with `XTTS_ENABLED=True`; Docker API selected-recipe validation found provider `xtts`, checkpoint path, 6 references, and golden preview; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-06 | Provider selection honors explicit OpenVoice/XTTS/RVC fail-closed policy, records provider diagnostics, exposes optional XTTS/RVC capability state, validates the Stewie selected XTTS recipe before use, and does not silently use fallback TTS when XTTS is selected. |
| Reliable fallback TTS provider that works inside Docker | Not Verified | Needs Docker/runtime verification | Must test inside app runtime. |
| OpenVoice V2 integration as clone-capable provider when configured | Not Verified | Needs repository and runtime audit | Must handle disabled/unavailable/available states. |
| Health checks for API, worker, storage, ffmpeg, TTS providers, and OpenVoice availability | Not Verified | Needs repository audit | Verify endpoint response includes each dependency. |
| Regression tests for critical rendering and TTS behavior | Partial | `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-06 | Added coverage for voice manifest propagation, reference audio validation, processed reference artifacts, character reference datasets, prosody analysis, calibration batch scoring, saved recipe/model metadata, Stewie selected-recipe validation/execution metadata, render verification, OpenVoice/XTTS/RVC provider capability state, XTTS fail-closed behavior, XTTS cache bypass, exact-script persisted XTTS segment WAV artifacts, dialogue composite WAVs, final extracted audio metadata, and final MP4 audio assembly from persisted segment WAVs. |

## Product Modules

| Module | Status | Evidence | Notes |
|---|---:|---|---|
| Dashboard | Not Verified | Needs repository audit | Verify route/component. |
| Script Studio | Not Verified | Needs repository audit | Verify script entry and parsing feedback. |
| Character Library | Not Verified | Needs repository audit | Verify upload/select flow. |
| Voice Lab | Partial | `backend/app/tests/test_vertical_slice.py::test_reference_audio_upload_normalizes_audio_and_invalidates_embedding`; `test_character_reference_dataset_upload_analyze_and_attach_model`; `test_prosody_analyzer_extracts_pitch_pause_and_energy`; `test_character_calibration_batch_scores_and_saves_recipe`; `test_character_render_verification_marks_profile_verified`; `test_stewie_render_verification_requires_golden_preview`; `npm run build` passed on 2026-05-05 | Voice Lab persists original/processed reference artifacts, validation metadata, character datasets, prosody metrics, preview WAV links, calibration matrix/batch metadata, unsupported-control reporting, selected recipe/model-path save-back, Stewie golden-preview status, and render verification state; full manual runtime UX verification still needed. |
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
| `docs/AGENT_BRIEF.md` exists | Complete | `docs/AGENT_BRIEF.md` | Short always-read project memory summary added. |
| `docs/CONTEXT_INDEX.md` exists | Complete | `docs/CONTEXT_INDEX.md` | Defines when to read each full context doc. |
| `docs/TASK_ROUTING.md` exists | Complete | `docs/TASK_ROUTING.md` | Maps common task types to relevant docs and code areas. |
| `docs/REPO_MAP.md` exists | Complete | `docs/REPO_MAP.md` | Concise backend/frontend/runtime/storage/test map for targeted inspection. |
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
