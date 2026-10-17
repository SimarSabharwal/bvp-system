"""Recipient-scoped persisted notifications and announcements."""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask import abort, current_app, jsonify, request
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError

from app.api.v1 import api_v1
from app.api.v1.auth import current_identity, require_csrf, require_roles
from app.extensions import database
from app.models import (Announcement, Notification, OutboxEvent, Section, Student,
                        StudentEnrollment, Teacher, TeachingAssignment, User,
                        UserRole)


def _instant(value, name):
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"]))
    except (TypeError, ValueError, AttributeError):
        abort(400, description=f"{name} must be an ISO datetime.")


def _viewer_sections(db, user, roles, today):
    section_ids = set()
    if "STUDENT" in roles:
        student_id = db.scalar(select(Student.student_id).where(Student.user_id == user.user_id))
        if student_id:
            section_ids.update(db.scalars(select(StudentEnrollment.section_id).where(
                StudentEnrollment.student_id == student_id, StudentEnrollment.status == "ACTIVE",
                StudentEnrollment.starts_on <= today,
                or_(StudentEnrollment.ends_on.is_(None), StudentEnrollment.ends_on >= today))))
    if "TEACHER" in roles:
        teacher_id = db.scalar(select(Teacher.teacher_id).where(Teacher.user_id == user.user_id))
        if teacher_id:
            section_ids.update(db.scalars(select(TeachingAssignment.section_id).where(
                TeachingAssignment.teacher_id == teacher_id, TeachingAssignment.status == "ACTIVE",
                TeachingAssignment.starts_on <= today,
                or_(TeachingAssignment.ends_on.is_(None), TeachingAssignment.ends_on >= today))))
    return section_ids


@api_v1.get("/notifications")
def list_notifications():
    user, _ = current_identity()
    db = database.get_session()
    try:
        limit = int(request.args.get("limit", "50"))
        before_id = int(request.args["before_id"]) if "before_id" in request.args else None
        after_id = int(request.args["after_id"]) if "after_id" in request.args else None
    except ValueError:
        abort(400, description="limit and before_id must be integers.")
    if (not 1 <= limit <= 100 or (before_id is not None and before_id < 1)
            or (after_id is not None and after_id < 0)
            or (before_id is not None and after_id is not None)):
        abort(400, description="limit must be 1–100; use one valid before_id or after_id cursor.")
    query = select(Notification.notification_id, Notification.event_type, Notification.title,
                    Notification.message, Notification.related_session_id,
                    Notification.related_reallocation_id, Notification.created_at,
                    Notification.read_at).where(Notification.user_id == user.user_id)
    if before_id is not None:
        query = query.where(Notification.notification_id < before_id)
    if after_id is not None:
        query = query.where(Notification.notification_id > after_id)
    ordering = Notification.notification_id.asc() if after_id is not None else Notification.notification_id.desc()
    rows = db.execute(query.order_by(ordering).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    unread = db.scalar(select(func.count(Notification.notification_id)).where(
        Notification.user_id == user.user_id, Notification.read_at.is_(None))) or 0
    return jsonify({"items": [{"notification_id": row.notification_id, "event_type": row.event_type,
        "title": row.title, "message": row.message, "class_session_id": row.related_session_id,
        "reallocation_id": row.related_reallocation_id, "created_at": row.created_at.isoformat(),
        "read_at": row.read_at.isoformat() if row.read_at else None} for row in rows],
        "unread_count": unread,
        "next_before_id": rows[-1].notification_id if more and rows and after_id is None else None,
        "next_after_id": rows[-1].notification_id if more and rows and after_id is not None else None})


@api_v1.put("/notifications/<int:notification_id>/read")
def mark_notification_read(notification_id):
    user, _ = current_identity()
    require_csrf()
    db = database.get_session()
    row = db.scalar(select(Notification).where(Notification.notification_id == notification_id,
        Notification.user_id == user.user_id).with_for_update())
    if row is None:
        abort(404)
    if row.read_at is None:
        row.read_at = datetime.now(timezone.utc)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            abort(409, description="Notification state changed concurrently.")
    return jsonify({"notification_id": notification_id, "read_at": row.read_at.isoformat()})


@api_v1.post("/admin/announcements")
def publish_announcement():
    actor, _ = require_roles("ADMIN")
    require_csrf()
    data = request.get_json(silent=True)
    fields = {"title", "body", "audience_scope", "section_id", "expires_at"}
    if not isinstance(data, dict) or set(data) - fields or not {"title", "body", "audience_scope"} <= set(data):
        abort(400, description="Provide title, body, audience_scope, and section_id for section audiences.")
    title, body, scope = data["title"], data["body"], data["audience_scope"]
    if not isinstance(title, str) or not title.strip() or len(title) > 200 or not isinstance(body, str) or not body.strip() or len(body) > 20000:
        abort(400, description="Title must be 1–200 characters and body 1–20,000 characters.")
    if not isinstance(scope, str) or scope not in {"ALL", "STUDENTS", "TEACHERS", "SECTION"}:
        abort(400, description="audience_scope must be ALL, STUDENTS, TEACHERS, or SECTION.")
    section_id = data.get("section_id")
    if (scope == "SECTION" and (not isinstance(section_id, int) or isinstance(section_id, bool))) or (scope != "SECTION" and section_id is not None):
        abort(400, description="section_id is required only for SECTION audience.")
    now = datetime.now(timezone.utc)
    expires_at = _instant(data.get("expires_at"), "expires_at")
    if expires_at is not None and expires_at <= now:
        abort(400, description="expires_at must be in the future.")
    db = database.get_session()
    if scope == "SECTION" and db.get(Section, section_id) is None:
        abort(404, description="Section was not found.")
    today = now.astimezone(ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])).date()
    announcement = Announcement(created_by=actor.user_id, title=title.strip(), body=body.strip(),
        audience_scope=scope, section_id=section_id, published_at=now, expires_at=expires_at)
    db.add(announcement)
    db.flush()
    users_query = select(User.user_id).where(User.is_active.is_(True))
    if scope in {"STUDENTS", "TEACHERS"}:
        users_query = users_query.join(UserRole, UserRole.user_id == User.user_id).where(UserRole.role == scope[:-1])
    elif scope == "SECTION":
        student_users = select(Student.user_id).join(StudentEnrollment,
            StudentEnrollment.student_id == Student.student_id).where(
            StudentEnrollment.section_id == section_id, StudentEnrollment.status == "ACTIVE",
            StudentEnrollment.starts_on <= today,
            or_(StudentEnrollment.ends_on.is_(None), StudentEnrollment.ends_on >= today))
        teacher_users = select(Teacher.user_id).join(TeachingAssignment,
            TeachingAssignment.teacher_id == Teacher.teacher_id).where(
            TeachingAssignment.section_id == section_id, TeachingAssignment.status == "ACTIVE",
            TeachingAssignment.starts_on <= today,
            or_(TeachingAssignment.ends_on.is_(None), TeachingAssignment.ends_on >= today))
        users_query = users_query.where(User.user_id.in_(student_users.union(teacher_users)))
    recipient_ids = db.scalars(users_query.order_by(User.user_id)).all()
    for recipient_id in recipient_ids:
        db.add(Notification(user_id=recipient_id, event_type="ANNOUNCEMENT_POSTED",
            title=announcement.title, message=announcement.body))
    db.add(OutboxEvent(event_type="ANNOUNCEMENT_PUBLISHED", aggregate_type="announcement",
        aggregate_id=str(announcement.announcement_id),
        payload={"audience_scope": scope, "recipient_count": len(recipient_ids)}))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        abort(409, description="Announcement could not be published with the selected audience.")
    return jsonify({"announcement_id": announcement.announcement_id, "audience_scope": scope,
        "section_id": section_id, "published_at": now.isoformat(), "recipient_count": len(recipient_ids)}), 201


