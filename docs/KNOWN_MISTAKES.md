# Omniposter Known Mistakes

Last updated: 2026-05-05

This file is regression memory. Add to it when bugs are found or fixed. Do not remove entries unless they are obsolete and clearly replaced by a better rule.

## Reference Audio Treated Like Full Performance Clone

Date found:
2026-05-05

Symptom:
OpenVoice reference uploads made voices sound more human but did not reliably preserve cadence, rhythm, pitch behavior, emotion, pauses, accent, or speaking style.

Root cause:
Reference clips were treated too much like full performance clones, while OpenVoice primarily clones tone color. Prosody and style need explicit base speaker/style/profile settings, and bad reference clips need validation before use.

Fix:
Voice profiles now persist original uploads, processed mono 16 kHz WAV references, validation status/metrics/warnings, processed-reference OpenVoice embedding metadata, style/prosody settings, calibration recipe previews/save-back, and comparison artifacts for Voice Lab previews, render segment WAVs, dialogue composite WAVs, and final extracted audio.

Regression test:
`backend/app/tests/test_vertical_slice.py::test_reference_audio_upload_normalizes_audio_and_invalidates_embedding`, `test_reference_audio_upload_rejects_mostly_silent_audio`, `test_reference_audio_upload_rejects_clipped_audio`, `test_reference_audio_upload_accepts_soft_warning_metadata`, `test_openvoice_prepare_voice_profile_prefers_processed_reference_path`, `test_voice_lab_calibration_matrix_queues_recipe_previews`, `test_saved_calibration_recipe_is_snapshotted_for_video_render`, and `test_render_segment_metadata_exposes_safe_artifact_url`.

Rule:
Do not treat reference audio as a full performance clone. Always validate and process references, persist embeddings from processed audio, audition explicit calibration recipes, and keep prosody/style explicit in voice profile settings with unsupported controls degrading safely.

## Final MP4 Audio Did Not Use Persisted OpenVoice Segment WAVs

Date found:
2026-05-04

Symptom:
Render segment WAV artifacts sounded correct and used the selected OpenVoice profiles, but audio extracted from the final MP4 still sounded like local/espeak fallback.

Root cause:
The final video export did not have a persisted, auditable composite audio source built from the exact segment artifact WAV paths, leaving the compositor path able to use a different hidden/temp audio source.

Fix:
Final rendering now ffmpeg-concatenates the persisted segment WAV artifacts in script order into `generated/{job_id}/audio/dialogue_composite.wav`, uses that composite WAV as the final MoviePy audio input, logs all segment and assembly paths, and records assembly paths in job metadata.

Regression test:
`backend/app/tests/test_vertical_slice.py::test_render_preview_final_mp4_uses_persisted_segment_wavs`.

Rule:
The final MP4 must use a composite audio track built from the same segment WAV artifact paths shown in the render job panel.

## Completed Render Diagnostics Hidden After Active Job Ends

Date found:
2026-05-04

Symptom:
The Project Editor had render segment WAV links, but completed jobs disappeared from the visible render panel after refresh because only the active generation job endpoint was loaded.

Root cause:
The frontend set `generationJob` to `null` when `/projects/{project_id}/generation-jobs/active` returned 404, and there was no project-scoped generation job list used as a completed-job fallback.

Fix:
Added a project generation-job list endpoint and updated Project Editor to load the latest completed job when no active job exists. The latest render job panel is also visible outside the Generate tab.

Regression test:
`backend/app/tests/test_vertical_slice.py::test_generation_job_list_exposes_latest_completed_job`.

Rule:
Do not make render diagnostics depend only on active jobs; completed jobs must remain visible enough to inspect status, provider metadata, and segment artifacts.

## Render Segment Audio Hidden In Deleted Temp Directories

Date found:
2026-05-02

Symptom:
Voice Lab previews could sound correct while final video output sounded wrong, but the exact render segment WAVs were deleted after video assembly and could not be compared.

Root cause:
The render pipeline generated segment audio inside a temporary render work directory and removed that directory after ffmpeg/MoviePy assembly.

Fix:
Render segment WAVs are now written to stable generated job artifact storage and exposed through scoped job artifact URLs in job metadata.

Regression test:
`backend/app/tests/test_vertical_slice.py::test_render_speech_output_dir_uses_persisted_job_artifact_storage`, `test_render_segment_metadata_exposes_safe_artifact_url`, `test_generation_job_artifact_endpoint_serves_scoped_segment_wav`, and `test_render_audio_assembly_uses_segment_audio_paths`.

Rule:
Do not hide or delete render segment audio before it can be compared against Voice Lab previews and final video output.

## Selected OpenVoice Profiles Silently Replaced During Render

Date found:
2026-05-02

Symptom:
OpenVoice voice presets appeared selectable and previewable in Voice Lab, but generated videos could render with default/local TTS or overlay-only fallback instead of the selected OpenVoice profile.

Root cause:
Generation jobs did not persist a per-speaker voice profile/provider snapshot, and render-level fallback could hide TTS provider failures.

Fix:
Generation jobs now store a voice manifest, pass it through Celery into rendering, honor per-profile provider/fallback policy, and fail closed for OpenVoice-selected profiles.

Regression test:
`backend/app/tests/test_vertical_slice.py::test_generation_job_snapshots_selected_voice_profiles`, `test_generation_worker_uses_persisted_voice_manifest_after_binding_changes`, `test_generation_worker_persists_tts_provider_failure`, and `test_project_render_service_does_not_overlay_fallback_for_tts_errors`.

Rule:
Never render a video with a different TTS provider than the selected OpenVoice profile without failing the job or explicitly recording fallback status.

