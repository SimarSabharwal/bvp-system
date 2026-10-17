"""Session-linked attendance capture and derived student summaries."""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from flask import abort, current_app, jsonify, request
from sqlalchemy import case, func, select
from sqlalchemy.exc import IntegrityError

from app.api.v1 import api_v1
from app.api.v1.auth import current_identity, require_csrf, require_roles
from app.extensions import database
from app.models import (AttendanceRecord, AttendanceSession, AuditEvent, ClassSession,
                        Notification, OutboxEvent, PendingLecture, Student,
                        StudentEnrollment, Subject, Teacher)

STATUSES = {"PRESENT", "ABSENT", "LATE", "EXCUSED"}


def _commit(db):
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        abort(409, description="Attendance changed concurrently or violates session enrollment rules.")


def _manage_attendance(db, roles, user, class_session):
    if "ADMIN" in roles:
        return True
    if "TEACHER" not in roles:
        abort(403, description="Only the assigned teacher or an administrator may manage attendance.")
    teacher_id = db.scalar(select(Teacher.teacher_id).where(Teacher.user_id == user.user_id))
    if teacher_id is None or teacher_id != class_session.current_teacher_id:
        abort(403, description="Only the teacher assigned to this actual session may manage attendance.")
    return False


def _local_date(value):
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        abort(400, description="Dates must use YYYY-MM-DD format.")


@api_v1.post("/class-sessions/<int:class_session_id>/attendance/open")
def open_attendance(class_session_id):
    (user, roles) = current_identity()
    require_csrf()
    db = database.get_session()
    scheduled = db.scalar(select(ClassSession).where(
        ClassSession.class_session_id == class_session_id).with_for_update())
    if scheduled is None:
        abort(404)
    _manage_attendance(db, roles, user, scheduled)
    if scheduled.status != "SCHEDULED":
        abort(409, description="Attendance can only be opened for a scheduled actual session.")
    exists = db.scalar(select(AttendanceSession.attendance_session_id).where(
        AttendanceSession.class_session_id == class_session_id))
    if exists:
        abort(409, description="Attendance has already been opened for this class session.")
    attendance = AttendanceSession(class_session_id=class_session_id, section_id=scheduled.section_id,
                                   status="OPEN", opened_by=user.user_id)
    db.add(attendance)
    db.flush()
    enrolled_users = db.scalars(select(Student.user_id).join(StudentEnrollment,
        StudentEnrollment.student_id == Student.student_id).where(
        StudentEnrollment.section_id == scheduled.section_id,
        StudentEnrollment.status.in_(["ACTIVE", "ENDED"]),
        StudentEnrollment.starts_on <= scheduled.session_date,
        (StudentEnrollment.ends_on.is_(None) |
         (StudentEnrollment.ends_on >= scheduled.session_date))))
    for recipient_id in enrolled_users:
        db.add(Notification(user_id=recipient_id, event_type="ATTENDANCE_OPENED",
            title="Attendance is open", message="Attendance is now being recorded for your class session.",
            related_session_id=scheduled.class_session_id))
    db.add(OutboxEvent(event_type="ATTENDANCE_OPENED", aggregate_type="attendance_session",
                       aggregate_id=str(attendance.attendance_session_id),
                       payload={"class_session_id": class_session_id, "section_id": scheduled.section_id,
                                "subject_id": scheduled.current_subject_id}))
    _commit(db)
    return jsonify({"attendance_session_id": attendance.attendance_session_id,
                    "class_session_id": class_session_id, "status": attendance.status}), 201


@api_v1.get("/teacher/class-sessions/<int:class_session_id>/attendance")
def attendance_roster(class_session_id):
    user, roles = current_identity()
    db = database.get_session()
    scheduled = db.get(ClassSession, class_session_id)
    if scheduled is None:
        abort(404)
    _manage_attendance(db, roles, user, scheduled)
    attendance = db.scalar(select(AttendanceSession).where(
        AttendanceSession.class_session_id == class_session_id))
    if attendance is None:
        abort(404, description="Attendance is not open for this session.")
    rows = db.execute(select(Student.student_id, Student.erp_id, Student.full_name,
                             AttendanceRecord.status, AttendanceRecord.marked_at)
        .join(StudentEnrollment, StudentEnrollment.student_id == Student.student_id)
        .outerjoin(AttendanceRecord, (AttendanceRecord.student_id == Student.student_id) &
                   (AttendanceRecord.attendance_session_id == attendance.attendance_session_id))
        .where(StudentEnrollment.section_id == scheduled.section_id,
               StudentEnrollment.status.in_(["ACTIVE", "ENDED"]),
               StudentEnrollment.starts_on <= scheduled.session_date,
               (StudentEnrollment.ends_on.is_(None) | (StudentEnrollment.ends_on >= scheduled.session_date)))
        .order_by(Student.full_name, Student.student_id).limit(501)).all()
    truncated = len(rows) > 500
    rows = rows[:500]
    return jsonify({"attendance_session_id": attendance.attendance_session_id,
                    "class_session_id": class_session_id, "status": attendance.status,
                    "items": [{"student_id": row[0], "erp_id": row[1], "full_name": row[2],
                               "attendance": row[3], "marked_at": row[4].isoformat() if row[4] else None}
                              for row in rows], "truncated": truncated})


