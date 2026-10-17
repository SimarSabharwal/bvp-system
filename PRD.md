# Product Requirements Document

## Real-Time Smart Academic ERP with Dynamic Lecture Reallocation

**Version:** 1.0 (Draft) | **Date:** 30 September 2026 | **Repo:** BVP-REALTIME-SYSTEM

---

## 1. Overview

### 1.1 Problem Statement

Academic timetables are static and respond poorly to disruptions such as faculty absence or room unavailability. The result: cancelled lectures, idle teachers, unused rooms, delayed syllabus completion and slow communication with students.

### 1.2 Product Vision

A real-time academic resource management platform that connects students, teachers, classrooms, timetables and attendance, and **dynamically reorganises the timetable** when a disruption occurs, so academic time is used rather than wasted.

### 1.3 Core Differentiator

When a teacher is unavailable, the system does **not** ask another teacher to teach that subject. It finds another valid lecture the affected section needs, taught by an available teacher **in their own subject**. The missed lecture becomes _Pending Reallocation_ and is rescheduled into a later valid slot.

### 1.4 What This Product Is Not

Not merely an attendance app, a generic college ERP, or a substitute-teacher tool. ERP and attendance features support the scheduling engine.

---

## 2. Goals and Success Metrics

|Goal|Metric|
|---|---|
|Reduce wasted lecture periods|% of disrupted slots recovered with a valid lecture (target ≥ 70%)|
|Recover missed lectures|% of pending lectures rescheduled within 7 days|
|Fast communication|Timetable change reaches users in < 3 seconds|
|Zero conflicts|0 teacher/room/section double-bookings|
|Better utilisation|Increase in room and teacher utilisation vs baseline|
|Reduced admin effort|Manual timetable edits per week (decrease)|
|Syllabus tracking|Completed vs required hours visible per subject|

**Secondary objectives:** automate timetable updates, maintain central attendance, keep full schedule history, track curriculum completion.

---

## 3. Users and Personas

|Persona|Needs|
|---|---|
|**Student** (e.g. Rahul, BCA Sem 3, Sec A)|Live timetable, change alerts, attendance %, announcements|
|**Teacher** (e.g. Dr. Sharma)|Own timetable, free periods, mark availability, run attendance, receive allocations|
|**Admin / Coordinator**|Manage master data, rules, approvals, reports, override reallocations|

---

## 4. Scope

### In Scope (MVP)

- Authentication and role-based access (Student, Teacher, Admin)
- Master data: courses, sections, subjects, teachers, classrooms
- Timetable management for sections, teachers and rooms
- Teacher availability and room availability
- Dynamic lecture reallocation (depth 1) and room reallocation
- Pending-lecture recovery
- Real-time updates and notifications
- Lecture-linked attendance (manual)
- Reallocation history / audit trail
- Basic reports

### Out of Scope for MVP (Later)

- QR attendance
- Cascading reallocation beyond depth 2
- Constraint-programming optimisation / ML
- Real-time classroom map, advanced analytics
- Native mobile apps

---

## 5. Functional Requirements

### 5.1 User Management (FR-1)

- FR-1.1 Users log in with role-based access.
- FR-1.2 Students are linked to course, semester and section; their timetable derives from the section.
- FR-1.3 Admin can create, edit and deactivate users.
- FR-1.4 Login returns the authenticated account's current role memberships and may accept an `active_role` only when it matches one of those memberships. The product provides separate Student, Teacher, and Admin interfaces; an account may enter only interfaces matching its memberships. Selecting or switching an interface never grants API permission.
- FR-1.5 Student records and attendance are self-only; a teacher can view their own schedule and manage availability/attendance only for their own assigned sessions; an admin can use the approved administrative workflows. Every API call enforces role and ownership on the server.
- FR-1.6 Users with multiple role memberships may switch among only those role interfaces. The server continues to enforce each endpoint's role and ownership rules regardless of the selected client interface.

### 5.2 Student Interface (FR-2)

- FR-2.1 View today's and weekly timetable.
- FR-2.2 See current and upcoming lecture with subject, teacher and room.
- FR-2.3 Lecture status shown: Completed, Ongoing, Upcoming, Changed, Cancelled.
- FR-2.4 Timetable updates live without reload.
- FR-2.5 View attendance: overall, subject-wise, percentage.
- FR-2.6 View notifications and announcements.

### 5.3 Teacher Interface (FR-3)

- FR-3.1 View today's and weekly timetable, subjects, groups and rooms.
- FR-3.2 Free periods clearly shown.
- FR-3.3 Mark self unavailable (date/time range, reason).
- FR-3.4 Start class and take attendance.
- FR-3.5 Receive notifications on new allocations and changes.

