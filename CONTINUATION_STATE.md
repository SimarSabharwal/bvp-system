# Student System — Continuation State

**Updated:** 2026-10-16  
**Current working stage:** Phase 10 — Frontend implementation and API-contract alignment  
**Current phase status:** Phases 1–8 are complete for approved API scope; Phase 9 remains partial pending representative data and Render verification; Phase 10 is partial with smart timetable draft generation and an isolated linked mock dataset added, while full role-workflow acceptance remains open.
**Project root:** `C:\Users\ssima\OneDrive\Desktop\Student System`

This file is a handoff for a future Codex session. Read it together with `logic.md`; it supplements the project records and does not replace them. Before modifying project files, follow `.agents/skills/stage-check/SKILL.md` and `.agents/skills/decision-overlap/SKILL.md`.

## Resume instructions

When the user resumes this project:

1. Read this file, the complete `logic.md`, `IMPLEMENTATION_PLAN.md`, `PRD_PHASE_CROSSWALK.md`, `PHASE_0_DECISIONS.md`, `DATABASE_DESIGN.md`, and PRD FR-10/FR-11/NFRs before editing.
2. Phase 2 is complete for migration/constraint scope: a temporary PostgreSQL 18 database applied `0001_initial_schema`, passed downgrade/re-upgrade, allowed adjacent sessions, and rejected section, teacher, and room overlaps independently. The temporary database was stopped and removed; no Render database was provisioned.
3. Phase 3 is complete for the approved sample-derived local-demo scope. The seed ran twice with stable persisted counts, and a forced late conflict proved transaction rollback. Do not duplicate or rerun completed work without a concrete requested change.
4. Keep the original `sample_data.json` unmapped and separate. The user explicitly authorized a separate, clearly labeled synthetic demo dataset on 2026-10-16; it includes approximate mock capacities and mock teacher/student relationships. Never present it as authoritative institutional data or deploy it as production data.
5. Never copy placeholder/demo passwords into a real environment. Optional local demo credentials remain local-only and hashed.
6. Cross-check any new phase work against its PRD crosswalk row and update the crosswalk plus this log after focused verification.

7. Phases 4–8 are complete for their approved API scope. Phase 10 provides three glassmorphic interfaces and a new admin mock-data loader/smart draft generator. The user-provided PDF is a Winter 2026 exam timetable; only BCA/BBA CBCS 2026 Sem-I catalog fields are used. Its exam dates/times are not class recurrence. Course `B` has explicitly synthetic placeholder subjects. The local demo database now has 3 courses, 9 sections, 14 subjects, 48 teachers, 9 students, 9 rooms, one mock academic year, and an unpublished five-day draft across the 9 sections. See `DEMO_GUIDE.md`; credentials remain in ignored `reports/demo-credentials.txt`, never in this handoff. Phase 9 remains partial pending representative-load and selected Render operations checks.

Phase 3 uses `scripts/seed_dev.py` and `data/dev_demo_seed.json`. On 2026-10-16, the dry-run passed (2 students, 1 faculty login, 8 subjects, no inferred timetable rows); two imports to a temporary PostgreSQL 18 database preserved persisted counts, and a forced late conflict left no partial insert. The validator rejected `sample_data.json` pending approved mappings. The earlier verification database was removed after that run. For the authenticated demo added on 2026-10-16, a separate PostgreSQL 18 cluster now lives in ignored `.local-demo-postgres/` and listens only on `127.0.0.1:55432`; ignored `.env` configures the local app, and `reports/demo-credentials.txt` holds the local-only logins. No Render database is provisioned. The seed remains limited to approved sample facts and adds no guessed institutional mappings.

## Confirmed decisions to preserve

- Render Web Service plus managed PostgreSQL 18 is the selected target; no Render resources or database have been provisioned. Exact region/plan is still undecided.
- Institution timezone is `Asia/Kolkata`.
- Existing sample records are demo-only; missing mappings are not permission to guess.
- Login IDs are ERP ID/faculty code; users can hold multiple roles.
- Teachers/admins manage availability; reallocation defaults to suggest-and-approve with admin-configurable auto-apply; `EXCUSED` attendance is excluded from percentages; only admins correct closed attendance.
- Publish generates section-based dated sessions across the full effective period, skipping holidays/exams. Lab subgroups and cross-section shared lectures are deferred past MVP.
- Keep per-request database reads limited to needed fields/rows; maintain the API-first, frontend-last order.

## Current implementation facts

