# Student System — Final Implementation Plan

**Status (2026-10-16):** Phases 1–8 are complete for approved backend/API scope. Phase 9 remains partial pending representative load/performance and production deployment verification. Phase 10 implementation remains partial; authenticated Student, Teacher, and Admin dashboards now run locally against PostgreSQL, while mapped academic workflows remain open. Full legacy institutional import remains deferred until authoritative mappings are supplied.
**Order:** Database and backend first; frontend is the final implementation phase.  
**Scope:** PRD MVP: role-based access, academic data, schedules, reallocation, pending lecture recovery, attendance, notifications, audit, and basic reporting.

This plan consolidates `PRD.md`, `DATABASE_DESIGN.md`, and `TECH_STACK_TRD.md`. Requirement ownership for every implementation phase is tracked in `PRD_PHASE_CROSSWALK.md`. Phase numbers here break the PRD's broader milestones into reviewable implementation stages; check the crosswalk instead of assuming matching phase numbers mean matching scope.

## Guiding rules

- PostgreSQL is the source of truth. Remove in-memory dictionaries from runtime behavior only after the corresponding data is migrated and reviewed.
- Keep the app as a modular Flask monolith with versioned JSON endpoints under `/api/v1`.
- Each API call returns only the fields needed for that request. Use bounded date queries, focused database projections, and pagination; do not load whole tables or serialize complete ORM graphs.
- Keep planned recurring timetable entries separate from dated class sessions, and preserve original/current session assignments and the reallocation audit trail.
- Enforce hard scheduling constraints in PostgreSQL and in transactional service validation. Never accept a proposed change on the strength of scoring alone.
- Keep current HTML pages working while backend phases are underway. Build or connect frontend features only in the final phase.
- Use the PRD as product intent, but do not fabricate missing academic or room data from the sample data.

## Phase 0 — Confirm decisions and data mappings

**Purpose:** Resolve choices that change schema, hosting, or access behavior before writing migrations.

Decide and record:

1. Use Render for the Flask API Web Service and managed PostgreSQL 18 in the same region. Singapore is recommended; select exact region, paid plans, sizing, budget, retention, and backup policy before deployment.
2. Use `Asia/Kolkata`; supply academic-year dates and authoritative course/semester/section/enrollment/capacity records before production data import.
3. Treat all current sample records as demo-only. Do not guess room identity/capacity/type, faculty qualifications, or teaching assignments.
4. Use ERP ID/faculty code login identifiers and explicit multi-role memberships. Teachers can report unavailability; admins can enter/override it.
5. Default reallocations to suggest-and-approve, with admin-configurable auto-apply as PRD FR-6.4 requires. Exclude `EXCUSED` from attendance percentage denominator; only admins can correct closed sessions.
6. Generate dated sessions for each timetable version's full effective period when published, skipping holidays and exams. Keep sessions section-based; defer lab subgroups and cross-section shared lectures past MVP.

**Exit:** Complete for schema planning: provider direction, timezone, identity, attendance, reallocation, session-generation, and MVP timetable structure are recorded in `PHASE_0_DECISIONS.md`. Production records and deployment sizing remain deferred until authoritative data and budget/load requirements are available.

## Phase 1 — Backend foundation

**Build:**

- Introduce a Flask application factory and versioned API blueprints. The current project root contains planning artifacts and an `old version/` reference tree, not an active `app.py`; preserve that archived reference and keep UI migration in Phase 10.
- Add environment-based configuration for development, test, and production. Remove the hard-coded Flask secret before any deployed environment is created.
- Add PostgreSQL connection setup through SQLAlchemy 2.x and Psycopg 3, with request-scoped sessions and explicit transaction boundaries.
- Add standard API JSON error handling, request ID response/logging, API version prefix, and OpenAPI 3 contract location.
- Establish consistent timestamps/timezone rules and API response conventions.

**Exit:** Application starts from configuration without a hard-coded database or session secret; `/api/v1` can be registered independently from HTML routes.

## Phase 2 — Database schema and migrations

**Build:** Create the normalized tables in `DATABASE_DESIGN.md` as explicit Alembic migrations:

- users, roles, student/teacher profiles;
- academic years, courses, sections, enrollments, subjects, section curriculum;
- teacher qualifications and section teaching assignments;
- rooms, features, availability, calendar/exam blocks;
- timetable versions and recurring entries;
- dated class sessions and pending lectures;
- reallocations/audit history, attendance sessions/records, notifications, outbox.
- scheduling-policy configuration and targeted announcements, so PRD admin policy controls and student announcement requirements are represented explicitly.

Add foreign keys, unique/check constraints, indexes for scoped queries, and PostgreSQL exclusion constraints for overlapping sessions/timetable entries. Cross-table constraints must have documented transactional validation or database triggers. Include migration rollback strategy and ensure deploys never create/alter production tables implicitly.

**Exit:** Complete. A fresh PostgreSQL 18 database applied the Alembic migration and completed a live downgrade/re-upgrade cycle. All 29 application tables were created; the section, teacher, and room overlap guards rejected conflicting sessions while allowing adjacent intervals.

The initial revision is `migrations/versions/0001_initial_schema.py`. Run `python -m alembic upgrade head` with `DATABASE_URL` configured to apply it. A PostgreSQL server is required; do not substitute SQLite for validation of PostgreSQL range/exclusion behavior.

## Phase 3 — Seed and data migration

**Build:**

- Create a repeatable development seed command separate from application startup.
- Import `sample_data.json` only after the Phase 0 mapping is approved.
- Create demo credentials only for local development and hash them. Do not carry demo passwords into production.
- Do not import empty runtime registration dictionaries as real records.
- For real user data, provide a separate reviewed import with a row-level error report, duplicate detection, and a rollback/re-run procedure.

The current development-only command accepts the normalized, sample-derived local demo fixture at `data/dev_demo_seed.json`; it deliberately rejects the legacy `sample_data.json` shape until its institutional mappings are approved. Validate without database access using `python scripts/seed_dev.py --dry-run`. A database import requires explicitly setting `APP_ENV=development`, a development PostgreSQL `DATABASE_URL` with Phase 2 migrations already applied and a loopback host (`localhost`, `127.0.0.1`, or `::1`), and a local-only `DEMO_PASSWORD`; the command stores only Werkzeug hashes and wraps all inserts in one rollback-safe transaction. Inspect its JSON error report before addressing any import conflict.

**Exit:** Complete for the approved sample-derived local development seed. The seed is separate from startup, is loopback/development-only, stores only password hashes, validates row references, reports conflicts, and ran twice against PostgreSQL with stable persisted counts. A forced late conflict rolled back an earlier insert. No timetable references were imported. The legacy institutional sample remains explicitly deferred until Phase 0 mappings are approved.

## Phase 4 — Identity, authentication, authorization

**Build:**

- Add login/logout/current-user APIs backed by `users` and role/profile tables.
- Store only a user identifier in the secure browser session; load active roles and status from the database for authorization.
- Hash and verify passwords with Werkzeug; add account deactivation and admin provisioning path.
- Enforce role and ownership checks on every protected operation. Student endpoints resolve the student from the session, not a client-supplied ERP ID.
- Add cookie security and CSRF protections for cookie-authenticated write requests; set production-only secure cookie requirements.
- Define account/login throttling and safe authentication error responses.

**Implementation:** `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`, `GET /api/v1/auth/csrf`, and signed-in `/students/me` and `/teachers/me` endpoints. `scripts/create_admin.py` interactively provisions the initial active admin; subsequent users and role changes use admin APIs. Failed-login windows/locks persist in PostgreSQL.

**Exit:** No student/teacher can access another person's private records by changing a URL, body ID, or query parameter; admin-only operations reject other roles.

**Status (2026-10-16):** Complete. Live PostgreSQL-backed checks covered case-insensitive login, failure throttling, current role reload/deactivation, CSRF enforcement, self-only profiles, and role denial.

## Phase 5 — Academic master data APIs

**Build:** Admin APIs for courses, academic years, sections, students, teachers, subjects, curriculum mappings, teaching assignments, rooms, and room features. Add narrow read APIs for current user and lookup needs.

**Data retrieval requirements:**

- Support explicit filters and bounded pagination on collections.
- Return only requested list fields; expose full details through an individual resource endpoint only where needed.
- Keep write responses small and return resource IDs/status for follow-up reads.
- Never expose authentication internals or unrestricted student data to general lookup endpoints.

