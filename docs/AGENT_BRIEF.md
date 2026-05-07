# Omniposter Agent Brief

Last updated: 2026-05-06

Read this as the short always-read project memory summary. Use `docs/CONTEXT_INDEX.md` and `docs/TASK_ROUTING.md` to decide which full docs and code areas are needed for the current task.

## Product

Omniposter is a creator workflow tool for repeatable script-to-video generation from reusable characters, background presets, voice profiles, job state, and generated media.

The project is a product workflow, not a one-off rendering script.

## Current P0 Priorities

- Verify the full script-to-video path from UI/API request through Celery job to generated video output.
- Verify character image selection and active speaker overlay mapping.
- Verify background preset discovery and selection.
- Verify Docker-safe fallback TTS.
- Verify job status, errors, logs, preview output, and export output.

## Non-Negotiable Safety Rules

- Do not touch `.git/`.
- Do not commit generated media, model checkpoints, dependency caches, Docker volumes, virtual environments, or local storage outputs.
- Do not mark any feature, bug fix, or MVP item complete without evidence.
- Preserve TTS provider abstraction.
- Preserve Docker-safe fallback TTS.
- Do not assume OpenVoice, XTTS, or RVC is available; detect and report runtime availability.
- Keep character assets separate from background presets.
- Use speaker segments as the canonical timeline for audio, captions, and active speaker portraits.
- Do not silently replace selected OpenVoice/XTTS/RVC profiles with fallback TTS.
- Final MP4 audio must use persisted segment WAV artifacts, not hidden temp audio.

## High-Value Project Memory

- `docs/PROJECT_MANUAL.md` is the source of truth for product intent, MVP goals, non-goals, and architecture expectations.
- `docs/CURRENT_STATUS.md` records what is working, partial, broken, prioritized, and recently changed.
- `docs/KNOWN_MISTAKES.md` records active regression rules; read the archive only when more historical detail is needed.
- `docs/ARCHITECTURE_DECISIONS.md` records decisions future agents should not reverse casually.
- `docs/MVP_CHECKLIST.md` tracks MVP readiness and must remain evidence-based.
- `docs/CODEX_WORKFLOW.md` defines the audit, implementation, verification, and documentation workflow.