- Phase 1 API foundation is in `app/`, with `wsgi.py`, `openapi.yaml`, and dependency definitions in `requirements.txt`.
- Phase 2 schema is in `app/models/__init__.py`; revision `0001_initial_schema` creates 29 domain tables and six GiST exclusion constraints. Revision `0004_subject_course` adds course, semester, curriculum-version and type metadata to subjects. Alembic head is `0004_subject_course`; applied to the isolated local demo database.
- Python compilation, metadata FK-target checks, and offline Alembic generation passed; the additional live PostgreSQL 18 migration, downgrade/re-upgrade, and independent overlap evidence is recorded in the final Phase 2/3 entry in `logic.md`.
- Earlier Phase 2 and Phase 4/5 PostgreSQL verification clusters were temporary. The current authenticated demo uses a separate local PostgreSQL 18 cluster under ignored `.local-demo-postgres/`, configured by ignored `.env` and running only on `127.0.0.1:55432`. Demo logins are listed in ignored `reports/demo-credentials.txt`. Render remains selected but is not provisioned.
- Application startup does not create tables. Apply schema changes with `python -m alembic upgrade head` after `DATABASE_URL` is configured.
- Phase 10 source is in `app/frontend.py`, `app/templates/index.html`, and `app/static/`; historical UI remains in `old version/`. Admin mock-data loader is `app/api/v1/mock_data.py` with `data/mock_catalog_winter_2026.json`; timetable generator is `app/api/v1/smart_timetable.py`. The loopback demo database has nine generated draft versions (180 recurring entries) for 2026-10-19 through 2026-10-23. Drafts are intentionally unpublished; admin can open them from Smart Timetable Creation. Keep Phase 10 partial until role/student/teacher/attendance/notification workflows are walked through and validated.
- Phase 3 now supports a local-only fixture limited to sample-derived identities and subject catalog, plus a transactional insert path, row-level preflight errors, duplicate/reference checks, schedule overlap checks for normalized timetable input, and JSON import reports. It does not translate the legacy `sample_data.json` or invent the missing academic/room/faculty mappings. Database writes require explicit development mode and a loopback host.
- Phase 4 adds signed HTTP-only/SameSite sessions with only `user_id` in session data; active status and role memberships are loaded from PostgreSQL on every protected request. It adds Werkzeug password hashes, login lockout after five failures in a 15-minute window (15-minute lock), CSRF checks on cookie-authenticated writes, self-derived student/teacher profiles, account/role admin operations, and the interactive first-admin command. Production config requires `SECRET_KEY` and PostgreSQL and sets secure cookies.
- Phase 5 adds admin management APIs for user/profile lifecycle, academic years, courses, sections, subjects, enrollments, curriculum/teacher qualification mappings, assignments, rooms, and room features, plus compact role-authenticated lookups. Identity/profile rows are deactivated and retained instead of physically deleted. Collections are capped at 100 rows, accept typed filters and selected safe fields, and project only returned fields from PostgreSQL. Secrets never appear in response projections.
- Phase 6 adds draft timetable version/entry management, constraint-checked publication and full-period dated session generation (excluding holidays, exams, and unavailable resources), availability/event APIs, compact self and admin schedule reads, and bounded free-slot computation. Live PostgreSQL evidence confirms one validated published entry generated one dated session.
- Phase 7 supports unavailable teacher/room analysis, hard-constraint candidate filtering, curriculum backlog-aware scoring, suggest-and-approve by default, configurable auto-apply, pending recovery, and audit/outbox/recipient-notification writes. Cascade plans are grouped, parent-linked, bounded to depth 2, and atomically approved/rejected/reverted; changes above the configured automatic limit require admin action.
- Phase 8 adds actual-session attendance open/roster/mark/close, date-effective enrollment enforcement, admin-only closed-session corrections, completion-linked recovered lectures, EXCUSED-excluding aggregates, recipient-owned notification paging/read state, role/section-scoped announcements, and bounded admin reports. Routes are in `app/api/v1/attendance.py`, `communications.py`, and `reports.py`.
- A disposable PostgreSQL 18 run applied, downgraded, and reapplied all migrations through 0003, then verified a depth-2 cascade group with three sessions, atomic approval/revert, assigned-teacher access, attendance lifecycle and correction, own attendance summary, all five reports, and announcement/notification recipient visibility. The temporary server, cluster, and verification script were stopped and removed; no Render database is provisioned.
- Phase 4/5 verification applied `0001_initial_schema` and `0002_login_attempts` to a temporary PostgreSQL 18 database, then exercised login, case-insensitive IDs, persistent throttling, roles, CSRF, user/profile creation, linked academic records, bounded projections, self-profile ownership, password-field rejection, teacher deactivation, and logout/current-session rejection. Temporary validation databases were stopped; no Render DB or project `DATABASE_URL` was retained.
- The workspace currently has no `.git` directory, so there is no Git commit/checkpoint. The source and this handoff are saved as ordinary project files.

## Source-of-truth order

For scope and requirements, use `PRD.md` and `PRD_PHASE_CROSSWALK.md`; for confirmed product choices use `PHASE_0_DECISIONS.md`; for schema behavior use `DATABASE_DESIGN.md`; for stage history use the append-only `logic.md`. If these disagree, investigate and report the mismatch rather than filling gaps from memory.