@api_v1.get("/announcements")
def list_announcements():
    user, roles = current_identity()
    db = database.get_session()
    try:
        limit = int(request.args.get("limit", "50"))
        before_id = int(request.args["before_id"]) if "before_id" in request.args else None
    except ValueError:
        abort(400, description="limit and before_id must be integers.")
    if not 1 <= limit <= 100 or (before_id is not None and before_id < 1):
        abort(400, description="limit must be 1–100 and before_id must be positive.")
    now = datetime.now(timezone.utc)
    q = select(Announcement.announcement_id, Announcement.title, Announcement.body,
        Announcement.audience_scope, Announcement.section_id, Announcement.published_at,
        Announcement.expires_at).where(Announcement.published_at <= now,
        or_(Announcement.expires_at.is_(None), Announcement.expires_at > now))
    if "ADMIN" not in roles:
        clauses = [Announcement.audience_scope == "ALL"]
        if "STUDENT" in roles: clauses.append(Announcement.audience_scope == "STUDENTS")
        if "TEACHER" in roles: clauses.append(Announcement.audience_scope == "TEACHERS")
        today = now.astimezone(ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])).date()
        sections = _viewer_sections(db, user, roles, today)
        if sections: clauses.append((Announcement.audience_scope == "SECTION") & Announcement.section_id.in_(sections))
        q = q.where(or_(*clauses))
    if before_id is not None:
        q = q.where(Announcement.announcement_id < before_id)
    rows = db.execute(q.order_by(Announcement.announcement_id.desc()).limit(limit + 1)).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return jsonify({"items": [{"announcement_id": r.announcement_id, "title": r.title, "body": r.body,
        "audience_scope": r.audience_scope, "section_id": r.section_id,
        "published_at": r.published_at.isoformat(), "expires_at": r.expires_at.isoformat() if r.expires_at else None}
        for r in rows], "next_before_id": rows[-1].announcement_id if more and rows else None})
