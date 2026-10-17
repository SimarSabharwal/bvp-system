"""Relational schema for the Student System PostgreSQL database."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, Enum, ForeignKey, ForeignKeyConstraint,
    Index, Integer, Numeric, PrimaryKeyConstraint, String, Text, Time, UniqueConstraint,
    func, text,
)
from sqlalchemy.dialects.postgresql import ExcludeConstraint, JSONB, TSTZRANGE, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative metadata used by Alembic; application startup never creates tables."""


def enum(name: str, *values: str) -> Enum:
    return Enum(*values, name=name, native_enum=True, create_constraint=True)


class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(primary_key=True)
    login_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (Index("uq_users_login_id_ci", func.lower(login_id), unique=True),)


class UserRole(Base):
    __tablename__ = "user_roles"
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), primary_key=True)
    role: Mapped[str] = mapped_column(enum("user_role", "STUDENT", "TEACHER", "ADMIN"), primary_key=True)


class LoginAttempt(Base):
    """Persistent, identifier-scoped throttling state for password login."""
    __tablename__ = "login_attempts"
    login_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    window_started_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    locked_until: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("failures >= 0", name="login_attempts_nonnegative_failures"),)


class Student(Base):
    __tablename__ = "students"
    student_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), unique=True, nullable=False)
    erp_id: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)


class Teacher(Base):
    __tablename__ = "teachers"
    teacher_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), unique=True, nullable=False)
    faculty_code: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(200), nullable=False)
    department: Mapped[str | None] = mapped_column(String(160))


class AcademicYear(Base):
    __tablename__ = "academic_years"
    academic_year_id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    starts_on: Mapped[object] = mapped_column(Date, nullable=False)
    ends_on: Mapped[object] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(enum("academic_year_status", "PLANNED", "ACTIVE", "COMPLETED"), nullable=False)
    __table_args__ = (CheckConstraint("starts_on <= ends_on", name="academic_year_valid_dates"), Index("uq_one_active_academic_year", "status", unique=True, postgresql_where=text("status = 'ACTIVE'")))


class Course(Base):
    __tablename__ = "courses"
    course_id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)


class Section(Base):
    __tablename__ = "sections"
    section_id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int] = mapped_column(ForeignKey("courses.course_id", ondelete="RESTRICT"), nullable=False)
    academic_year_id: Mapped[int] = mapped_column(ForeignKey("academic_years.academic_year_id", ondelete="RESTRICT"), nullable=False)
    semester: Mapped[int] = mapped_column(Integer, nullable=False)
    section_code: Mapped[str] = mapped_column(String(30), nullable=False)
    shift: Mapped[str] = mapped_column(enum("section_shift", "MORNING", "AFTERNOON", "EVENING"), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (UniqueConstraint("course_id", "academic_year_id", "semester", "section_code", name="uq_section_academic_identity"), UniqueConstraint("section_id", "course_id", name="uq_section_course"), CheckConstraint("semester > 0", name="section_positive_semester"), CheckConstraint("capacity IS NULL OR capacity > 0", name="section_positive_capacity"))


class StudentEnrollment(Base):
    __tablename__ = "student_enrollments"
    enrollment_id: Mapped[int] = mapped_column(primary_key=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.student_id", ondelete="RESTRICT"), nullable=False)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.section_id", ondelete="RESTRICT"), nullable=False)
    starts_on: Mapped[object] = mapped_column(Date, nullable=False)
    ends_on: Mapped[object | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(enum("enrollment_status", "ACTIVE", "ENDED", "WITHDRAWN"), nullable=False)
    __table_args__ = (UniqueConstraint("enrollment_id", "student_id", "section_id", name="uq_enrollment_attendance_ref"), CheckConstraint("ends_on IS NULL OR starts_on <= ends_on", name="enrollment_valid_dates"), ExcludeConstraint(("student_id", "="), (func.daterange(starts_on, ends_on, "[]"), "&&"), where=text("status = 'ACTIVE'"), using="gist", name="student_active_enrollment_period_no_overlap"))


class Subject(Base):
    __tablename__ = "subjects"
    subject_id: Mapped[int] = mapped_column(primary_key=True)
    course_id: Mapped[int | None] = mapped_column(ForeignKey("courses.course_id", ondelete="RESTRICT"))
    semester: Mapped[int | None] = mapped_column(Integer)
    curriculum_version: Mapped[str | None] = mapped_column(String(40))
    subject_type: Mapped[str | None] = mapped_column(String(40))
    code: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    requires_lab: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    __table_args__ = (CheckConstraint("semester IS NULL OR semester > 0", name="subject_positive_semester"),)


class SectionSubject(Base):
    __tablename__ = "section_subjects"
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.section_id", ondelete="RESTRICT"), primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.subject_id", ondelete="RESTRICT"), primary_key=True)
    required_lecture_hours: Mapped[object] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    required_lab_hours: Mapped[object] = mapped_column(Numeric(6, 2), nullable=False, server_default="0")
    __table_args__ = (CheckConstraint("required_lecture_hours >= 0 AND required_lab_hours >= 0", name="section_subject_nonnegative_hours"),)