@api_v1.put("/attendance-sessions/<int:attendance_session_id>/records/<int:student_id>")
def mark_attendance(attendance_session_id, student_id):
    user, roles = current_identity()
    require_csrf()
    data = request.get_json(silent=True)
    if not isinstance(data, dict) or set(data) != {"status"} or not isinstance(data.get("status"), str) or data["status"] not in STATUSES:
        abort(400, description="status must be PRESENT, ABSENT, LATE, or EXCUSED.")
    db = database.get_session()
    attendance = db.scalar(select(AttendanceSession).where(
        AttendanceSession.attendance_session_id == attendance_session_id).with_for_update())
    if attendance is None:
        abort(404)
    scheduled = db.scalar(select(ClassSession).where(
        ClassSession.class_session_id == attendance.class_session_id).with_for_update())
    if scheduled is None:
        abort(409, description="The linked class session is missing.")
    admin = _manage_attendance(db, roles, user, scheduled)
    if attendance.status != "OPEN" and not admin:
        abort(409, description="Closed attendance can only be corrected by an administrator.")
    enrollment = db.scalar(select(StudentEnrollment).where(
        StudentEnrollment.student_id == student_id,
        StudentEnrollment.section_id == attendance.section_id,
        StudentEnrollment.status.in_(["ACTIVE", "ENDED"]),
        StudentEnrollment.starts_on <= scheduled.session_date,
        (StudentEnrollment.ends_on.is_(None) |
         (StudentEnrollment.ends_on >= scheduled.session_date))).with_for_update())
    if enrollment is None:
        abort(422, description="Student was not actively enrolled in this session's section on its date.")
    record = db.scalar(select(AttendanceRecord).where(
        AttendanceRecord.attendance_session_id == attendance_session_id,
        AttendanceRecord.student_id == student_id).with_for_update())
    old_status = record.status if record else None
    if record is None:
        record = AttendanceRecord(attendance_session_id=attendance_session_id, student_id=student_id,
            section_id=attendance.section_id, enrollment_id=enrollment.enrollment_id,
            status=data["status"], marked_by=user.user_id)
        db.add(record)
    else:
        record.status = data["status"]
        record.enrollment_id = enrollment.enrollment_id
        record.marked_by = user.user_id
        record.marked_at = datetime.now(timezone.utc)
    db.add(AuditEvent(actor_id=user.user_id, entity_type="attendance_record",
        entity_id=f"{attendance_session_id}:{student_id}",
        action="CORRECTED" if old_status and attendance.status == "CLOSED" else "RECORDED",
        details={"class_session_id": scheduled.class_session_id,
                 "previous_status": old_status, "status": data["status"]}))
    student_user_id = db.scalar(select(Student.user_id).where(Student.student_id == student_id))
    db.add(Notification(user_id=student_user_id, event_type="ATTENDANCE_RECORDED",
        title="Attendance recorded", message=f"Your attendance was recorded as {data['status']}.",
        related_session_id=scheduled.class_session_id))
    db.add(OutboxEvent(event_type="ATTENDANCE_RECORDED", aggregate_type="class_session",
        aggregate_id=str(scheduled.class_session_id),
        payload={"student_id": student_id, "status": data["status"]}))
    _commit(db)
    return jsonify({"attendance_session_id": attendance_session_id, "student_id": student_id,
                    "status": data["status"], "marked_at": record.marked_at.isoformat()})


