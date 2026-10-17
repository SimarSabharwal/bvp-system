"""Constraint-first schedule change proposals and pending lecture recovery."""
from __future__ import annotations

from datetime import datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from flask import abort, current_app, jsonify, request
from sqlalchemy import func, or_, select, tuple_
from sqlalchemy.exc import IntegrityError

from app.api.v1 import api_v1
from app.api.v1.auth import require_csrf, require_roles
from app.extensions import database
from app.models import (AcademicEvent, AuditEvent, ClassSession, Notification, OutboxEvent,
                        PendingLecture, Reallocation, Room, RoomAvailability, Student, StudentEnrollment,
                        SchedulingPolicy, Section, SectionSubject, Subject, Teacher, TeacherAvailability,
                        TeachingAssignment)

def _instant(value, name):
    try:
        result=datetime.fromisoformat(value.replace("Z","+00:00"))
        return result if result.tzinfo else result.replace(tzinfo=ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"]))
    except (TypeError,ValueError,AttributeError): abort(400,description=f"{name} must be an ISO datetime.")

def _conflict(db, session, assignment_id, room_id, starts, ends, *, excluding=(), allow_overlap=False):
    assignment=db.get(TeachingAssignment,assignment_id); room=db.get(Room,room_id)
    if assignment is None or assignment.section_id!=session.section_id or assignment.subject_id!=session.current_subject_id or assignment.status!="ACTIVE": return "Assignment does not teach this section and subject."
    day=starts.astimezone(ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])).date()
    if assignment.starts_on>day or (assignment.ends_on and assignment.ends_on<day): return "Assignment is not active at the proposed time."
    if room is None or room.status!="ACTIVE": return "Room is unavailable."
    section=db.get(Section,session.section_id); subject=db.get(Subject,session.current_subject_id)
    if room.capacity is None or section.capacity is None: return "Room or section capacity is unknown; capacity cannot be validated."
    if room.capacity<section.capacity: return "Room capacity is insufficient."
    if subject.requires_lab and room.room_type not in {"COMPUTER_LAB","SCIENCE_LAB"}: return "Room type is incompatible with this subject."
    if db.scalar(select(TeacherAvailability.availability_id).where(TeacherAvailability.teacher_id==assignment.teacher_id,TeacherAvailability.status=="UNAVAILABLE",TeacherAvailability.starts_at<ends,TeacherAvailability.ends_at>starts)): return "Teacher is unavailable."
    if db.scalar(select(RoomAvailability.room_availability_id).where(RoomAvailability.room_id==room_id,RoomAvailability.status=="UNAVAILABLE",RoomAvailability.starts_at<ends,RoomAvailability.ends_at>starts)): return "Room is unavailable."
    if db.scalar(select(AcademicEvent.event_id).where(AcademicEvent.event_type.in_(["HOLIDAY","EXAM"]),AcademicEvent.starts_at<ends,AcademicEvent.ends_at>starts,or_(AcademicEvent.section_id.is_(None),AcademicEvent.section_id==session.section_id))): return "Academic event blocks this time."
    if allow_overlap: return None
    overlaps=db.scalar(select(ClassSession.class_session_id).where(ClassSession.class_session_id!=session.class_session_id,ClassSession.class_session_id.notin_(set(excluding)|{session.class_session_id}),ClassSession.status.notin_(["CANCELLED","VOID"]),ClassSession.current_starts_at<ends,ClassSession.current_ends_at>starts,or_(ClassSession.section_id==session.section_id,ClassSession.current_teacher_id==assignment.teacher_id,ClassSession.current_room_id==room_id)))
    return "Section, teacher, or room is already booked." if overlaps else None

def _blockers(db, session, assignment_id, room_id, starts, ends, moving_ids):
    assignment=db.get(TeachingAssignment,assignment_id)
    if assignment is None: return []
    return db.scalars(select(ClassSession).where(
        ClassSession.class_session_id.notin_(set(moving_ids)|{session.class_session_id}),
        ClassSession.status.notin_(["CANCELLED","VOID"]),
        ClassSession.current_starts_at<ends,ClassSession.current_ends_at>starts,
        or_(ClassSession.section_id==session.section_id,
            ClassSession.current_teacher_id==assignment.teacher_id,
            ClassSession.current_room_id==room_id),
    ).order_by(ClassSession.class_session_id)).all()

