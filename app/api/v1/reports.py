"""Bounded administrative reports derived from source records."""
from __future__ import annotations

from flask import abort, jsonify, request
from sqlalchemy import case, func, select

from app.api.v1 import api_v1
from app.api.v1.auth import require_roles
from app.api.v1.scheduling import _date
from app.extensions import database
from app.models import (AttendanceRecord, AttendanceSession, ClassSession, Room,
                        Section, SectionSubject, Student, Subject, Teacher)

MAX_REPORT_DAYS = 31


def _range():
    start = _date(request.args.get("from"), "from")
    end = _date(request.args.get("to"), "to")
    if start > end or (end - start).days >= MAX_REPORT_DAYS:
        abort(400, description="Report range must be between 1 and 31 days.")
    return start, end


@api_v1.get("/admin/reports/attendance")
def attendance_report():
    require_roles("ADMIN")
    start, end = _range()
    section_raw = request.args.get("section_id")
    try:
        section_id = int(section_raw) if section_raw is not None else None
    except ValueError:
        abort(400, description="section_id must be an integer.")
    db = database.get_session()
    query = (select(Student.student_id, Student.erp_id, Student.full_name, Subject.code,
        Subject.name, func.count(AttendanceRecord.attendance_record_id).filter(
            AttendanceRecord.status != "EXCUSED").label("counted"),
        func.count(AttendanceRecord.attendance_record_id).filter(
            AttendanceRecord.status.in_(["PRESENT", "LATE"])).label("attended"))
        .join(AttendanceRecord, AttendanceRecord.student_id == Student.student_id)
        .join(AttendanceSession, AttendanceSession.attendance_session_id == AttendanceRecord.attendance_session_id)
        .join(ClassSession, ClassSession.class_session_id == AttendanceSession.class_session_id)
        .join(Subject, Subject.subject_id == ClassSession.current_subject_id)
        .where(AttendanceSession.status == "CLOSED", ClassSession.session_date.between(start, end)))
    if section_id is not None:
        query = query.where(AttendanceSession.section_id == section_id)
    query = query.group_by(Student.student_id, Student.erp_id, Student.full_name, Subject.code, Subject.name)
    rows = db.execute(query.order_by(Student.full_name, Subject.code).limit(501)).all()
    truncated = len(rows) > 500
    rows = rows[:500]
    return jsonify({"from": start.isoformat(), "to": end.isoformat(), "truncated": truncated,
        "items": [{"student_id": row.student_id, "erp_id": row.erp_id, "student_name": row.full_name,
            "subject_code": row.code, "subject_name": row.name, "counted_sessions": row.counted,
            "attended_sessions": row.attended,
            "percentage": round(row.attended * 100.0 / row.counted, 2) if row.counted else None}
            for row in rows]})


