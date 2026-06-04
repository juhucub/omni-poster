# AGENTS.md - Omniposter Codex Agent Instructions

Last updated: 2026-06-04

You are a Codex development agent working on **Omniposter**, a creator workflow tool for generating repeatable video content from reusable assets.

Your job is not only to change code. Your job is to preserve project memory, avoid repeated regressions, and leave the repository more verifiable than you found it.

## Required Read-First Files

Before any implementation, audit, refactor, or bug fix, read:

1. AGENTS.md
2. docs/AGENT_BRIEF.md
3. docs/CONTEXT_INDEX.md

Then use docs/CONTEXT_INDEX.md, docs/TASK_ROUTING.md, and docs/REPO_MAP.md to decide which full context docs and code areas are required for the specific task.

Do not read every full context document unless the task is broad, architectural, MVP-wide, or explicitly asks for a full audit.

If any file is missing, create a minimal version before proceeding and mention that in the final response.

## Codex Docs Hierarchy

`AGENTS.md`
- Tell Codex what to read and how to behave.

`docs/AGENT_BRIEF.md`
- Short always-read project memory summary.
- Captures highest-value product, priority, and regression-safety facts.

`docs/CONTEXT_INDEX.md`
- Routing index for deciding which full context docs to read.
- Prevents default full-doc loading for narrow tasks.

`docs/TASK_ROUTING.md`
- Maps common task types to relevant docs and code areas.

`docs/REPO_MAP.md`
- Concise backend, frontend, test, runtime, and storage map for targeted inspection.

`docs/PROJECT_MANUAL.md`
- Product and architecture source of truth.
- Explains what Omniposter is supposed to become.

`docs/CURRENT_STATUS.md`
- Current project memory.
- Explains what is working, partial, broken, prioritized, and recently changed.

`docs/KNOWN_MISTAKES.md`
- Regression memory.
- Explains what not to repeat.

`docs/ARCHITECTURE_DECISIONS.md`
- Architectural decision record.
- Explains why the system is designed this way.

`docs/MVP_CHECKLIST.md`
- MVP readiness tracker
- Explains what is complete, partial, missing, or not verified.

`docs/CODEX_WORKFLOW.md`
- Requires audit, implementation, verification, and documentation workflow.

`docs/AGENT_HANDOFF.md`
- Protocol for switching work between Codex, Claude Code, and other coding agents without losing scope, evidence, or safety invariants.

## Global Rules

### Evidence Rules

- Never mark a feature as complete without evidence.
- Evidence must come from code, tests, endpoint behavior, manual verification, command output, or exact implementation locations.
- If you cannot verify something, mark it `Not Verified`, not `Complete`.
- Do not claim a bug is fixed unless you can explain the previous symptom, root cause, changed files, and verification result.

### Scope Rules

- Keep tasks small and scoped.
- Prefer one complete vertical slice over broad unfinished refactors.
- Do not rewrite unrelated areas.
- Do not rename modules, move storage paths, or replace providers unless the task explicitly requires it.
- Preserve existing working behavior unless the task asks to change it.

### Git and Filesystem Safety

- Treat `.git/` as read-only.
- Never modify, copy, move, delete, or run bulk operations against `.git/`.
- Never run destructive cleanup commands against the repository root.
- Never commit large generated media, model checkpoints, or dependency caches.
- Do not add generated videos, large background clips, OpenVoice checkpoints, virtual environments, `node_modules`, Docker volumes, or local storage outputs to git.
- Search for an existing owner before creating new source files.
- Do not create duplicate/copy files such as `* 2.py`, `* copy.py`, `*.bak`, or `*.old`.
- Keep runtime outputs out of source directories; generated media, local DBs, voice datasets, checkpoints, render cache, and frontend build/test output must stay ignored.
- Update `docs/REPO_STRUCTURE.md` when adding permanent directories or changing source/runtime ownership.

### Product Safety

- The user is building a creator workflow tool, not a one-off video script.
- Preserve reusable assets, repeatable generation, and module boundaries.
- Speaker identity, character assets, voice profiles, script segments, audio timing, captions, and active portrait overlays must remain aligned.
- Do not mix background presets with character assets.
- Do not assume OpenVoice is available; detect and report provider availability through health checks.
- Always keep a Docker-safe local fallback TTS path.

### Documentation Safety

At the end of every implementation or audit, decide whether the context docs need updates.

Living project memory files:

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
- `docs/AGENT_HANDOFF.md`

Update docs only when necessary and only with small, factual, evidence-based changes.

If no doc update is needed, explicitly say:

> No doc updates needed because: [reason].

Do not casually overwrite `docs/PROJECT_MANUAL.md`. Update it only when product intent, MVP scope, architecture, roadmap, or non-goals change.

## Required Final Response Format

Every Codex task must end with:

```md
## Summary
Briefly explain what was done.

## Changed Files
List every changed file.

## Tests Run
List commands run and results.

## Manual Requirements Addressed
List which Project Manual requirements this task addressed.

## Known Mistakes Protected Against
List relevant entries from KNOWN_MISTAKES.md or say "None."

## Documentation Updates
List which context docs were updated and why.
If none, say why.

## Remaining Risks
List anything still uncertain, incomplete, or not verified.

## Recommended Next Task
Give the next best scoped Codex task.

## Recommended Git Commands For User
Provide exact suggested `git add ...` and `git commit -m "..."` commands for the user to run manually. Agents must not run those commands unless explicitly asked.
```

## Preferred Working Style

1. Read the required docs.
2. Inspect the relevant code before editing.
3. State the implementation plan briefly.
4. Make the smallest correct change.
5. Add or update tests when possible.
6. Run targeted verification.
7. Update context docs only when the evidence requires it.
8. Produce the required final response.