def _planned_collision(db, session, assignment_id, room_id, starts, ends, plan):
    assignment=db.get(TeachingAssignment,assignment_id)
    for session_id, move in plan.items():
        other=db.get(ClassSession,session_id)
        other_assignment=db.get(TeachingAssignment,move[0])
        if not other or not other_assignment or move[2]>=ends or move[3]<=starts: continue
        if other.section_id==session.section_id or other_assignment.teacher_id==assignment.teacher_id or move[1]==room_id:
            return True
    return False

def _plan_move(db, session, assignment_id, room_id, starts, ends, depth, max_depth, plan, visiting, parent_session_id=None):
    """Plan one move and recursively clear any sessions blocking its target."""
    sid=session.class_session_id
    if sid in visiting: return None
    if _conflict(db,session,assignment_id,room_id,starts,ends,excluding=plan,allow_overlap=True): return None
    if _planned_collision(db,session,assignment_id,room_id,starts,ends,plan): return None
    blockers=_blockers(db,session,assignment_id,room_id,starts,ends,plan)
    candidate=dict(plan); candidate[sid]=(assignment_id,room_id,starts,ends,depth,parent_session_id)
    if not blockers: return candidate
    if depth>=max_depth: return None
    next_visiting=set(visiting)|{sid}
    tz=ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])
    duration=session.current_ends_at-session.current_starts_at
    for blocker in blockers:
        resolved=None
        for offset in range(8):
            local_day=blocker.current_starts_at.astimezone(tz).date()+timedelta(days=offset)
            for hour in range(8,18):
                for minute in (0,30):
                    target=datetime(local_day.year,local_day.month,local_day.day,hour,minute,tzinfo=tz)
                    if target==blocker.current_starts_at: continue
                    try_assignment=blocker.current_assignment_id; try_room=blocker.current_room_id
                    result=_plan_move(db,blocker,try_assignment,try_room,target,target+duration,
                                      depth+1,max_depth,candidate,next_visiting,sid)
                    if result is not None:
                        resolved=result; break
                if resolved is not None: break
            if resolved is not None: break
        if resolved is None: return None
        candidate=resolved
    return candidate

def _move_depth(plan):
    return max((move[4] for move in plan.values()),default=0)

def _queue_schedule_notice(db, session, proposal, event_type, title, message, extra_teacher_ids=()):
    recipients=set(db.scalars(select(Student.user_id).join(StudentEnrollment,
        StudentEnrollment.student_id==Student.student_id).where(
        StudentEnrollment.section_id==session.section_id,StudentEnrollment.status=="ACTIVE",
        StudentEnrollment.starts_on<=session.session_date,
        or_(StudentEnrollment.ends_on.is_(None),StudentEnrollment.ends_on>=session.session_date))))
    teacher_ids=set(extra_teacher_ids)|{session.current_teacher_id}
    recipients.update(db.scalars(select(Teacher.user_id).where(Teacher.teacher_id.in_(teacher_ids))))
    for user_id in recipients:
        db.add(Notification(user_id=user_id,event_type=event_type,title=title,message=message,
            related_session_id=session.class_session_id,related_reallocation_id=proposal.reallocation_id))

def _policy(db, section_id):
    return db.scalar(select(SchedulingPolicy).where(SchedulingPolicy.section_id==section_id)) or db.scalar(select(SchedulingPolicy).where(SchedulingPolicy.scope=="INSTITUTION",SchedulingPolicy.section_id.is_(None)))

@api_v1.get("/admin/scheduling-policy")
def get_policy():
    require_roles("ADMIN"); db=database.get_session(); rows=db.scalars(select(SchedulingPolicy).order_by(SchedulingPolicy.section_id)).all()
    return jsonify({"items":[{"policy_id":p.policy_id,"scope":p.scope,"section_id":p.section_id,"reallocation_mode":p.reallocation_mode,"max_cascade_depth":p.max_cascade_depth,"scoring_weights":p.scoring_weights} for p in rows]})

