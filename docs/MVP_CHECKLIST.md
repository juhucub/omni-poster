# Omniposter MVP Checklist

Last updated: 2026-05-13

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
| Upload or select background videos from presets | Partial | `backend/app/tests/test_vertical_slice.py::test_background_presets_are_loaded_from_bundled_media_dir`; `test_image_background_upload_and_preset_selection`; `test_project_preview_settings_save_load_background_speakers_and_layout`; `npm run build` passed on 2026-05-13 | Background presets/uploads now support video and static image backgrounds, and selected preset metadata persists into project preview settings; manual UI verification still needed. |
| Write a two-speaker or multi-speaker dialogue script | Partial | `POST /script-generation/generate`; `POST /projects/{project_id}/script/generate`; `frontend/src/pages/ProjectEditorPage.tsx`; `backend/app/tests/test_script_generation.py`; `python3 -m pytest backend/app/tests/test_script_generation.py` passed with `15 passed` on 2026-05-13; `npm run build` passed on 2026-05-13 | Format-aware local-first generation now produces structured speaker-separated scripts, visible provider/fallback diagnostics, and accept-gated render-ready lines; manual browser verification still needed. |
| Parse script lines into speaker segments | Partial | `backend/app/services/scripts.py`; `backend/app/services/script_generation/service.py::generated_script_to_dialogue_lines`; `backend/app/tests/test_script_generation.py`; `backend/app/tests/test_vertical_slice.py`; both test suites passed on 2026-05-13 | Manual `<Speaker> dialogue` parsing remains, and generated scripts are converted into render-compatible speaker lines with caption/section metadata; manual UI verification still needed. |
| Map each speaker to a character image | Partial | `backend/app/tests/test_vertical_slice.py::test_project_preview_settings_save_load_background_speakers_and_layout`; `test_voice_profile_summary_exposes_associated_character_image`; `test_character_images_are_not_loaded_from_background_preset_directories`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-08 | Project preview settings and voice/profile summaries expose character portrait URLs from character storage only; manual UI verification still needed. |
| Map each speaker to a voice profile | Partial | `backend/app/tests/test_vertical_slice.py::test_generation_job_snapshots_selected_voice_profiles`; `test_generation_job_snapshots_preview_settings`; `test_saved_calibration_recipe_is_snapshotted_for_video_render`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-08 | Generation jobs snapshot selected speaker voice profile/provider payloads, saved calibration recipes, portrait metadata, and preview settings; real UI/runtime verification still needed. |
| Generate TTS audio per line or segment | Partial | `backend/app/tests/test_vertical_slice.py::test_local_speech_service_prefers_generation_voice_manifest`; `test_render_segment_metadata_exposes_safe_artifact_url`; `test_xtts_provider_uses_stewie_selected_recipe_exactly`; `test_xtts_render_job_synthesizes_exact_script_segments_to_persisted_wavs`; `test_tts_orchestrator_does_not_use_xtts_voice_cache_for_render_segments`; Docker API `XTTSProvider().synthesize_line(...)` wrote `/data/uploads/voice_models/stewie_griffin/previews/render_smoke/stewie_recipe_smoke_container.wav` with `provider_used='xtts'` and 6 reference WAVs; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-06 | TTS layer uses persisted per-speaker voice manifest, processed reference WAV metadata, calibration recipe controls, optional XTTS/RVC provider adapters, and exposes per-segment render WAV metadata. Automated tests verify XTTS render jobs synthesize exact parsed script text to per-job segment WAVs and bypass shared XTTS cache; real full video-job XTTS runtime verification is still needed. |
| Assemble audio, background, captions/text overlays, and active speaker portraits into video | Partial | `backend/app/tests/test_vertical_slice.py::test_render_preview_final_mp4_uses_persisted_segment_wavs`; `test_xtts_render_job_synthesizes_exact_script_segments_to_persisted_wavs`; `test_ffmpeg_render_cache_reuses_tts_and_invalidates_changed_inputs`; `test_debug_mode_extracts_final_audio_and_preview_skips`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `96 passed` on 2026-05-13 | FFmpeg-first assembly uses normalized persisted segment WAVs, cached background/overlay/final artifacts, render plans, cache reports, and debug-only final audio extraction; real rendered MP4 still needs manual runtime review. |
| Preview generated output | Partial | `frontend/src/components/command-room/CommandRoom.tsx`; `frontend/src/pages/ProjectEditorPage.tsx`; `backend/app/tests/test_vertical_slice.py::test_project_preview_settings_save_load_background_speakers_and_layout`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `98 passed`; `npm run build` passed on 2026-05-13 | Command Room and Project Editor render a browser pre-render preview from persisted background, speaker portraits, caption style, layout, and size controls. Manual browser verification against the HTML references and actual generated media still needed. |
| Export generated video file | Not Verified | Needs repository audit | Verify generated video path and download/export behavior. |
| View job status, errors, and generation logs from UI | Partial | `backend/app/tests/test_vertical_slice.py::test_generation_job_list_exposes_latest_completed_job`; `test_generation_job_artifacts_summary_exposes_debug_urls`; `backend/app/tests/test_vertical_slice.py::test_generation_job_artifact_endpoint_serves_scoped_segment_wav`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` and `npm run build` passed on 2026-05-13 | Command Room and Project Editor load latest render jobs and expose status, progress, segment WAVs, normalized WAVs, dialogue composite, render plan, cache report, timing profile, final extracted debug audio, and MP4 diagnostics; manual UX verification still needed. |

## Technical MVP

| Requirement | Status | Evidence | Notes |
|---|---:|---|---|
| FastAPI backend with clear REST endpoints | Not Verified | Needs repository audit | List endpoints and verify health/generation routes. |
| React + Tailwind frontend with generation forms and preview panels | Partial | `frontend/src/components/command-room/CommandRoom.tsx`; `frontend/src/components/command-room/commandRoom.css`; `frontend/src/pages/ProjectEditorPage.tsx`; `frontend/src/pages/VoiceLabPage.tsx`; `npm run build` passed on 2026-05-13 | Command Room adds the dashboard shell, start-production form, preview/render workspace, voice mapping, scene library, pipeline, health, queues, and channel panels; Project Editor remains available. Manual browser verification still needed. |
| Celery worker for long-running generation jobs | Partial | `backend/app/tasks/generation.py`; `backend/app/tasks/voice_operations.py`; `backend/app/tasks/voice_preview.py`; `backend/app/celery_app.py`; `backend/app/tests/test_vertical_slice.py::test_voice_operation_reference_upload_uses_staged_file_without_read_bytes`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `93 passed` on 2026-05-11 | Generation jobs and memory-heavy Voice Lab operations are queued through Celery; staged Voice Lab uploads are processed from disk in worker jobs instead of via whole-file `Path.read_bytes()`. Manual Docker replay is still needed for repeated real reference upload/calibration OOM verification. |
| Local storage structure for uploaded assets, generated files, voice profiles, and presets | Not Verified | Needs repository audit | Verify storage service and `.gitignore`. |
| TTS provider abstraction | Partial | `backend/app/tests/test_vertical_slice.py::test_tts_orchestrator_does_not_fallback_when_openvoice_selected_but_unavailable`; `test_tts_orchestrator_does_not_fallback_when_xtts_selected_but_unavailable`; `test_generation_worker_persists_xtts_provider_failure`; `test_tts_provider_capabilities_route_returns_registry_state`; `test_stewie_selected_recipe_validates_required_paths`; `test_xtts_provider_uses_stewie_selected_recipe_exactly`; Docker API/worker import checks passed with `XTTS_ENABLED=True`; Docker API selected-recipe validation found provider `xtts`, checkpoint path, 6 references, and golden preview; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed on 2026-05-06 | Provider selection honors explicit OpenVoice/XTTS/RVC fail-closed policy, records provider diagnostics, exposes optional XTTS/RVC capability state, validates the Stewie selected XTTS recipe before use, and does not silently use fallback TTS when XTTS is selected. |
| Reliable fallback TTS provider that works inside Docker | Not Verified | Needs Docker/runtime verification | Must test inside app runtime. |
| OpenVoice V2 integration as clone-capable provider when configured | Not Verified | Needs repository and runtime audit | Must handle disabled/unavailable/available states. |
| Health checks for API, worker, storage, ffmpeg, TTS providers, and OpenVoice availability | Not Verified | Needs repository audit | Verify endpoint response includes each dependency. |
| Regression tests for critical rendering and TTS behavior | Partial | `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `98 passed` on 2026-05-13 | Coverage includes voice manifest propagation, provider fail-closed behavior, persisted and normalized segment WAV assembly, FFmpeg render planning/cache behavior, debug-only audio extraction, image background support, render layout snapshots, preview settings persistence, artifact summary metadata, production aliases, portrait/background storage separation, XTTS runtime/cache metadata, OpenVoice render-profile stages, and staged Voice Lab upload memory regression protection. |

