"""Bounded administrative schedule and free-slot projections."""
from datetime import date, time, timedelta
from zoneinfo import ZoneInfo
from flask import abort, current_app, jsonify, request
from sqlalchemy import or_, select
from app.api.v1 import api_v1
from app.api.v1.auth import require_roles
from app.api.v1.scheduling import _date, _instant, MAX_RANGE_DAYS
from app.extensions import database
from app.models import (AcademicEvent, ClassSession, Room, RoomAvailability, Section,
                        Subject, Teacher, TeacherAvailability)

@api_v1.get("/admin/schedules")
def scoped_schedule():
    require_roles("ADMIN"); db=database.get_session(); kind=request.args.get("resource_type"); raw=request.args.get("resource_id")
    if kind not in {"SECTION","TEACHER","ROOM"} or not raw: abort(400,description="Provide resource_type and resource_id.")
    try: rid=int(raw)
    except ValueError: abort(400,description="resource_id must be an integer.")
    start=_date(request.args.get("from"),"from"); end=_date(request.args.get("to"),"to")
    if start>end or (end-start).days>=MAX_RANGE_DAYS: abort(400,description="Schedule range must be between 1 and 31 days.")
    column={"SECTION":ClassSession.section_id,"TEACHER":ClassSession.current_teacher_id,"ROOM":ClassSession.current_room_id}[kind]
    q=select(ClassSession.class_session_id,ClassSession.session_date,ClassSession.current_starts_at,ClassSession.current_ends_at,ClassSession.status,Subject.code,Subject.name,Teacher.full_name,Section.section_code,Room.building,Room.room_number).join(Subject,Subject.subject_id==ClassSession.current_subject_id).join(Teacher,Teacher.teacher_id==ClassSession.current_teacher_id).join(Section,Section.section_id==ClassSession.section_id).join(Room,Room.room_id==ClassSession.current_room_id).where(column==rid,ClassSession.session_date.between(start,end)).order_by(ClassSession.session_date,ClassSession.current_starts_at).limit(500)
    rows=db.execute(q).all()
    return jsonify({"items":[{"class_session_id":r[0],"date":r[1].isoformat(),"starts_at":r[2].isoformat(),"ends_at":r[3].isoformat(),"status":r[4],"subject":{"code":r[5],"name":r[6]},"teacher":r[7],"section":r[8],"room":"{} {}".format(r[9],r[10])} for r in rows]})

@api_v1.get("/admin/free-slots")
def free_slots():
    require_roles("ADMIN"); db=database.get_session(); kind=request.args.get("resource_type"); raw=request.args.get("resource_id")
    if kind not in {"SECTION","TEACHER","ROOM"} or not raw: abort(400,description="Provide resource_type and resource_id.")
    try: rid=int(raw)
    except ValueError: abort(400,description="resource_id must be an integer.")
    day=_date(request.args.get("date"),"date"); start=_instant(request.args.get("from"),"from"); end=_instant(request.args.get("to"),"to")
    if start>=end or (end-start).total_seconds()>86400: abort(400,description="Free-slot window must be positive and at most one day.")
    tz=ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"]); local_end=end.astimezone(tz)
    if start.astimezone(tz).date()!=day or (local_end.date()!=day and not (local_end.date()==day+timedelta(days=1) and local_end.timetz().replace(tzinfo=None)==time.min)): abort(400,description="Free-slot interval must fall within the requested institution date.")
    col={"SECTION":ClassSession.section_id,"TEACHER":ClassSession.current_teacher_id,"ROOM":ClassSession.current_room_id}[kind]
    busy=list(db.execute(select(ClassSession.current_starts_at,ClassSession.current_ends_at).where(col==rid,ClassSession.status.notin_(["CANCELLED","VOID"]),ClassSession.current_starts_at<end,ClassSession.current_ends_at>start)))
    if kind=="TEACHER": busy.extend(db.execute(select(TeacherAvailability.starts_at,TeacherAvailability.ends_at).where(TeacherAvailability.teacher_id==rid,TeacherAvailability.status=="UNAVAILABLE",TeacherAvailability.starts_at<end,TeacherAvailability.ends_at>start)))
    if kind=="ROOM": busy.extend(db.execute(select(RoomAvailability.starts_at,RoomAvailability.ends_at).where(RoomAvailability.room_id==rid,RoomAvailability.status=="UNAVAILABLE",RoomAvailability.starts_at<end,RoomAvailability.ends_at>start)))
    event_scope=or_(AcademicEvent.section_id.is_(None),AcademicEvent.section_id==rid) if kind=="SECTION" else AcademicEvent.section_id.is_(None)
    busy.extend(db.execute(select(AcademicEvent.starts_at,AcademicEvent.ends_at).where(AcademicEvent.event_type.in_(["HOLIDAY","EXAM"]),AcademicEvent.starts_at<end,AcademicEvent.ends_at>start,event_scope)))
    merged=[]
    for a,b in sorted((max(a,start),min(b,end)) for a,b in busy):
        if not merged or a>merged[-1][1]: merged.append([a,b])
        else: merged[-1][1]=max(merged[-1][1],b)
    gaps=[]; cursor=start
    for a,b in merged:
        if cursor<a: gaps.append({"starts_at":cursor.isoformat(),"ends_at":a.isoformat()})
        cursor=max(cursor,b)
    if cursor<end: gaps.append({"starts_at":cursor.isoformat(),"ends_at":end.isoformat()})
    return jsonify({"resource_type":kind,"resource_id":rid,"date":day.isoformat(),"free_slots":gaps})