@api_v1.put("/admin/scheduling-policy")
def update_policy():
    actor,_=require_roles("ADMIN"); require_csrf(); data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)-{"scope","section_id","reallocation_mode","max_cascade_depth","scoring_weights"}: abort(400,description="Invalid policy fields.")
    scope=data.get("scope","INSTITUTION"); section_id=data.get("section_id")
    if scope not in {"INSTITUTION","SECTION"} or (scope=="INSTITUTION" and section_id is not None) or (scope=="SECTION" and not isinstance(section_id,int)): abort(400,description="Policy scope and section do not match.")
    mode=data.get("reallocation_mode","SUGGEST_AND_APPROVE"); depth=data.get("max_cascade_depth",1); weights=data.get("scoring_weights",{})
    if mode not in {"SUGGEST_AND_APPROVE","AUTO_APPLY"} or not isinstance(depth,int) or isinstance(depth,bool) or depth not in {1,2} or not isinstance(weights,dict) or any(not isinstance(v,(int,float)) or v<0 for v in weights.values()): abort(400,description="Invalid mode, cascade limit, or scoring weights.")
    db=database.get_session(); obj=db.scalar(select(SchedulingPolicy).where(SchedulingPolicy.section_id==section_id) if section_id is not None else select(SchedulingPolicy).where(SchedulingPolicy.scope=="INSTITUTION",SchedulingPolicy.section_id.is_(None)))
    if obj is None: obj=SchedulingPolicy(scope=scope,section_id=section_id); db.add(obj)
    obj.scope=scope; obj.reallocation_mode=mode; obj.max_cascade_depth=depth; obj.scoring_weights=weights; obj.updated_by=actor.user_id
    try: db.commit()
    except IntegrityError: db.rollback(); abort(409,description="Policy scope conflicts with existing configuration.")
    return jsonify({"policy_id":obj.policy_id,"scope":obj.scope,"section_id":obj.section_id,"reallocation_mode":obj.reallocation_mode,"max_cascade_depth":obj.max_cascade_depth,"scoring_weights":obj.scoring_weights})

