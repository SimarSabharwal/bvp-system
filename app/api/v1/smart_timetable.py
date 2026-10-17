"""Admin smart timetable draft generation from existing academic records."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import abort, current_app, jsonify, request
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.api.v1 import api_v1
from app.api.v1.auth import require_csrf, require_roles
from app.extensions import database
from app.models import (AcademicEvent, AcademicYear, Course, Room, Section,
                        SectionSubject, Subject, TeachingAssignment,
                        TeacherAvailability, RoomAvailability, TimetableEntry,
                        TimetableVersion)


def _clock(value: object, field: str) -> time:
    if not isinstance(value, str):
        abort(400, description=f"{field} must be an HH:MM time.")
    try:
        parsed = time.fromisoformat(value)
    except ValueError:
        abort(400, description=f"{field} must be an HH:MM time.")
    if parsed.tzinfo:
        abort(400, description=f"{field} must be a local time without a timezone.")
    return parsed


@api_v1.post("/admin/smart-timetables/generate")
def generate_smart_timetable():
    """Create conflict-checked draft versions for all sections in a year.

    Publication stays a separate admin action so the normal atomic session
    generation and database exclusion constraints remain the final gate.
    """
    require_roles("ADMIN")
    require_csrf()
    data = request.get_json(silent=True)
    allowed = {"academic_year_id", "course_ids", "effective_from", "effective_to", "weekdays",
               "morning_start", "morning_end", "morning_lecture_minutes",
               "morning_break_minutes", "afternoon_start", "afternoon_end",
               "afternoon_lecture_minutes", "afternoon_break_minutes", "lectures_per_day"}
    if not isinstance(data, dict) or set(data) != allowed:
        abort(400, description="Provide academic year, effective dates, weekdays, four-lecture timelines, and break settings.")
    try:
        year_id = data["academic_year_id"]
        if isinstance(year_id, bool): raise ValueError
        year_id = int(year_id)
        course_ids = data["course_ids"]
        if not isinstance(course_ids, list) or not course_ids or any(isinstance(item, bool) or not isinstance(item, int) or item <= 0 for item in course_ids): raise ValueError
        course_ids = sorted(set(course_ids))
        start_date = date.fromisoformat(data["effective_from"])
        end_date = date.fromisoformat(data["effective_to"])
        weekdays = data["weekdays"]
        if not isinstance(weekdays, list) or not weekdays or any(isinstance(day, bool) or not isinstance(day, int) or day not in range(7) for day in weekdays): raise ValueError
        weekdays = sorted(set(weekdays))
        if data["lectures_per_day"] != 4: raise ValueError
        m_start, m_end = _clock(data["morning_start"], "morning_start"), _clock(data["morning_end"], "morning_end")
        a_start, a_end = _clock(data["afternoon_start"], "afternoon_start"), _clock(data["afternoon_end"], "afternoon_end")
        m_len, a_len = int(data["morning_lecture_minutes"]), int(data["afternoon_lecture_minutes"])
        m_break, a_break = int(data["morning_break_minutes"]), int(data["afternoon_break_minutes"])
        if any(isinstance(data[key], bool) for key in ("morning_lecture_minutes", "afternoon_lecture_minutes", "morning_break_minutes", "afternoon_break_minutes")): raise ValueError
        if not (1 <= m_len <= 180 and 1 <= a_len <= 180 and 0 <= m_break <= 60 and 0 <= a_break <= 60): raise ValueError
    except (TypeError, ValueError, KeyError):
        abort(400, description="Invalid date, day, lecture duration, break, or four-lecture setting.")
    if start_date > end_date or (end_date - start_date).days > 370:
        abort(400, description="The effective date range must be ordered and no longer than 371 days.")

    def make_slots(first: time, hard_end: time, duration: int, gap: int):
        slots, cursor = [], datetime.combine(start_date, first)
        limit = datetime.combine(start_date, hard_end)
        for _ in range(4):
            slot_end = cursor + timedelta(minutes=duration)
            if slot_end > limit:
                return None
            slots.append((cursor.time(), slot_end.time()))
            cursor = slot_end + timedelta(minutes=gap)
        return slots

    morning_slots = make_slots(m_start, m_end, m_len, m_break)
    afternoon_slots = make_slots(a_start, a_end, a_len, a_break)
    if morning_slots is None or afternoon_slots is None:
        abort(422, description="Four lectures and configured breaks must fit inside the morning 09:10–13:15 and afternoon 13:30–16:30 windows.")

    db = database.get_session()
    year = db.get(AcademicYear, year_id)
    if year is None: abort(404, description="Academic year was not found.")
    if start_date < year.starts_on or end_date > year.ends_on:
        abort(422, description="The timetable dates must fit inside the selected academic year.")
    sections = db.scalars(select(Section).where(Section.academic_year_id == year_id, Section.course_id.in_(course_ids)).order_by(Section.shift, Section.course_id, Section.semester, Section.section_code)).all()
    if not sections: abort(422, description="The selected academic year has no sections.")
    selected_section_ids = {section.section_id for section in sections}
    existing_versions = db.scalars(select(TimetableVersion).where(
        TimetableVersion.status.in_(["DRAFT", "PUBLISHED"]),
        TimetableVersion.effective_from <= end_date, TimetableVersion.effective_to >= start_date)).all()
    duplicate_sections = sorted({version.section_id for version in existing_versions if version.section_id in selected_section_ids})
    if duplicate_sections:
        abort(409, description="An overlapping draft or published timetable already exists for one or more selected sections. Revise or remove the draft, or choose a non-overlapping date range.")
    existing_version_ids = [version.timetable_version_id for version in existing_versions]
    existing_entries = db.scalars(select(TimetableEntry).where(TimetableEntry.timetable_version_id.in_(existing_version_ids))).all() if existing_version_ids else []
    courses = {row.course_id: row for row in db.scalars(select(Course)).all()}
    subject_course = {row.subject_id: row.course_id for row in db.scalars(select(Subject)).all()}
    rooms = db.scalars(select(Room).where(Room.status == "ACTIVE").order_by(Room.room_id)).all()
    tz = ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])
    range_start = datetime.combine(start_date, time.min, tzinfo=tz)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz)
    unavailable_teachers = db.scalars(select(TeacherAvailability).where(
        TeacherAvailability.status == "UNAVAILABLE", TeacherAvailability.starts_at < range_end,
        TeacherAvailability.ends_at > range_start)).all()
    unavailable_rooms = db.scalars(select(RoomAvailability).where(
        RoomAvailability.status == "UNAVAILABLE", RoomAvailability.starts_at < range_end,
        RoomAvailability.ends_at > range_start)).all()
    section_rows = []
    for section in sections:
        curriculum = db.scalars(select(SectionSubject).where(SectionSubject.section_id == section.section_id)).all()
        assignments = db.scalars(select(TeachingAssignment).join(SectionSubject,
            (SectionSubject.section_id == TeachingAssignment.section_id) & (SectionSubject.subject_id == TeachingAssignment.subject_id))
            .where(TeachingAssignment.section_id == section.section_id, TeachingAssignment.status == "ACTIVE",
                   TeachingAssignment.starts_on <= end_date,
                   or_(TeachingAssignment.ends_on.is_(None), TeachingAssignment.ends_on >= start_date))
            .order_by(TeachingAssignment.assignment_id)).all()
        eligible = [item for item in assignments if subject_course.get(item.subject_id) == section.course_id and (db.get(Subject, item.subject_id).semester is None or db.get(Subject, item.subject_id).semester == section.semester)]
        if not curriculum or not eligible:
            code = courses.get(section.course_id).code if courses.get(section.course_id) else str(section.course_id)
            abort(422, description=f"Section {code} {section.section_code} has no curriculum and active qualified teaching assignments for this date range.")
        if section.shift not in {"MORNING", "AFTERNOON"}:
            abort(422, description=f"Section {section.section_code} uses an unsupported shift for this timetable.")
        section_rows.append((section, eligible, morning_slots if section.shift == "MORNING" else afternoon_slots))

    # Treat each weekday as a shared resource grid across all selected sections.
    # The same assignments/rooms can be reused on another weekday.
    drafts: list[dict] = []
    draft_map: dict[int, TimetableVersion] = {}
    names = {}
    for section, _, _ in section_rows:
        course_code = courses.get(section.course_id).code if courses.get(section.course_id) else f"course-{section.course_id}"
        names[section.section_id] = f"Smart {course_code}-{section.section_code} {start_date.isoformat()} to {end_date.isoformat()}"
        version = TimetableVersion(section_id=section.section_id, name=names[section.section_id], status="DRAFT", effective_from=start_date, effective_to=end_date)
        db.add(version)
        draft_map[section.section_id] = version
    db.flush()

    for weekday in weekdays:
        for section, assignments, slots in section_rows:
            used_subjects: set[int] = set()
            for slot_index, (slot_start, slot_end) in enumerate(slots):
                candidates = sorted(assignments, key=lambda assignment: (assignment.subject_id in used_subjects, assignment.assignment_id))
                placed = None
                for assignment in candidates:
                    if assignment.subject_id in used_subjects and len({row.subject_id for row in assignments}) >= 4:
                        continue
                    if assignment.starts_on > start_date or (assignment.ends_on and assignment.ends_on < end_date):
                        continue
                    subject = db.get(Subject, assignment.subject_id)
                    section_subject = db.get(SectionSubject, (section.section_id, assignment.subject_id))
                    if subject is None or section_subject is None: continue
                    for room in rooms:
                        if room.capacity is None or section.capacity is None or room.capacity < section.capacity: continue
                        if subject.requires_lab and room.room_type not in {"COMPUTER_LAB", "SCIENCE_LAB"}: continue
                        slot_unavailable = False
                        date_cursor = start_date
                        while date_cursor <= end_date:
                            if date_cursor.weekday() == weekday:
                                slot_start_at = datetime.combine(date_cursor, slot_start, tzinfo=tz)
                                slot_end_at = datetime.combine(date_cursor, slot_end, tzinfo=tz)
                                if any(row.teacher_id == assignment.teacher_id and row.starts_at < slot_end_at and row.ends_at > slot_start_at for row in unavailable_teachers) or any(row.room_id == room.room_id and row.starts_at < slot_end_at and row.ends_at > slot_start_at for row in unavailable_rooms):
                                    slot_unavailable = True
                                    break
                            date_cursor += timedelta(days=1)
                        if slot_unavailable: continue
                        clashes = any(row["weekday"] == weekday and row["starts_at_local"] < slot_end and row["ends_at_local"] > slot_start and (row["teacher_id"] == assignment.teacher_id or row["room_id"] == room.room_id or row["section_id"] == section.section_id) for row in drafts)
                        clashes = clashes or any(row.weekday == weekday and row.starts_at_local < slot_end and row.ends_at_local > slot_start and (row.teacher_id == assignment.teacher_id or row.room_id == room.room_id or row.section_id == section.section_id) for row in existing_entries)
                        if clashes: continue
                        placed = (assignment, room, subject)
                        break
                    if placed: break
                if not placed:
                    abort(422, description=f"No conflict-free teacher and suitable room are available for {courses.get(section.course_id).code if courses.get(section.course_id) else section.course_id} {section.section_code}, weekday {weekday + 1}, lecture {slot_index + 1}. No draft was saved.")
                assignment, room, _subject = placed
                entry = TimetableEntry(timetable_version_id=draft_map[section.section_id].timetable_version_id,
                    section_id=section.section_id, teaching_assignment_id=assignment.assignment_id,
                    teacher_id=assignment.teacher_id, subject_id=assignment.subject_id, room_id=room.room_id,
                    weekday=weekday, starts_at_local=slot_start, ends_at_local=slot_end)
                db.add(entry)
                drafts.append({"section_id": section.section_id, "teacher_id": assignment.teacher_id,
                    "room_id": room.room_id, "weekday": weekday, "starts_at_local": slot_start,
                    "ends_at_local": slot_end, "subject_id": assignment.subject_id})
                used_subjects.add(assignment.subject_id)

    date_plan = []
    events = db.scalars(select(AcademicEvent).where(AcademicEvent.event_type.in_(["HOLIDAY", "EXAM"]),
        AcademicEvent.starts_at < datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=tz),
        AcademicEvent.ends_at > datetime.combine(start_date, time.min, tzinfo=tz))).all()
    day = start_date
    while day <= end_date:
        if day.weekday() in weekdays:
            matching = [row for row in drafts if row["weekday"] == day.weekday()]
            skipped = []
            for row in matching:
                start = datetime.combine(day, row["starts_at_local"], tzinfo=tz)
                end = datetime.combine(day, row["ends_at_local"], tzinfo=tz)
                overlapping = [event for event in events if event.starts_at < end and event.ends_at > start and (event.section_id is None or event.section_id == row["section_id"])]
                if overlapping:
                    skipped.append({"section_id": row["section_id"], "subject_id": row["subject_id"], "reason": sorted({event.title for event in overlapping})})
            date_plan.append({"date": day.isoformat(), "required_class_count": len(matching) - len(skipped),
                              "excluded_class_count": len(skipped), "exclusions": skipped})
        day += timedelta(days=1)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        abort(409, description="The draft set conflicts with an existing timetable version or resource relationship; nothing was saved.")
    return jsonify({"status": "DRAFTS_CREATED", "versions": [{"timetable_version_id": version.timetable_version_id, "section_id": section_id, "name": names[section_id], "entry_count": sum(1 for row in drafts if row["section_id"] == section_id)} for section_id, version in draft_map.items()], "sections": len(sections), "weekdays": weekdays, "lectures_per_section_day": 4, "required_dates": [item["date"] for item in date_plan if item["required_class_count"]], "excluded_dates": [item["date"] for item in date_plan if not item["required_class_count"]], "partial_exclusions": [item for item in date_plan if item["excluded_class_count"]], "generated_entries": len(drafts), "published": False}), 201