**Implementation:** `/api/v1/admin/{resource}` collections and resource detail/patch/delete endpoints cover user lifecycle, student/teacher profiles, academic years, courses, sections, subjects, student enrollments, curriculum mappings, qualifications, teaching assignments, rooms, and room features. `/api/v1/lookups/{resource}` exposes bounded compact course/section/subject/teacher/room/academic-year lists. User/profile creation hashes passwords and atomically writes role/profile records. User/profile history is retained; deactivate accounts instead of deleting identity records.

**Exit:** Master data can be managed without editing source code; teacher qualification and section curriculum mappings are queryable and valid.

**Status (2026-10-16):** Complete. Live PostgreSQL-backed checks created and queried related academic year/course/section/subject/enrollment/qualification/assignment/room records, enforced filters/pagination/field allowlists, and confirmed user password hashes are not selected or returned.

## Phase 6 — Timetable, sessions, and availability APIs

**Build:**

- CRUD draft timetable versions and entries; validate section, teacher assignment, curriculum subject, room type/capacity, time ranges, and recurring overlaps.
- Publish timetable versions with effective dates; retain archived schedules.
- Generate dated sessions according to the confirmed schedule generation policy; store source entry and immutable scheduled-value snapshots.
- Add availability and academic-event APIs; calculate free slots from sessions plus blocks.
- Add student/teacher timetable reads that accept a specific date or bounded range and use SQL projections for just session time/status and needed subject/teacher/room labels.

**Exit:** A request for one person's one-day schedule returns only that day's sessions and compact labels; invalid or conflicting schedules are rejected by service checks and database constraints.

**Implementation (2026-10-16):** Added draft version and entry create/read/update/delete, capacity/type/assignment/recurring-overlap validation, immutable publication, complete effective-period session generation with holiday/exam and resource-unavailability exclusions, teacher/admin availability create/read/update, academic events, student/teacher self-timetable projections, admin section/teacher/room projections, and interval-based free-slot reads. Capacity must be known to prove the hard capacity rule; unknown room/section capacity is rejected.

**Status:** Complete. Temporary PostgreSQL 18 integration verified migrations, entry creation, dated session generation, and role/session route registration. PRD FR-5.1–5.3 and Phase 6 exit are covered. The browser UI remains Phase 10.

## Phase 7 — Reallocation and pending lecture recovery

**Build:**

- Find affected dated sessions after teacher/room unavailability.
- Generate only candidates passing all hard constraints: teacher qualification/assignment, curriculum membership, resource availability, capacity/type, no exam block, and no section/teacher/room overlap.
- Rank valid candidates using configurable soft weights; expose concise candidate reasons.
- Add admin APIs for the reallocation mode, cascade limit, and scoring policy; default to suggest-and-approve and enforce cascade depth 1 by default, configurable up to 2.
- Create proposal, approve, reject, and revert workflows; suggest-and-approve is the default, and admins can configure auto-apply as required by PRD FR-6.4.
- Enforce configurable automatic cascade depth (default 1, maximum 2); require admin review beyond the configured limit.
- On acceptance, use one transaction to lock relevant rows, revalidate constraints, update the actual session, create/update pending lecture state, append reallocation history, and enqueue notifications.
- Recover pending lectures into later valid slots without duplicating the original lecture or marking recovery complete before the actual session is held.
- Return a clean conflict response if a concurrent change takes the slot; never silently overwrite.

**Exit:** Every accepted schedule change has complete before/after history; no invalid candidate can be applied; no-candidate cases go to admin review with reasons.

**Implementation (2026-10-16):** Added unavailable-resource analysis; constraint-checked and weighted teacher/room replacement proposals; section/institution approval or auto-apply policy; approval/rejection/revert; recovery-slot search, proposal, retry, and admin resolution; session row locking and stale-state checks; PostgreSQL constraint revalidation; audit history and transactional outbox events. No-candidate results cancel the affected occurrence into an OPEN pending lecture and retain an admin-review proposal. Added bounded recursive cascade planning through depth 2, parent-linked grouped proposals, atomic group approval/rejection/revert, configuration-aware auto-apply, and per-recipient schedule notifications.