@api_v1.post("/admin/reallocations/analyze")
def analyze_unavailability():
    actor,_=require_roles("ADMIN"); require_csrf(); data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!={"resource_type","resource_id","starts_at","ends_at","reason"} or data["resource_type"] not in {"TEACHER","ROOM"}: abort(400,description="Provide a teacher or room and unavailable interval.")
    starts,ends=_instant(data["starts_at"],"starts_at"),_instant(data["ends_at"],"ends_at")
    if starts>=ends: abort(400,description="starts_at must precede ends_at.")
    db=database.get_session(); teacher=data["resource_id"] if data["resource_type"]=="TEACHER" else None; room=data["resource_id"] if data["resource_type"]=="ROOM" else None
    # Persist the unavailable block in the same transaction as proposals so the
    # candidate set and future slot checks see the trigger that caused analysis.
    if teacher is not None:
        if db.get(Teacher, teacher) is None: abort(404)
        db.add(TeacherAvailability(teacher_id=teacher,starts_at=starts,ends_at=ends,status="UNAVAILABLE",reason=data["reason"],created_by=actor.user_id))
    else:
        if db.get(Room, room) is None: abort(404)
        db.add(RoomAvailability(room_id=room,starts_at=starts,ends_at=ends,status="UNAVAILABLE",reason=data["reason"],created_by=actor.user_id))
    db.flush()
    q=select(ClassSession).where(ClassSession.status=="SCHEDULED",ClassSession.current_starts_at<ends,ClassSession.current_ends_at>starts)
    q=q.where(ClassSession.current_teacher_id==teacher) if teacher else q.where(ClassSession.current_room_id==room)
    affected=db.scalars(q.with_for_update()).all(); result=[]
    subject_pairs={(row.section_id,row.current_subject_id) for row in affected}
    required_rows=db.execute(select(SectionSubject.section_id,SectionSubject.subject_id,
        (SectionSubject.required_lecture_hours+SectionSubject.required_lab_hours)).where(
        tuple_(SectionSubject.section_id,SectionSubject.subject_id).in_(subject_pairs))).all()
    completed_rows=db.execute(select(ClassSession.section_id,ClassSession.current_subject_id,
        func.coalesce(func.sum(func.extract("epoch",ClassSession.current_ends_at-ClassSession.current_starts_at)/3600),0))
        .where(ClassSession.status=="COMPLETED",
               tuple_(ClassSession.section_id,ClassSession.current_subject_id).in_(subject_pairs))
        .group_by(ClassSession.section_id,ClassSession.current_subject_id)).all()
    completed={(section_id,subject_id):float(hours) for section_id,subject_id,hours in completed_rows}
    remaining={(section_id,subject_id):max(float(required)-completed.get((section_id,subject_id),0),0)
               for section_id,subject_id,required in required_rows}
    affected.sort(key=lambda row:(-remaining.get((row.section_id,row.current_subject_id),0),row.current_starts_at,row.class_session_id))
    for session in affected:
        if data["resource_type"]=="TEACHER":
            assignments=db.scalars(select(TeachingAssignment).where(TeachingAssignment.section_id==session.section_id,TeachingAssignment.subject_id==session.current_subject_id,TeachingAssignment.status=="ACTIVE",TeachingAssignment.teacher_id!=session.current_teacher_id)).all()
        else: assignments=[db.get(TeachingAssignment,session.current_assignment_id)]
        candidates=[]
        rooms=db.scalars(select(Room).where(Room.status=="ACTIVE")).all() if data["resource_type"]=="TEACHER" else [r for r in [db.get(Room,other) for other in db.scalars(select(Room.room_id).where(Room.room_id!=session.current_room_id))] if r]
        for assignment in assignments:
            if assignment is None: continue
            for candidate_room in rooms:
                if data["resource_type"]=="ROOM" and candidate_room.room_id==session.current_room_id: continue
                plan=None
                for depth_limit in range(3):
                    plan=_plan_move(db,session,assignment.assignment_id,candidate_room.room_id,
                                    session.current_starts_at,session.current_ends_at,0,depth_limit,{},set())
                    if plan is not None: break
                if plan is None: continue
                candidates.append((assignment,candidate_room,plan))
        policy=_policy(db,session.section_id); weights=(policy.scoring_weights if policy else {})
        keep_room=float(weights.get("keep_room",10)); teacher_load=float(weights.get("teacher_load",1))
        backlog_weight=float(weights.get("remaining_hours",1)); backlog_hours=remaining.get((session.section_id,session.current_subject_id),0)
        scored=[]
        for assignment,candidate_room,plan in candidates:
            load=db.scalar(select(func.count(ClassSession.class_session_id)).where(ClassSession.current_teacher_id==assignment.teacher_id,ClassSession.session_date==session.session_date,ClassSession.status=="SCHEDULED")) or 0
            score=(keep_room if candidate_room.room_id==session.current_room_id else 0)-(teacher_load*load)+(backlog_weight*backlog_hours)
            cascade_cost=float(weights.get("cascade_change",5))
            score-=cascade_cost*max(0,len(plan)-1)
            scored.append((score,assignment,candidate_room,load,plan))
        scored.sort(key=lambda item:(-item[0],item[2].room_id,item[1].teacher_id))
        pending=None
        if not candidates:
            session.status="CANCELLED"; pending=PendingLecture(class_session_id=session.class_session_id,section_id=session.section_id,subject_id=session.current_subject_id,preferred_assignment_id=session.current_assignment_id,state="OPEN"); db.add(pending); db.flush()
        proposals=[]
        if policy and policy.reallocation_mode=="AUTO_APPLY":
            in_limit=[item for item in scored if _move_depth(item[4])<=policy.max_cascade_depth]
            selected=in_limit[:1] if in_limit else scored[:1]
        else:
            selected=scored[:5]
        for score,assignment,candidate_room,load,plan in selected:
            why=f"{data['reason']} Score {score:g}: {'kept existing room; ' if candidate_room.room_id==session.current_room_id else ''}teacher has {load} scheduled session(s) that day; subject has {backlog_hours:g} required hour(s) remaining."
            group_id=uuid4(); by_session={}; members=[]
            for planned_session_id,move in sorted(plan.items(),key=lambda item:(item[1][4],item[0])):
                planned_session=db.get(ClassSession,planned_session_id)
                member_reason=why if planned_session_id==session.class_session_id else f"Cascade move to clear session {session.class_session_id}."
                proposal=Reallocation(cascade_group_id=group_id,cascade_depth=move[4],
                    parent_reallocation_id=(by_session[move[5]].reallocation_id if move[5] is not None else None),
                    class_session_id=planned_session_id,status="PROPOSED",reason=member_reason,initiator_id=actor.user_id,
                    proposed_assignment_id=move[0],proposed_room_id=move[1],proposed_starts_at=move[2],proposed_ends_at=move[3],
                    previous_assignment_id=planned_session.current_assignment_id,previous_room_id=planned_session.current_room_id,
                    previous_starts_at=planned_session.current_starts_at,previous_ends_at=planned_session.current_ends_at)
                db.add(proposal); db.flush(); by_session[planned_session_id]=proposal; members.append(proposal)
            group_depth=_move_depth(plan)
            automatic=bool(policy and policy.reallocation_mode=="AUTO_APPLY" and group_depth<=policy.max_cascade_depth)
            proposal_info={"cascade_group_id":str(group_id),"reallocation_id":by_session[session.class_session_id].reallocation_id,
                "member_reallocation_ids":[member.reallocation_id for member in members],"cascade_depth":group_depth,
                "admin_approval_required":not automatic,"assignment_id":assignment.assignment_id,
                "teacher_id":assignment.teacher_id,"room_id":candidate_room.room_id,
                "reason":"All moves passed assignment, availability, room, event, and overlap checks."}
            proposals.append(proposal_info)
            if automatic:
                try:
                    for member in sorted(members,key=lambda item:(-item.cascade_depth,item.reallocation_id)):
                        _apply(db,member,actor.user_id)
                except Exception:
                    db.rollback()
                    raise
        if not candidates:
            proposal=Reallocation(class_session_id=session.class_session_id,status="PROPOSED",reason=f"{data['reason']} No valid candidate; admin review required.",initiator_id=actor.user_id,previous_assignment_id=session.current_assignment_id,previous_room_id=session.current_room_id,previous_starts_at=session.current_starts_at,previous_ends_at=session.current_ends_at); db.add(proposal)
        result.append({"class_session_id":session.class_session_id,"proposals":proposals,"admin_review_required":not bool(candidates) or any(item["admin_approval_required"] for item in proposals),"pending_lecture_id":pending.pending_lecture_id if pending else None})
    db.add(OutboxEvent(event_type="RESOURCE_UNAVAILABLE",aggregate_type=data["resource_type"].lower(),aggregate_id=str(data["resource_id"]),payload={"affected_sessions":len(affected)}))
    try: db.commit()
    except IntegrityError: db.rollback(); abort(409,description="Schedule changed concurrently; analyze again against current data.")
    return jsonify({"affected_sessions":len(affected),"items":result})