class TeacherSubject(Base):
    __tablename__ = "teacher_subjects"
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.teacher_id", ondelete="RESTRICT"), primary_key=True)
    subject_id: Mapped[int] = mapped_column(ForeignKey("subjects.subject_id", ondelete="RESTRICT"), primary_key=True)


class TeachingAssignment(Base):
    __tablename__ = "teaching_assignments"
    assignment_id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    section_id: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_on: Mapped[object] = mapped_column(Date, nullable=False)
    ends_on: Mapped[object | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(enum("assignment_status", "ACTIVE", "ENDED"), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["teacher_id", "subject_id"], ["teacher_subjects.teacher_id", "teacher_subjects.subject_id"], name="fk_assignment_qualification", ondelete="RESTRICT"), ForeignKeyConstraint(["section_id", "subject_id"], ["section_subjects.section_id", "section_subjects.subject_id"], name="fk_assignment_curriculum", ondelete="RESTRICT"), UniqueConstraint("assignment_id", "section_id", "subject_id", name="uq_assignment_section_subject"), UniqueConstraint("assignment_id", "section_id", "subject_id", "teacher_id", name="uq_assignment_session_ref"), CheckConstraint("ends_on IS NULL OR starts_on <= ends_on", name="assignment_valid_dates"), ExcludeConstraint(("teacher_id", "="), ("subject_id", "="), ("section_id", "="), (func.daterange(starts_on, ends_on, "[]"), "&&"), where=text("status = 'ACTIVE'"), using="gist", name="teaching_assignment_period_no_overlap"))


class Room(Base):
    __tablename__ = "rooms"
    room_id: Mapped[int] = mapped_column(primary_key=True)
    building: Mapped[str] = mapped_column(String(100), nullable=False)
    room_number: Mapped[str] = mapped_column(String(40), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer)
    room_type: Mapped[str] = mapped_column(enum("room_type", "NORMAL", "COMPUTER_LAB", "SCIENCE_LAB"), nullable=False)
    status: Mapped[str] = mapped_column(enum("room_status", "ACTIVE", "INACTIVE"), nullable=False)
    __table_args__ = (UniqueConstraint("building", "room_number", name="uq_room_location"), CheckConstraint("capacity IS NULL OR capacity > 0", name="room_positive_capacity"))


class RoomFeature(Base):
    __tablename__ = "room_features"
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.room_id", ondelete="RESTRICT"), primary_key=True)
    feature_code: Mapped[str] = mapped_column(String(60), primary_key=True)