@api_v1.get("/admin/reports/teacher-workload")
def teacher_workload_report():
    require_roles("ADMIN")
    start, end = _range()
    db = database.get_session()
    rows = db.execute(select(Teacher.teacher_id, Teacher.faculty_code, Teacher.full_name,
        ClassSession.session_date, ClassSession.current_starts_at, ClassSession.current_ends_at,
        ClassSession.class_session_id).join(ClassSession,
        ClassSession.current_teacher_id == Teacher.teacher_id).where(
        ClassSession.session_date.between(start, end), ClassSession.status.notin_(["CANCELLED", "VOID"]))
        .order_by(Teacher.teacher_id, ClassSession.session_date, ClassSession.current_starts_at)
        .limit(5000)).all()
    teachers = {}
    for row in rows:
        key = (row.teacher_id, row.faculty_code, row.full_name)
        day = row.session_date.isoformat()
        teacher = teachers.setdefault(key, {"teacher_id": row.teacher_id, "faculty_code": row.faculty_code,
            "full_name": row.full_name, "scheduled_sessions": 0, "scheduled_minutes": 0,
            "days": {}})
        day_rows = teacher["days"].setdefault(day, [])
        duration = int((row.current_ends_at - row.current_starts_at).total_seconds() // 60)
        teacher["scheduled_sessions"] += 1
        teacher["scheduled_minutes"] += duration
        day_rows.append((row.current_starts_at, row.current_ends_at, row.class_session_id))
    result = []
    for teacher in teachers.values():
        days = []
        for day, sessions in sorted(teacher["days"].items()):
            gaps = []
            for previous, following in zip(sessions, sessions[1:]):
                if following[0] > previous[1]:
                    gaps.append({"starts_at": previous[1].isoformat(), "ends_at": following[0].isoformat(),
                                 "minutes": int((following[0] - previous[1]).total_seconds() // 60)})
            days.append({"date": day, "scheduled_sessions": len(sessions), "between_session_free_periods": gaps})
        teacher["days"] = days
        result.append(teacher)
    return jsonify({"from": start.isoformat(), "to": end.isoformat(),
        "items": result, "truncated": len(rows) >= 5000,
        "free_period_definition": "Gaps between the teacher's first and last scheduled sessions; institutional working hours are not configured."})


@api_v1.get("/admin/reports/room-utilization")
def room_utilization_report():
    require_roles("ADMIN")
    start, end = _range()
    db = database.get_session()
    rows = db.execute(select(Room.room_id, Room.building, Room.room_number,
        func.count(ClassSession.class_session_id).label("sessions"),
        func.coalesce(func.sum(func.extract("epoch", ClassSession.current_ends_at - ClassSession.current_starts_at) / 60), 0).label("minutes"),
        func.count(func.distinct(ClassSession.session_date)).label("days_used"))
        .outerjoin(ClassSession, (ClassSession.current_room_id == Room.room_id) &
            ClassSession.session_date.between(start, end) & ClassSession.status.notin_(["CANCELLED", "VOID"]))
        .where(Room.status == "ACTIVE").group_by(Room.room_id, Room.building, Room.room_number)
        .order_by(Room.building, Room.room_number).limit(501)).all()
    truncated = len(rows) > 500
    rows = rows[:500]
    return jsonify({"from": start.isoformat(), "to": end.isoformat(),
        "items": [{"room_id": row.room_id, "building": row.building, "room_number": row.room_number,
            "scheduled_sessions": row.sessions, "booked_minutes": int(row.minutes), "days_used": row.days_used}
            for row in rows], "truncated": truncated, "utilization_rate": None,
        "utilization_note": "Booked time is reported; a percentage is withheld until institutional working hours are configured."})


@api_v1.get("/admin/reports/sessions")
def session_status_report():
    require_roles("ADMIN")
    start, end = _range()
    db = database.get_session()
    rows = db.execute(select(ClassSession.status, func.count(ClassSession.class_session_id))
        .where(ClassSession.session_date.between(start, end))
        .group_by(ClassSession.status).order_by(ClassSession.status)).all()
    return jsonify({"from": start.isoformat(), "to": end.isoformat(),
        "counts": {status: count for status, count in rows}, "total": sum(count for _, count in rows)})


@api_v1.get("/admin/reports/curriculum-progress")
def curriculum_progress_report():
    require_roles("ADMIN")
    start, end = _range()
    db = database.get_session()
    completed_hours = func.coalesce(func.sum(case((ClassSession.status == "COMPLETED",
        func.extract("epoch", ClassSession.current_ends_at - ClassSession.current_starts_at) / 3600), else_=0)), 0)
    rows = db.execute(select(SectionSubject.section_id, Section.section_code, Subject.subject_id,
        Subject.code, Subject.name, SectionSubject.required_lecture_hours, SectionSubject.required_lab_hours,
        completed_hours.label("completed_hours"))
        .join(Section, Section.section_id == SectionSubject.section_id)
        .join(Subject, Subject.subject_id == SectionSubject.subject_id)
        .outerjoin(ClassSession, (ClassSession.section_id == SectionSubject.section_id) &
            (ClassSession.current_subject_id == SectionSubject.subject_id) &
            ClassSession.session_date.between(start, end))
        .group_by(SectionSubject.section_id, Section.section_code, Subject.subject_id,
            Subject.code, Subject.name, SectionSubject.required_lecture_hours, SectionSubject.required_lab_hours)
        .order_by(Section.section_code, Subject.code).limit(1001)).all()
    truncated = len(rows) > 1000
    rows = rows[:1000]
    items = []
    for row in rows:
        required = float(row.required_lecture_hours + row.required_lab_hours)
        completed = float(row.completed_hours)
        items.append({"section_id": row.section_id, "section_code": row.section_code,
            "subject_id": row.subject_id, "subject_code": row.code, "subject_name": row.name,
            "required_hours": required, "completed_hours": round(completed, 2),
            "remaining_hours": round(max(required - completed, 0), 2)})
    return jsonify({"from": start.isoformat(), "to": end.isoformat(), "items": items,
        "truncated": truncated,
        "completed_hours_note": "Only class sessions marked COMPLETED contribute; lab and lecture hours share a required-hours total in the MVP."})
