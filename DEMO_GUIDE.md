# Authenticated Local Demo

## Open the demo

The local Flask app is running at <http://127.0.0.1:5050/>. It uses an isolated PostgreSQL 18 cluster bound to `127.0.0.1:55432` and the project migrations. PostgreSQL trusts connections on this loopback-only demo port; Student System accounts still require their hashed application passwords. Both the database files and application configuration are local-only and ignored by Git.

## Demo accounts

All accounts use the shared generated password in `reports/demo-credentials.txt`.

| Interface | Login ID |
|---|---|
| Student | `0251BCA001` |
| Student | `0251BCA101` |
| Teacher | `MKC` |
| Admin | `admin-demo` |
| Mock student | `MOCK-STU-01` through `MOCK-STU-09` |
| Mock teacher | `MOCK-TCH-011` through `MOCK-TCH-094` (IDs have gaps by section and subject) |

Each account has only its assigned server-side role. Sign out before signing into another account. The application still enforces role access on every API request.

## Mock academic dataset

The Admin Master Data section now has **Load linked mock data**. A synthetic dataset is already loaded in the local PostgreSQL demo: 3 courses (BCA, BBA, literal B), 9 sections (BCA: 1 morning + 1 afternoon; BBA: 3 morning + 3 afternoon; B: 1 morning), 14 subjects, 9 students, 48 teachers, and 9 classrooms. It also creates the academic year, enrollments, section curricula, teacher qualifications and teaching assignments needed by the schedule generator. Mock capacity values and identities are explicitly fictional. The local login IDs above share the existing password in `reports/demo-credentials.txt`.

For BCA/BBA, the imported subject codes/names are from Semester I, CBCS 2026 in the attached Winter 2026 examination timetable. Exam dates and exam slots were deliberately not imported as recurring class periods. B has four subjects with `[DEMO PLACEHOLDER]` in their names because no subject catalog for course B was supplied. Replace placeholders before using real institutional data.

The local demo database contains nine **unpublished** draft versions, covering 2026-10-19 through 2026-10-23 with four lectures per selected weekday for each section (180 recurring entries). They use 09:10 morning start, 13:15 latest morning end, 13:30 afternoon start, 16:30 latest afternoon end, and editable duration/break examples. The Admin can open each draft from **Smart Timetable Creation** and publish it only after review. No dated class sessions have been created yet.

The older sample-derived seed remains separate and unmodified; it still contains two original student profiles, one teacher login and eight subjects without authoritative academic mappings. Do not treat the synthetic mock dataset as institutional data.

These accounts and records are for local review only. Do not reuse their password, publish the local service, or deploy the local `.env` file.

## Restart and stop

To start the database after it has been stopped:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D '.local-demo-postgres' -l '.local-demo-postgres\postgres-server.log' -o "-h 127.0.0.1 -p 55432" start
```

Start the Flask app in a separate PowerShell window:

```powershell
& '.venv314\Scripts\python.exe' -m flask --app wsgi run --host 127.0.0.1 --port 5050 --no-reload
```

Stop Flask with `Ctrl+C`. Stop PostgreSQL with:

```powershell
& 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe' -D '.local-demo-postgres' stop -m fast
```

## Current phase limits

The role login, identity, CSRF/logout, route boundaries, and all three dashboards have been checked locally. Phase 10 remains partial until data-dependent workflows are verified with approved schedule/enrollment mappings. Phase 9 remains partial until representative load tests and the selected Render deployment's operations are verified.
