# Student System — Technology Stack and Technical Requirements (Draft)

**Status (2026-10-16):** Phases 1–8 are complete for approved backend/API scope; Phase 9 remains partial pending representative performance and Render operations verification; Phase 10 remains partial after authenticated local role-dashboard/access checks, with data-dependent workflow verification still open.  
**Scope:** API, database, scheduling, data integrity, and the Phase 10 frontend client.  
**Basis:** `PRD.md`, `DATABASE_DESIGN.md`, and the current Flask implementation.

This document records the selected implementation stack and backend behavior. Phases 1–8 provide the Flask foundation, PostgreSQL schema, safe sample-derived development seed, role-aware cookie authentication, bounded academic master-data and timetable APIs, grouped reallocation/recovery, attendance, recipient notifications, announcements, and bounded reports. Phase 7 supports atomic cascades through depth 2; Phase 8 APIs are implemented and verified against temporary PostgreSQL 18. Realtime delivery/hardening remain Phase 9 and the frontend remains Phase 10. Full institutional data import and hosted deployment remain deferred.

Student, Teacher, and Admin are separate Phase 10 interfaces. An account may have multiple database-backed role memberships; login returns those memberships and the client may switch only among them. Every API remains independently guarded by current membership and record ownership. `ROLE_ACCESS_MATRIX.md` is the detailed route and interface contract.

## 1. Recommended stack

| Layer | Recommendation | Why |
|---|---|---|
| Frontend | Flask-served HTML/CSS with native ES modules and vanilla JavaScript; no Node.js or build step | Keeps the interface same-origin with the cookie-authenticated Flask API and avoids an extra runtime/deployment pipeline. |
| Language/runtime | Python 3.12+ | Keeps the existing Python application and is supported by the proposed libraries. Select and lock the exact runtime for the chosen host during implementation. |
| API framework | Flask 3.1.x, organized with an application factory and blueprints | Evolves the existing Flask app into a modular API without a framework rewrite. Flask documents blueprints for structuring larger applications and application factories for configurable instances. |
| API style | Versioned REST/JSON under `/api/v1` | Straightforward request/response model for the existing app and future clients; keeps business rules in backend services instead of browser code. |
| API schemas | Pydantic 2.x request/response models | Validate incoming fields and produce stable response shapes at the API boundary. Keep database models separate from public API schemas. |
| Database | Render managed PostgreSQL 18.x | Relational constraints, transactions, foreign keys, and range/exclusion constraints fit the scheduling and audit requirements. Keep the API and database in the same Render region. |
| ORM and SQL | SQLAlchemy 2.0.x | Explicit relational mappings and transaction/session control; use SQLAlchemy Core for database-specific constraints where useful. |
| DB driver | Psycopg 3.x | Current PostgreSQL adapter for Python; use its synchronous mode for the initial synchronous Flask API. |
| Schema migrations | Alembic 1.x | Version-controlled database schema changes linked to SQLAlchemy metadata. Every production schema change ships as a migration; do not use `create_all()` as deployment migration strategy. |
| Authentication | Existing Flask session model, hardened | Store the user ID in a secure, HTTP-only, same-site cookie; load current roles from the database for authorization so role changes take effect. Hash passwords with Werkzeug's password hashing helpers. |
| Background work / event delivery | PostgreSQL outbox table plus a worker after core transactions are stable | Ensures committed timetable/attendance changes can be delivered after commit and retried. Avoid making an external message broker a prerequisite for the first database-backed API. |
| Live update transport | WebSockets with reconnect handling and bounded polling fallback | The PRD calls for live updates, and Render supports WebSockets. Persist events in the outbox so reconnecting clients can recover missed updates. |
| Production serving | Render Web Service running Flask through Gunicorn, plus Render managed PostgreSQL 18 in the same region | Provider selected during Phase 0. Singapore is the recommended region for India; exact region and paid plan depend on deployment configuration, load, and budget. |
| API contract | OpenAPI 3.x document committed with the API | Gives clients a stable, reviewable contract independent of the frontend implementation. |

Use compatible patch releases and lock them in a dependency lock file when implementation starts. Do not mix major upgrades into feature work without a deliberate migration.

### Why retain Flask