## Marking Features Complete Without Evidence

Date found:
2026-05-01

Symptom:
Codex or documentation claims a feature is complete without proof from code, tests, endpoints, command output, or manual verification.

Root cause:
The task relied on intended behavior instead of verified behavior.

Fix:
Require every `Complete` checklist status to include evidence.

Regression test:
Needed.

Rule:
Never mark something complete without evidence from code, tests, endpoint behavior, command output, or manual verification.

## Skipping Read-First Context Docs

Date found:
2026-05-01

Symptom:
Codex repeats old mistakes, ignores current priorities, or reverses prior architecture decisions.

Root cause:
The agent did not read the project context files before making changes.

Fix:
`AGENTS.md` requires reading all context docs before implementation.

Regression test:
Needed.

Rule:
Always read `AGENTS.md`, `PROJECT_MANUAL.md`, `CURRENT_STATUS.md`, `KNOWN_MISTAKES.md`, `ARCHITECTURE_DECISIONS.md`, `MVP_CHECKLIST.md`, and `CODEX_WORKFLOW.md` before changing code.

## Character Assets Mixed With Background Presets

Date found:
2026-05-01

Symptom:
Speaker portraits use files from the background preset directory instead of selected character PNGs.

Root cause:
Asset discovery or speaker mapping does not keep character assets and background presets separate.

Fix:
Needed unless already verified in code.

Regression test:
Needed. Add a test that confirms speaker portraits are resolved only from character mappings or character storage, never from background preset storage.

Rule:
Never load speaker portraits from background preset directories.

## Background Presets Missing From UI Choices

Date found:
2026-05-01

Symptom:
Pregenerated background sources stored in `backend/storage/presets` do not appear as selectable background sources.

Root cause:
Not verified. Likely causes include wrong storage path, missing API endpoint, frontend not calling the endpoint, unsupported file extension filtering, or container volume mismatch.

Fix:
Needed unless already verified in code.

Regression test:
Needed. Add backend and frontend-facing verification that preset files appear in background choices.

Rule:
Background preset discovery must be tested against the actual configured preset storage path.

## TTS Provider Not Docker-Safe

Date found:
2026-05-01

Symptom:
TTS works on the host but fails or produces unusable output inside Docker.

Root cause:
The implementation depends on host-specific TTS behavior or unavailable runtime dependencies.

Fix:
Use a Docker-safe fallback TTS provider and expose provider health checks.

Regression test:
Needed. Add a test or health check that verifies fallback TTS availability inside the app runtime.

Rule:
Every TTS change must preserve a Docker-safe fallback path.

## TTS Voices Too Slow, Distorted, or Garbled

Date found:
2026-05-01

Symptom:
Generated voices sound too slow, deep, distorted, or garbled.

Root cause:
Not verified. Potential causes include incorrect sample rate conversion, bad provider defaults, unsuitable espeak/OpenVoice parameters, repeated audio transformations, or mismatched voice profile settings.

Fix:
Needed unless already verified in code.

Regression test:
Needed. Add regression coverage for generated audio duration, sample rate, file validity, and provider settings.

Rule:
Do not change TTS defaults without checking output duration, sample rate, and playable audio validity.

## OpenVoice Availability Assumed

Date found:
2026-05-01

Symptom:
The app behaves as if OpenVoice is available even when checkpoints, dependencies, or runtime device support are missing.

Root cause:
Provider initialization is not guarded by configuration and health checks.

Fix:
OpenVoice must be optional, explicitly configured, and reported through health checks.

Regression test:
Needed. Add tests for OpenVoice disabled, unavailable, and available states.

Rule:
Never assume OpenVoice is installed. Always detect and report availability.

## Speaker Overlay Timing Not Bound To Segment Audio

Date found:
2026-05-01

Symptom:
Active speaker overlays switch too early, too late, or independently of the generated dialogue audio.

Root cause:
Overlay timing is not derived from the finalized speaker segment audio timeline.

Fix:
Speaker segments should be the canonical source for audio timing, captions, and active portrait overlays.

Regression test:
Needed. Add a render-planning test that verifies speaker overlay intervals match segment audio intervals.

Rule:
Active speaker portraits must be timed from generated segment durations, not guessed from script order alone.

## Updating Documentation Too Broadly

Date found:
2026-05-01

Symptom:
Context docs become noisy, overwritten, or less trustworthy after a task.

Root cause:
The agent updates docs as a generic cleanup step instead of making small evidence-based changes.

Fix:
Update docs only when necessary and explain why.

Regression test:
Needed.

Rule:
Keep documentation updates small, factual, and evidence-based.

## Committing Large Generated Media Or Model Artifacts

Date found:
2026-05-01

Symptom:
Git history or pushes are blocked by large videos, generated outputs, model checkpoints, or dependency caches.

Root cause:
Generated and local runtime artifacts are not excluded or are accidentally added.

Fix:
Ensure storage outputs, generated media, model checkpoints, and caches are excluded from git.

Regression test:
Needed. Verify `.gitignore` covers local generated artifacts.

Rule:
Never commit generated videos, uploaded media, OpenVoice checkpoints, local storage outputs, dependency caches, or Docker volumes.

## Dangerous Git Directory Operations

Date found:
2026-05-01

Symptom:
Repository metadata becomes corrupted or git commands fail unexpectedly.

Root cause:
Automation or cleanup commands touch `.git/`.

Fix:
Treat `.git/` as read-only and avoid destructive repository-root operations.

Regression test:
Needed.

Rule:
Never modify, copy, move, delete, or bulk-edit `.git/`.
