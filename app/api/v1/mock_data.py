"""Explicitly demo-only synthetic academic data loader."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from flask import abort, current_app, jsonify, request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash

from app.api.v1 import api_v1
from app.api.v1.auth import require_csrf, require_roles
from app.extensions import database
from app.models import (AcademicYear, Course, Room, Section, SectionSubject,
                        Student, StudentEnrollment, Subject, Teacher,
                        TeacherSubject, TeachingAssignment, User, UserRole)


FIXTURE = Path(__file__).resolve().parents[3] / "data" / "mock_catalog_winter_2026.json"


@api_v1.post("/admin/mock-data/seed")
def seed_mock_academic_data():
    """Create a linked, clearly labeled demo dataset; never available in prod."""
    require_roles("ADMIN")
    require_csrf()
    if current_app.config.get("APP_ENV") == "production":
        abort(404)
    payload = request.get_json(silent=True)
    allowed = {"academic_year_name", "starts_on", "ends_on", "demo_password"}
    if not isinstance(payload, dict) or set(payload) != allowed:
        abort(400, description="Provide a demo academic-year name, start/end dates, and a shared mock-account password.")
    teacher_count = 0
    try:
        year_start, year_end = date.fromisoformat(payload["starts_on"]), date.fromisoformat(payload["ends_on"])
    except (TypeError, ValueError):
        abort(400, description="Academic-year dates must be ISO dates.")
    year_name, password = payload["academic_year_name"], payload["demo_password"]
    if not isinstance(year_name, str) or not year_name.strip() or len(year_name) > 80 or year_start > year_end:
        abort(400, description="Provide a valid academic-year name and ordered dates.")
    if not isinstance(password, str) or not 12 <= len(password) <= 1024:
        abort(400, description="The mock-account password must be 12 to 1024 characters.")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    db = database.get_session()
    if db.scalar(select(AcademicYear.academic_year_id).where(AcademicYear.name == year_name.strip())):
        abort(409, description="That demo academic year already exists; choose another name rather than duplicating it.")
    codes = [row["code"] for row in fixture["courses"]]
    if db.scalar(select(Course.course_id).where(Course.code.in_(codes)).limit(1)):
        abort(409, description="A course code in this mock dataset already exists. Review Master Data before loading the demo set.")
    if db.scalar(select(User.user_id).where(User.login_id.like("MOCK-%")).limit(1)):
        abort(409, description="Mock accounts already exist. The demo seeder does not modify existing records.")
    try:
        academic_year = AcademicYear(name=year_name.strip(), starts_on=year_start, ends_on=year_end, status="PLANNED")
        db.add(academic_year)
        db.flush()
        course_rows = {row["code"]: Course(code=row["code"], name=row["name"]) for row in fixture["courses"]}
        db.add_all(course_rows.values())
        db.flush()
        subject_rows = {}
        for row in fixture["subjects"]:
            subject = Subject(course_id=course_rows[row["course_code"]].course_id, semester=row["semester"],
                curriculum_version=row["curriculum_version"], subject_type=row["subject_type"],
                code=row["code"], name=row["name"], requires_lab=False)
            db.add(subject)
            subject_rows[(row["course_code"], row["code"])] = subject
        db.flush()
        sections = []
        for index, row in enumerate(fixture["sections"], 1):
            section = Section(course_id=course_rows[row["course_code"]].course_id,
                academic_year_id=academic_year.academic_year_id, semester=1,
                section_code=row["section_code"], shift=row["shift"], capacity=40)
            db.add(section)
            db.flush()
            sections.append((section, row["course_code"], index))
        rooms = [Room(building="Mock Building", room_number=f"M-{index:02d}", capacity=50,
                      room_type="NORMAL", status="ACTIVE") for index in range(1, 10)]
        db.add_all(rooms)
        db.flush()
        for section, course_code, section_index in sections:
            user = User(login_id=f"MOCK-STU-{section_index:02d}", password_hash=generate_password_hash(password))
            db.add(user)
            db.flush()
            student = Student(user_id=user.user_id, erp_id=f"MOCK-STU-{section_index:02d}", full_name=f"Mock Student {section_index:02d}")
            db.add_all([UserRole(user_id=user.user_id, role="STUDENT"), student])
            db.flush()
            db.add(StudentEnrollment(student_id=student.student_id, section_id=section.section_id, starts_on=year_start, ends_on=year_end, status="ACTIVE"))
            for subject_index, subject in enumerate((value for (code, _), value in subject_rows.items() if code == course_code), 1):
                teacher_no = (section_index * 10) + subject_index
                teacher_user = User(login_id=f"MOCK-TCH-{teacher_no:03d}", password_hash=generate_password_hash(password))
                db.add(teacher_user)
                db.flush()
                teacher = Teacher(user_id=teacher_user.user_id, faculty_code=f"MOCK-TCH-{teacher_no:03d}",
                    full_name=f"Mock Teacher {teacher_no:03d}", department=course_code)
                db.add(teacher)
                db.flush()
                db.add_all([UserRole(user_id=teacher_user.user_id, role="TEACHER"),
                    SectionSubject(section_id=section.section_id, subject_id=subject.subject_id),
                    TeacherSubject(teacher_id=teacher.teacher_id, subject_id=subject.subject_id)])
                db.add(TeachingAssignment(teacher_id=teacher.teacher_id, subject_id=subject.subject_id,
                    section_id=section.section_id, starts_on=year_start, ends_on=year_end, status="ACTIVE"))
                teacher_count += 1
        db.commit()
    except IntegrityError:
        db.rollback()
        abort(409, description="Mock data conflicts with existing records. No partial demo dataset was saved.")
    return jsonify({"status": "created", "demo_only": True, "academic_year_id": academic_year.academic_year_id,
        "courses": len(course_rows), "sections": len(sections), "subjects": len(subject_rows),
        "students": len(sections), "teachers": teacher_count,
        "rooms": len(rooms), "login_id_prefixes": ["MOCK-STU-", "MOCK-TCH-"],
        "password_note": "The shared password was supplied by the admin and is stored only as a password hash."}), 201