## Product Modules

| Module | Status | Evidence | Notes |
|---|---:|---|---|
| Dashboard | Partial | `frontend/src/App.tsx`; `frontend/src/components/command-room/CommandRoom.tsx`; `frontend/src/components/command-room/commandRoom.css`; `npm run build` passed on 2026-05-13 | `/` now renders the Command Room dashboard with unauthenticated local-shell state, authenticated paused/active sync state, required sidebar order, production cards, start-production, preview/render, voice, scene, health, queue, release, and channel panels. Manual visual parity verification still needed. |
| Script Studio | Partial | `POST /script-generation/generate`; `frontend/src/pages/ProjectEditorPage.tsx`; `backend/app/tests/test_script_generation.py`; `python3 -m pytest backend/app/tests/test_script_generation.py` passed with `15 passed`; `npm run build` passed on 2026-05-13 | Project Editor can generate structured scripts by format/platform, show Ollama/fallback status and warnings, preview sectioned lines, and accept valid scripts into revisions; manual browser verification still needed. |
| Character Library | Not Verified | Needs repository audit | Verify upload/select flow. |
| Voice Lab | Partial | `backend/app/tests/test_vertical_slice.py::test_reference_audio_upload_normalizes_audio_and_invalidates_embedding`; `test_voice_operation_reference_upload_uses_staged_file_without_read_bytes`; `test_character_reference_dataset_upload_analyze_and_attach_model`; `test_character_calibration_batch_scores_and_saves_recipe`; `test_prepare_voice_profile_persists_embedding_metadata`; `backend/app/tasks/voice_operations.py`; `GET /voice-lab/operations/{job_id}`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `93 passed` on 2026-05-11 | Voice Lab persists voice/replication state and queues memory-heavy reference processing, dataset analysis, model attach, profile prepare, and calibration batch work to `voice_worker`; staged upload processing no longer materializes the full pending file in worker memory. Full manual runtime UX/OOM verification still needed. |
| Background Presets | Partial | `backend/app/tests/test_vertical_slice.py::test_background_presets_are_loaded_from_bundled_media_dir`; `test_image_background_upload_and_preset_selection`; `test_project_preview_settings_save_load_background_speakers_and_layout`; `python3 -m pytest backend/app/tests/test_vertical_slice.py` passed with `96 passed` on 2026-05-13 | Video and image preset discovery plus project preview persistence are covered; manual UI/runtime verification still needed. |
| Video Generator | Partial | `backend/app/tests/test_vertical_slice.py::test_generation_job_snapshots_preview_settings`; `test_generation_worker_uses_persisted_voice_manifest_after_binding_changes`; `test_ffmpeg_render_cache_reuses_tts_and_invalidates_changed_inputs`; `npm run build` passed on 2026-05-13 | Project Editor has a pre-render preview, draft/final/debug render modes, and snapshots preview layout into generation jobs; manual browser verification still needed. |
| Job Monitor | Partial | `backend/app/tests/test_vertical_slice.py::test_generation_job_list_exposes_latest_completed_job`; `test_generation_job_artifacts_summary_exposes_debug_urls`; `npm run build` passed on 2026-05-13 | Command Room render queue and Project Editor expose latest render status plus segment WAV, normalized WAV, dialogue composite WAV, render plan, cache report, timing profile, debug final extracted audio, and MP4 diagnostics; manual UX verification still needed. |
| Generated Media Library | Not Verified | Needs repository audit | Verify list/preview/export. |
| Upload / Publishing Prep | Partial | `frontend/src/components/command-room/CommandRoom.tsx`; existing metadata/publish routes; `npm run build` passed on 2026-05-13 | Command Room release/channel panels show local, paused, and active gating around existing publish support; real platform publishing remains intentionally limited to existing backend support and needs manual verification. |
| System Health and Settings | Partial | `frontend/src/components/command-room/CommandRoom.tsx`; `npm run build` passed on 2026-05-13 | Command Room Studio Health summarizes voice engine, preview persistence, render engine, segment cache, artifact storage, and frontend sync state. Backend health endpoint breadth still needs separate verification. |

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
