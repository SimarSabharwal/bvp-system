# Backend Operations Runbook

## Readiness and process health

- `GET /api/v1/health` checks only that the API process responds.
- `GET /api/v1/ready` checks that PostgreSQL accepts a `SELECT 1`; it returns 503 when the database is not configured or cannot be reached. Keep provider health checks on the liveness endpoint and use readiness for traffic routing.
- Application logs include request IDs and error types, not request bodies, credentials, SQL parameters, or notification contents. Restrict access to database and provider logs.

## Realtime service

Run the Flask service with a WebSocket-capable Gunicorn configuration and proxy. Configure the host/proxy to preserve HTTP Upgrade headers and allow long-lived WebSocket connections. Flask-Sock documents Gunicorn as a supported production server and supports ping/pong keepalive; this app enables 25-second keepalives and limits inbound socket messages to 1 KiB. Each app process uses one PostgreSQL `LISTEN` connection regardless of its number of WebSocket clients. `WS_MAX_CONNECTIONS` is a per-process cap; size it together with the worker count and database connection allowance.

Run one or more outbox dispatchers alongside the web service:

```powershell
python scripts/dispatch_outbox.py
```

The dispatcher claims due rows with `FOR UPDATE SKIP LOCKED`. It publishes only a payload-free notification ID through PostgreSQL `NOTIFY`; recipient data stays in the notification table and is fetched through the authenticated socket or `GET /api/v1/notifications?after_id=...`. Marking an outbox event delivered and issuing `NOTIFY` share one transaction. A failure rolls back both, records only the exception class, and retries with exponential backoff up to five minutes. Clients reconnect with their last notification ID; the socket replays missed recipient rows before listening for new wake-ups and polls the cursor at the heartbeat interval to recover during listener reconnects. Each heartbeat also revalidates the active user and enforces the cookie's original eight-hour expiry. REST polling by `after_id` is the bounded fallback and reconnect recovery path.

The dispatcher can process one batch for deployment checks:

```powershell
python scripts/dispatch_outbox.py --once
```

Start the dispatcher as a separate supervised process. Do not run it as an unmonitored Flask request or inside every Gunicorn worker.

## Database backup and restore

Use PostgreSQL client tools compatible with the managed PostgreSQL major version. Store backups encrypted with access limited to designated operators; never commit a backup or print a connection URL.

Create a custom-format backup before a schema migration and on the institution's approved retention schedule:

```powershell
$env:BACKUP_FILE = "student-system-$(Get-Date -Format yyyyMMdd-HHmmss).dump"
pg_dump --format=custom --no-owner --file $env:BACKUP_FILE $env:DATABASE_URL
```

Restore a backup into a newly created, empty recovery database first. Validate the restored schema, migration head, login, schedule reads, and a representative notification/attendance query before pointing any service at it:

```powershell
pg_restore --no-owner --exit-on-error --dbname $env:RESTORE_DATABASE_URL $env:BACKUP_FILE
```

For an approved recovery, switch the service to the validated database URL, restart the API and dispatcher, and confirm `/api/v1/ready`. Preserve the prior database until the recovery is accepted. For a bad migration, restore to a separate database and direct the service to that recovered copy; do not attempt destructive in-place repair on the only backup. Record backup timestamp, database identifier, restore validation, and operator in the institution's operations record.

Before applying migrations, take a verified backup and run `python -m alembic upgrade head` as a controlled release step. Application startup never creates or changes tables implicitly.

## Capacity and performance evidence

Set `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT`, `DB_POOL_RECYCLE`, and `WS_MAX_CONNECTIONS` for the selected provider and worker count. `WS_MAX_CONNECTIONS` applies per process; WebSocket fanout uses one listener connection per process, while notification reads borrow the normal bounded SQLAlchemy pool. Do not infer support for several hundred concurrent users from configuration values. Measure on a representative, approved dataset and selected production service size. The Phase 9 targets are: common reallocation analysis under 2 seconds and committed change notifications delivered to connected users within 3 seconds. Record dataset shape, request concurrency, percentile latency, errors, and pool pressure with every capacity result.

For an isolated local synthetic baseline only, apply migrations to a disposable local PostgreSQL database named `phase9_bench`, then run:

```powershell
python scripts/benchmark_phase9.py --database-url $env:DATABASE_URL --sections 20 --requests 5 --workers 3
```

Add `--ws-clients 100` (up to 300) to open distinct signed-in synthetic users and measure one outbox notification fanout to those connected local clients. The script refuses non-loopback hosts or any database name other than `phase9_bench`, writes a JSON report under `reports/`, and labels its results as non-production evidence. It exercises the actual reallocation API through Flask's test client and the WebSocket endpoint through a local Werkzeug server. It does not model Render networking, provider limits, or representative institutional traffic. Do not use it as the Phase 9 production acceptance run.
