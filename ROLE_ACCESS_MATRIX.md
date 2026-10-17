# Role Access Matrix

This is the canonical authorization and interface map for the Student System MVP. The API is authoritative: hiding a control in a client never grants or removes permission. Role memberships are loaded from PostgreSQL on each protected request and checked together with record ownership/assignment. Login may return more than one role; a person can open each interface represented by their roles, while every API request remains independently authorized.

## Interface entry points

| Interface | Available when login returns | Default landing and primary areas |
|---|---|---|
| Student | `STUDENT` | `/students/me`; today's/weekly own-section timetable, own attendance, notifications, announcements |
| Teacher | `TEACHER` | `/teachers/me`; own timetable/free periods, own availability, assigned-session attendance, notifications, announcements |
| Admin | `ADMIN` | Admin dashboard; users/master data, academic calendar, timetable editor, room/teacher availability, reallocation queue/policy, attendance correction, reports, announcements |

When multiple roles are returned, show a role switcher limited to those roles. The login request may include `active_role`; the server accepts it only if it is among the account's current memberships and stores it as interface context, never as a substitute for endpoint authorization. Do not infer a role from an ERP ID or client-supplied user/profile ID. `GET /api/v1/auth/me` returns the caller's memberships and current interface context. A role switch changes the active interface only; it does not change the user's server-side memberships. The shared timetable endpoint accepts `view_as=STUDENT` or `view_as=TEACHER` for a multi-role account and rejects values the account does not hold.

## API access

All paths below are under `/api/v1`.

| Endpoint group | Student | Teacher | Admin | Ownership and scope |
|---|---:|---:|---:|---|
| `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`, `GET /auth/csrf` | Own account | Own account | Own account | Login returns only the authenticated user's ID and current role memberships. Writes require CSRF after login. |
| `GET /students/me` | Yes | No | No | Session-derived student profile/current enrollment only. |
| `GET /teachers/me` | No | Yes | No | Session-derived teacher profile only. Admin profile management is under `/admin`. |
| `GET /schedule/me` | Yes | Yes | No | Student schedule derives from own current enrollment; teacher schedule derives from own teacher profile. Date range is bounded. Multi-role users select a membership using `view_as`. |
| `GET /students/me/attendance` | Yes | No | No | Student's own aggregate only. |
| `POST /class-sessions/{id}/attendance/open`, `GET /teacher/class-sessions/{id}/attendance`, `PUT /attendance-sessions/{id}/records/{student_id}`, `POST /attendance-sessions/{id}/close` | No | Assigned teacher only | Yes | Teacher must be the current teacher on that actual session. Student records must belong to the session section and date. Closed-session correction is admin-only. |
| `GET /notifications`, `PUT /notifications/{id}/read` | Own | Own | Own | Recipient `user_id` is always taken from the session. |
| `GET /announcements` | Audience/section | Audience/section | All | Reads require published, unexpired, matching role/section audience. |
| `POST /admin/announcements` | No | No | Yes | Admin only; recipient set is resolved by server. |
| `GET /lookups/{resource}` | Yes | Yes | Yes | Compact academic lookup data only. Non-admin teacher lookup omits faculty login code. No student identities or account secrets. |
| `/admin/{resource}` master-data management | No | No | Yes | Admin only; bounded projections and server-side input allowlists. |
| `/admin/timetable-versions`, `/admin/timetable-entries`, `/admin/academic-events` | No | No | Yes | Admin only; writes require CSRF and relational/overlap validation. |
| `/admin/teacher-availability` | No | Own teacher rows | Yes | Teacher may create/read/change only their own unavailability; cannot submit a room block. Admin can manage all. |
| `/admin/room-availability` | No | No | Yes | Admin only. |
| `/admin/schedules`, `/admin/free-slots`, `/admin/scheduling-policy`, `/admin/reallocations`, `/admin/pending-lectures`, `/admin/reports` | No | No | Yes | Admin only; scoped/bounded queries and transaction revalidation. |
| `GET /health`, `GET /ready` | Public | Public | Public | No identity data. Readiness exposes only ready/not-ready and database dependency. |
| `WS /api/v1/ws/events` (OpenAPI path `/ws/events` under `/api/v1`) | Own recipient rows | Own recipient rows | Own recipient rows | Requires signed-in session cookie; rejects disallowed browser Origin. WebSocket sends only the caller's persisted notifications. Reconnect with `after_id`; REST cursor polling is the fallback. |

## Enforcement rules

- Unauthenticated protected requests return 401; authenticated requests lacking a required role or ownership relationship return 403 (or a non-disclosing 404 where resource existence is sensitive).
- Every cookie-authenticated state-changing HTTP request requires `X-CSRF-Token` from `GET /auth/csrf`. Login is exempt because no authenticated cookie exists yet.
- Production sessions use `Secure`, `HttpOnly`, `SameSite=Lax`, and an eight-hour maximum lifetime; production must supply `SECRET_KEY` and PostgreSQL configuration.
- WebSocket handshakes validate browser `Origin` against the request host or `WEBSOCKET_ALLOWED_ORIGINS`. Messages are invalidation/cursor data plus recipient-owned notification rows; no global outbox payload is broadcast.
- Field allowlists, date/range bounds, and page limits are server-side. Client-provided role, user ID, student ID, teacher ID, or section ID never establishes authority.
- The interface must handle 401, 403, expired session, and 409 conflict states without showing another role's navigation or data.

## Phase 10 acceptance

- A student login sees only the Student interface and can retrieve only the current student's records.
- A teacher login sees only the Teacher interface and can manage attendance only for sessions assigned to that teacher.
- An admin login sees the Admin interface and can access approved administrative actions.
- Multi-role login shows only interfaces corresponding to returned memberships; direct URL/API access is still checked by server authorization.
- Changing IDs in a URL, body, or query cannot expose another person's protected data.