The archived `old version/` application is Flask, and the PRD calls for evolving the product as a modular monolith. Flask supports JSON responses, blueprints, and application factories. The active project root had no application entry point at Phase 1 start, so the API foundation was added as a new package while the historical UI was left intact for the final integration phase. SQLAlchemy and Alembic provide the persistence and schema-evolution layer needed by later phases.

### Hosting and realtime constraint

Render is selected for the Flask API and PostgreSQL, replacing the PRD's provisional Vercel deployment direction for the backend. Use WebSockets for live updates with reconnect handling and bounded polling fallback because connections can end during deploys or instance replacement. Keep event persistence in the PostgreSQL outbox so transport interruptions do not lose committed changes. Render's free Postgres expires after 30 days and free services are for previews, not production; select paid service sizes after expected load and budget are established. See [Render Flask deployment](https://render.com/docs/deploy-flask), [Render Postgres](https://render.com/docs/postgresql-creating-connecting), [WebSockets](https://render.com/docs/websocket), and [free instance limitations](https://render.com/docs/free).

## 2. Backend shape

Keep a modular monolith. Route handlers should be thin and should not contain scheduling or attendance business rules.

```text
HTTP client
    ↓ JSON /api/v1
Flask blueprints (auth, students, teachers, timetable, admin)
    ↓ validate request and authorize role
Service layer (schedule, reallocation, attendance, notifications)
    ↓ short SQLAlchemy transaction
PostgreSQL
    ↓ committed outbox events
Worker / WebSocket publisher (later phase; bounded polling fallback)
```

Suggested package boundaries:

```text
app/
  __init__.py           application factory and blueprint registration
  config.py             environment-based settings
  extensions.py         SQLAlchemy engine/session setup
  models/               normalized persistence models
  api/v1/               request parsing, auth, response mapping
  schemas/              Pydantic request and response schemas
  services/             scheduling, attendance, reallocation, notifications
  policies/             role and resource access checks
migrations/             Alembic revisions
seed/                   explicit development/demo seed data
openapi.yaml            public API contract
```

The final structure can be adjusted during implementation, but route handlers should not directly mutate global dictionaries or bypass the service layer.

## 3. API requirements

### Contract conventions

- Prefix every endpoint with `/api/v1`.
- Use JSON request and response bodies for API routes; keep HTML routes only where the existing interface still needs them.
- Validate all path parameters, query parameters, and bodies before calling business logic.
- Return stable HTTP status codes and a consistent error shape, for example:

```json
{
  "error": {
    "code": "schedule_conflict",
    "message": "The teacher is already scheduled during this time.",
    "details": []
  }
}
```

- Use ISO 8601 dates/timestamps with explicit timezone handling. Store instants as `timestamptz`; interpret recurring local timetable times using institution timezone `Asia/Kolkata`.
- Paginate history, notifications, and report lists. Do not return unlimited collections by default.
- Never expose password hashes, session secrets, internal exception traces, or private student data to unauthorized users.
- Publish and update `openapi.yaml` with every API contract change.

### Fetch only the data the caller needs

The API must use **small, purpose-specific reads and responses**. A client request for today's timetable must not load every student, every week, attendance history, notifications, or full related database rows. This is a core requirement for the API, not a later optimization.

- Design endpoints around a user task or view, such as today's timetable, a date range, one attendance summary, or the next notification page.
- Require a date/range filter for timetable queries. Set a reasonable maximum range and reject unbounded requests.
- Select only the database columns needed for the response. Join only the related tables needed to supply display values such as subject name, teacher name, or room label. Avoid `SELECT *` and avoid serializing ORM models directly.
- Map database results to small response schemas. Do not return password/auth fields, internal audit details, or entire related objects by default.
- Return paginated/cursor-based collections for history, attendance records, notifications, and admin lists. Enforce a maximum page size.
- Fetch aggregates such as attendance percentages with a focused query; do not download every attendance row to compute one percentage in application memory.
- Avoid N+1 query patterns. Use explicit joins/projections or bounded eager loading for the exact relationships needed by the response.
- Keep response expansion opt-in only when a real caller needs it. Do not add a general `include=everything` behavior. If field selection is later required for bandwidth, document allowed fields per endpoint and enforce authorization before selection.
- For create/update calls, return the changed resource's ID, status, and the small set of fields the caller needs immediately. Provide a separate GET for any additional detail.
- Use `ETag`/conditional requests or a `changed_since` cursor for frequently refreshed data when useful, so unchanged records do not need to be resent.

Example: a student dashboard request should return only the selected date's sessions and the compact labels/statuses used in that view. It should not return the student's entire profile or all attendance records.

```http
GET /api/v1/students/me/timetable?date=2026-10-15
```

```json
{
  "date": "2026-10-15",
  "sessions": [
    {
      "session_id": "…",
      "starts_at": "2026-10-15T09:10:00+05:30",
      "ends_at": "2026-10-15T10:05:00+05:30",
      "subject": {"code": "JP", "name": "Java Programming"},
      "teacher": {"display_name": "Dr. …"},
      "room": {"label": "AK108"},
      "status": "UPCOMING"
    }
  ]
}
```

The server derives the student identity from the authenticated session; the client must not provide an ERP ID to choose whose private data is returned.

### Initial endpoint groups

| Group | Representative endpoints | Access |
|---|---|---|
| Auth | `POST /api/v1/auth/login`, `POST /api/v1/auth/logout`, `GET /api/v1/auth/me`, `GET /api/v1/auth/csrf` | Public login; authenticated session reads; CSRF header required on logout and other cookie-authenticated writes |
| Student self-service | `GET /students/me`, `/students/me/timetable`, `/students/me/attendance`, `/notifications`, and `/announcements` | Student profile, schedule, attendance, and notifications derive only from the authenticated user |
| Teacher self-service | `GET /teachers/me`, `/teachers/me/timetable`, `/teacher/class-sessions/{id}/attendance`, and availability APIs | Teacher profile derives from the signed-in identity; attendance requires the actual assigned teacher |
| Admin master data | Implemented `/api/v1/admin/{resource}` and detail route for users, profiles, academic years, courses, sections, subjects, curriculum/qualification links, enrollments, assignments, rooms, and features | Admin; field allowlists and bounded pagination |
| Timetable | `GET /sections/{id}/timetable`, admin draft/publish endpoints | Authenticated read; admin write |
| Reallocation | `POST /admin/reallocations/analyze`, `/admin/reallocations/{id}/decision`, and `/admin/reallocations/{id}/revert` | Proposal groups apply/reject/revert atomically; suggest-and-approve is default; auto-apply honors configured depth |
| Attendance | `POST /class-sessions/{id}/attendance/open`, `GET /teacher/class-sessions/{id}/attendance`, `PUT /attendance-sessions/{id}/records/{student_id}`, and `/attendance-sessions/{id}/close` | Assigned teacher/admin; students receive their own derived summary; admins alone correct closed sessions |
| Announcements and reports | `POST /admin/announcements`, `GET /announcements`, and `/admin/reports/{attendance,teacher-workload,room-utilization,sessions,curriculum-progress}` | Published announcement visibility is role/section scoped; report ranges are bounded and admin-protected |
| Event stream | Authenticated WebSocket (later phase) | Recipient-scoped; reconnect with a cursor and use bounded polling to recover missed events |

The OpenAPI contract is maintained in `openapi.yaml`; later phase routes must remain versioned under `/api/v1` and match that contract.

## 4. Data and transaction requirements

Use the normalized schema in `DATABASE_DESIGN.md` as the baseline. The following rules are mandatory:

1. All application-owned IDs use primary keys; business identifiers (ERP ID, faculty code, course code, room label) have explicit unique constraints.
2. Foreign keys are enabled and migrations create the constraints. Do not rely on application convention alone for referential integrity.
3. A class session cannot overlap another active session for the same section, teacher, or room. Enforce dated overlaps in PostgreSQL with exclusion constraints and half-open intervals. Add recurring timetable overlap constraints within the same timetable version and weekday.
4. A teacher can only be assigned to a subject when they are qualified, the subject belongs to the section curriculum, and an effective teaching assignment exists.
5. Room capacity/type, teacher and room availability, and exam blocks must be checked before a change is accepted.
6. Reallocation is one atomic transaction: lock relevant rows, validate constraints, change the dated session, create/update the pending lecture and history records, then enqueue notifications. Roll back the whole operation if validation fails.
7. Attendance records refer to the actual `class_session`; enforce one record per student per attendance session and verify the student belongs to that session's section.
8. Preserve timetable versions, session snapshots, and reallocation decisions. Corrections add history rather than silently replacing prior data.
9. Calculate attendance percentages, completed hours, and remaining hours from source records. Do not keep independent totals that can drift.
10. Use UTC for stored instants, but retain the institution's configured local timezone for recurring timetable interpretation and display.
11. API list/detail reads use scoped SQL projections and bounded result sets; do not load whole tables or serialize complete ORM graphs for small UI/API requests.

PostgreSQL exclusion constraints can prevent overlapping ranges. Rules that require checking related tables still need transactional service validation or database triggers; a normal `CHECK` constraint cannot enforce a cross-table rule.

## 5. Scheduling and reallocation behavior

### Reallocation workflow

1. Create or update a teacher unavailability range.
2. Find affected dated sessions in that range.
3. Build candidate teaching assignments for the affected section and time. Candidate subject must be in the section curriculum; the teacher must be qualified, assigned, free, and available.
4. Require an available suitable room, sufficient capacity, no exam block, and no overlapping section, teacher, or room session.
5. Rank only candidates that pass every hard constraint. Soft scoring may prefer lower disruption, suitable rooms, backlog recovery, and balanced workloads.
6. Record each proposed reallocation with its reason and before/after values. Use suggest-and-approve by default; allow admins to configure auto-apply as required by PRD FR-6.4.
7. In approval mode, apply only after approval; in auto-apply mode, apply only when the configured policy permits it. In either mode, update the session, pending lecture, audit history, and outbox atomically. Changes beyond the configured cascade limit require admin review.
8. If no candidate passes hard constraints, set the session to `ADMIN_REVIEW` and return candidate failure reasons suitable for an admin, without inventing a teacher or room.
9. When recovering a pending lecture later, validate teacher, section, room, availability, and conflicts again. Mark recovered only after the recovery session is accepted/created.

### Concurrency

Two admins or automation jobs can act on the same free slot at once. Before accepting a proposal, lock the affected session and relevant resource/slot rows, re-check availability, and rely on database constraints as the final guard. A collision must fail cleanly and return a conflict response; never overwrite a competing accepted change.

## 6. Security, privacy, and operations

- Read database URLs, Flask secret keys, and external service credentials from environment/secret management. Remove the hard-coded `app.secret_key` before the database-backed app is deployed.
- Hash passwords with a password hashing function; never log passwords or tokens. Require strong secret values and rotate them if exposed.
- Configure browser session cookies as `Secure`, `HttpOnly`, and `SameSite`; add CSRF protection for cookie-authenticated state-changing requests.
- Check role and record ownership on the server for every protected request. Students can read only their own enrollment, timetable, attendance, and notifications. Teachers can act only on their assigned sections/sessions unless admin policy grants more.
- Login returns current role memberships to select the eligible Student, Teacher, and/or Admin interface; client-side role selection never grants access. Multi-role accounts are supported.
- Use an eight-hour permanent signed-cookie lifetime, `Secure`/`HttpOnly`/`SameSite=Lax` production cookies, CSRF tokens on state-changing cookie-authenticated routes, a 1 MiB request-body cap, and WebSocket Origin validation. Production must configure the actual UI origins in `WEBSOCKET_ALLOWED_ORIGINS` when the UI is hosted on a separate origin.
- The socket emits only authenticated recipient-owned notifications. PostgreSQL `NOTIFY` payloads contain event IDs only; notification content is fetched from recipient-scoped rows. Reconnect uses the notification ID cursor and REST polling fallback.
- Use parameterized SQL through SQLAlchemy/Psycopg. Avoid string-built SQL for user-provided values.
- Keep PII out of routine logs. Log request ID, actor ID, operation, result, and error code; keep a separate restricted audit trail for sensitive changes.
- Use managed database backups and test restoration before production use. Keep migration/backup operations separate from normal API requests.
- Provide health/readiness endpoints that do not disclose secrets. Readiness should fail when required services such as PostgreSQL are unavailable.
- Set connection pool limits for the selected hosting provider and database connection limits. Do not open a new engine per request.

## 7. Non-functional targets from the PRD

| Area | Requirement |
|---|---|
| Reallocation latency | Produce a valid suggestion or admin-review outcome within 2 seconds for a typical college dataset. |
| Update delivery | Accepted schedule changes and notifications reach connected clients within 3 seconds when realtime delivery is enabled. |
| Scheduling correctness | Zero accepted teacher, section, or room double-bookings. Database constraints are the last line of defense. |
| Recovery | Track pending lectures and make them queryable until recovered, rejected, or explicitly cancelled by an authorized admin. |
| Availability | Failed notification delivery must not undo a committed schedule change; retry from the outbox. |
| Scale | Support several hundred concurrent users on one deployment, subject to load testing and selected provider limits. |
| Audit | Retain who proposed, approved, rejected, or reverted every schedule change, with timestamps and reasons. |
| Privacy | Enforce student/teacher data visibility by role and record ownership. |

These are acceptance targets, not proven performance claims. Measure them against a representative dataset and the selected hosting environment during implementation.

## 8. Delivery sequence

1. **Foundation:** app factory, config/secrets, PostgreSQL connection, SQLAlchemy models, first Alembic migrations, role-aware API error handling.
2. **Academic data:** courses, academic years, sections, enrollments, subjects, rooms, teacher qualifications, teaching assignments, explicit seed workflow.
3. **Read APIs:** student/teacher profiles and timetable views from persisted data; remove dependency on in-memory global dictionaries after migration is reviewed.
4. **Timetable correctness:** timetable versions, dated sessions, constraints, availability and exam blocks.
5. **Reallocation:** candidate service, proposal/review flow, atomic acceptance, pending lecture recovery, audit trail.
6. **Attendance:** attendance sessions and per-student records tied to dated sessions; derived summaries.
7. **Notifications:** durable notification records and transactional outbox; bounded polling first, then WebSockets with reconnect recovery.
8. **Reports and hardening:** reports, backup/restore process, concurrency checks, load/performance work, deployment-specific settings.

Do not migrate `sample_data.json` straight into production. It lacks confirmed academic year/course/semester/section relationships, room capacity/type, teacher contact data, and qualification/assignment mappings. Use it only for a development seed after those mappings are explicitly supplied.

## 9. Confirmed decisions and remaining setup

1. Render is selected for Flask and managed PostgreSQL 18. Choose the exact Singapore (recommended) or other region, paid service sizes, budget, retention, and backup policy before provisioning.
2. Institution timezone is `Asia/Kolkata`. Supply academic-year dates and authoritative course/semester/section/enrollment records before production imports.
3. Existing sample data is demo-only; room canonical mappings, capacity/type, teacher qualifications, and assignments must come from verified records.
4. Lab subgroups and cross-section shared lectures are deferred beyond MVP; session generation is section-based for the full published effective period, excluding holidays and exams.
5. Identity uses ERP ID/faculty code and supports multiple roles; availability can be reported by teachers and managed by admins; suggest-and-approve is the default with admin-configurable auto-apply per FR-6.4; excused attendance is excluded and closed-session corrections are admin-only.
6. Initial administrator provisioning is implemented as interactive `scripts/create_admin.py`; account creation, role membership, and deactivation are available through protected APIs. Email verification and password reset remain future requirements and are not claimed by Phases 4–5.

## 10. Official references

- [Flask application factories](https://flask.palletsprojects.com/en/stable/patterns/appfactories/) and [blueprints](https://flask.palletsprojects.com/en/stable/blueprints/)
- [SQLAlchemy ORM and transaction sessions](https://docs.sqlalchemy.org/en/20/orm/session.html)
- [Alembic migrations](https://alembic.sqlalchemy.org/en/latest/)
- [Psycopg 3 documentation](https://www.psycopg.org/psycopg3/docs/)
- [Pydantic validation models](https://docs.pydantic.dev/latest/concepts/models/)
- [Werkzeug password hashing helpers](https://werkzeug.palletsprojects.com/en/stable/utils/#security-helpers)
- [Render Flask deployment](https://render.com/docs/deploy-flask), [Render PostgreSQL](https://render.com/docs/postgresql-creating-connecting), [Render WebSockets](https://render.com/docs/websocket), and [free service limitations](https://render.com/docs/free)
- [Flask cookie security settings](https://flask.palletsprojects.com/en/stable/web-security/#set-cookie-options)
- [PostgreSQL range types and exclusion constraints](https://www.postgresql.org/docs/current/rangetypes.html)
- [PostgreSQL constraints](https://www.postgresql.org/docs/current/ddl-constraints.html)
