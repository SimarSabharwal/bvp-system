"""Run a bounded, local-only synthetic Phase 9 reallocation benchmark.

This measures Flask test-client/PostgreSQL application latency and one local
WebSocket sample. It is not a production or concurrent WebSocket load test.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from threading import Lock
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, time as local_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from werkzeug.security import generate_password_hash

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import create_app
from app.config import normalize_database_url
from app.models import (
    AcademicYear,
    ClassSession,
    Course,
    Room,
    Section,
    SectionSubject,
    Subject,
    Teacher,
    TeacherSubject,
    TeachingAssignment,
    TimetableEntry,
    TimetableVersion,
    User,
    UserRole,
    Notification,
    OutboxEvent,
)


def _percentile(values: list[float], percentile: float) -> float:
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * percentile) - 1))
    return ordered[index]


def _seed(database_url: str, sections_count: int, password: str, ws_clients: int) -> tuple[list[int], int, list[int]]:
    from sqlalchemy import create_engine

    engine = create_engine(database_url, pool_pre_ping=True)
    now = date(2027, 1, 1)
    tz = ZoneInfo("Asia/Kolkata")
    benchmark_hash = generate_password_hash(password)
    with Session(engine) as db, db.begin():
        admin = User(login_id="phase9-bench-admin", password_hash=benchmark_hash)
        db.add(admin)
        db.flush()
        db.add(UserRole(user_id=admin.user_id, role="ADMIN"))
        year = AcademicYear(name="PHASE9-BENCH-2027", starts_on=now, ends_on=date(2035, 12, 31), status="ACTIVE")
        course = Course(code="P9B", name="Phase 9 Synthetic Benchmark")
        subject = Subject(code="P9B-S1", name="Synthetic Benchmark Subject", requires_lab=False)
        db.add_all([year, course, subject])
        db.flush()

        targets: list[int] = []
        for index in range(sections_count):
            section = Section(
                course_id=course.course_id,
                academic_year_id=year.academic_year_id,
                semester=1,
                section_code=f"B{index:04d}",
                shift="MORNING",
                capacity=40,
            )
            db.add(section)
            db.flush()
            db.add(SectionSubject(section_id=section.section_id, subject_id=subject.subject_id, required_lecture_hours=40))
            teachers: list[Teacher] = []
            assignments: list[TeachingAssignment] = []
            for role in ("primary", "backup"):
                user = User(login_id=f"p9bench-{index}-{role}", password_hash=benchmark_hash)
                db.add(user)
                db.flush()
                teacher = Teacher(user_id=user.user_id, faculty_code=f"P9B-{index}-{role}", full_name=f"Synthetic {role} {index}")
                db.add(teacher)
                db.flush()
                db.add(TeacherSubject(teacher_id=teacher.teacher_id, subject_id=subject.subject_id))
                assignment = TeachingAssignment(
                    teacher_id=teacher.teacher_id,
                    subject_id=subject.subject_id,
                    section_id=section.section_id,
                    starts_on=now,
                    status="ACTIVE",
                )
                db.add(assignment)
                teachers.append(teacher)
                assignments.append(assignment)

            room = Room(building="Synthetic", room_number=f"R{index:04d}", capacity=50, room_type="NORMAL", status="ACTIVE")
            db.add(room)
            db.flush()
            session_date = now + timedelta(days=index)
            version = TimetableVersion(
                section_id=section.section_id,
                name=f"Synthetic {index}",
                status="PUBLISHED",
                effective_from=session_date,
                effective_to=session_date,
                published_by=admin.user_id,
            )
            db.add(version)
            db.flush()
            entry = TimetableEntry(
                timetable_version_id=version.timetable_version_id,
                section_id=section.section_id,
                teaching_assignment_id=assignments[0].assignment_id,
                teacher_id=teachers[0].teacher_id,
                subject_id=subject.subject_id,
                room_id=room.room_id,
                weekday=session_date.weekday(),
                starts_at_local=local_time(9),
                ends_at_local=local_time(10),
            )
            db.add(entry)
            db.flush()
            starts = datetime.combine(session_date, local_time(9), tzinfo=tz)
            ends = datetime.combine(session_date, local_time(10), tzinfo=tz)
            session_row = ClassSession(
                entry_id=entry.entry_id,
                pending_lecture_id=None,
                section_id=section.section_id,
                session_date=session_date,
                original_assignment_id=assignments[0].assignment_id,
                original_subject_id=subject.subject_id,
                original_teacher_id=teachers[0].teacher_id,
                original_room_id=room.room_id,
                current_assignment_id=assignments[0].assignment_id,
                current_subject_id=subject.subject_id,
                current_teacher_id=teachers[0].teacher_id,
                current_room_id=room.room_id,
                original_starts_at=starts,
                original_ends_at=ends,
                current_starts_at=starts,
                current_ends_at=ends,
                status="SCHEDULED",
            )
            db.add(session_row)
            db.flush()
            targets.append(teachers[0].teacher_id)
        websocket_user_ids: list[int] = []
        for index in range(ws_clients):
            user = User(
                login_id=f"phase9-ws-bench-{index}",
                password_hash=benchmark_hash,
            )
            db.add(user)
            db.flush()
            db.add(UserRole(user_id=user.user_id, role="STUDENT"))
            websocket_user_ids.append(user.user_id)
        admin_id = admin.user_id
    engine.dispose()
    return targets, admin_id, websocket_user_ids


def _measure_websocket_delivery(app, user_ids: list[int], password: str) -> dict:
    """Measure one outbox wake through authenticated local WebSocket clients."""
    import json as json_module
    import threading

    from simple_websocket import Client
    from werkzeug.serving import make_server

    from app.models import Notification as NotificationModel, OutboxEvent as OutboxEventModel
    from scripts.dispatch_outbox import dispatch_batch

    # Drain prior reallocation events so the sample sees only the event created below.
    with app.app_context():
        while dispatch_batch(app):
            pass

    server = make_server("127.0.0.1", 0, app, threaded=True)
    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()
    clients = []
    try:
        login = app.test_client()
        response = login.post("/api/v1/auth/login", json={
            "login_id": "phase9-bench-admin", "password": password, "active_role": "ADMIN",
        })
        if response.status_code != 200:
            raise RuntimeError("Local WebSocket benchmark login failed")
        origin = f"http://127.0.0.1:{server.server_port}"
        serializer = app.session_interface.get_signing_serializer(app)
        if serializer is None:
            raise RuntimeError("Session serializer is unavailable")

        def connect_user(user_id: int):
            cookie_value = serializer.dumps({"user_id": user_id, "_permanent": True})
            client = Client.connect(
                f"ws://127.0.0.1:{server.server_port}/api/v1/ws/events",
                headers={
                    "Cookie": f"{app.config['SESSION_COOKIE_NAME']}={cookie_value}",
                    "Origin": origin,
                },
            )
            connected = json_module.loads(client.receive(timeout=10))
            if connected.get("type") != "connected":
                client.close()
                raise RuntimeError("Local WebSocket handshake failed")
            return client

        with ThreadPoolExecutor(max_workers=min(max(1, len(user_ids)), 50)) as pool:
            futures = [pool.submit(connect_user, user_id) for user_id in user_ids]
            for future in as_completed(futures):
                clients.append(future.result())

        factory = app.extensions["student_system.session_factory"]
        with factory() as db, db.begin():
            db.add_all([
                NotificationModel(
                    user_id=user_id,
                    event_type="PHASE9_BENCHMARK",
                    title="Synthetic realtime benchmark",
                    message="Disposable local benchmark event",
                )
                for user_id in user_ids
            ])
            db.add(OutboxEventModel(
                event_type="PHASE9_BENCHMARK",
                aggregate_type="benchmark",
                aggregate_id="fanout",
                payload={"synthetic": True},
            ))
        committed_at = time.perf_counter()
        with app.app_context():
            if dispatch_batch(app) < 1:
                raise RuntimeError("Local outbox event was not dispatched")

        def receive(client):
            try:
                frame = client.receive(timeout=3)
                elapsed_ms = (time.perf_counter() - committed_at) * 1000
                if frame and json_module.loads(frame).get("type") == "notification":
                    return elapsed_ms
                return None
            except TimeoutError:
                return None

        receive_start = time.perf_counter()
        with ThreadPoolExecutor(max_workers=min(max(1, len(clients)), 100)) as pool:
            delivery_values = list(pool.map(receive, clients))
        completed = [value for value in delivery_values if value is not None]
        return {
            "connected_clients": len(clients),
            "successful_deliveries": len(completed),
            "timed_out_or_invalid": len(delivery_values) - len(completed),
            "delivery_ms": {
                "p50": round(statistics.median(completed), 2) if completed else None,
                "p95": round(_percentile(completed, 0.95), 2) if completed else None,
                "max": round(max(completed), 2) if completed else None,
            },
            "receive_wait_seconds": round(time.perf_counter() - receive_start, 3),
        }
    finally:
        for client in clients:
            client.close()
        server.shutdown()
        server.server_close()
        server_thread.join(timeout=3)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--sections", type=int, default=100)
    parser.add_argument("--requests", type=int, default=30)
    parser.add_argument("--workers", type=int, default=5)
    parser.add_argument("--ws-clients", type=int, default=1, help="Authenticated local WebSocket recipients, maximum 300.")
    parser.add_argument("--password", default="local-only-benchmark-password")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase9-local-benchmark.json")
    args = parser.parse_args()
    url = normalize_database_url(args.database_url)
    parsed = make_url(url)
    if parsed.host not in {"localhost", "127.0.0.1", "::1"} or parsed.database != "phase9_bench":
        parser.error("Refusing non-local database; database name must be phase9_bench.")
    if not (1 <= args.requests <= args.sections <= 1000 and 1 <= args.workers <= 50 and 1 <= args.ws_clients <= 300):
        parser.error("Use 1 <= requests <= sections <= 1000, 1 <= workers <= 50, and 1 <= ws-clients <= 300.")

    targets, admin_id, websocket_user_ids = _seed(url, args.sections, args.password, args.ws_clients)
    pool_size = max(5, args.workers, min(args.ws_clients, 50))
    app = create_app({
        "TESTING": True,
        "DATABASE_URL": url,
        "SECRET_KEY": "phase9-local-benchmark-only",
        "DB_POOL_SIZE": pool_size,
        "DB_MAX_OVERFLOW": pool_size,
        "WS_MAX_CONNECTIONS": args.ws_clients,
    })
    pool_stats = {"checked_out": 0, "max_checked_out": 0}
    pool_lock = Lock()
    engine = app.extensions["student_system.database_engine"]

    def on_checkout(*_args) -> None:
        with pool_lock:
            pool_stats["checked_out"] += 1
            pool_stats["max_checked_out"] = max(pool_stats["max_checked_out"], pool_stats["checked_out"])

    def on_checkin(*_args) -> None:
        with pool_lock:
            pool_stats["checked_out"] -= 1

    event.listen(engine, "checkout", on_checkout)
    event.listen(engine, "checkin", on_checkin)

    def call(index: int) -> tuple[int, float, int]:
        client = app.test_client()
        response = client.post("/api/v1/auth/login", json={"login_id": "phase9-bench-admin", "password": args.password, "active_role": "ADMIN"})
        if response.status_code != 200 or response.json["user_id"] != admin_id:
            return index, 0.0, response.status_code
        csrf = client.get("/api/v1/auth/csrf").json["csrf_token"]
        request_date = (date(2027, 1, 1) + timedelta(days=index)).isoformat()
        starts = f"{request_date}T09:00:00+05:30"
        ends = f"{request_date}T10:00:00+05:30"
        before = time.perf_counter()
        response = client.post(
            "/api/v1/admin/reallocations/analyze",
            json={"resource_type": "TEACHER", "resource_id": targets[index], "starts_at": starts, "ends_at": ends, "reason": "Synthetic Phase 9 benchmark"},
            headers={"X-CSRF-Token": csrf},
        )
        elapsed = (time.perf_counter() - before) * 1000
        return index, elapsed, response.status_code

    elapsed_values: list[float] = []
    statuses: list[int] = []
    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(call, index) for index in range(args.requests)]
        for future in as_completed(futures):
            _, elapsed, status = future.result()
            elapsed_values.append(elapsed)
            statuses.append(status)
    wall_seconds = time.perf_counter() - wall_start
    notification_delivery = _measure_websocket_delivery(app, websocket_user_ids, args.password)
    report = {
        "scope": "local synthetic benchmark; not a production or representative institutional load test",
        "database": "temporary local PostgreSQL 18; synthetic records only",
        "synthetic_shape": {"sections": args.sections, "teachers": args.sections * 2, "rooms": args.sections, "dated_sessions": args.sections},
        "request_count": args.requests,
        "concurrent_workers": args.workers,
        "successful_requests": sum(1 for status in statuses if status == 200),
        "http_status_counts": {str(status): statuses.count(status) for status in sorted(set(statuses))},
        "latency_ms": {
            "p50": round(statistics.median(elapsed_values), 2),
            "p95": round(_percentile(elapsed_values, 0.95), 2),
            "p99": round(_percentile(elapsed_values, 0.99), 2),
            "max": round(max(elapsed_values), 2),
        },
        "wall_seconds": round(wall_seconds, 3),
        "throughput_requests_per_second": round(args.requests / wall_seconds, 2),
        "database_pool": {
            "configured_size": pool_size,
            "max_overflow": pool_size,
            "max_simultaneous_checked_out": pool_stats["max_checked_out"],
        },
        "prd_reallocation_target_ms": 2000,
        "prd_target_evidence": "not comparable to production: local app test client, synthetic rows, localhost DB, no web server/proxy, and non-institutional schedule distribution",
        "websocket_notification_fanout": notification_delivery,
        "notification_delivery_target_ms": 3000,
        "notification_sample_scope": "authenticated local WebSocket clients and local app server; excludes production network and proxy",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["successful_requests"] == args.requests and notification_delivery["timed_out_or_invalid"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
