---
name: student-system-workflows
description: Build, change, or troubleshoot the Student System project’s student and faculty workflows, timetable behavior, and Flask interface.
metadata:
  short-description: Work on the Student System app
---

# Student System Workflows

Use this skill when making changes to the Student System project, especially its student or faculty registration, login, dashboard, timetable, and interface behavior.

## Project context

- At the Phase 1 baseline, the project root has planning artifacts and the historical Flask/Jinja UI is under `old version/`; there is no active root `app.py`. Phase 1 creates the new API package. Treat the checked-in code as the source of truth and do not move or replace the historical UI before the final frontend phase.
- `PRD.md` describes a broader academic ERP, including admin, attendance, persistence, realtime updates, and dynamic reallocation. Those are product goals, not necessarily implemented features. Inspect the relevant code before relying on them.
- In the archived `old version/app.py`, student schedules use `MORNING` and `AFTERNOON`, faculty schedules are derived from timetable dictionaries, and user/schedule changes are in-memory only. Do not treat those archived behaviors as active API functionality.
- Historical screen files are under `old version/`. Check actual paths and Flask configuration before moving templates or static assets.

## How to work in this project

- Before editing, inspect the route, helper, template, and static files that implement the requested workflow. Follow existing naming and rendering patterns unless the request calls for a broader redesign.
- Keep student and faculty access paths distinct. Preserve session checks on protected dashboards and ensure a workflow uses the identity stored for the signed-in role.
- Keep timetable times consistently formatted as zero-padded 24-hour `HH:MM` strings when relying on the existing lexical comparisons. Handle breaks and empty faculty/room values as non-lectures where relevant.
- When changing schedule data or helpers, consider both student views and faculty views; the two are derived from shared schedule dictionaries.
- Keep changes aligned with the MVP and the user's request. Do not build out every PRD feature just because it is described there, and do not silently replace the current Flask app or in-memory model.
- For work assigned to an implementation phase, read `IMPLEMENTATION_PLAN.md` and compare the phase's requirements and exit criteria to `PRD.md` and `PRD_PHASE_CROSSWALK.md` when available. Surface uncovered PRD requirements or conflicts before changing dependent behavior; keep accepted deferrals explicit.
- If requirements are ambiguous, use the PRD as intent and the implementation as present behavior. Ask only when the distinction changes the requested result materially.
- Describe any meaningful limitation caused by in-memory data or draft-only PRD requirements when it affects the result.

## Verification

When the user asks for verification, run the narrowest useful checks for the changed behavior. For route or template changes, confirm the relevant paths and rendering behavior; for schedule logic, check representative morning and afternoon cases, including boundaries and breaks. Do not claim a feature is persistent, real-time, or role-secure beyond what the implementation establishes.
