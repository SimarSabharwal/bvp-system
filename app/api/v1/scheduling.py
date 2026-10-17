"""Timetable publication, dated session, availability, and calendar APIs."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from flask import abort, current_app, jsonify, request, session
from sqlalchemy import delete, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import load_only

from app.api.v1 import api_v1
from app.api.v1.auth import current_identity, require_csrf, require_roles
from app.extensions import database
from app.models import (AcademicEvent, ClassSession, Room, RoomAvailability, Section,
                        Student, StudentEnrollment, Subject, Teacher, TeacherAvailability,
                        TeachingAssignment, TimetableEntry, TimetableVersion, User,
                        UserRole, AuditEvent, OutboxEvent)

MAX_RANGE_DAYS = 31

def _json():
    value = request.get_json(silent=True)
    if not isinstance(value, dict): abort(400, description="A JSON object is required.")
    return value

def _date(value, field):
    try: return date.fromisoformat(value)
    except (TypeError, ValueError): abort(400, description=f"{field} must be an ISO date.")

def _instant(value, field):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None: parsed = parsed.replace(tzinfo=ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"]))
        return parsed
    except (TypeError, ValueError, AttributeError): abort(400, description=f"{field} must be an ISO datetime.")

def _commit(db):
    try: db.commit()
    except IntegrityError:
        db.rollback(); abort(409, description="The requested change conflicts with current academic data or schedule constraints.")

def _room_ok(db, room_id, section_id, subject_id):
    row = db.execute(select(Room.capacity, Room.room_type, Room.status, Section.capacity, Subject.requires_lab)
                     .select_from(Room).join(Section, Section.section_id == section_id).join(Subject, Subject.subject_id == subject_id)
                     .where(Room.room_id == room_id)).one_or_none()
    return bool(row and row.status == "ACTIVE" and row.capacity is not None and row[3] is not None and row.capacity >= row[3]
                and (not row.requires_lab or row.room_type in {"COMPUTER_LAB", "SCIENCE_LAB"}))

def _validate_entry(db, version, data, entry_id=None):
    allowed={"teaching_assignment_id","room_id","weekday","starts_at_local","ends_at_local"}
    if set(data)-allowed or not allowed <= set(data): abort(400, description="Entry requires assignment, room, weekday, start and end.")
    try:
        if isinstance(data["weekday"],bool) or isinstance(data["teaching_assignment_id"],bool) or isinstance(data["room_id"],bool): raise ValueError
        weekday=int(data["weekday"]); start=time.fromisoformat(data["starts_at_local"]); end=time.fromisoformat(data["ends_at_local"])
        assignment_id=int(data["teaching_assignment_id"]); room_id=int(data["room_id"])
    except (TypeError,ValueError): abort(400, description="Invalid timetable entry values.")
    if weekday not in range(7) or start.tzinfo is not None or end.tzinfo is not None or start >= end: abort(400, description="Weekday or local time range is invalid.")
    assignment=db.scalar(select(TeachingAssignment).where(TeachingAssignment.assignment_id==assignment_id,
        TeachingAssignment.section_id==version.section_id,TeachingAssignment.status=="ACTIVE",
        TeachingAssignment.starts_on<=version.effective_to,
        or_(TeachingAssignment.ends_on.is_(None),TeachingAssignment.ends_on>=version.effective_from)))
    if assignment is None: abort(422, description="Assignment must be active for this section and effective period.")
    section = db.get(Section, version.section_id)
    subject = db.get(Subject, assignment.subject_id)
    if subject is None or section is None or subject.course_id != section.course_id or subject.semester not in (None, section.semester):
        abort(422, description="The assigned subject must belong to the section's course and semester.")
    if not _room_ok(db, room_id, assignment.section_id, assignment.subject_id): abort(422, description="Room is inactive, undersized, or incompatible with this subject.")
    conflicts=db.scalars(select(TimetableEntry).where(TimetableEntry.timetable_version_id==version.timetable_version_id,
        TimetableEntry.entry_id!= (entry_id or -1),TimetableEntry.weekday==weekday,
        TimetableEntry.starts_at_local<end,TimetableEntry.ends_at_local>start)).all()
    for other in conflicts:
        if other.section_id==version.section_id or other.teacher_id==assignment.teacher_id or other.room_id==room_id:
            abort(409, description="Recurring section, teacher, or room overlap in this draft.")
    return dict(timetable_version_id=version.timetable_version_id,section_id=version.section_id,
        teaching_assignment_id=assignment.assignment_id,teacher_id=assignment.teacher_id,subject_id=assignment.subject_id,
        room_id=room_id,weekday=weekday,starts_at_local=start,ends_at_local=end)

@api_v1.post("/admin/timetable-versions")
def create_version():
    actor,_=require_roles("ADMIN"); require_csrf(); data=_json()
    if set(data)!={"section_id","name","effective_from","effective_to"}: abort(400,description="Provide section_id, name and effective dates.")
    start,end=_date(data["effective_from"],"effective_from"),_date(data["effective_to"],"effective_to")
    if start>end: abort(400,description="effective_from must not follow effective_to.")
    db=database.get_session(); obj=TimetableVersion(section_id=data["section_id"],name=data["name"],status="DRAFT",effective_from=start,effective_to=end)
    db.add(obj); _commit(db); return jsonify({"timetable_version_id":obj.timetable_version_id,"status":obj.status}),201

@api_v1.route("/admin/timetable-versions/<int:version_id>",methods=["GET","PATCH"])
def timetable_version(version_id):
    require_roles("ADMIN"); db=database.get_session(); obj=db.get(TimetableVersion,version_id)
    if obj is None: abort(404)
    if request.method=="GET":
        entries=db.scalars(select(TimetableEntry).where(TimetableEntry.timetable_version_id==version_id).order_by(TimetableEntry.weekday,TimetableEntry.starts_at_local)).all()
        return jsonify({"timetable_version_id":obj.timetable_version_id,"section_id":obj.section_id,"name":obj.name,"status":obj.status,"effective_from":obj.effective_from.isoformat(),"effective_to":obj.effective_to.isoformat(),"entries":[{"entry_id":e.entry_id,"teaching_assignment_id":e.teaching_assignment_id,"teacher_id":e.teacher_id,"subject_id":e.subject_id,"room_id":e.room_id,"weekday":e.weekday,"starts_at_local":e.starts_at_local.isoformat(),"ends_at_local":e.ends_at_local.isoformat()} for e in entries]})
    require_csrf(); data=_json()
    if obj.status!="DRAFT" or set(data)-{"name","effective_from","effective_to"}: abort(409,description="Only draft version name/effective dates can be changed.")
    if "name" in data: obj.name=data["name"]
    if "effective_from" in data: obj.effective_from=_date(data["effective_from"],"effective_from")
    if "effective_to" in data: obj.effective_to=_date(data["effective_to"],"effective_to")
    if obj.effective_from>obj.effective_to: abort(400,description="Invalid effective period.")
    _commit(db); return jsonify({"timetable_version_id":obj.timetable_version_id,"status":obj.status})

@api_v1.delete("/admin/timetable-versions/<int:version_id>")
def delete_timetable_version(version_id):
    require_roles("ADMIN"); require_csrf(); db=database.get_session(); obj=db.scalar(select(TimetableVersion).where(TimetableVersion.timetable_version_id==version_id).with_for_update())
    if obj is None: abort(404)
    if obj.status!="DRAFT": abort(409,description="Only draft timetable versions can be deleted; published history is retained.")
    db.execute(delete(TimetableEntry).where(TimetableEntry.timetable_version_id==version_id)); db.delete(obj); _commit(db)
    return jsonify({"status":"deleted"})

@api_v1.route("/admin/timetable-versions/<int:version_id>/entries",methods=["POST"])
def create_entry(version_id):
    require_roles("ADMIN"); require_csrf(); db=database.get_session(); version=db.get(TimetableVersion,version_id)
    if version is None: abort(404)
    if version.status!="DRAFT": abort(409,description="Published timetable entries are immutable; create a new version.")
    obj=TimetableEntry(**_validate_entry(db,version,_json())); db.add(obj); _commit(db)
    return jsonify({"entry_id":obj.entry_id,"status":"created"}),201

@api_v1.delete("/admin/timetable-entries/<int:entry_id>")
def delete_entry(entry_id):
    require_roles("ADMIN"); require_csrf(); db=database.get_session(); obj=db.get(TimetableEntry,entry_id)
    if obj is None: abort(404)
    version=db.get(TimetableVersion,obj.timetable_version_id)
    if version.status!="DRAFT": abort(409,description="Published timetable entries are immutable.")
    db.delete(obj); _commit(db); return jsonify({"status":"deleted"})

@api_v1.patch("/admin/timetable-entries/<int:entry_id>")
def update_entry(entry_id):
    require_roles("ADMIN"); require_csrf(); db=database.get_session(); obj=db.scalar(select(TimetableEntry).where(TimetableEntry.entry_id==entry_id).with_for_update())
    if obj is None: abort(404)
    version=db.get(TimetableVersion,obj.timetable_version_id)
    if version.status!="DRAFT": abort(409,description="Published timetable entries are immutable; create a new version.")
    allowed={"teaching_assignment_id","room_id","weekday","starts_at_local","ends_at_local"}; data=_json()
    if not data or set(data)-allowed: abort(400,description="Provide one or more supported timetable entry fields.")
    merged={"teaching_assignment_id":obj.teaching_assignment_id,"room_id":obj.room_id,"weekday":obj.weekday,"starts_at_local":obj.starts_at_local.isoformat(),"ends_at_local":obj.ends_at_local.isoformat()}; merged.update(data)
    values=_validate_entry(db,version,merged,entry_id)
    for key,value in values.items():
        if key not in {"timetable_version_id","section_id"}: setattr(obj,key,value)
    _commit(db); return jsonify({"entry_id":entry_id,"status":"updated"})

@api_v1.post("/admin/timetable-versions/<int:version_id>/publish")
def publish_timetable(version_id):
    actor,_=require_roles("ADMIN"); require_csrf(); db=database.get_session()
    version=db.scalar(select(TimetableVersion).where(TimetableVersion.timetable_version_id==version_id).with_for_update())
    if version is None: abort(404)
    if version.status!="DRAFT": abort(409,description="Only a draft can be published.")
    entries=db.scalars(select(TimetableEntry).where(TimetableEntry.timetable_version_id==version_id).order_by(TimetableEntry.entry_id)).all()
    if not entries: abort(422,description="A timetable must contain at least one entry before publication.")
    tz=ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"]); events=db.scalars(select(AcademicEvent).where(AcademicEvent.event_type.in_(["HOLIDAY","EXAM"]),AcademicEvent.starts_at<datetime.combine(version.effective_to+timedelta(days=1),time.min,tzinfo=tz),AcademicEvent.ends_at>datetime.combine(version.effective_from,time.min,tzinfo=tz),or_(AcademicEvent.section_id.is_(None),AcademicEvent.section_id==version.section_id))).all()
    generated=0; day=version.effective_from
    while day<=version.effective_to:
        for entry in entries:
            if day.weekday()!=entry.weekday: continue
            start=datetime.combine(day,entry.starts_at_local,tz); end=datetime.combine(day,entry.ends_at_local,tz)
            if any(ev.starts_at<end and ev.ends_at>start for ev in events): continue
            if not _room_ok(db,entry.room_id,entry.section_id,entry.subject_id): abort(422,description="Entry room is no longer suitable.")
            assignment=db.get(TeachingAssignment,entry.teaching_assignment_id)
            if assignment is None or assignment.status!="ACTIVE" or assignment.starts_on>day or (assignment.ends_on and assignment.ends_on<day): abort(422,description="An entry assignment is not active on every generated date.")
            if db.scalar(select(TeacherAvailability.availability_id).where(TeacherAvailability.teacher_id==assignment.teacher_id,TeacherAvailability.status=="UNAVAILABLE",TeacherAvailability.starts_at<end,TeacherAvailability.ends_at>start)):
                abort(422,description="A teacher is unavailable during a generated session.")
            if db.scalar(select(RoomAvailability.room_availability_id).where(RoomAvailability.room_id==entry.room_id,RoomAvailability.status=="UNAVAILABLE",RoomAvailability.starts_at<end,RoomAvailability.ends_at>start)):
                abort(422,description="A room is unavailable during a generated session.")
            db.add(ClassSession(entry_id=entry.entry_id,pending_lecture_id=None,section_id=entry.section_id,session_date=day,original_assignment_id=assignment.assignment_id,original_subject_id=assignment.subject_id,original_teacher_id=assignment.teacher_id,original_room_id=entry.room_id,current_assignment_id=assignment.assignment_id,current_subject_id=assignment.subject_id,current_teacher_id=assignment.teacher_id,current_room_id=entry.room_id,original_starts_at=start,original_ends_at=end,current_starts_at=start,current_ends_at=end,status="SCHEDULED")); generated+=1
        day+=timedelta(days=1)
    version.status="PUBLISHED"; version.published_by=actor.user_id
    db.add(AuditEvent(actor_id=actor.user_id,entity_type="timetable_version",entity_id=str(version_id),action="PUBLISHED",details={"generated_sessions":generated}))
    db.add(OutboxEvent(event_type="TIMETABLE_PUBLISHED",aggregate_type="timetable_version",aggregate_id=str(version_id),payload={"section_id":version.section_id,"session_count":generated}))
    _commit(db); return jsonify({"timetable_version_id":version_id,"status":"PUBLISHED","generated_sessions":generated})

@api_v1.route("/admin/academic-events",methods=["GET","POST"])
def academic_events():
    actor,_=require_roles("ADMIN"); db=database.get_session()
    if request.method=="GET":
        rows=db.scalars(select(AcademicEvent).order_by(AcademicEvent.starts_at).limit(100)).all()
        return jsonify({"items":[{"event_id":e.event_id,"section_id":e.section_id,"event_type":e.event_type,"starts_at":e.starts_at.isoformat(),"ends_at":e.ends_at.isoformat(),"title":e.title} for e in rows]})
    require_csrf(); d=_json(); allowed={"section_id","event_type","starts_at","ends_at","title"}
    if set(d)!=allowed or d["event_type"] not in {"HOLIDAY","EXAM","OTHER"}: abort(400,description="Invalid academic event fields.")
    obj=AcademicEvent(section_id=d["section_id"],event_type=d["event_type"],starts_at=_instant(d["starts_at"],"starts_at"),ends_at=_instant(d["ends_at"],"ends_at"),title=d["title"]); db.add(obj); _commit(db); return jsonify({"event_id":obj.event_id}),201

@api_v1.route("/admin/teacher-availability",methods=["GET","POST"])
def teacher_availability(): return _availability("teacher")
@api_v1.route("/admin/room-availability",methods=["GET","POST"])
def room_availability(): return _availability("room")

@api_v1.patch("/admin/teacher-availability/<int:availability_id>")
def change_teacher_availability(availability_id): return _change_availability("teacher",availability_id)

@api_v1.patch("/admin/room-availability/<int:availability_id>")
def change_room_availability(availability_id): return _change_availability("room",availability_id)

def _change_availability(kind, availability_id):
    actor,roles=require_roles("ADMIN","TEACHER"); require_csrf(); db=database.get_session(); model=TeacherAvailability if kind=="teacher" else RoomAvailability
    idkey="availability_id" if kind=="teacher" else "room_availability_id"; item=db.scalar(select(model).where(getattr(model,idkey)==availability_id).with_for_update())
    if item is None: abort(404)
    if "ADMIN" not in roles:
        teacher=db.scalar(select(Teacher.teacher_id).where(Teacher.user_id==actor.user_id))
        if kind!="teacher" or item.teacher_id!=teacher: abort(403)
    data=_json(); allowed={"starts_at","ends_at","status","reason"}
    if not data or set(data)-allowed: abort(400,description="Provide supported availability fields.")
    if "starts_at" in data: item.starts_at=_instant(data["starts_at"],"starts_at")
    if "ends_at" in data: item.ends_at=_instant(data["ends_at"],"ends_at")
    if "status" in data:
        if data["status"] not in {"AVAILABLE","UNAVAILABLE"}: abort(400,description="Invalid availability status.")
        item.status=data["status"]
    if "reason" in data: item.reason=data["reason"]
    if item.starts_at>=item.ends_at: abort(400,description="starts_at must precede ends_at.")
    _commit(db); return jsonify({idkey:availability_id,"status":"updated"})

def _availability(kind):
    actor,roles=require_roles("ADMIN","TEACHER"); db=database.get_session(); model=TeacherAvailability if kind=="teacher" else RoomAvailability; key="teacher_id" if kind=="teacher" else "room_id"; idkey="availability_id" if kind=="teacher" else "room_availability_id"
    if request.method=="GET":
        q=select(model).order_by(model.starts_at).limit(100)
        if "ADMIN" not in roles:
            teacher=db.scalar(select(Teacher.teacher_id).where(Teacher.user_id==actor.user_id));
            if kind!="teacher" or teacher is None: abort(403)
            q=q.where(model.teacher_id==teacher)
        rows=db.scalars(q).all(); return jsonify({"items":[{idkey:getattr(x,idkey),key:getattr(x,key),"starts_at":x.starts_at.isoformat(),"ends_at":x.ends_at.isoformat(),"status":x.status,"reason":x.reason} for x in rows]})
    require_csrf(); d=_json(); expected={key,"starts_at","ends_at","status","reason"}
    if set(d)!=expected or d["status"] not in {"AVAILABLE","UNAVAILABLE"}: abort(400,description="Invalid availability fields.")
    if "ADMIN" not in roles:
        teacher=db.scalar(select(Teacher.teacher_id).where(Teacher.user_id==actor.user_id));
        if kind!="teacher" or teacher!=d[key]: abort(403)
    obj=model(**{key:d[key],"starts_at":_instant(d["starts_at"],"starts_at"),"ends_at":_instant(d["ends_at"],"ends_at"),"status":d["status"],"reason":d["reason"],"created_by":actor.user_id}); db.add(obj); _commit(db)
    return jsonify({idkey:getattr(obj,idkey),"status":"created"}),201

@api_v1.get("/schedule/me")
def my_schedule():
    user,roles=require_roles("STUDENT","TEACHER"); db=database.get_session(); today=datetime.now(ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])).date(); start=_date(request.args.get("date",today.isoformat()),"date"); end=_date(request.args.get("to",start.isoformat()),"to")
    view_as=request.args.get("view_as")
    if view_as is not None and (view_as not in {"STUDENT","TEACHER"} or view_as not in roles): abort(403,description="The requested schedule interface is not one of your active roles.")
    session_role=session.get("active_role")
    if session_role is not None and session_role not in roles: abort(403,description="The selected interface is no longer active for this account.")
    if view_as is None and session_role is not None and session_role not in {"STUDENT","TEACHER"}: abort(403,description="Select the Student or Teacher interface to view a personal timetable.")
    active_role=view_as or session_role or ("STUDENT" if "STUDENT" in roles else "TEACHER")
    if "date" in request.args and "to" in request.args: abort(400,description="Use date for one day or from/to for a range.")
    if "from" in request.args:
        start=_date(request.args["from"],"from"); end=_date(request.args.get("to"),"to")
    elif "to" in request.args and "date" not in request.args: abort(400,description="to requires from.")
    if start>end or (end-start).days>=MAX_RANGE_DAYS: abort(400,description="Schedule range must be between 1 and 31 days.")
    if active_role=="STUDENT":
        student=db.scalar(select(Student).where(Student.user_id==user.user_id)); local_today=datetime.now(ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])).date()
        enrol=db.scalar(select(StudentEnrollment).where(StudentEnrollment.student_id==student.student_id,StudentEnrollment.status=="ACTIVE",StudentEnrollment.starts_on<=local_today,or_(StudentEnrollment.ends_on.is_(None),StudentEnrollment.ends_on>=local_today)).order_by(StudentEnrollment.starts_on.desc())) if student else None
        if enrol is None: abort(404,description="No current student section was found.")
        q=select(ClassSession.class_session_id,ClassSession.session_date,ClassSession.current_starts_at,ClassSession.current_ends_at,ClassSession.status,Subject.code,Subject.name,Teacher.full_name,Room.building,Room.room_number).join(Subject,Subject.subject_id==ClassSession.current_subject_id).join(Teacher,Teacher.teacher_id==ClassSession.current_teacher_id).join(Room,Room.room_id==ClassSession.current_room_id).where(ClassSession.section_id==enrol.section_id)
    else:
        teacher=db.scalar(select(Teacher.teacher_id).where(Teacher.user_id==user.user_id));
        if teacher is None: abort(404,description="Teacher profile was not found.")
        q=select(ClassSession.class_session_id,ClassSession.session_date,ClassSession.current_starts_at,ClassSession.current_ends_at,ClassSession.status,Subject.code,Subject.name,Section.section_code,Room.building,Room.room_number).join(Subject,Subject.subject_id==ClassSession.current_subject_id).join(Section,Section.section_id==ClassSession.section_id).join(Room,Room.room_id==ClassSession.current_room_id).where(ClassSession.current_teacher_id==teacher)
    rows=db.execute(q.where(ClassSession.session_date>=start,ClassSession.session_date<=end).order_by(ClassSession.session_date,ClassSession.current_starts_at).limit(500)).all()
    return jsonify({"view_as":active_role,"items": [{"class_session_id": r[0], "date": r[1].isoformat(), "starts_at": r[2].isoformat(), "ends_at": r[3].isoformat(), "status": r[4], "subject": {"code": r[5], "name": r[6]}, "counterparty": r[7], "room": "{} {}".format(r[-2], r[-1])} for r in rows]})

