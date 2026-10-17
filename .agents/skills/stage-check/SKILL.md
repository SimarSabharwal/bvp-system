---
name: stage-check
description: Use for project work organized into stages, phases, or milestones. Read the project-root logic.md before changes, log each completed stage, and verify its requested outcome.
metadata:
  short-description: Track and verify project stages
---

# Stage Check

Use this skill when the user asks to work in stages, phases, or milestones, or explicitly asks for a stage completion log. Keep the log in the project root as `logic.md`.

## Before changing files

1. Read the project-root `logic.md` before making any implementation or documentation changes. Treat it as continuity context, not as a substitute for inspecting the actual files.
2. If `logic.md` does not exist, record that it was absent and proceed from the user's request and current project state. Create it when this stage is completed.
3. Identify the current stage's requested outcome, acceptance conditions, and any constraints carried forward from earlier log entries. Inspect relevant source files before editing them.
4. For every implementation phase, cross-check its work items and exit criteria against the corresponding PRD functional requirements, non-functional requirements, scope, and acceptance criteria. Use `PRD_PHASE_CROSSWALK.md` when present. Flag uncovered or contradictory requirements before implementing that dependent work; mark explicitly deferred PRD items as deferred rather than silently dropping them.

## At the end of each stage

1. Compare the result with the user's requested outcome and the stage's acceptance conditions. Recheck the phase against its PRD crosswalk row and update the crosswalk status/evidence if it is maintained. Confirm that no PRD requirement assigned to the phase was omitted or contradicted. Run focused checks or inspect the resulting artifacts that provide meaningful evidence. Do not claim success based only on planned work or the presence of changed files.
2. If something is incomplete and can be completed safely within scope, continue the work and verify again. If blocked, record the partial result, the specific blocker, and remaining work; do not label the stage complete.
3. Append a clearly headed entry to the project-root `logic.md`, preserving earlier entries. Include:
   - stage name/number and date;
   - requested outcome and completion status (`Complete` or `Partial`);
   - every changed file and a concise explanation of its changes;
   - important decisions or assumptions;
   - focused verification performed and its result;
   - any blocker or remaining task.
4. After updating the log, confirm the stage artifacts and new log entry are present and that the completion status matches the evidence. If that inspection reveals an issue, fix it and update the entry.

Keep entries factual and concise. Never put credentials, tokens, or other secrets in `logic.md`. A later stage should add a new entry rather than erase the history of earlier stages.