**Status:** Complete. A live PostgreSQL 18 flow exercised a deliberately blocked depth-2 chain, verified three linked members, accepted all three atomically, reverted all three atomically, and confirmed schedule notifications, audit rows, and outbox events. Default suggest-and-approve and configurable auto-apply remain aligned with FR-6.4; when a proposal exceeds the configured automatic depth it is held for admin approval. No-candidate results create pending lectures and admin-review proposals. PRD FR-6.1–6.5, FR-7.1, and audit/history requirements are covered for the API scope. Notifications persist in the same transaction and delivery remains in Phase 9.

## Phase 8 — Attendance, notifications, and reporting APIs

**Build:**

- Open/close attendance sessions from actual dated class sessions and record one status per student per session.
- Enforce section membership and teacher assignment at write time; allow students to read only their own attendance.
- Compute subject and overall percentages from attendance records using focused SQL aggregates and the confirmed excused-absence policy.
- Persist notifications per recipient and use a transactional outbox for delivery retries.
- Add scoped announcement publishing and recipient reads with explicit audience, publish, and expiry rules.
- Add basic reports for attendance, teacher workload/free periods, room utilization, session status, and curriculum progress using bounded, role-protected queries.

**Exit:** Attendance always references the actual class session; duplicate records are rejected; a failed notification delivery does not undo a committed schedule change.

**Implementation (2026-10-16):** Added teacher/admin attendance open, roster, per-student mark/update, and close APIs tied to actual dated sessions and active enrollments; admin-only correction after close; audited changes and completion-linked pending recovery; derived student subject/overall percentages excluding EXCUSED from the denominator; recipient-owned notification pagination/read state; role/section-scoped announcement publishing/reads; and bounded admin reports for attendance, teacher workload/gaps, room booked time, session states, and curriculum hours. State changes enqueue outbox records transactionally.

**Status:** Complete for Phase 8 API scope. Temporary PostgreSQL 18 integration verified migrations, a depth-2 grouped reallocation and revert, attendance open/roster/mark/close/admin correction, the student-only percentage, notification ownership and announcement audience reads, and all five reports. OpenAPI and route registration were checked. Room utilization reports booked minutes and sessions; it withholds a percentage because institutional operating hours have not been supplied. Teacher free periods are gaps between scheduled sessions for the same reason. Realtime transport/outbox dispatch and retries remain Phase 9.

## Phase 9 — Realtime delivery and backend hardening

**Status:** Partial — implementation and local PostgreSQL/security verification are complete for the documented scope; representative latency/concurrency and production backup/proxy checks remain open.

**Implemented and verified:**

- Authenticated, recipient-scoped WebSocket events, reconnect cursors, persisted outbox dispatch/retries, and bounded polling recovery.
- Database readiness, safe operational logging, connection pool and socket caps, bounded requests, session expiry, and origin/CSRF checks.
- Student/Teacher/Admin access matrix and PRD/OpenAPI contract alignment; every implemented HTTP API operation is documented.
- Live PostgreSQL integration verified notification delivery and recipient scoping, dispatcher retry behavior, concurrent outbox claims, backup/restore, and active-account socket revocation.
- Latest local synthetic benchmark: 20 sections, 40 teachers, 20 rooms, 20 dated sessions; 5/5 reallocation API requests succeeded at 3 workers (p50 225.19 ms, p95/p99 233.18 ms; 7.61 requests/s). The instrumented pool high-water was 50 checked-out connections with pool size 50 and overflow 50 during the combined benchmark.
- Authenticated WebSocket fanout connected 100 synthetic users; all 100/100 received the committed notification, with p50 482.03 ms and p95 620.60 ms (maximum 628.29 ms). This used a local Werkzeug server and localhost PostgreSQL only; it does not measure Render networking, proxy behavior, production provider limits, or representative institutional schedule distribution, so it is baseline evidence only.

**Remaining before phase acceptance:**

- Add authenticated, recipient-scoped WebSocket timetable/notification events with reconnect cursors and bounded polling fallback. Persist events in the outbox to recover across connection interruptions.
- Add reconnect cursor/last-event handling and polling fallback.
- Add database backup/restore procedure, health/readiness endpoints, safe logs, connection pool settings, and production secret configuration.
- Verify PRD reallocation (<2s) and change-notification (<3s) targets with representative institutional data and production-like concurrency.
- Verify backup/restore, proxy/TLS/WebSocket settings, pool sizing, and provider limits in the selected Render environment.

