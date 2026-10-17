"""Validated, idempotent importer for normalized local development fixtures."""

from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AcademicYear,
    Course,
    Section,
    Student,
    StudentEnrollment,
    Subject,
    SectionSubject,
    Teacher,
    TeacherSubject,
    TeachingAssignment,
    Room,
    User,
    UserRole,
    TimetableVersion,
    TimetableEntry,
    SchedulingPolicy,
)


class SeedInputError(ValueError):
    """Input validation error with one or more row-level findings."""

    def __init__(self, errors: list[dict[str, str]]) -> None:
        self.errors = errors
        super().__init__(f"Seed input has {len(errors)} validation error(s)")


def load_seed(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise SeedInputError([{"row": str(path), "message": str(error)}]) from error
    if not isinstance(payload, dict):
        raise SeedInputError([{"row": "$", "message": "Expected a JSON object."}])
    if payload.get("format") != "student-system-dev-seed-v1":
        raise SeedInputError([{
            "row": "$.format",
            "message": "Expected normalized student-system-dev-seed-v1 input. Legacy sample_data.json needs an approved mapping first.",
        }])
    return payload


def validate_seed(payload: dict[str, Any]) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    if payload.get("purpose") != "sample-derived-local-demo-only":
        errors.append({"row": "$.purpose", "message": "Only sample-derived local demo fixture data is accepted."})
    groups = (
        "academic_years", "courses", "subjects", "sections", "rooms", "students",
        "teachers", "admins", "timetable_versions",
    )
    for group in groups:
        if not isinstance(payload.get(group), list):
            errors.append({"row": f"$.{group}", "message": "Expected a list."})
    if errors:
        return errors

    required_fields = {
        "academic_years": ("name", "starts_on", "ends_on", "status"),
        "courses": ("code", "name"),
        "subjects": ("code", "name", "requires_lab"),
        "sections": ("course_code", "academic_year", "semester", "section_code", "shift", "capacity", "subject_codes"),
        "rooms": ("building", "room_number", "capacity", "room_type", "status"),
        "students": ("login_id", "erp_id", "full_name"),
        "teachers": ("login_id", "faculty_code", "full_name", "subject_codes"),
        "admins": ("login_id",),
        "timetable_versions": ("section_code", "name", "status", "effective_from", "effective_to", "entries"),
    }
    for group, fields in required_fields.items():
        for index, row in enumerate(payload[group]):
            if isinstance(row, dict):
                for field in fields:
                    if field not in row or row[field] is None:
                        errors.append({"row": f"$.{group}[{index}].{field}", "message": "Required field is missing."})
    if errors:
        return errors

    def ensure_unique(group: str, key_fields: tuple[str, ...]) -> None:
        seen: set[tuple[Any, ...]] = set()
        for index, row in enumerate(payload[group]):
            if not isinstance(row, dict):
                errors.append({"row": f"$.{group}[{index}]", "message": "Expected an object."})
                continue
            key = tuple(row.get(field) for field in key_fields)
            if any(value is None or not isinstance(value, (str, int)) or isinstance(value, bool) for value in key):
                errors.append({"row": f"$.{group}[{index}]", "message": f"Missing unique key: {', '.join(key_fields)}."})
                continue
            if key in seen:
                errors.append({"row": f"$.{group}[{index}]", "message": f"Duplicate key {key!r}."})
            seen.add(key)

    for group, fields in (
        ("academic_years", ("name",)), ("courses", ("code",)), ("subjects", ("code",)),
        ("sections", ("academic_year", "course_code", "semester", "section_code")),
        ("rooms", ("building", "room_number")), ("students", ("erp_id",)),
        ("teachers", ("faculty_code",)), ("admins", ("login_id",)),
        ("timetable_versions", ("section_code", "name")),
    ):
        ensure_unique(group, fields)
    ensure_unique("sections", ("section_code",))

    student_logins = [row.get("login_id") for row in payload["students"] if isinstance(row, dict)]
    teacher_logins = [row.get("login_id") for row in payload["teachers"] if isinstance(row, dict)]
    admin_logins = [row.get("login_id") for row in payload["admins"] if isinstance(row, dict)]
    all_logins = student_logins + teacher_logins + admin_logins
    valid_logins = [value for value in all_logins if isinstance(value, str) and value]
    if len(valid_logins) != len(all_logins) or len(valid_logins) != len(set(valid_logins)):
        errors.append({"row": "$.users", "message": "Login IDs must be unique across students, teachers, and admins."})

    def string_keys(group: str, field: str) -> set[str]:
        return {row[field] for row in payload[group] if isinstance(row, dict) and isinstance(row.get(field), str)}

    years = string_keys("academic_years", "name")
    courses = string_keys("courses", "code")
    subjects = string_keys("subjects", "code")
    sections = string_keys("sections", "section_code")
    faculty = string_keys("teachers", "faculty_code")
    rooms = {(row.get("building"), row.get("room_number")) for row in payload["rooms"] if isinstance(row, dict) and isinstance(row.get("building"), str) and isinstance(row.get("room_number"), str)}

    def reference(ok: bool, path: str, message: str) -> None:
        if not ok:
            errors.append({"row": path, "message": message})

    for i, row in enumerate(payload["academic_years"]):
        if not isinstance(row, dict):
            continue
        try:
            start, end = date.fromisoformat(row["starts_on"]), date.fromisoformat(row["ends_on"])
            if start > end:
                raise ValueError("starts_on must be on or before ends_on")
        except (KeyError, TypeError, ValueError) as error:
            errors.append({"row": f"$.academic_years[{i}]", "message": f"Invalid date range: {error}"})
        if row.get("status") not in {"PLANNED", "ACTIVE", "COMPLETED"}:
            errors.append({"row": f"$.academic_years[{i}].status", "message": "Unknown academic-year status."})
    for group, allowed in (
        ("sections", {"MORNING", "AFTERNOON", "EVENING"}),
        ("rooms", {"NORMAL", "COMPUTER_LAB", "SCIENCE_LAB"}),
    ):
        field = "shift" if group == "sections" else "room_type"
        for i, row in enumerate(payload[group]):
            if isinstance(row, dict) and row.get(field) not in allowed:
                errors.append({"row": f"$.{group}[{i}].{field}", "message": f"Unknown value: {row.get(field)!r}."})
    for i, row in enumerate(payload["sections"] + payload["rooms"]):
        if isinstance(row, dict) and (not isinstance(row.get("capacity"), int) or isinstance(row.get("capacity"), bool) or row["capacity"] <= 0):
            group = "sections" if i < len(payload["sections"]) else "rooms"
            row_index = i if group == "sections" else i - len(payload["sections"])
            errors.append({"row": f"$.{group}[{row_index}].capacity", "message": "Capacity must be a positive integer in local development input."})
    for i, row in enumerate(payload["sections"]):
        if not isinstance(row, dict):
            continue
        reference(isinstance(row.get("course_code"), str) and row["course_code"] in courses, f"$.sections[{i}].course_code", "Unknown course code.")
        reference(isinstance(row.get("academic_year"), str) and row["academic_year"] in years, f"$.sections[{i}].academic_year", "Unknown academic year.")
        if not isinstance(row.get("subject_codes"), list):
            errors.append({"row": f"$.sections[{i}].subject_codes", "message": "Expected a list."})
        else:
            if any(not isinstance(code, str) for code in row["subject_codes"]):
                errors.append({"row": f"$.sections[{i}].subject_codes", "message": "Subject codes must be strings."})
            elif len(row["subject_codes"]) != len(set(row["subject_codes"])):
                errors.append({"row": f"$.sections[{i}].subject_codes", "message": "Duplicate subject code."})
            for j, code in enumerate(row["subject_codes"]):
                reference(isinstance(code, str) and code in subjects, f"$.sections[{i}].subject_codes[{j}]", f"Unknown subject code: {code!r}.")
    for i, row in enumerate(payload["students"]):
        if isinstance(row, dict):
            if row.get("section_code") is not None:
                reference(isinstance(row.get("section_code"), str) and row["section_code"] in sections, f"$.students[{i}].section_code", "Unknown section code.")
    for i, row in enumerate(payload["teachers"]):
        if not isinstance(row, dict):
            continue
        if not isinstance(row.get("subject_codes"), list):
            errors.append({"row": f"$.teachers[{i}].subject_codes", "message": "Expected a list."})
        else:
            if any(not isinstance(code, str) for code in row["subject_codes"]):
                errors.append({"row": f"$.teachers[{i}].subject_codes", "message": "Subject codes must be strings."})
            elif len(row["subject_codes"]) != len(set(row["subject_codes"])):
                errors.append({"row": f"$.teachers[{i}].subject_codes", "message": "Duplicate subject code."})
            for j, code in enumerate(row["subject_codes"]):
                reference(isinstance(code, str) and code in subjects, f"$.teachers[{i}].subject_codes[{j}]", f"Unknown subject code: {code!r}.")
    sections_by_code = {row.get("section_code"): row for row in payload["sections"] if isinstance(row, dict)}
    teachers_by_code = {row.get("faculty_code"): row for row in payload["teachers"] if isinstance(row, dict)}
    years_by_name = {row.get("name"): row for row in payload["academic_years"] if isinstance(row, dict)}
    for i, version in enumerate(payload["timetable_versions"]):
        if not isinstance(version, dict):
            continue
        reference(isinstance(version.get("section_code"), str) and version["section_code"] in sections, f"$.timetable_versions[{i}].section_code", "Unknown section code.")
        if version.get("status") != "DRAFT":
            errors.append({"row": f"$.timetable_versions[{i}].status", "message": "Development seed accepts draft timetables only."})
        entries = version.get("entries")
        if not isinstance(entries, list):
            errors.append({"row": f"$.timetable_versions[{i}].entries", "message": "Expected a list."})
            continue
        seen_slots: set[tuple[int, str]] = set()
        seen_intervals: list[tuple[int, time, time, str, tuple[str, str]]] = []
        for j, entry in enumerate(entries):
            row_path = f"$.timetable_versions[{i}].entries[{j}]"
            if not isinstance(entry, dict):
                errors.append({"row": row_path, "message": "Expected an object."})
                continue
            reference(isinstance(entry.get("subject_code"), str) and entry["subject_code"] in subjects, f"{row_path}.subject_code", "Unknown subject code.")
            reference(isinstance(entry.get("faculty_code"), str) and entry["faculty_code"] in faculty, f"{row_path}.faculty_code", "Unknown faculty code.")
            room_key = (entry.get("building"), entry.get("room_number"))
            reference(all(isinstance(value, str) for value in room_key) and room_key in rooms, f"{row_path}.room", "Unknown room.")
            teacher = teachers_by_code.get(entry.get("faculty_code"))
            section = sections_by_code.get(version.get("section_code"))
            if teacher and entry.get("subject_code") not in teacher.get("subject_codes", []):
                errors.append({"row": f"{row_path}.subject_code", "message": "Teacher is not qualified for this subject in the fixture."})
            if section and entry.get("subject_code") not in section.get("subject_codes", []):
                errors.append({"row": f"{row_path}.subject_code", "message": "Subject is not part of the section curriculum in the fixture."})
            if section:
                year = years_by_name.get(section.get("academic_year"))
                if year:
                    try:
                        start_date = date.fromisoformat(version["effective_from"])
                        end_date = date.fromisoformat(version["effective_to"])
                        if start_date > end_date or start_date < date.fromisoformat(year["starts_on"]) or end_date > date.fromisoformat(year["ends_on"]):
                            raise ValueError("timetable effective period must fit inside its academic year")
                    except (KeyError, TypeError, ValueError) as error:
                        errors.append({"row": f"$.timetable_versions[{i}]", "message": f"Invalid timetable dates: {error}"})
            try:
                start = time.fromisoformat(entry["starts_at_local"])
                end = time.fromisoformat(entry["ends_at_local"])
                if start >= end:
                    raise ValueError("start must be before end")
                weekday = int(entry["weekday"])
                if not 0 <= weekday <= 6:
                    raise ValueError("weekday must be between 0 and 6")
                slot = (weekday, start.isoformat())
                if slot in seen_slots:
                    raise ValueError("duplicate start time in this timetable version")
                seen_slots.add(slot)
                room_key = (entry["building"], entry["room_number"])
                for old_day, old_start, old_end, old_teacher, old_room in seen_intervals:
                    overlaps = weekday == old_day and start < old_end and old_start < end
                    if overlaps and (old_teacher == entry["faculty_code"] or old_room == room_key):
                        raise ValueError("teacher or room overlaps another timetable entry")
                    if overlaps:
                        raise ValueError("section overlaps another timetable entry")
                seen_intervals.append((weekday, start, end, entry["faculty_code"], room_key))
            except (KeyError, TypeError, ValueError) as error:
                errors.append({"row": row_path, "message": f"Invalid timetable entry: {error}"})
    return errors


def _get_or_create(session: Session, model, lookup: dict[str, Any], values: dict[str, Any]):
    row = session.scalar(select(model).filter_by(**lookup))
    if row is None:
        row = model(**lookup, **values)
        session.add(row)
        session.flush()
        return row
    mismatches = [key for key, value in values.items() if getattr(row, key) != value]
    if mismatches:
        raise ValueError(
            f"Existing {model.__tablename__} row {lookup!r} differs in: {', '.join(mismatches)}. "
            "No rows were changed; resolve the conflict before reseeding."
        )
    return row


def seed_demo(session: Session, payload: dict[str, Any], password_hash: str) -> dict[str, int]:
    """Insert validated local demo records; caller owns one transaction."""
    if errors := validate_seed(payload):
        raise SeedInputError(errors)

    def get_user(login_id: str) -> User:
        user = session.scalar(select(User).where(User.login_id == login_id))
        if user is None:
            user = User(login_id=login_id, password_hash=password_hash, is_active=True)
            session.add(user)
            session.flush()
        elif not user.is_active:
            raise ValueError(f"Existing demo login {login_id!r} is inactive; seed will not reactivate it.")
        return user

    def add_role(user: User, role: str) -> None:
        existing = session.get(UserRole, (user.user_id, role))
        if existing is None:
            session.add(UserRole(user_id=user.user_id, role=role))

    year_rows = {}
    for row in payload["academic_years"]:
        year_rows[row["name"]] = _get_or_create(
            session, AcademicYear, {"name": row["name"]},
            {"starts_on": date.fromisoformat(row["starts_on"]), "ends_on": date.fromisoformat(row["ends_on"]), "status": row["status"]},
        )
    course_rows = {row["code"]: _get_or_create(session, Course, {"code": row["code"]}, {"name": row["name"]}) for row in payload["courses"]}
    subject_rows = {row["code"]: _get_or_create(session, Subject, {"code": row["code"]}, {"name": row["name"], "requires_lab": row["requires_lab"]}) for row in payload["subjects"]}
    section_rows = {}
    for row in payload["sections"]:
        course, year = course_rows[row["course_code"]], year_rows[row["academic_year"]]
        lookup = {"course_id": course.course_id, "academic_year_id": year.academic_year_id, "semester": row["semester"], "section_code": row["section_code"]}
        section_rows[row["section_code"]] = _get_or_create(session, Section, lookup, {"shift": row["shift"], "capacity": row["capacity"]})
    room_rows = {}
    for row in payload["rooms"]:
        lookup = {"building": row["building"], "room_number": row["room_number"]}
        room_rows[(row["building"], row["room_number"])] = _get_or_create(session, Room, lookup, {"capacity": row["capacity"], "room_type": row["room_type"], "status": row["status"]})

    for row in payload["students"]:
        user = get_user(row["login_id"])
        add_role(user, "STUDENT")
        student = _get_or_create(session, Student, {"erp_id": row["erp_id"]}, {"user_id": user.user_id, "full_name": row["full_name"]})
        if row.get("section_code"):
            section = section_rows[row["section_code"]]
            year = year_rows[next(spec["academic_year"] for spec in payload["sections"] if spec["section_code"] == row["section_code"])]
            _get_or_create(session, StudentEnrollment, {"student_id": student.student_id, "section_id": section.section_id, "starts_on": year.starts_on}, {"ends_on": year.ends_on, "status": "ACTIVE"})

    teacher_rows = {}
    for row in payload["teachers"]:
        user = get_user(row["login_id"])
        add_role(user, "TEACHER")
        teacher = _get_or_create(session, Teacher, {"faculty_code": row["faculty_code"]}, {"user_id": user.user_id, "full_name": row["full_name"], "department": row.get("department")})
        for code in row["subject_codes"]:
            subject = subject_rows[code]
            if session.get(TeacherSubject, (teacher.teacher_id, subject.subject_id)) is None:
                session.add(TeacherSubject(teacher_id=teacher.teacher_id, subject_id=subject.subject_id))
        teacher_rows[row["faculty_code"]] = teacher

    for row in payload["admins"]:
        user = get_user(row["login_id"])
        add_role(user, "ADMIN")

    section_specs = {row["section_code"]: row for row in payload["sections"]}
    for section_code, section in section_rows.items():
        for subject_code in section_specs[section_code]["subject_codes"]:
            subject = subject_rows[subject_code]
            if session.get(SectionSubject, (section.section_id, subject.subject_id)) is None:
                session.add(SectionSubject(section_id=section.section_id, subject_id=subject.subject_id))
    session.flush()

    for version in payload["timetable_versions"]:
        section = section_rows[version["section_code"]]
        section_spec = section_specs[version["section_code"]]
        academic_year = year_rows[section_spec["academic_year"]]
        timetable = _get_or_create(
            session, TimetableVersion,
            {"section_id": section.section_id, "name": version["name"]},
            {"status": version["status"], "effective_from": date.fromisoformat(version["effective_from"]), "effective_to": date.fromisoformat(version["effective_to"]), "published_by": None},
        )
        for entry in version["entries"]:
            teacher = teacher_rows[entry["faculty_code"]]
            subject = subject_rows[entry["subject_code"]]
            assignment = _get_or_create(
                session, TeachingAssignment,
                {"teacher_id": teacher.teacher_id, "subject_id": subject.subject_id, "section_id": section.section_id, "starts_on": academic_year.starts_on},
                {"ends_on": academic_year.ends_on, "status": "ACTIVE"},
            )
            room = room_rows[(entry["building"], entry["room_number"])]
            entry_lookup = {"timetable_version_id": timetable.timetable_version_id, "weekday": entry["weekday"], "starts_at_local": time.fromisoformat(entry["starts_at_local"])}
            _get_or_create(
                session, TimetableEntry, entry_lookup,
                {"section_id": section.section_id, "teaching_assignment_id": assignment.assignment_id, "teacher_id": teacher.teacher_id, "subject_id": subject.subject_id, "room_id": room.room_id, "ends_at_local": time.fromisoformat(entry["ends_at_local"])},
            )

    policy = session.scalar(select(SchedulingPolicy).where(SchedulingPolicy.section_id.is_(None)))
    if policy is None:
        session.add(SchedulingPolicy(scope="INSTITUTION", section_id=None, reallocation_mode="SUGGEST_AND_APPROVE", max_cascade_depth=1, scoring_weights={}))
    elif policy.reallocation_mode != "SUGGEST_AND_APPROVE" or policy.max_cascade_depth != 1:
        raise ValueError("Existing institution scheduling policy differs from the demo default; seed will not overwrite it.")

    session.flush()
    return {
        "users": len(payload["students"]) + len(payload["teachers"]) + len(payload["admins"]),
        "students": len(payload["students"]),
        "teachers": len(payload["teachers"]),
        "sections": len(payload["sections"]),
        "subjects": len(payload["subjects"]),
        "rooms": len(payload["rooms"]),
        "timetable_entries": sum(len(version["entries"]) for version in payload["timetable_versions"]),
    }