### 5.4 Admin (FR-4)

- FR-4.1 Manage students, teachers, subjects, courses, sections, classrooms.
- FR-4.1a Link each subject to its course and, when known, semester, curriculum version and subject type. A subject may enter a section curriculum only when its course and semester match.
- FR-4.2 Manage timetables, academic calendar and exam periods.
- FR-4.3 Manage teacher-subject-section mappings.
- FR-4.4 Configure scheduling and reallocation rules and weights.
- FR-4.5 Approve or reject reallocations that need review.
- FR-4.6 Generate reports.

### 5.5 Timetable (FR-5)

- FR-5.1 Separate **timetable entries** (planned) from **class sessions** (what actually happens).
- FR-5.2 Timetable views for section, teacher and classroom.
- FR-5.3 Free slots computed for teachers, sections and rooms.
- FR-5.4 Admin can generate conflict-checked draft timetables from selected academic-year courses and existing curricula, assignments, rooms, dates and weekdays. Four daily lectures must fit inside the morning 09:10–13:15 and afternoon 13:30–16:30 latest-end windows. Admin configures lecture and break durations for each shift.
- FR-5.5 The generator identifies required dates and dates/classes excluded by matching HOLIDAY or EXAM calendar events. It creates unpublished draft versions; admin reviews and publishes through the existing atomic session-generation workflow.

### 5.6 Dynamic Lecture Reallocation Engine (FR-6) — Core

**Trigger:** teacher marked unavailable.

**Algorithm:**

1. Identify affected sessions.
2. Find teachers free in that slot.
3. Filter to subjects each teacher teaches to the affected section (via `teacher_subjects`).
4. Confirm the subject is in the section's curriculum and has remaining required lectures.
5. Find a suitable room (capacity, type, status).
6. Check all hard constraints, including knock-on conflicts.
7. Score valid candidates and choose the best.
8. Apply the change, record history, notify.
9. Set the original lecture to **Pending Reallocation**.
10. If no valid candidate exists, mark **Admin Review** (or Cancelled if admin decides).

**Requirements:**

- FR-6.1 Never assign a teacher to a subject they don't teach.
- FR-6.2 If a moved lecture leaves its original slot empty, flag that session for reassessment; never duplicate a lecture unless one is genuinely required.
- FR-6.3 Maximum automatic cascade depth is configurable (default 1, max 2). Beyond that, require admin approval.
- FR-6.4 Provide a suggest-and-approve mode as well as auto-apply (admin setting).
- FR-6.5 Lecture recovery: when the original teacher is available, search for a slot where teacher, section and room are all free, and propose the pending lecture.

**Hard constraints**

- Teacher, section and room cannot be double-booked.
- Teacher only teaches assigned/qualified subject.
- Subject must be in the section's curriculum.
- Room capacity must fit the section; lab subjects need lab rooms.
- No overlap with exams; unavailable teachers/rooms cannot be allocated.

**Soft constraints (scored)**

- Minimise timetable changes; prefer existing classrooms and same building.
- Balance teacher workload.
- Prioritise subjects with more remaining/behind-schedule lectures.
- Avoid excessive consecutive lectures.
- Recover missed lectures quickly.

**Scoring**

```
Score = curriculum priority + subject backlog + teacher availability
      + room suitability + timetable compatibility
      - disruption penalty - workload penalty
```

Weights are admin-configurable.

### 5.7 Room Reallocation (FR-7)

- FR-7.1 When a room becomes unavailable, find a free room meeting capacity and type.
- FR-7.2 Update the session, notify students and teacher instantly.

### 5.8 Curriculum Tracking (FR-8)

- FR-8.1 Track required, completed and remaining hours per subject per section.
- FR-8.2 Completed count updates when a session is marked complete.
- FR-8.3 Data feeds the engine's scoring.

### 5.9 Attendance (FR-9)

- FR-9.1 Attendance sessions are created from the lecture (teacher, subject, section, room, date and time pre-filled).
- FR-9.2 Statuses: Present, Absent, Late, Excused.
- FR-9.3 Attendance follows the **actual** session, including reallocated ones.
- FR-9.4 Students see subject-wise and overall percentages.
- FR-9.5 _(Later)_ Expiring QR attendance tied to lecture ID, session ID and timestamp.

### 5.10 Notifications (FR-10)

- Events: lecture changed, room changed, teacher unavailable, new lecture allocated, attendance opened or recorded, timetable updated, lecture starting soon, announcement posted.
- FR-10.1 In-app real-time delivery; persisted for history and read state.
- FR-10.2 Messages are specific, e.g. "Your 10:00 DBMS lecture has moved. Java with Teacher B in Room 201."