def _apply(db, proposal, actor_id):
    session=db.scalar(select(ClassSession).where(ClassSession.class_session_id==proposal.class_session_id).with_for_update())
    is_recovery = bool(proposal.pending_lecture_id)
    if session is None or (session.status!="SCHEDULED" and not (is_recovery and session.status=="CANCELLED")):
        abort(409,description="The session is no longer available to reallocate.")
    if (session.current_assignment_id!=proposal.previous_assignment_id or session.current_room_id!=proposal.previous_room_id
            or session.current_starts_at!=proposal.previous_starts_at or session.current_ends_at!=proposal.previous_ends_at):
        abort(409,description="The session changed after this proposal; analyze the current schedule again.")
    assignment_id=proposal.proposed_assignment_id; room_id=proposal.proposed_room_id; starts=proposal.proposed_starts_at; ends=proposal.proposed_ends_at
    if not assignment_id or not room_id or not starts or not ends: abort(409,description="This admin-review item has no applicable candidate.")
    why=_conflict(db,session,assignment_id,room_id,starts,ends)
    if why: abort(409,description="Candidate no longer satisfies constraints: "+why)
    assignment=db.scalar(select(TeachingAssignment).where(TeachingAssignment.assignment_id==assignment_id).with_for_update())
    if assignment is None or assignment.status!="ACTIVE": abort(409,description="The teaching assignment is no longer active.")
    old_teacher_id=session.current_teacher_id
    session.current_assignment_id=assignment_id; session.current_teacher_id=assignment.teacher_id; session.current_room_id=room_id; session.current_starts_at=starts; session.current_ends_at=ends; session.status="SCHEDULED"
    proposal.status="ACCEPTED"; proposal.decided_by=actor_id; proposal.decided_at=datetime.now(ZoneInfo("UTC"))
    db.add(AuditEvent(actor_id=actor_id,entity_type="reallocation",entity_id=str(proposal.reallocation_id),action="ACCEPTED",details={"cascade_group_id":str(proposal.cascade_group_id),"cascade_depth":proposal.cascade_depth,"class_session_id":session.class_session_id,"before":{"assignment_id":proposal.previous_assignment_id,"room_id":proposal.previous_room_id,"starts_at":proposal.previous_starts_at.isoformat(),"ends_at":proposal.previous_ends_at.isoformat()},"after":{"assignment_id":assignment_id,"room_id":room_id,"starts_at":starts.isoformat(),"ends_at":ends.isoformat()}}))
    db.add(OutboxEvent(event_type="CLASS_SESSION_REALLOCATED",aggregate_type="class_session",aggregate_id=str(session.class_session_id),payload={"reallocation_id":proposal.reallocation_id,"section_id":session.section_id,"teacher_id":assignment.teacher_id,"room_id":room_id}))
    subject=db.get(Subject,session.current_subject_id); room=db.get(Room,room_id)
    _queue_schedule_notice(db,session,proposal,"SCHEDULE_CHANGED","Class schedule updated",
        f"Your {subject.code} session is now scheduled for {starts.isoformat()} in {room.building} {room.room_number}.",[old_teacher_id])
    db.flush()

