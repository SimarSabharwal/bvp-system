# Phase 0 — Decisions and Data Mapping

**Status:** Complete for schema planning; production data mapping/import is deferred until real institutional records are supplied.
**Purpose:** Resolve schema-critical choices and map existing sample data without inventing institutional facts.

## Verified current data

The current Flask app/sample data contains two demo student accounts (`0251BCA001`, morning shift; `0251BCA101`, afternoon shift), one faculty login (`MKC`), nine faculty name codes, nine subject codes, and 50 timetable entries including 10 breaks. Room labels include AK108, UG104, FF LAB, 108, and 109. The data does not establish the academic year/course/semester/section mapping, real student enrollments, room capacities/types, faculty qualifications, or formal teaching assignments. Treat all of it as demo data; do not import it as production data or carry over its placeholder passwords.

## Confirmed decisions

| Area | Decision |
|---|---|
| Database and deployment provider | Render for the Flask API Web Service and managed PostgreSQL 18, in the same region. Singapore is the recommended region for proximity to India, but the exact region and paid service plans remain deployment choices. Do not use free Render Postgres for production; its free database expires after 30 days. |
| Backend serving | Flask API served with Gunicorn on Render. Local development may use local PostgreSQL. |
| Institution timezone | `Asia/Kolkata`. Store instants as `timestamptz`; interpret recurring timetable wall-clock times in this timezone. |
| Academic mappings and sample data | Existing student/timetable records are demo data only. Keep unknown course/year/section/room/faculty mappings explicitly unmapped until authoritative records are provided. |
| Login identifiers and roles | Student ERP ID and faculty code are login identifiers. A user may have multiple explicit role memberships. |
| Availability | Teachers may report their own unavailability; admins may enter or override it. |
| Reallocation | Suggest-and-approve is the default mode. Per PRD FR-6.4, admins may configure auto-apply; include explicit mode configuration and retain approval workflows. |
| Attendance | `EXCUSED` is excluded from the attendance percentage denominator. Only admins may correct attendance after a session is closed. |
| Dated class generation | On timetable publication, generate dated sessions for the full version effective period, skipping holidays and exam periods. |
| MVP timetable structure | Section-based sessions. Lab subgroups and shared lectures across sections are deferred beyond MVP. |

## Deferred, non-blocking items

- Exact Render region, service tier, sizing, expected load, budget, retention, and backup policy must be selected before deployment provisioning.
- Production seed/import awaits real course, academic-year, semester, section, enrollment, room, qualification, and assignment records. This does not prevent designing the schema or implementing a clearly separated development seed.
- Academic-year dates and the institution calendar must be provided as data before publishing a real timetable; the timezone and generation behavior are decided.

## Phase 0 exit checklist

- [x] Database and hosting provider direction recorded.
- [x] Institution timezone recorded; academic-year dates remain supplied calendar data.
- [x] Existing sample records explicitly restricted to demo-only use pending verified mappings.
- [x] Unknown room identities/capacities/types explicitly left unmapped rather than guessed.
- [x] Identity, role, availability, reallocation, attendance, lab/shared-lecture, and session-generation policies recorded.
- [x] No schema-critical behavior choice remains implicit.

Do not create production records from the demo sample or provision deployment resources until real mappings, service plans, and operational requirements are reviewed.
