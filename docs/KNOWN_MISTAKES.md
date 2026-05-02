# Omniposter Known Mistakes

Last updated: 2026-05-01

This file is regression memory. Add to it when bugs are found or fixed. Do not remove entries unless they are obsolete and clearly replaced by a better rule.

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