@api_v1.post("/admin/reallocations/<int:reallocation_id>/decision")
def decide_reallocation(reallocation_id):
    actor,_=require_roles("ADMIN"); require_csrf(); data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!={"decision"} or data["decision"] not in {"APPROVE","REJECT"}: abort(400,description="decision must be APPROVE or REJECT.")
    db=database.get_session(); proposal=db.scalar(select(Reallocation).where(Reallocation.reallocation_id==reallocation_id).with_for_update())
    if proposal is None: abort(404)
    group=db.scalars(select(Reallocation).where(Reallocation.cascade_group_id==proposal.cascade_group_id).order_by(Reallocation.cascade_depth.desc(),Reallocation.reallocation_id).with_for_update()).all()
    if not group or any(item.status!="PROPOSED" for item in group): abort(409,description="Every member of the cascade group must still be proposed.")
    if data["decision"]=="APPROVE":
        try:
            for item in group: _apply(db,item,actor.user_id)
            db.commit()
        except IntegrityError:
            db.rollback(); abort(409,description="A cascade slot changed concurrently; no group member was applied.")
        except Exception:
            db.rollback(); raise
        status="ACCEPTED"
    else:
        now=datetime.now(ZoneInfo("UTC"))
        for item in group: item.status="REJECTED"; item.decided_by=actor.user_id; item.decided_at=now
        db.add(AuditEvent(actor_id=actor.user_id,entity_type="reallocation_group",entity_id=str(proposal.cascade_group_id),action="REJECTED",details={"member_ids":[item.reallocation_id for item in group]}))
        db.commit(); status="REJECTED"
    return jsonify({"cascade_group_id":str(proposal.cascade_group_id),"reallocation_ids":[item.reallocation_id for item in group],"status":status})

@api_v1.post("/admin/reallocations/<int:reallocation_id>/revert")
def revert_reallocation(reallocation_id):
    actor,_=require_roles("ADMIN"); require_csrf(); db=database.get_session()
    p=db.scalar(select(Reallocation).where(Reallocation.reallocation_id==reallocation_id).with_for_update())
    if p is None: abort(404)
    group=db.scalars(select(Reallocation).where(Reallocation.cascade_group_id==p.cascade_group_id).order_by(Reallocation.cascade_depth,Reallocation.reallocation_id).with_for_update()).all()
    if not group or any(item.status!="ACCEPTED" for item in group): abort(409,description="Every cascade member must be accepted before the group can be reverted.")
    try:
        for item in group: _revert_one(db,item,actor.user_id)
        db.commit()
    except IntegrityError:
        db.rollback(); abort(409,description="Could not restore the cascade because current schedule constraints changed.")
    except Exception:
        db.rollback(); raise
    return jsonify({"cascade_group_id":str(p.cascade_group_id),"reallocation_ids":[item.reallocation_id for item in group],"status":"REVERTED"})

