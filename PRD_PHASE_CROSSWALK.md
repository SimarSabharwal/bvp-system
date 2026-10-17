# PRD-to-Implementation Phase Crosswalk

**Purpose:** Ensure every implementation phase has a traceable relationship to the PRD and that no in-scope requirement is silently dropped. Phase numbers in `IMPLEMENTATION_PLAN.md` are finer-grained engineering steps; they do not have to match the PRD milestone numbers one-to-one.

## Functional requirement coverage

| PRD requirement | Planned implementation phase(s) | Coverage note |
|---|---:|---|
| FR-1 User management | 3, 4, 5, 10 | Phase 3 provides the approved local demo seed; Phase 4 provides password/session auth, DB-backed roles, admin lifecycle and self profiles; Phase 5 provisions and links student/teacher profiles, enrollments, and scoped reads; frontend remains Phase 10. |
| FR-1.4–1.6 Role-specific access and interfaces | 4, 5, 8, 9, 10 | API returns current memberships; role/ownership enforcement is server-side; Phase 9 reviews the access matrix/security behavior; Phase 10 renders only the Student, Teacher, and Admin interfaces the account is entitled to use. Multi-role memberships remain supported. |
| FR-2 Student interface | 6, 8, 10 | Scoped timetable and attendance/notification APIs first; frontend last. |
| FR-3 Teacher interface | 6, 7, 8, 10 | Timetable/availability/reallocation/attendance APIs first; frontend last. |
| FR-4 Admin | 5, 6, 7, 8, 10 | Phase 5 delivers academic master-data and user/profile APIs. Timetable/calendar, policy, approval/report APIs follow in Phases 6–8; Phase 10 adds linked mock data and smart timetable creation. |
| FR-5 Timetable | 2, 6, 7, 10 | Normalized schema and hard constraints, timetable/session APIs, reallocation updates, then views; Phase 10 generates course/semester-matched drafts and reports required/excluded dates. |
| FR-6 Dynamic lecture reallocation | 2, 6, 7, 8, 9 | Database constraints, availability/session facts, candidate/approval engine, notifications, and hardening. FR-6.3 uses default cascade depth 1 and configurable maximum 2. FR-6.4 supports both suggest-and-approve and admin-configured auto-apply; approval is the default. |
| FR-7 Room reallocation | 2, 6, 7, 8, 10 | Room availability and overlap constraints, reallocation service, notifications, and admin-facing screens. |
| FR-8 Curriculum tracking | 2, 5, 7, 8, 10 | Phase 5 manages required-hour mappings; Phase 7 uses remaining required hours in reallocation priority/scoring; Phase 8 derives completed and remaining hours from completed sessions; screens remain Phase 10. |
| FR-9 Attendance | 2, 8, 10 | Session-linked schema and attendance/percentage APIs are complete; student/teacher screens remain Phase 10. |
| FR-10 Notifications and announcements | 2, 8, 9, 10 | Durable recipient notifications, read state, scoped announcement APIs, and outbox writes are complete in Phase 8; realtime delivery remains Phase 9 and UI remains Phase 10. |
| FR-11 Realtime updates | 8, 9, 10 | Persist events first; deliver over authenticated WebSockets with reconnect and polling recovery; connect clients last. |
| FR-12 Audit and history | 2, 7, 9, 10 | Durable history schema, transactional updates, retention/operations, then history views. |
| FR-13 Reports and analytics | 8, 10 | Bounded admin APIs cover attendance, workload/free gaps, room booked time, session status, and curriculum progress; screens remain Phase 10. |

## Implementation phase progress