@api_v1.post("/attendance-sessions/<int:attendance_session_id>/close")
def close_attendance(attendance_session_id):
    user, roles = current_identity()
    require_csrf()
    db = database.get_session()
    attendance = db.scalar(select(AttendanceSession).where(
        AttendanceSession.attendance_session_id == attendance_session_id).with_for_update())
    if attendance is None:
        abort(404)
    scheduled = db.scalar(select(ClassSession).where(
        ClassSession.class_session_id == attendance.class_session_id).with_for_update())
    if scheduled is None:
        abort(409, description="The linked class session is missing.")
    _manage_attendance(db, roles, user, scheduled)
    if attendance.status != "OPEN":
        abort(409, description="Attendance is already closed.")
    if scheduled.current_ends_at > datetime.now(timezone.utc):
        abort(409, description="Attendance cannot close before the actual session end time.")
    eligible = db.scalar(select(func.count(StudentEnrollment.enrollment_id)).where(
        StudentEnrollment.section_id == scheduled.section_id,
        StudentEnrollment.status.in_(["ACTIVE", "ENDED"]),
        StudentEnrollment.starts_on <= scheduled.session_date,
        (StudentEnrollment.ends_on.is_(None) |
         (StudentEnrollment.ends_on >= scheduled.session_date)))) or 0
    marked = db.scalar(select(func.count(AttendanceRecord.attendance_record_id)).where(
        AttendanceRecord.attendance_session_id == attendance_session_id)) or 0
    if marked != eligible:
        abort(409, description=f"Attendance needs one status for every enrolled student before closing ({marked}/{eligible} recorded).")
    now = datetime.now(timezone.utc)
    attendance.status = "CLOSED"
    attendance.closed_at = now
    scheduled.status = "COMPLETED"
    if scheduled.pending_lecture_id:
        pending = db.scalar(select(PendingLecture).where(
            PendingLecture.pending_lecture_id == scheduled.pending_lecture_id).with_for_update())
        if pending and pending.state == "SCHEDULED":
            pending.state = "RECOVERED"
    db.add(OutboxEvent(event_type="ATTENDANCE_CLOSED", aggregate_type="attendance_session",
        aggregate_id=str(attendance_session_id),
        payload={"class_session_id": scheduled.class_session_id, "section_id": scheduled.section_id}))
    _commit(db)
    return jsonify({"attendance_session_id": attendance_session_id, "status": attendance.status,
                    "class_session_status": scheduled.status})


@api_v1.get("/students/me/attendance")
def my_attendance_summary():
    user, roles = current_identity()
    if "STUDENT" not in roles:
        abort(403, description="This summary is available to students only.")
    raw_from, raw_to = request.args.get("from"), request.args.get("to")
    if (raw_from is None) != (raw_to is None):
        abort(400, description="Provide both from and to, or neither.")
    institution_today = datetime.now(ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])).date()
    first = _local_date(raw_from) if raw_from else institution_today
    last = _local_date(raw_to) if raw_to else first
    if first > last or (last - first).days > 365:
        abort(400, description="Attendance range must be between 1 and 366 days.")
    db = database.get_session()
    student_id = db.scalar(select(Student.student_id).where(Student.user_id == user.user_id))
    if student_id is None:
        abort(404, description="Student profile was not found.")
    denominator = func.count(AttendanceRecord.attendance_record_id).filter(AttendanceRecord.status != "EXCUSED")
    attended = func.count(AttendanceRecord.attendance_record_id).filter(
        AttendanceRecord.status.in_(["PRESENT", "LATE"]))
    pct = case((denominator == 0, None), else_=attended * 100.0 / denominator)
    q = (select(Subject.subject_id, Subject.code, Subject.name, denominator.label("counted"),
                attended.label("attended"), pct.label("percentage"))
         .join(ClassSession, ClassSession.current_subject_id == Subject.subject_id)
         .join(AttendanceSession, AttendanceSession.class_session_id == ClassSession.class_session_id)
         .join(AttendanceRecord, AttendanceRecord.attendance_session_id == AttendanceSession.attendance_session_id)
         .where(AttendanceRecord.student_id == student_id, AttendanceSession.status == "CLOSED",
                ClassSession.session_date.between(first, last))
         .group_by(Subject.subject_id, Subject.code, Subject.name)
         .order_by(Subject.code).limit(100))
    rows = db.execute(q).all()
    total = sum(row.counted for row in rows)
    total_attended = sum(row.attended for row in rows)
    return jsonify({"from": first.isoformat(), "to": last.isoformat(),
        "overall": {"counted_sessions": total, "attended_sessions": total_attended,
                    "percentage": round(total_attended * 100.0 / total, 2) if total else None},
        "subjects": [{"subject_id": row.subject_id, "code": row.code, "name": row.name,
                      "counted_sessions": row.counted, "attended_sessions": row.attended,
                      "percentage": round(float(row.percentage), 2) if row.percentage is not None else None}
                     for row in rows]})