def _revert_one(db,p,actor_id):
    s=db.scalar(select(ClassSession).where(ClassSession.class_session_id==p.class_session_id).with_for_update())
    assignment=db.get(TeachingAssignment,p.previous_assignment_id)
    if s is None or s.status!="SCHEDULED" or assignment is None: abort(409,description="The original schedule cannot be restored safely.")
    before={"assignment_id":s.current_assignment_id,"room_id":s.current_room_id,"starts_at":s.current_starts_at.isoformat(),"ends_at":s.current_ends_at.isoformat()}
    if p.pending_lecture_id:
        s.status="CANCELLED"
        pending=db.scalar(select(PendingLecture).where(PendingLecture.pending_lecture_id==p.pending_lecture_id).with_for_update())
        if pending is not None: pending.state="OPEN"
    else:
        reason=_conflict(db,s,p.previous_assignment_id,p.previous_room_id,p.previous_starts_at,p.previous_ends_at)
        if reason: abort(409,description="Original slot is no longer valid: "+reason)
        s.current_assignment_id=p.previous_assignment_id; s.current_teacher_id=assignment.teacher_id; s.current_room_id=p.previous_room_id; s.current_starts_at=p.previous_starts_at; s.current_ends_at=p.previous_ends_at
    p.status="REVERTED"; p.decided_by=actor_id; p.decided_at=datetime.now(ZoneInfo("UTC"))
    db.add(AuditEvent(actor_id=actor_id,entity_type="reallocation",entity_id=str(p.reallocation_id),action="REVERTED",details={"before":before,"restored":{"assignment_id":p.previous_assignment_id,"room_id":p.previous_room_id,"starts_at":p.previous_starts_at.isoformat(),"ends_at":p.previous_ends_at.isoformat()}}))
    db.add(OutboxEvent(event_type="CLASS_SESSION_REALLOCATION_REVERTED",aggregate_type="class_session",aggregate_id=str(s.class_session_id),payload={"reallocation_id":p.reallocation_id}))
    db.flush()