### 5.11 Real-Time Updates (FR-11)

- Database change → backend → event → WebSocket → client UI update.
- Fallback to polling if the socket disconnects.

### 5.12 Audit and History (FR-12)

- Every reallocation stores: original, new, reason, time, initiator (system/admin), status (proposed/accepted/rejected/reverted).
- Original schedule is never overwritten.

### 5.13 Reports and Analytics (FR-13)

- Attendance (student, subject, trends), teacher workload and free periods, room utilisation, lectures scheduled/completed/reallocated/cancelled, subject hours progress.

---

## 6. Lecture State Model

```
SCHEDULED → STARTING SOON → ONGOING → COMPLETED

SCHEDULED → TEACHER UNAVAILABLE → REALLOCATION PENDING → REALLOCATED → ONGOING → COMPLETED

Other: ROOM CHANGE, CANCELLED, RESCHEDULED, ADMIN REVIEW
```

---

## 7. Data Model

**Tables:** users, students, teachers, courses, sections, subjects, teacher_subjects (teacher, subject, section), student_enrollments, classrooms, classroom_features, timetables, timetable_entries, class_sessions, teacher_availability, room_availability, reallocations, attendance_sessions, attendance_records, notifications, academic_calendar.

**Key entities**

|Entity|Key fields|
|---|---|
|Student|student_id, user_id, name, roll_number, course_id, semester, section_id|
|Teacher|teacher_id, user_id, name, department, email, status|
|Subject|subject_id, course_id, code, name, semester, curriculum_version, subject_type, required_lecture_hours, requires_lab|
|Classroom|classroom_id, building, room_number, capacity, room_type, status|
|TimetableEntry|entry_id, section_id, subject_id, teacher_id, classroom_id, day, start, end|
|ClassSession|session_id, entry_id, date, actual subject/teacher/room, state, reason|
|Reallocation|id, original session data, new data, reason, changed_at, status|
|AttendanceSession|session_id, lecture_id, teacher_id, subject_id, section_id, date, start, end|
|AttendanceRecord|record_id, session_id, student_id, status, timestamp|

**Enums:** room_type (NORMAL, COMPUTER_LAB, SCIENCE_LAB, SEMINAR_HALL, AUDITORIUM); room_status (AVAILABLE, OCCUPIED, MAINTENANCE, UNAVAILABLE).

The schema must be normalised; no single monolithic timetable table.

---

## 8. Non-Functional Requirements

|Area|Requirement|
|---|---|
|Performance|Reallocation result within 2 s for a typical college dataset; UI updates < 3 s|
|Correctness|Hard constraints enforced at the database and service levels|
|Reliability|Reallocation is transactional (all or nothing)|
|Security|Role-based access, hashed passwords, HTTPS, session/token expiry|
|Privacy|Students see only their own private records; teachers see only assigned sessions/sections and their own availability; admins use authorized administrative data|
|Scalability|Support several hundred concurrent users on a single deployment|
|Usability|Responsive UI for mobile browsers|
|Maintainability|Modular services; engine logic separate from routes|
|Auditability|Complete change history retained|

Security and privacy controls are defined in `ROLE_ACCESS_MATRIX.md`; it is the endpoint-level acceptance map for FR-1.4–1.6, FR-2, FR-3, and FR-4. Authentication returns the account's current database-backed role memberships. Users with multiple memberships can switch among those interfaces, but all data access remains subject to server-side role and ownership checks. Session cookies expire after eight hours, state-changing cookie-authenticated requests require CSRF validation, and browser WebSocket connections validate Origin.

---

## 9. Architecture

```
Frontend (HTML/CSS/JS → React later)
        ↓
Python backend (Flask / FastAPI)
  ├─ Timetable service
  ├─ Attendance service
  ├─ Notification service
  └─ Dynamic Scheduler (rule-based constraint engine)
        ↓
PostgreSQL
        ↓
WebSocket / real-time layer
```

Keep it a modular monolith. The existing repo (`app.py`, `templates/`, `static/`, Vercel deployment) is evolved rather than replaced. Note that Vercel's serverless model does not suit long-lived WebSockets, so plan a hosted realtime option (e.g. managed WebSocket/pub-sub service) or a different host for the backend.

---

## 10. API Outline (Draft)