**Exit:** Backend API behavior and error formats are stable; schema migrations and seed/import procedures are repeatable; API documentation covers the endpoints the frontend will call; representative performance and deployed operations meet the PRD targets.

## Phase 10 — Frontend (last implementation phase)

**Status:** Partial — the three authenticated role dashboards, local login/current identity, CSRF/logout, allowed route access, and cross-role denial have now been exercised against a disposable PostgreSQL database. Student and Teacher schedule data remains empty because the approved seed has no academic mappings; data-dependent schedule/attendance/availability/report workflows remain unverified. Phase 9 remains Partial pending representative-load and Render deployment checks.

**Implemented and verified:**

- Connected single-page interface to the versioned `/api/v1` backend, replacing legacy template globals with authenticated REST calls and real-time events.
- Delivered three distinct, responsive role interfaces (Student, Teacher, Admin) styled with modern glassmorphism aesthetic (`backdrop-filter: blur(16px)`, translucent cards, high-contrast palette designed for WCAG 2.1 AA; formal audit pending).
- Provided multi-role switcher in the header, strictly limited to memberships returned by `POST /auth/login` or `GET /auth/me`. Server-side endpoint authorization remains authoritative.
- Student interface: daily and weekly timetable views with lecture status pills, server-computed attendance summary and subject breakdown (excluding `EXCUSED` records from denominator), announcements, and notifications.
- Teacher interface: assigned schedule with automatic free period / gap detection, attendance management (open, student roster, mark status, close), and self-service unavailability reporting.
- Admin interface: system health/readiness metrics, master data creation/listing and account deactivation (users, students, teachers, courses, sections, subjects, rooms, academic years), timetable draft creation, load-by-ID, entry create/edit/remove and atomic publication, institutional auto-apply/depth policy, announcement publisher, and five report categories.
- Real-time WebSocket connection to the existing `/api/v1/ws/events` server route (OpenAPI path `/ws/events` under the `/api/v1` base) with automatic notification cursor tracking (`after_id`), exponential backoff reconnect, and polling fallback.
- Session-bound CSRF token retrieval (`GET /auth/csrf`) and header enforcement (`X-CSRF-Token`) for all state-changing writes.
- Informative loading skeletons, empty states, validation error banners, and session expiry dialogs.

**Remaining acceptance:** Complete schedule, attendance, availability, admin mutation, notification, and report browser workflows after approved academic mappings are available. Existing backend does not expose a timetable-version collection GET; the UI supports creation and load-by-ID rather than inventing a list endpoint. The API limits room utilization to booked minutes because operating hours are not configured. Phase 9 production acceptance remains separate and open.

**Phase 10 addition:** Subject records carry a course link and optional semester, curriculum version and subject type. Admin Master Data can load a development-only linked mock dataset (BCA/BBA CBCS 2026 Sem-I catalog from the attached PDF; literal `B` has clearly marked demo placeholder subjects). Smart Timetable Creation selects the academic year, courses, effective dates and weekdays; checks four lectures against the morning/afternoon windows; allocates qualified teachers and suitable rooms; checks resource overlap and known unavailable periods; reports required dates and calendar exclusions; and creates drafts only. Admin review and transactional publication remain separate.

## Completion criteria

- PostgreSQL is the single durable source of truth; runtime user and timetable state is no longer held only in Python dictionaries.
- The API has a documented, versioned contract and each call fetches only the required fields and rows.
- Teacher, section, and room double-bookings cannot be committed.
- Teachers cannot be assigned subjects they are not qualified/assigned to teach.
- Missed lectures remain tracked until recovered or explicitly resolved.
- Attendance is tied to actual class sessions and respects role/ownership access.
- Every schedule change is auditable and notifications are recoverable after delivery failures.
- Frontend implementation may proceed against locally verified backend/API contracts while Phase 9's external Render acceptance remains open by explicit project direction; that sequencing does not waive Phase 9 production checks or authorize a production launch claim.

## Work intentionally deferred

- QR attendance, advanced optimization/ML, cascade depth beyond the approved limit, native mobile apps, and advanced analytics.
- Auto-apply is disabled by default; it may be enabled through an explicit admin setting, consistent with PRD FR-6.4.
- Exact Render region/paid service sizing and production data import until deployment requirements and authoritative institutional mappings are supplied.