@api_v1.post("/admin/pending-lectures/<int:pending_id>/propose-recovery")
def propose_recovery(pending_id):
    actor,_=require_roles("ADMIN"); require_csrf(); data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!={"teaching_assignment_id","room_id","starts_at","ends_at"}: abort(400,description="Provide assignment, room and slot.")
    db=database.get_session(); pending=db.scalar(select(PendingLecture).where(PendingLecture.pending_lecture_id==pending_id).with_for_update())
    if pending is None: abort(404)
    if pending.state not in {"OPEN","SCHEDULED"}: abort(409,description="Pending lecture has already been resolved.")
    origin=db.get(ClassSession,pending.class_session_id); starts=_instant(data["starts_at"],"starts_at"); ends=_instant(data["ends_at"],"ends_at")
    if starts>=ends: abort(400,description="Invalid recovery interval.")
    day=starts.astimezone(ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"])).date(); assignment=db.get(TeachingAssignment,data["teaching_assignment_id"]); room_id=data["room_id"]
    if assignment is None or assignment.section_id!=pending.section_id or assignment.subject_id!=pending.subject_id or assignment.status!="ACTIVE" or assignment.starts_on>day or (assignment.ends_on and assignment.ends_on<day): abort(422,description="Recovery assignment is not valid for this section/subject/time.")
    if _conflict(db,origin,assignment.assignment_id,room_id,starts,ends): abort(422,description="Recovery slot fails hard scheduling constraints.")
    recovery=db.scalar(select(ClassSession).where(ClassSession.pending_lecture_id==pending_id).with_for_update())
    if recovery is not None and recovery.status!="CANCELLED": abort(409,description="The recovery session is already scheduled or held.")
    if recovery is None:
        recovery=ClassSession(entry_id=None,pending_lecture_id=pending_id,section_id=pending.section_id,session_date=day,original_assignment_id=origin.original_assignment_id,original_subject_id=pending.subject_id,original_teacher_id=origin.original_teacher_id,original_room_id=origin.original_room_id,current_assignment_id=assignment.assignment_id,current_subject_id=pending.subject_id,current_teacher_id=assignment.teacher_id,current_room_id=room_id,original_starts_at=starts,original_ends_at=ends,current_starts_at=starts,current_ends_at=ends,status="CANCELLED"); db.add(recovery); db.flush()
    else:
        recovery.session_date=day; recovery.current_assignment_id=assignment.assignment_id; recovery.current_teacher_id=assignment.teacher_id; recovery.current_room_id=room_id; recovery.current_starts_at=starts; recovery.current_ends_at=ends
    proposal=Reallocation(class_session_id=recovery.class_session_id,pending_lecture_id=pending_id,status="PROPOSED",reason="Pending lecture recovery proposed for a validated free slot.",initiator_id=actor.user_id,proposed_assignment_id=assignment.assignment_id,proposed_room_id=room_id,proposed_starts_at=starts,proposed_ends_at=ends,previous_assignment_id=assignment.assignment_id,previous_room_id=room_id,previous_starts_at=starts,previous_ends_at=ends); db.add(proposal); _commit(db)
    return jsonify({"pending_lecture_id":pending_id,"class_session_id":recovery.class_session_id,"reallocation_id":proposal.reallocation_id,"status":"PROPOSED"}),201

@api_v1.get("/admin/pending-lectures/<int:pending_id>/candidates")
def recovery_candidates(pending_id):
    require_roles("ADMIN"); db=database.get_session(); pending=db.get(PendingLecture,pending_id)
    if pending is None: abort(404)
    if pending.state not in {"OPEN","SCHEDULED"}: abort(409,description="Pending lecture has already been resolved.")
    try: first=datetime.fromisoformat(request.args["from"]).date(); last=datetime.fromisoformat(request.args["to"]).date()
    except (KeyError,ValueError): abort(400,description="Provide ISO from and to dates.")
    if first>last or (last-first).days>14: abort(400,description="Recovery search window must be at most 15 days.")
    origin=db.get(ClassSession,pending.class_session_id); duration=origin.original_ends_at-origin.original_starts_at
    assignments=db.scalars(select(TeachingAssignment).where(TeachingAssignment.section_id==pending.section_id,TeachingAssignment.subject_id==pending.subject_id,TeachingAssignment.status=="ACTIVE",TeachingAssignment.starts_on<=last,or_(TeachingAssignment.ends_on.is_(None),TeachingAssignment.ends_on>=first)).order_by(TeachingAssignment.teacher_id)).all()
    assignments.sort(key=lambda item:(item.assignment_id!=pending.preferred_assignment_id,item.teacher_id))
    rooms=db.scalars(select(Room).where(Room.status=="ACTIVE").order_by(Room.room_id)).all(); tz=ZoneInfo(current_app.config["INSTITUTION_TIMEZONE"]); results=[]; day=first
    while day<=last and len(results)<100:
        for hour in range(8,18):
            for minute in (0,30):
                starts=datetime(day.year,day.month,day.day,hour,minute,tzinfo=tz); ends=starts+duration
                for assignment in assignments:
                    if assignment.starts_on>day or (assignment.ends_on and assignment.ends_on<day): continue
                    for room in rooms:
                        if _conflict(db,origin,assignment.assignment_id,room.room_id,starts,ends): continue
                        results.append({"teaching_assignment_id":assignment.assignment_id,"teacher_id":assignment.teacher_id,"room_id":room.room_id,"starts_at":starts.isoformat(),"ends_at":ends.isoformat()})
                        if len(results)>=100: break
                    if len(results)>=100: break
                if len(results)>=100: break
            if len(results)>=100: break
        day+=timedelta(days=1)
    return jsonify({"pending_lecture_id":pending_id,"items":results,"truncated":len(results)>=100})

@api_v1.post("/admin/pending-lectures/<int:pending_id>/resolve")
def resolve_pending_lecture(pending_id):
    actor,_=require_roles("ADMIN"); require_csrf(); data=request.get_json(silent=True)
    if not isinstance(data,dict) or set(data)!={"reason"} or not isinstance(data["reason"],str) or not data["reason"].strip(): abort(400,description="An admin resolution reason is required.")
    db=database.get_session(); pending=db.scalar(select(PendingLecture).where(PendingLecture.pending_lecture_id==pending_id).with_for_update())
    if pending is None: abort(404)
    if pending.state not in {"OPEN","SCHEDULED"}: abort(409,description="Pending lecture is already resolved.")
    recovery=db.scalar(select(ClassSession).where(ClassSession.pending_lecture_id==pending_id).with_for_update())
    if recovery is not None and recovery.status=="SCHEDULED": abort(409,description="A recovery is already scheduled; cancel or revert that proposal first.")
    pending.state="RESOLVED"
    db.add(AuditEvent(actor_id=actor.user_id,entity_type="pending_lecture",entity_id=str(pending_id),action="RESOLVED",details={"reason":data["reason"].strip()}))
    db.add(OutboxEvent(event_type="PENDING_LECTURE_RESOLVED",aggregate_type="pending_lecture",aggregate_id=str(pending_id),payload={"section_id":pending.section_id,"subject_id":pending.subject_id}))
    try: db.commit()
    except IntegrityError: db.rollback(); abort(409,description="Pending lecture changed concurrently.")
    return jsonify({"pending_lecture_id":pending_id,"state":"RESOLVED"})