|Endpoint|Purpose|
|---|---|
|`POST /auth/login`|Authenticate|
|`GET /auth/me`, `GET /students/me`, `GET /teachers/me`|Current role memberships and self profile|
|`GET /schedule/me`|Student own-section or teacher own timetable|
|`/admin/teacher-availability`|Teacher's own availability; admin may manage all|
|`/admin/room-availability`, `/admin/schedules`, `/admin/free-slots`|Admin resource availability and schedule projections|
|`/admin/reallocations/*`, `/admin/pending-lectures/*`|Admin candidate, decision, revert and recovery operations|
|`/class-sessions/{id}/attendance/*`, `/attendance-sessions/*`|Assigned teacher attendance; admins may manage/correct|
|`GET /students/me/attendance`|Student's own attendance summary|
|`GET /notifications`, `GET /announcements`|Signed-in user's notifications and authorized audience announcements|
|`WS /ws/events`|Authenticated recipient-scoped realtime notifications with cursor recovery|

The full role-to-endpoint authorization and interface map is maintained in `ROLE_ACCESS_MATRIX.md` and must stay aligned with the OpenAPI contract.

---

## 11. UI Screens

**Student interface:** Home (today's timetable with status), Weekly timetable, own Attendance, Notifications and authorized Announcements. **Teacher interface:** Dashboard (today, free periods), Weekly timetable, own Availability, attendance for assigned sessions, Notifications and authorized Announcements. **Admin interface:** Master data, Timetable editor, academic calendar, resource availability, Reallocation review queue, Rules and weights, attendance correction, Reports and Announcements. After login, show only interfaces present in the account's role memberships; multiple-role accounts can switch between those memberships.

The Admin console also provides **Smart Timetable Creation**. It uses records linked to the selected academic year and courses, creates one draft per section, allocates active qualified teachers and suitable rooms, checks repeating section/teacher/room conflicts and configured unavailability, and leaves publication for admin review.

---

## 12. Worked Example

Teacher A (DBMS) reports unavailable for BCA 3A at 10:00–11:00. Teacher B teaches Java to BCA 3A and is free, and Room 201 is free. The engine proposes Java, Teacher B, Room 201 at 10:00. DBMS is marked Pending Reallocation. Later the engine finds Wednesday 2–3 free for BCA 3A, Teacher A and Room 204, and proposes the DBMS recovery. Students and teachers are notified at each step. The Java session originally at 11:00 is flagged for reassessment rather than duplicated.

---

## 13. Milestones

|Phase|Deliverables|
|---|---|
|1. Foundation|Auth, roles, master data, PostgreSQL schema|
|2. Timetables|Section/teacher/room timetables, free-slot queries, student and teacher views|
|3. Engine v1|Availability, hard constraints, single-depth reallocation, pending lectures, history|
|4. Realtime|WebSockets, notifications|
|5. Attendance|Lecture-linked attendance and percentages|
|6. Admin and reports|Approval queue, rules, analytics|
|7. Enhancements|Recovery optimisation, cascade depth 2, QR attendance, room map|

---

## 14. Risks and Mitigations

|Risk|Mitigation|
|---|---|
|Chaotic cascading changes|Cap depth; admin approval beyond it|
|Inaccurate availability data|Simple teacher self-service; admin override|
|Engine finds no valid option|Fall back to Admin Review; show reasons|
|Vercel unsuited to WebSockets|Managed realtime service or alternative host|
|Scope creep|Freeze MVP scope above|
|Race conditions on concurrent changes|Transactions and row locking|

---

## 15. Open Questions

1. Is reallocation auto-applied or suggested for admin approval by default?
2. Who can mark a teacher unavailable: the teacher, the admin, or both?
3. Lead time: how late before a lecture can a change be made?
4. Should students be able to opt out of or contest a reallocated lecture?
5. Are lab batches (sub-groups of a section) required in the MVP?
6. Expected size: number of students, teachers, rooms, sections?
7. Are electives or shared lectures across sections supported?

---

## 16. Acceptance Criteria (MVP)

- No conflict of teacher, section or room can be produced by any operation.
- When a teacher is marked unavailable, a valid reallocation is proposed or the session goes to Admin Review.
- No teacher is ever assigned outside their own subject.
- Students and teachers see changes without refreshing.
- The Student, Teacher and Admin interfaces expose only their role's navigation, while all endpoint permissions and record ownership are independently enforced by the API.
- Smart timetable generation creates course/semester-matched, conflict-checked drafts within the selected shift windows and identifies calendar-excluded class dates before publication.
- Changing a user, student, teacher, session or section ID in a request cannot disclose data outside the caller's role and ownership scope.
- Original schedule and every change remain viewable in history.
- Pending lectures can be rescheduled into a valid slot.
- Attendance is recorded against the actual session held.
