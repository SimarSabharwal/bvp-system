"""Bounded administrative APIs for academic master data."""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from flask import abort, current_app, jsonify, request
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.inspection import inspect
from sqlalchemy.orm import load_only
from sqlalchemy.sql.sqltypes import Boolean, Date as SQLDate, Integer as SQLInteger, Numeric as SQLNumeric, String as SQLString
from werkzeug.security import generate_password_hash

from app.api.v1 import api_v1
from app.api.v1.auth import require_csrf, require_roles
from app.extensions import database
from app.models import (
    AcademicYear, Course, Room, RoomFeature, Section, SectionSubject, Student,
    StudentEnrollment, Subject, Teacher, TeacherSubject, TeachingAssignment,
    User, UserRole,
)


SPECS = {
    "academic-years": (AcademicYear, "academic_year_id", ("name", "starts_on", "ends_on", "status"), ("academic_year_id", "name", "starts_on", "ends_on", "status"), ("name", "status")),
    "courses": (Course, "course_id", ("code", "name"), ("course_id", "code", "name"), ("code",)),
    "sections": (Section, "section_id", ("course_id", "academic_year_id", "semester", "section_code", "shift", "capacity"), ("section_id", "course_id", "academic_year_id", "semester", "section_code", "shift", "capacity"), ("course_id", "academic_year_id", "semester", "shift")),
    "subjects": (Subject, "subject_id", ("course_id", "semester", "curriculum_version", "subject_type", "code", "name", "requires_lab"), ("subject_id", "course_id", "semester", "curriculum_version", "subject_type", "code", "name", "requires_lab"), ("code", "course_id")),
    "section-subjects": (SectionSubject, ("section_id", "subject_id"), ("section_id", "subject_id", "required_lecture_hours", "required_lab_hours"), ("section_id", "subject_id", "required_lecture_hours", "required_lab_hours"), ("section_id", "subject_id")),
    "teacher-subjects": (TeacherSubject, ("teacher_id", "subject_id"), ("teacher_id", "subject_id"), ("teacher_id", "subject_id"), ("teacher_id", "subject_id")),
    "student-enrollments": (StudentEnrollment, "enrollment_id", ("student_id", "section_id", "starts_on", "ends_on", "status"), ("enrollment_id", "student_id", "section_id", "starts_on", "ends_on", "status"), ("student_id", "section_id", "status")),
    "teaching-assignments": (TeachingAssignment, "assignment_id", ("teacher_id", "subject_id", "section_id", "starts_on", "ends_on", "status"), ("assignment_id", "teacher_id", "subject_id", "section_id", "starts_on", "ends_on", "status"), ("teacher_id", "subject_id", "section_id", "status")),
    "rooms": (Room, "room_id", ("building", "room_number", "capacity", "room_type", "status"), ("room_id", "building", "room_number", "capacity", "room_type", "status"), ("building", "room_type", "status")),
    "room-features": (RoomFeature, ("room_id", "feature_code"), ("room_id", "feature_code"), ("room_id", "feature_code"), ("room_id", "feature_code")),
}

USER_FIELDS = ("user_id", "login_id", "email", "is_active", "created_at", "updated_at")


