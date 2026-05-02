# Omniposter Codex Workflow

Last updated: 2026-05-01

This is the required workflow for Codex tasks in Omniposter.

## 1. Read Context First

Before changing anything, read:

```bash
cat AGENTS.md
cat docs/PROJECT_MANUAL.md
cat docs/CURRENT_STATUS.md
cat docs/KNOWN_MISTAKES.md
cat docs/ARCHITECTURE_DECISIONS.md
cat docs/MVP_CHECKLIST.md
cat docs/CODEX_WORKFLOW.md
```

If a file is missing, create a minimal version and mention it in the final response.

## 2. Classify The Task

Classify the request as one of:

- Audit only
- Bug fix
- Feature implementation
- Refactor
- Test addition
- Documentation update
- Architecture change
- MVP verification

Architecture changes require reading `docs/ARCHITECTURE_DECISIONS.md` carefully and updating it if a new decision is made.

## 3. Audit Before Editing

Before implementation, inspect relevant files.

Recommended commands:

```bash
find . -maxdepth 3 -type f | sort | sed 's#^./##' | head -200
find . -maxdepth 4 -type f \( -name '*.py' -o -name '*.ts' -o -name '*.tsx' -o -name '*.js' -o -name '*.jsx' -o -name '*.md' \) | sort
grep -R "FastAPI\|APIRouter\|Celery\|ffmpeg\|OpenVoice\|tts\|voice\|preset\|character\|speaker\|segment" -n backend frontend docs 2>/dev/null | head -200
```

Adapt commands to the actual repo structure.

## 4. Build A Small Plan

Before editing, identify:

- Files likely to change.
- Tests likely to run.
- Current known mistake risks.
- Whether docs may need an update.
- How completion will be verified.

Do not perform broad rewrites unless required.

## 5. Implement In A Small Vertical Slice

Prefer vertical slices that can be tested.

Examples:

- Background preset discovery endpoint + UI selector + regression test.
- Speaker mapping parser + render plan test.
- Fallback TTS provider health check + generated audio validity test.
- Job status endpoint + UI display of errors/logs.

Avoid partial wide refactors.

## 6. Verification Expectations

Run the most targeted verification available.

Backend examples:

```bash
pytest
pytest tests/test_tts*.py
pytest tests/test_render*.py
python -m pytest
```

Frontend examples:

```bash
npm test
npm run build
pnpm test
pnpm build
```

Docker/runtime examples:

```bash
docker compose ps
docker compose up --build
docker compose exec api python -c "import shutil; print(shutil.which('ffmpeg'))"
curl http://localhost:8000/health
```

Use the commands that match the repo.

If a command cannot be run, explain why.

## 7. Documentation Maintenance Decision

At the end of every audit or implementation, decide whether docs need updates.

### Update `docs/CURRENT_STATUS.md` when:

- A feature is completed.
- A feature is discovered to be incomplete.
- A bug is fixed.
- A new blocker is found.
- Tests reveal a behavior change.
- Current MVP priority changes.

Use this structure:

```md
# Omniposter Current Status

Last updated: YYYY-MM-DD

## Working
- ...

## Partially Working
- ...

## Broken / Needs Fix
- ...

## Current MVP Priority
P0:
- ...
P1:
- ...
P2:
- ...

## Recent Changes
- ...

## Open Questions
- ...
```

### Update `docs/MVP_CHECKLIST.md` when:

- A checklist item can be marked `Complete`, `Partial`, `Missing`, or `Not Verified`.
- Evidence is found for or against MVP readiness.
- Tests are added that verify a manual requirement.

Each updated checklist row must include evidence:

- File path
- Test name
- Endpoint name
- Command result
- Exact implementation location

### Update `docs/KNOWN_MISTAKES.md` when:

- A bug is fixed.
- A repeated failure mode is discovered.
- A regression risk is found.
- A test is added to prevent a previous mistake.

Use this format:

```md
## [Bug or Regression Name]

Date found:
YYYY-MM-DD

Symptom:
What the user or system observed.

Root cause:
What caused it.

Fix:
What changed.

Regression test:
Test file/name if added. If missing, say “Needed.”

Rule:
What future Codex agents must never do again.
```

### Update `docs/ARCHITECTURE_DECISIONS.md` when:

- A new architectural pattern is introduced.
- A major tool, provider, service, or storage strategy changes.
- FastAPI, Celery, Redis, ffmpeg, TTS provider architecture, OpenVoice integration, storage layout, or Docker assumptions change.
- A decision is made that future agents should not reverse casually.

Use ADR format:

```md
## ADR-XXX: Title

Status: Accepted
Date: YYYY-MM-DD

### Context
Why this decision was needed.

### Decision
What was decided.

### Consequences
What this changes or constrains.

### Files/Areas Affected
- ...
```

### Update `docs/CODEX_WORKFLOW.md` only when:

- The development workflow changes.
- A new required audit/implementation/verification step is added.
- A new required output format is introduced.
- A new safety rule should apply to every Codex task.

### Update `AGENTS.md` only when:

- A global agent instruction changes.
- A new hard rule is needed.
- A new required read-first file is added.
- A dangerous repeated behavior needs to be blocked globally.

### Update `docs/PROJECT_MANUAL.md` only when:

- Product scope changes.
- MVP goals change.
- Non-goals change.
- A new product module becomes part of the intended MVP.
- The architecture source of truth changes.

Do not update `PROJECT_MANUAL.md` for normal implementation progress.

## 8. Required Final Response

Every task must end with:

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
List relevant entries from KNOWN_MISTAKES.md or say “None.”

## Documentation Updates
List which context docs were updated and why.
If none, say why.

## Remaining Risks
List anything still uncertain, incomplete, or not verified.

## Recommended Next Task
Give the next best scoped Codex task.
```

## Reusable Codex Task Footer

Append this to development prompts:

```md
At the end of this task, decide whether any Codex context docs need to be updated.

Treat these files as living project memory:

- AGENTS.md
- docs/PROJECT_MANUAL.md
- docs/CURRENT_STATUS.md
- docs/KNOWN_MISTAKES.md
- docs/ARCHITECTURE_DECISIONS.md
- docs/MVP_CHECKLIST.md
- docs/CODEX_WORKFLOW.md

Required behavior:

1. Always read these files before implementation:
   - AGENTS.md
   - docs/PROJECT_MANUAL.md
   - docs/CURRENT_STATUS.md
   - docs/KNOWN_MISTAKES.md
   - docs/ARCHITECTURE_DECISIONS.md
   - docs/MVP_CHECKLIST.md
   - docs/CODEX_WORKFLOW.md

2. After implementation or audit, update docs only when necessary.

3. If no doc update is needed, explicitly say:
   “No doc updates needed because: [reason].”

4. Never mark something as complete without evidence from code, tests, or manual verification.

5. Never overwrite the Project Manual casually. Only update docs/PROJECT_MANUAL.md if the user’s product intent, MVP scope, architecture, or roadmap has changed.

6. Always keep documentation updates small, factual, and evidence-based.

Final response must include:

## Summary
## Changed Files
## Tests Run
## Manual Requirements Addressed
## Known Mistakes Protected Against
## Documentation Updates
## Remaining Risks
## Recommended Next Task
```

## Recommended Codex Prompt Pattern

Use this shape for future tasks:

```md
You are working in the Omniposter repo.

Task:
[One specific bug fix, feature, audit, or test addition.]

Constraints:
- Read the Codex context docs first.
- Keep the change scoped.
- Do not touch .git.
- Do not commit generated media, checkpoints, or local storage outputs.
- Preserve the TTS provider abstraction.
- Preserve Docker-safe fallback TTS.
- Keep character assets separate from background presets.
- Use speaker segments as the canonical timeline for audio, captions, and active speaker overlays.
- Add or update tests when practical.
- Update context docs only when evidence requires it.

Acceptance criteria:
- [Concrete outcome 1]
- [Concrete outcome 2]
- [Tests or command expected]
- [Docs updated or explicitly not needed]

[Paste the reusable Codex task footer.]
```

## Best Next Codex Task

Recommended first task:

```md
Audit the current Omniposter repository against docs/MVP_CHECKLIST.md.

Do not implement features yet.

Read all Codex context docs first. Then inspect backend, frontend, Docker, storage, tests, and health-check code. Update docs/CURRENT_STATUS.md and docs/MVP_CHECKLIST.md with evidence-based statuses only. Do not mark anything Complete without file paths, endpoints, tests, or command results. Add missing known mistakes only if you find repeated regression risks in code.

Run the safest available verification commands, such as backend tests, frontend build/tests, and Docker health checks if configured.

End with the required final response format.
```