class SchedulingPolicy(Base):
    __tablename__ = "scheduling_policies"
    policy_id: Mapped[int] = mapped_column(primary_key=True)
    scope: Mapped[str] = mapped_column(String(40), nullable=False, server_default="INSTITUTION")
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.section_id", ondelete="RESTRICT"), unique=True)
    reallocation_mode: Mapped[str] = mapped_column(enum("reallocation_mode", "SUGGEST_AND_APPROVE", "AUTO_APPLY"), nullable=False, server_default="SUGGEST_AND_APPROVE")
    max_cascade_depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    scoring_weights: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    updated_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    updated_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (CheckConstraint("max_cascade_depth BETWEEN 1 AND 2", name="policy_cascade_depth_range"), CheckConstraint("(scope = 'INSTITUTION' AND section_id IS NULL) OR (scope = 'SECTION' AND section_id IS NOT NULL)", name="policy_scope_matches_section"),)


class TeacherAvailability(Base):
    __tablename__ = "teacher_availability"
    availability_id: Mapped[int] = mapped_column(primary_key=True)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("teachers.teacher_id", ondelete="RESTRICT"), nullable=False)
    starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(enum("availability_status", "AVAILABLE", "UNAVAILABLE"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (CheckConstraint("starts_at < ends_at", name="teacher_availability_valid_time"),)


class RoomAvailability(Base):
    __tablename__ = "room_availability"
    room_availability_id: Mapped[int] = mapped_column(primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.room_id", ondelete="RESTRICT"), nullable=False)
    starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(enum("availability_status", "AVAILABLE", "UNAVAILABLE"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    __table_args__ = (CheckConstraint("starts_at < ends_at", name="room_availability_valid_time"),)


class AcademicEvent(Base):
    __tablename__ = "academic_events"
    event_id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.section_id", ondelete="RESTRICT"))
    event_type: Mapped[str] = mapped_column(enum("academic_event_type", "HOLIDAY", "EXAM", "OTHER"), nullable=False)
    starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    ends_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    __table_args__ = (CheckConstraint("starts_at < ends_at", name="academic_event_valid_time"),)


class TimetableVersion(Base):
    __tablename__ = "timetable_versions"
    timetable_version_id: Mapped[int] = mapped_column(primary_key=True)
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.section_id", ondelete="RESTRICT"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(enum("timetable_status", "DRAFT", "PUBLISHED", "ARCHIVED"), nullable=False)
    effective_from: Mapped[object] = mapped_column(Date, nullable=False)
    effective_to: Mapped[object] = mapped_column(Date, nullable=False)
    published_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    __table_args__ = (UniqueConstraint("timetable_version_id", "section_id", name="uq_timetable_version_section"), CheckConstraint("effective_from <= effective_to", name="timetable_valid_dates"), ExcludeConstraint(("section_id", "="), (func.daterange(effective_from, effective_to, "[]"), "&&"), where=text("status = 'PUBLISHED'"), using="gist", name="no_published_version_period_overlap"))


class TimetableEntry(Base):
    __tablename__ = "timetable_entries"
    entry_id: Mapped[int] = mapped_column(primary_key=True)
    timetable_version_id: Mapped[int] = mapped_column(Integer, nullable=False)
    section_id: Mapped[int] = mapped_column(Integer, nullable=False)
    teaching_assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    teacher_id: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.room_id", ondelete="RESTRICT"), nullable=False)
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    starts_at_local: Mapped[object] = mapped_column(Time, nullable=False)
    ends_at_local: Mapped[object] = mapped_column(Time, nullable=False)
    __table_args__ = (ForeignKeyConstraint(["timetable_version_id", "section_id"], ["timetable_versions.timetable_version_id", "timetable_versions.section_id"], name="fk_entry_version_section", ondelete="RESTRICT"), ForeignKeyConstraint(["teaching_assignment_id", "section_id", "subject_id", "teacher_id"], ["teaching_assignments.assignment_id", "teaching_assignments.section_id", "teaching_assignments.subject_id", "teaching_assignments.teacher_id"], name="fk_entry_assignment_tuple", ondelete="RESTRICT"), UniqueConstraint("entry_id", "section_id", name="uq_entry_section"), CheckConstraint("weekday BETWEEN 0 AND 6", name="entry_weekday_range"), CheckConstraint("starts_at_local < ends_at_local", name="entry_valid_time"), Index("ix_entries_version_weekday_time", "timetable_version_id", "weekday", "starts_at_local"))


class ClassSession(Base):
    __tablename__ = "class_sessions"
    class_session_id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int | None] = mapped_column(Integer)
    pending_lecture_id: Mapped[int | None] = mapped_column(ForeignKey("pending_lectures.pending_lecture_id", ondelete="RESTRICT", use_alter=True, name="fk_recovery_session_pending_lecture"))
    section_id: Mapped[int] = mapped_column(ForeignKey("sections.section_id", ondelete="RESTRICT"), nullable=False)
    session_date: Mapped[object] = mapped_column(Date, nullable=False)
    original_assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    original_subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    original_teacher_id: Mapped[int] = mapped_column(Integer, nullable=False)
    original_room_id: Mapped[int] = mapped_column(ForeignKey("rooms.room_id", ondelete="RESTRICT"), nullable=False)
    current_assignment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_teacher_id: Mapped[int] = mapped_column(Integer, nullable=False)
    current_room_id: Mapped[int] = mapped_column(ForeignKey("rooms.room_id", ondelete="RESTRICT"), nullable=False)
    original_starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    original_ends_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    current_starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    current_ends_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(enum("class_session_status", "SCHEDULED", "COMPLETED", "CANCELLED", "VOID"), nullable=False)
    __table_args__ = (ForeignKeyConstraint(["original_assignment_id", "section_id", "original_subject_id", "original_teacher_id"], ["teaching_assignments.assignment_id", "teaching_assignments.section_id", "teaching_assignments.subject_id", "teaching_assignments.teacher_id"], name="fk_session_original_assignment", ondelete="RESTRICT"), ForeignKeyConstraint(["current_assignment_id", "section_id", "current_subject_id", "current_teacher_id"], ["teaching_assignments.assignment_id", "teaching_assignments.section_id", "teaching_assignments.subject_id", "teaching_assignments.teacher_id"], name="fk_session_current_assignment", ondelete="RESTRICT"), ForeignKeyConstraint(["entry_id", "section_id"], ["timetable_entries.entry_id", "timetable_entries.section_id"], name="fk_session_entry_section", ondelete="RESTRICT"), CheckConstraint("(entry_id IS NOT NULL AND pending_lecture_id IS NULL) OR (entry_id IS NULL AND pending_lecture_id IS NOT NULL)", name="session_has_schedule_source"), CheckConstraint("original_starts_at < original_ends_at AND current_starts_at < current_ends_at", name="session_valid_time"), UniqueConstraint("class_session_id", "section_id", name="uq_session_section"), UniqueConstraint("class_session_id", "section_id", "current_subject_id", name="uq_session_subject_section"), UniqueConstraint("entry_id", "session_date", name="uq_session_entry_date"), UniqueConstraint("pending_lecture_id", name="uq_session_pending_recovery"), ExcludeConstraint(("section_id", "="), (func.tstzrange(current_starts_at, current_ends_at, "[)"), "&&"), where=text("status NOT IN ('CANCELLED', 'VOID')"), using="gist", name="no_section_time_overlap"), ExcludeConstraint(("current_teacher_id", "="), (func.tstzrange(current_starts_at, current_ends_at, "[)"), "&&"), where=text("status NOT IN ('CANCELLED', 'VOID')"), using="gist", name="no_teacher_time_overlap"), ExcludeConstraint(("current_room_id", "="), (func.tstzrange(current_starts_at, current_ends_at, "[)"), "&&"), where=text("status NOT IN ('CANCELLED', 'VOID')"), using="gist", name="no_room_time_overlap"), Index("ix_sessions_section_date_time", "section_id", "session_date", "current_starts_at"), Index("ix_sessions_teacher_date_time", "current_teacher_id", "session_date", "current_starts_at"), Index("ix_sessions_room_date_time", "current_room_id", "session_date", "current_starts_at"))


class PendingLecture(Base):
    __tablename__ = "pending_lectures"
    pending_lecture_id: Mapped[int] = mapped_column(primary_key=True)
    class_session_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    section_id: Mapped[int] = mapped_column(Integer, nullable=False)
    subject_id: Mapped[int] = mapped_column(Integer, nullable=False)
    preferred_assignment_id: Mapped[int | None] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(enum("pending_lecture_state", "OPEN", "SCHEDULED", "RECOVERED", "RESOLVED"), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    due_by: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (ForeignKeyConstraint(["class_session_id", "section_id", "subject_id"], ["class_sessions.class_session_id", "class_sessions.section_id", "class_sessions.current_subject_id"], name="fk_pending_origin_session_subject", ondelete="RESTRICT"), ForeignKeyConstraint(["preferred_assignment_id", "section_id", "subject_id"], ["teaching_assignments.assignment_id", "teaching_assignments.section_id", "teaching_assignments.subject_id"], name="fk_pending_preferred_assignment", ondelete="RESTRICT"))


class Reallocation(Base):
    __tablename__ = "reallocations"
    reallocation_id: Mapped[int] = mapped_column(primary_key=True)
    cascade_group_id: Mapped[object] = mapped_column(UUID(as_uuid=True), nullable=False, default=uuid4, server_default=text("gen_random_uuid()"))
    cascade_depth: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    parent_reallocation_id: Mapped[int | None] = mapped_column(ForeignKey("reallocations.reallocation_id", ondelete="RESTRICT", name="fk_reallocation_parent"))
    class_session_id: Mapped[int] = mapped_column(ForeignKey("class_sessions.class_session_id", ondelete="RESTRICT"), nullable=False)
    pending_lecture_id: Mapped[int | None] = mapped_column(ForeignKey("pending_lectures.pending_lecture_id", ondelete="RESTRICT"))
    status: Mapped[str] = mapped_column(enum("reallocation_status", "PROPOSED", "ACCEPTED", "REJECTED", "REVERTED"), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    initiator_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    proposed_assignment_id: Mapped[int | None] = mapped_column(ForeignKey("teaching_assignments.assignment_id", ondelete="RESTRICT"))
    proposed_room_id: Mapped[int | None] = mapped_column(ForeignKey("rooms.room_id", ondelete="RESTRICT"))
    proposed_starts_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    proposed_ends_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    previous_assignment_id: Mapped[int] = mapped_column(ForeignKey("teaching_assignments.assignment_id", ondelete="RESTRICT"), nullable=False)
    previous_room_id: Mapped[int] = mapped_column(ForeignKey("rooms.room_id", ondelete="RESTRICT"), nullable=False)
    previous_starts_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    previous_ends_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    decided_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    decided_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("cascade_depth BETWEEN 0 AND 2", name="reallocation_cascade_depth_range"), CheckConstraint("parent_reallocation_id IS NOT NULL OR cascade_depth = 0", name="reallocation_cascade_root_depth"), CheckConstraint("proposed_ends_at IS NULL OR proposed_starts_at < proposed_ends_at", name="reallocation_proposed_valid_time"), CheckConstraint("previous_starts_at < previous_ends_at", name="reallocation_previous_valid_time"), Index("ix_reallocations_session_created", "class_session_id", "created_at"), Index("ix_reallocations_cascade_group_depth", "cascade_group_id", "cascade_depth"))


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    attendance_session_id: Mapped[int] = mapped_column(primary_key=True)
    class_session_id: Mapped[int] = mapped_column(Integer, unique=True, nullable=False)
    section_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(enum("attendance_session_status", "OPEN", "CLOSED"), nullable=False)
    opened_by: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    opened_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    closed_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (ForeignKeyConstraint(["class_session_id", "section_id"], ["class_sessions.class_session_id", "class_sessions.section_id"], name="fk_attendance_session_section", ondelete="RESTRICT"), UniqueConstraint("attendance_session_id", "section_id", name="uq_attendance_session_section"), CheckConstraint("closed_at IS NULL OR opened_at <= closed_at", name="attendance_session_valid_times"))


class AttendanceRecord(Base):
    __tablename__ = "attendance_records"
    attendance_record_id: Mapped[int] = mapped_column(primary_key=True)
    attendance_session_id: Mapped[int] = mapped_column(Integer, nullable=False)
    student_id: Mapped[int] = mapped_column(Integer, nullable=False)
    section_id: Mapped[int] = mapped_column(Integer, nullable=False)
    enrollment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(enum("attendance_status", "PRESENT", "ABSENT", "LATE", "EXCUSED"), nullable=False)
    marked_by: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    marked_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (ForeignKeyConstraint(["attendance_session_id", "section_id"], ["attendance_sessions.attendance_session_id", "attendance_sessions.section_id"], name="fk_record_session_section", ondelete="RESTRICT"), ForeignKeyConstraint(["enrollment_id", "student_id", "section_id"], ["student_enrollments.enrollment_id", "student_enrollments.student_id", "student_enrollments.section_id"], name="fk_record_enrolled_section", ondelete="RESTRICT"), UniqueConstraint("attendance_session_id", "student_id", name="uq_attendance_student_session"), Index("ix_attendance_student_session", "student_id", "attendance_session_id"))


class Notification(Base):
    __tablename__ = "notifications"
    notification_id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    event_type: Mapped[str] = mapped_column(String(60), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    related_session_id: Mapped[int | None] = mapped_column(ForeignKey("class_sessions.class_session_id", ondelete="RESTRICT"))
    related_reallocation_id: Mapped[int | None] = mapped_column(ForeignKey("reallocations.reallocation_id", ondelete="RESTRICT"))
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    read_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_notifications_user_recent", "user_id", "created_at", "notification_id"), Index("ix_notifications_user_unread", "user_id", "created_at", postgresql_where=text("read_at IS NULL")))


class OutboxEvent(Base):
    __tablename__ = "outbox_events"
    outbox_event_id: Mapped[int] = mapped_column(primary_key=True)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(80), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    available_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    delivered_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    last_error: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (CheckConstraint("attempts >= 0", name="outbox_nonnegative_attempts"), Index("ix_outbox_pending", "available_at", "outbox_event_id", postgresql_where=text("delivered_at IS NULL")))


class Announcement(Base):
    __tablename__ = "announcements"
    announcement_id: Mapped[int] = mapped_column(primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    audience_scope: Mapped[str] = mapped_column(enum("announcement_scope", "ALL", "STUDENTS", "TEACHERS", "SECTION"), nullable=False)
    section_id: Mapped[int | None] = mapped_column(ForeignKey("sections.section_id", ondelete="RESTRICT"))
    published_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[object | None] = mapped_column(DateTime(timezone=True))
    __table_args__ = (CheckConstraint("(audience_scope = 'SECTION' AND section_id IS NOT NULL) OR (audience_scope <> 'SECTION' AND section_id IS NULL)", name="announcement_scope_matches_section"), CheckConstraint("expires_at IS NULL OR published_at IS NULL OR published_at < expires_at", name="announcement_valid_dates"))


class AuditEvent(Base):
    __tablename__ = "audit_events"
    audit_event_id: Mapped[int] = mapped_column(primary_key=True)
    actor_id: Mapped[int | None] = mapped_column(ForeignKey("users.user_id", ondelete="RESTRICT"))
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str] = mapped_column(String(100), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[object] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    __table_args__ = (Index("ix_audit_entity_recent", "entity_type", "entity_id", "occurred_at"),)