def _encode(value):
    if isinstance(value, (date,)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def _row(obj, columns):
    return {name: _encode(getattr(obj, name)) for name in columns}


def _body(allowed):
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        abort(400, description="A JSON object is required.")
    unknown = set(payload) - set(allowed)
    if unknown:
        abort(400, description="Unsupported fields: " + ", ".join(sorted(unknown)))
    return payload


def _validated_values(model, payload, *, require_required=False):
    """Convert and validate primitive JSON values according to mapped columns."""
    columns = {column.key: column for column in inspect(model).columns}
    output = {}
    for name, value in payload.items():
        column_type = columns[name].type
        if value is None:
            if not columns[name].nullable:
                abort(400, description=f"{name} cannot be null.")
            output[name] = None
        elif isinstance(column_type, SQLDate):
            try:
                output[name] = date.fromisoformat(value) if isinstance(value, str) else value
                if not isinstance(output[name], date):
                    raise ValueError()
            except (TypeError, ValueError):
                abort(400, description=f"{name} must be an ISO date.")
        elif isinstance(column_type, SQLInteger):
            if not isinstance(value, int) or isinstance(value, bool):
                abort(400, description=f"{name} must be an integer.")
            output[name] = value
        elif isinstance(column_type, SQLNumeric):
            try:
                output[name] = Decimal(str(value))
            except (InvalidOperation, ValueError):
                abort(400, description=f"{name} must be numeric.")
        elif isinstance(column_type, Boolean):
            if not isinstance(value, bool):
                abort(400, description=f"{name} must be a boolean.")
            output[name] = value
        elif isinstance(column_type, SQLString) or hasattr(column_type, "enums"):
            if not isinstance(value, str):
                abort(400, description=f"{name} must be a string.")
            if getattr(column_type, "length", None) and len(value) > column_type.length:
                abort(400, description=f"{name} is too long.")
            if hasattr(column_type, "enums") and value not in column_type.enums:
                abort(400, description=f"{name} has an unsupported value.")
            output[name] = value
        else:
            output[name] = value
    if require_required:
        for name, column in columns.items():
            if name not in payload and not column.nullable and column.default is None and column.server_default is None and not column.autoincrement:
                abort(400, description=f"{name} is required.")
    return output


def _filter_value(model, field, value):
    column_type = inspect(model).columns[field].type
    if isinstance(column_type, SQLInteger):
        try:
            return int(value)
        except (TypeError, ValueError):
            abort(400, description=f"{field} must be an integer.")
    if isinstance(column_type, Boolean):
        if value not in {"true", "false"}:
            abort(400, description=f"{field} must be true or false.")
        return value == "true"
    return _validated_values(model, {field: value})[field]


def _object_or_404(db, model, key, value):
    criteria = _criteria(model, key, value)
    obj = db.scalar(select(model).options(load_only(*_write_columns(model, key))).where(*criteria))
    if obj is None:
        abort(404, description="Resource was not found.")
    return obj


def _criteria(model, key, value):
    parts = value.split(",") if isinstance(key, tuple) else [value]
    keys = key if isinstance(key, tuple) else (key,)
    if len(parts) != len(keys):
        abort(404)
    criteria = []
    for field, part in zip(keys, parts):
        try:
            part = int(part) if field.endswith("_id") else part
        except ValueError:
            abort(404)
        criteria.append(getattr(model, field) == part)
    return criteria


def _write_columns(model, key):
    # Keep the session credential out of ordinary admin updates.
    selected = set(key if isinstance(key, tuple) else (key,))
    selected.update(column.key for column in inspect(model).columns if column.key not in {"password_hash"})
    return [getattr(model, name) for name in selected]


def _commit(db):
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        abort(409, description="The change conflicts with existing data or a relationship constraint.")


@api_v1.get("/admin/<resource>")
def list_master_data(resource):
    require_roles("ADMIN")
    if resource == "users":
        model, key, writable, columns, filterable = User, "user_id", (), USER_FIELDS, ("is_active",)
    elif resource == "students":
        model, key, writable, columns, filterable = Student, "student_id", (), ("student_id", "erp_id", "full_name", "user_id"), ("erp_id",)
    elif resource == "teachers":
        model, key, writable, columns, filterable = Teacher, "teacher_id", (), ("teacher_id", "faculty_code", "full_name", "department", "user_id"), ("faculty_code", "department")
    elif resource in SPECS:
        model, key, writable, columns, filterable = SPECS[resource]
    else:
        abort(404)
    params = request.args.to_dict(flat=True)
    allowed_params = set(filterable) | {"limit", "offset", "fields"}
    if set(params) - allowed_params:
        abort(400, description="Unsupported filter or list parameter.")
    try:
        limit = int(params.get("limit", 25))
        offset = int(params.get("offset", 0))
    except ValueError:
        abort(400, description="limit and offset must be integers.")
    if not 1 <= limit <= int(current_app.config["API_MAX_PAGE_SIZE"]) or offset < 0:
        abort(400, description="Pagination is outside the supported range.")
    requested = tuple(params.get("fields", "").split(",")) if params.get("fields") else tuple(columns)
    if not requested or set(requested) - set(columns):
        abort(400, description="Requested fields are not available for this resource.")
    db = database.get_session()
    query = select(*(getattr(model, name) for name in requested))
    for field in filterable:
        if field in params:
            value = _filter_value(model, field, params[field])
            query = query.where(getattr(model, field) == value)
    key_columns = key if isinstance(key, tuple) else (key,)
    query = query.order_by(*(getattr(model, name) for name in key_columns)).limit(limit).offset(offset)
    items = [{name: _encode(value) for name, value in row.items()} for row in db.execute(query).mappings()]
    return jsonify({"items": items, "page": {"limit": limit, "offset": offset, "next_offset": offset + limit if len(items) == limit else None}})


@api_v1.post("/admin/<resource>")
def create_master_data(resource):
    require_roles("ADMIN")
    require_csrf()
    db = database.get_session()
    if resource in {"students", "teachers"}:
        is_student = resource == "students"
        fields = {"login_id", "password", "email", "user_id", "erp_id", "full_name"} if is_student else {"login_id", "password", "email", "user_id", "faculty_code", "full_name", "department"}
        payload = _body(fields)
        user_id, login_id, password, full_name = payload.get("user_id"), payload.get("login_id"), payload.get("password"), payload.get("full_name")
        person_code = payload.get("erp_id" if is_student else "faculty_code")
        email, department = payload.get("email"), payload.get("department")
        if not all(isinstance(value, str) and value.strip() for value in (full_name, person_code)) or len(full_name) > 200 or len(person_code) > 100:
            abort(400, description="Provide non-empty profile identity fields.")
        if email is not None and (not isinstance(email, str) or len(email) > 320):
            abort(400, description="email must be a string up to 320 characters.")
        if not is_student and department is not None and (not isinstance(department, str) or len(department) > 160):
            abort(400, description="department must be a string up to 160 characters.")
        if user_id is not None:
            if not isinstance(user_id, int) or isinstance(user_id, bool) or login_id is not None or password is not None or payload.get("email") is not None:
                abort(400, description="When linking a profile, provide only user_id and profile fields.")
            user = db.get(User, user_id)
            if user is None or not user.is_active:
                abort(404, description="An active user account was not found.")
            existing_profile = db.scalar(select(Student.student_id if is_student else Teacher.teacher_id).where((Student.user_id if is_student else Teacher.user_id) == user.user_id))
            if existing_profile is not None:
                abort(409, description="This account already has that profile type.")
        else:
            if not isinstance(login_id, str) or not login_id.strip() or len(login_id) > 100 or not isinstance(password, str) or not 12 <= len(password) <= 1024:
                abort(400, description="Provide a login ID and a password of at least 12 characters.")
            user = User(login_id=login_id.strip(), email=payload.get("email"), password_hash=generate_password_hash(password))
            db.add(user)
            db.flush()
        role = "STUDENT" if is_student else "TEACHER"
        if db.get(UserRole, (user.user_id, role)) is None:
            db.add(UserRole(user_id=user.user_id, role=role))
        person = Student(user_id=user.user_id, erp_id=person_code.strip(), full_name=full_name.strip()) if is_student else Teacher(user_id=user.user_id, faculty_code=person_code.strip(), full_name=full_name.strip(), department=payload.get("department"))
        db.add(person)
        _commit(db)
        return jsonify({"id": person.student_id if is_student else person.teacher_id, "user_id": user.user_id, "status": "created", "role": role}), 201
    if resource == "users":
        payload = _body({"login_id", "password", "email", "roles"})
        roles = payload.get("roles")
        valid_roles = {"STUDENT", "TEACHER", "ADMIN"}
        if (not isinstance(payload.get("login_id"), str) or not payload["login_id"].strip() or len(payload["login_id"]) > 100
                or not isinstance(payload.get("password"), str) or not 12 <= len(payload["password"]) <= 1024
                or not isinstance(roles, list) or not roles or any(not isinstance(role, str) or role not in valid_roles for role in roles)):
            abort(400, description="Provide login_id, a password of at least 12 characters, and one or more valid roles.")
        if payload.get("email") is not None and (not isinstance(payload["email"], str) or len(payload["email"]) > 320):
            abort(400, description="email must be a string up to 320 characters.")
        user = User(login_id=payload["login_id"].strip(), email=payload.get("email"), password_hash=generate_password_hash(payload["password"]))
        db.add(user)
        db.flush()
        db.add_all([UserRole(user_id=user.user_id, role=role) for role in set(roles)])
        _commit(db)
        return jsonify({"id": user.user_id, "status": "created"}), 201
    spec = SPECS.get(resource)
    if spec is None:
        abort(404)
    model, key, writable, columns, filterable = spec
    payload = _body(writable)
    if resource == "section-subjects":
        section = db.get(Section, payload.get("section_id"))
        subject = db.get(Subject, payload.get("subject_id"))
        if section is not None and subject is not None and (subject.course_id != section.course_id or subject.semester not in (None, section.semester)):
            abort(422, description="The subject course and semester must match the section.")
    obj = model(**_validated_values(model, payload, require_required=True))
    db.add(obj)
    _commit(db)
    identifier = getattr(obj, key) if isinstance(key, str) else _row(obj, key)
    return jsonify({"id": identifier, "status": "created"}), 201


@api_v1.route("/admin/<resource>/<path:resource_id>", methods=["GET", "PATCH", "DELETE"])
def manage_master_data(resource, resource_id):
    actor, _ = require_roles("ADMIN")
    db = database.get_session()
    if resource == "users":
        model, key, writable, columns = User, "user_id", {"email", "is_active", "password", "roles"}, USER_FIELDS
    elif resource == "students":
        model, key, writable, columns = Student, "student_id", {"erp_id", "full_name"}, ("student_id", "erp_id", "full_name", "user_id")
    elif resource == "teachers":
        model, key, writable, columns = Teacher, "teacher_id", {"faculty_code", "full_name", "department"}, ("teacher_id", "faculty_code", "full_name", "department", "user_id")
    elif resource in SPECS:
        model, key, writable, columns, _ = SPECS[resource]
    else:
        abort(404)
    if request.method == "GET":
        fields = tuple(request.args.get("fields", "").split(",")) if request.args.get("fields") else tuple(columns)
        if set(request.args) - {"fields"} or not fields or set(fields) - set(columns):
            abort(400, description="Requested fields are not available for this resource.")
        criteria = _criteria(model, key, resource_id)
        row = db.execute(select(*(getattr(model, name) for name in fields)).where(*criteria)).mappings().one_or_none()
        if row is None:
            abort(404, description="Resource was not found.")
        if resource == "users":
            data = {name: _encode(value) for name, value in row.items()}
            data["roles"] = list(db.scalars(select(UserRole.role).where(UserRole.user_id == data["user_id"]).order_by(UserRole.role)))
            return jsonify(data)
        return jsonify({name: _encode(value) for name, value in row.items()})
    require_csrf()
    if request.method == "DELETE":
        if resource in {"users", "students", "teachers"}:
            abort(409, description="User and profile records are retained for relationship integrity; deactivate the linked account instead.")
        try:
            result = db.execute(delete(model).where(*_criteria(model, key, resource_id)))
            db.commit()
        except IntegrityError:
            db.rollback()
            abort(409, description="Resource is referenced by existing records and cannot be deleted.")
        if result.rowcount == 0:
            abort(404, description="Resource was not found.")
        return jsonify({"id": resource_id, "status": "deleted"})
    allowed = writable if resource in {"users", "students", "teachers"} else writable
    payload = _body(allowed)
    obj = _object_or_404(db, model, key, resource_id)
    if resource == "users" and "password" in payload:
        if not isinstance(payload["password"], str) or not 12 <= len(payload["password"]) <= 1024:
            abort(400, description="Password must contain 12 to 1024 characters.")
        obj.password_hash = generate_password_hash(payload.pop("password"))
    roles_present = resource == "users" and "roles" in payload
    roles = payload.pop("roles", None) if resource == "users" else None
    if roles_present:
        valid_roles = {"STUDENT", "TEACHER", "ADMIN"}
        if not isinstance(roles, list) or not roles or any(not isinstance(role, str) or role not in valid_roles for role in roles):
            abort(400, description="roles must contain one or more valid role names.")
        if obj.user_id == actor.user_id and "ADMIN" not in roles:
            abort(409, description="An administrator cannot remove their own admin role.")
        if "ADMIN" not in roles and "ADMIN" in db.scalars(select(UserRole.role).where(UserRole.user_id == obj.user_id)):
            other_admin = db.scalar(select(UserRole.user_id).join(User, User.user_id == UserRole.user_id).where(UserRole.role == "ADMIN", User.user_id != obj.user_id, User.is_active.is_(True)).limit(1))
            if other_admin is None:
                abort(409, description="The final active administrator role cannot be removed.")
        db.query(UserRole).filter(UserRole.user_id == obj.user_id).delete(synchronize_session=False)
        db.add_all([UserRole(user_id=obj.user_id, role=role) for role in set(roles)])
    if resource == "users" and "is_active" in payload and not isinstance(payload["is_active"], bool):
        abort(400, description="is_active must be a boolean.")
    if resource == "users" and payload.get("is_active") is False and "ADMIN" in db.scalars(select(UserRole.role).where(UserRole.user_id == obj.user_id)):
        other_admin = db.scalar(select(UserRole.user_id).join(User, User.user_id == UserRole.user_id).where(UserRole.role == "ADMIN", User.user_id != obj.user_id, User.is_active.is_(True)).limit(1))
        if other_admin is None:
            abort(409, description="The final active administrator cannot be deactivated.")
    for name, value in payload.items():
        setattr(obj, name, _validated_values(model, {name: value})[name])
    if resource == "section-subjects":
        section = db.get(Section, obj.section_id)
        subject = db.get(Subject, obj.subject_id)
        if section is None or subject is None or subject.course_id != section.course_id or subject.semester not in (None, section.semester):
            abort(422, description="The subject course and semester must match the section.")
    if resource == "users":
        obj.updated_at = datetime.now(timezone.utc)
    _commit(db)
    identifier = getattr(obj, key) if isinstance(key, str) else _row(obj, key)
    return jsonify({"id": identifier, "status": "updated"})


@api_v1.get("/lookups/<resource>")
def lookup(resource):
    user, roles = require_roles("ADMIN", "TEACHER", "STUDENT")
    if resource not in {"academic-years", "courses", "sections", "subjects", "rooms", "teachers"}:
        abort(404)
    # Lookup fields are intentionally small and omit all student identities and account data.
    model, _, _, columns, filters = SPECS[resource] if resource in SPECS else (None, None, None, None, None)
    if resource == "courses": model, columns, filters = Course, ("course_id", "code", "name"), ("code",)
    if resource == "sections": model, columns, filters = Section, ("section_id", "course_id", "academic_year_id", "semester", "section_code", "shift"), ("course_id", "academic_year_id", "semester")
    if resource == "subjects": model, columns, filters = Subject, ("subject_id", "course_id", "semester", "curriculum_version", "subject_type", "code", "name", "requires_lab"), ("code", "course_id")
    if resource == "rooms": model, columns, filters = Room, ("room_id", "building", "room_number", "room_type", "status"), ("status",)
    if resource == "teachers":
        model, columns, filters = Teacher, ("teacher_id", "faculty_code", "full_name", "department"), ("department",)
        if "ADMIN" not in roles:
            columns = ("teacher_id", "full_name", "department")
    if resource == "academic-years": model, columns, filters = AcademicYear, ("academic_year_id", "name", "starts_on", "ends_on", "status"), ("status",)
    if set(request.args) - set(filters):
        abort(400, description="Unsupported lookup filter.")
    db = database.get_session()
    query = select(*(getattr(model, name) for name in columns))
    for name in filters:
        if name in request.args:
            value = _filter_value(model, name, request.args[name])
            query = query.where(getattr(model, name) == value)
    items = [{name: _encode(value) for name, value in row.items()} for row in db.execute(query.order_by(getattr(model, columns[0])).limit(100)).mappings()]
    return jsonify({"items": items})