| Implementation phase | PRD cross-check status |
|---|---|
| 0 — Decisions and data mapping | Complete for schema planning; production data import remains deferred. |
| 1 — Backend foundation | Complete; API infrastructure is in place and does not claim to deliver later auth/master-data features. |
| 2 — Database schema and migrations | Complete; PostgreSQL 18 applied migrations through `0004_subject_course`, which adds a course link and semester/catalog metadata to subjects; the existing six GiST overlap exclusions remain in force. |
| 3 — Seed and data migration | Complete for the approved local-demo scope; the normalized fixture passed preflight and two database runs preserved counts (3 users, 2 students, 1 teacher, 8 subjects, 3 roles, 1 policy). A forced late conflict rolled back cleanly. Legacy institutional import is deferred pending approved mappings. |
| 4 — Identity, authentication, authorization | Complete; signed Flask sessions store the user ID, roles/status reload from PostgreSQL, Werkzeug hashes are used, persistent lockout throttling is migrated, cookie writes require a session-bound CSRF header, and current student/teacher profile routes use the signed-in identity. Initial admin provisioning is interactive and never prints the password. |
| 5 — Academic master data APIs | Complete; admin management and bounded list/detail projections cover accounts/profiles, academic years, courses, sections, subjects, enrollments, curriculum links, qualifications, teaching assignments, rooms, and room features. Identity/profile rows are retained and deactivated rather than physically deleted. Compact role-authenticated lookups contain no student/credential records. PostgreSQL foreign keys/exclusions validate relationships. |
| 6 — Timetable, sessions, and availability APIs | Complete; live PostgreSQL verification created a validated draft, published it, generated the dated session, and confirmed compact scoped timetable routes, calendar/availability endpoints, and bounded free-slot queries. |
| 7 — Reallocation and pending lecture recovery | Complete; live PostgreSQL 18 verified a depth-2 grouped plan, atomic acceptance and revert, and per-member audit/outbox/notification writes. The configured auto-apply depth remains capped at 1 or 2; proposals beyond that limit require admin action. |
| 8 — Attendance, notifications, and reporting APIs | Complete for API scope; live PostgreSQL 18 verified the actual-session attendance lifecycle, enrollment validation, admin closed-session correction, excused exclusion, scoped announcements/notifications, and each bounded report. Realtime delivery and worker retries remain Phase 9. |
| 9 — Realtime and hardening | Partial; authenticated recipient-scoped WebSocket, notification cursor recovery, outbox dispatcher/retry, database readiness, connection bounds, role-security review, OpenAPI parity, and local synthetic benchmarks are implemented and verified. The latest localhost run delivered one committed notification to 100/100 authenticated synthetic WebSocket clients (p95 620.60 ms); reallocation API requests were 5/5 successful at 3 workers (p95 233.18 ms). Representative institutional concurrency/2s/3s acceptance evidence and selected-provider backup/restore/proxy verification remain open. |
| 10 — Frontend | Partial; existing role dashboards remain. Admin master data now has an opt-in linked mock-data loader, and Smart Timetable Creation configures shift windows, generates a conflict-checked draft per selected section, and reports required dates/calendar exclusions without auto-publishing. Data-backed browser walkthrough and publish/ownership acceptance remain open. Phase 9 production verification remains separate and partial. |

## Non-functional requirement coverage

| PRD requirement | Planned implementation phase(s) | Acceptance evidence |
|---|---:|---|
| Reallocation within 2 seconds | 7, 9 | Measure candidate generation against representative data; report measured latency. |
| Change notifications within 3 seconds | 8, 9 | Measure committed-event to connected-client delivery; fallback behavior remains available. |
| Zero teacher/section/room double-bookings | 2, 6, 7, 9 | PostgreSQL constraints plus transactional revalidation and concurrency checks. |
| Transactional reliability | 2, 7, 8 | Rollback leaves no partial schedule, attendance, audit, or outbox mutation. |
| Security and privacy | 1, 4, 5, 8, 9, 10 | Phase 9 verifies role/ownership boundaries, signed session expiry, CSRF, WebSocket Origin, bounded bodies/cursors, and safe error/log output. Phase 10 limits switcher to memberships returned by login and enforces API authorization on every call. Full role matrix is in `ROLE_ACCESS_MATRIX.md`. |
| Several hundred concurrent users | 1, 9 | Provider-aware pool configuration and representative load/performance assessment; not assumed from design alone. |
| Responsive usability | 10 | Partial; responsive cards, navigation, focus states, and reduced-motion support are implemented. Cross-width visual/assistive-technology acceptance and formal WCAG 2.1 AA audit remain pending. |
| Modular maintainability | 1, 6, 7, 8 | Separate API, service, policy, persistence, and event-delivery responsibilities. |
| Complete audit history | 2, 7, 9 | Verify each accepted/rejected/reverted schedule change has actor, reason, timestamp, and before/after state. |

## PRD milestone translation

| PRD milestone | Corresponding implementation phases |
|---|---:|
| 1. Foundation (auth, roles, master data, PostgreSQL schema) | 1, 2, 4, 5 |
| 2. Timetables | 2, 5, 6 |
| 3. Engine v1 | 2, 6, 7 |
| 4. Realtime | 8, 9, 10 |
| 5. Attendance | 2, 8, 10 |
| 6. Admin and reports | 5, 6, 7, 8, 10 |
| 7. Enhancements | Deferred by approved MVP scope; revisit after MVP acceptance. |

## Explicit scope alignment

- Keep QR attendance, advanced optimization/ML, native mobile apps, maps, and advanced analytics out of MVP as the PRD specifies.
- Use section-based schedules for MVP. Lab subgroups and cross-section shared lectures are deferred by the recorded product decision; reopen only through an explicit decision and corresponding schema/phase review.
- Suggest-and-approve is the initial reallocation policy; admin-configurable auto-apply remains supported to satisfy PRD FR-6.4.
- Phase 10 is the final implementation phase. By explicit project direction, frontend implementation proceeds against the existing locally verified API while Phase 9's representative-data and Render acceptance remains open; this does not mark Phase 9 complete or waive its production criteria.

## Phase completion check

Before a phase starts, confirm its planned tasks and exit criteria cover the assigned PRD references and do not conflict with current decisions. When a phase closes, record what is implemented, what evidence verifies it, and any accepted deferrals. Update this crosswalk if requirement ownership changes.
