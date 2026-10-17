"""Session authentication and current identity endpoints."""

from __future__ import annotations

import hashlib
import hmac
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from flask import abort, current_app, jsonify, request, session
from sqlalchemy import func, select
from sqlalchemy.orm import load_only
from werkzeug.security import check_password_hash

from app.api.v1 import api_v1
from app.extensions import database
from app.models import LoginAttempt, Student, StudentEnrollment, Teacher, User, UserRole, Section


def current_identity(*, required: bool = True):
    user_id = session.get("user_id")
    if not isinstance(user_id, int):
        if required:
            abort(401, description="Authentication is required.")
        return None
    db = database.get_session()
    user = db.scalar(select(User).options(load_only(User.user_id, User.login_id, User.email, User.is_active, User.updated_at)).where(User.user_id == user_id, User.is_active.is_(True)))
    if user is None:
        session.clear()
        if required:
            abort(401, description="Authentication is required.")
        return None
    roles = list(db.scalars(select(UserRole.role).where(UserRole.user_id == user.user_id).order_by(UserRole.role)))
    return user, roles


def require_roles(*allowed: str):
    identity = current_identity()
    if not set(identity[1]).intersection(allowed):
        abort(403, description="You do not have permission to perform this operation.")
    return identity


def csrf_token() -> str:
    cookie = request.cookies.get(current_app.config.get("SESSION_COOKIE_NAME", "session"), "")
    if not cookie:
        abort(401, description="Authentication is required.")
    key = current_app.secret_key
    if not key:
        abort(503, description="Authentication is not configured.")
    return hmac.new(key.encode(), b"csrf:" + cookie.encode(), hashlib.sha256).hexdigest()


def require_csrf() -> None:
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = csrf_token()
    if not hmac.compare_digest(supplied, expected):
        abort(403, description="A valid CSRF token is required.")


def _record_failure(db, key: str, now: datetime) -> bool:
    attempt = db.get(LoginAttempt, key, with_for_update=True)
    if attempt is None:
        attempt = LoginAttempt(login_id=key, failures=1, window_started_at=now)
        db.add(attempt)
        try:
            db.flush()
        except Exception:
            db.rollback()
            attempt = db.get(LoginAttempt, key, with_for_update=True)
            if attempt is None:
                raise
            attempt.failures += 1
    elif now - attempt.window_started_at > timedelta(seconds=current_app.config["AUTH_LOGIN_WINDOW_SECONDS"]):
        attempt.failures = 1
        attempt.window_started_at = now
        attempt.locked_until = None
    else:
        attempt.failures += 1
    if attempt.failures >= current_app.config["AUTH_LOGIN_MAX_FAILURES"]:
        attempt.locked_until = now + timedelta(seconds=current_app.config["AUTH_LOGIN_LOCK_SECONDS"])
    db.flush()
    return attempt.locked_until is not None and attempt.locked_until > now


@api_v1.post("/auth/login")
def login():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict) or set(payload) - {"login_id", "password", "active_role"}:
        abort(400, description="Provide login_id, password, and optionally an active_role from your memberships.")
    login_id, password = payload.get("login_id"), payload.get("password")
    if not isinstance(login_id, str) or not isinstance(password, str) or not login_id.strip() or len(login_id) > 100 or len(password) > 1024:
        abort(400, description="Provide a valid login_id and password.")
    key = login_id.strip().casefold()
    db = database.get_session()
    now = datetime.now(timezone.utc)
    attempt = db.get(LoginAttempt, key)
    if attempt and attempt.locked_until and attempt.locked_until > now:
        abort(429, description="Login is temporarily unavailable. Try again later.")
    user = db.scalar(select(User).where(func.lower(User.login_id) == key, User.is_active.is_(True)))
    if user is None or not check_password_hash(user.password_hash, password):
        locked = _record_failure(db, key, now)
        db.commit()
        abort(429 if locked else 401, description="Login is temporarily unavailable. Try again later." if locked else "Login failed.")
    if attempt is not None:
        db.delete(attempt)
    roles = list(db.scalars(select(UserRole.role).where(UserRole.user_id == user.user_id).order_by(UserRole.role)))
    active_role = payload.get("active_role")
    if active_role is not None and (not isinstance(active_role, str) or active_role not in roles):
        db.rollback()
        abort(403, description="The requested interface is not one of your active roles.")
    db.commit()
    session.clear()
    session.permanent = True
    session["user_id"] = user.user_id
    if active_role:
        session["active_role"] = active_role
    return jsonify({"user_id": user.user_id, "roles": roles, "active_role": active_role}), 200


@api_v1.get("/auth/me")
def me():
    user, roles = current_identity()
    db = database.get_session()
    student = db.scalar(select(Student).where(Student.user_id == user.user_id))
    teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.user_id))
    return jsonify({
        "user": {"user_id": user.user_id, "login_id": user.login_id, "email": user.email, "roles": roles,
                 "active_role": session.get("active_role") if session.get("active_role") in roles else None},
        "profile": ({"type": "student", "student_id": student.student_id, "erp_id": student.erp_id, "full_name": student.full_name} if student else
                    {"type": "teacher", "teacher_id": teacher.teacher_id, "faculty_code": teacher.faculty_code, "full_name": teacher.full_name, "department": teacher.department} if teacher else None),
    })


@api_v1.get("/students/me")
def student_me():
    user, roles = require_roles("STUDENT")
    db = database.get_session()
    student = db.scalar(select(Student).where(Student.user_id == user.user_id))
    if student is None:
        abort(404, description="Student profile was not found.")
    today = datetime.now(ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])).date()
    enrollment = db.scalar(
        select(StudentEnrollment)
        .where(
            StudentEnrollment.student_id == student.student_id,
            StudentEnrollment.status == "ACTIVE",
            StudentEnrollment.starts_on <= today,
            (StudentEnrollment.ends_on.is_(None) | (StudentEnrollment.ends_on >= today)),
        )
        .order_by(StudentEnrollment.starts_on.desc())
    )
    section = db.get(Section, enrollment.section_id) if enrollment else None
    return jsonify({
        "student_id": student.student_id,
        "erp_id": student.erp_id,
        "full_name": student.full_name,
        "enrollment": ({"section_id": section.section_id, "course_id": section.course_id, "academic_year_id": section.academic_year_id, "semester": section.semester, "section_code": section.section_code, "shift": section.shift, "starts_on": enrollment.starts_on.isoformat(), "ends_on": enrollment.ends_on.isoformat() if enrollment.ends_on else None} if enrollment and section else None),
    })


@api_v1.get("/teachers/me")
def teacher_me():
    user, roles = require_roles("TEACHER")
    db = database.get_session()
    teacher = db.scalar(select(Teacher).where(Teacher.user_id == user.user_id))
    if teacher is None:
        abort(404, description="Teacher profile was not found.")
    return jsonify({"teacher_id": teacher.teacher_id, "faculty_code": teacher.faculty_code, "full_name": teacher.full_name, "department": teacher.department})


@api_v1.get("/auth/csrf")
def get_csrf():
    current_identity()
    return jsonify({"csrf_token": csrf_token()})


@api_v1.post("/auth/logout")
def logout():
    current_identity()
    require_csrf()
    session.clear()
    return jsonify({"status": "logged_out"})

