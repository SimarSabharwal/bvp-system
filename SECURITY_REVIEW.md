# Security Review — Phase 9

**Date:** 2026-10-16  
**Scope:** Active Flask API, session authentication, route authorization, API projections, notification delivery, operational configuration, and role-specific interface contract.  
**Review type:** Source review plus local app/route checks and temporary PostgreSQL 18 integration. No production deployment or representative institutional database is configured; this is not a penetration test or production security certification.

## Access control reviewed

- Protected endpoints call the DB-backed identity helper, which reloads active status and role memberships on each request. The frontend cannot choose a role or record owner by submitting an ID.
- Student schedule and attendance summaries derive from the signed-in user's current enrollment/profile. Teacher schedule and attendance derive from the signed-in teacher profile and the session's currently assigned teacher. Admin/master-data and report operations require `ADMIN`.
- Teachers may access only their own teacher-availability records; they cannot manage room availability. Student notification/read state is filtered by the signed-in user ID. Announcement reads resolve role and current section membership.
- Cookie-authenticated writes require the session-bound CSRF header. Production requires an explicit secret and PostgreSQL URL, secure HTTP-only SameSite cookies, and now an eight-hour maximum signed-session lifetime. Request bodies are capped at 1 MiB; list/range limits remain server-side.
- WebSocket handshakes require a signed-in active account, validate browser Origin, and send only the caller's notification rows. The socket rechecks active account status each heartbeat and closes at the signed cookie's original eight-hour deadline. PostgreSQL wake-up payloads contain only a numeric outbox ID. Reconnection reads persisted recipient rows using the caller's notification cursor.
- WebSocket server ping/pong is enabled every 25 seconds; inbound messages are capped at 1 KiB. The app's cursor poll on heartbeat recovers persisted notifications if a process temporarily loses its PostgreSQL listener.

## Findings addressed in this phase

| Finding | Severity | Action |
|---|---|---|
| WebSocket cookie authentication lacked an Origin check, creating cross-site WebSocket hijacking risk in browsers. | High | Reject origins other than the request origin and configured `WEBSOCKET_ALLOWED_ORIGINS`; authentication and recipient filtering still apply. |
| Compact teacher lookups exposed faculty login codes to student and teacher roles without a workflow need. | Medium | Admin lookup retains the faculty code; student/teacher lookups return only display name, department, and internal display ID. |
| Signed browser sessions had no explicit maximum lifetime. | Medium | Make authenticated sessions permanent with an eight-hour configurable lifetime; active account/role state remains reloaded on each request. |
| API request body size was not explicitly bounded. | Medium | Add a configurable 1 MiB default Flask request cap. |

## Residual risks and deployment requirements

- Login lockout is keyed by normalized login ID. An attacker who knows a victim's identifier may deliberately trigger the configured temporary lock. Add provider/WAF-level IP and network throttling and monitoring before public launch; do not remove account-based throttling without an abuse-control replacement.
- A stolen signed cookie can be used until it expires unless the account is deactivated. Password reset, global session revocation, MFA, email verification, and account recovery are not implemented in this MVP scope.
- Configure `WEBSOCKET_ALLOWED_ORIGINS` with the exact production UI origin when UI and API have different hosts. Ensure the reverse proxy forwards the correct Host and TLS scheme and preserves WebSocket Upgrade headers.
- Role-specific API checks are present, but separate Student/Teacher/Admin screens have not been built; Phase 10 must follow `ROLE_ACCESS_MATRIX.md` and must not treat hidden navigation as authorization.
- Production secret rotation, database backup/restore execution, TLS/proxy behavior, and provider-level connection limits still need verification in the selected Render environment. No production credentials or service were available to this review.
- PostgreSQL delivery, outbox retry after an actual database failure, WebSocket reconnect under disconnect, several-hundred-user capacity, and the PRD's 2s/3s latency targets require live database and representative load evidence before Phase 9 can be marked complete.

## Review conclusion

The reviewed API has server-side role and ownership checks for the current MVP workflows, and the issues listed above were either corrected in Phase 9 or are explicit pre-deployment follow-ups. Mark this review as **Phase 9 implementation evidence only**, not a guarantee that the deployed system is secure under all conditions.

## Verification evidence

- Python compile and Flask app-factory/route registration passed; the OpenAPI operation audit matched every implemented HTTP API method with no undocumented or stale operations.
- Unauthenticated requests to protected student, teacher, admin, notification, and announcement routes returned 401. Admin and cross-role/ownership requests were denied in live PostgreSQL API checks; authorized role reads returned scoped data.
- A 1 MiB + 1 request body returned 413; readiness returned 503 without a configured database. Login role selection was checked against current memberships, including a multi-role account.
- Live PostgreSQL checks covered notification cursor ownership, dispatcher retry and recovery, concurrent `SKIP LOCKED` claims, and backup/restore to a fresh temporary database. Live WebSocket checks covered signed-session authentication, same-origin enforcement, recipient-only delivery, reconnect catch-up, cookie expiry, and deactivated-account closure.
- Temporary database, server, scripts, logs, and dump were disposable and have been removed. No production service or institutional dataset was accessed.
- Latest local synthetic benchmark ran the actual reallocation API against PostgreSQL 18 with 20 sections, 40 teachers, 20 rooms, 20 dated sessions, 5 requests, and 3 workers; all 5 returned 200 (p50 225.19 ms, p95 233.18 ms). The local WebSocket sample connected 100 authenticated synthetic users and delivered the committed notification to all 100 (p95 620.60 ms; maximum 628.29 ms). These localhost samples do not measure representative institutional traffic, production network/proxy conditions, or provider capacity, and do not support production capacity claims.
