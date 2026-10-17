"""Authenticated WebSocket delivery backed by recipient notification rows."""

from __future__ import annotations

import queue
import select as socket_select
import threading
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit
from psycopg import connect

from flask import current_app, g, request
from itsdangerous import BadSignature
from flask_sock import Sock
from sqlalchemy import select

from app.api.v1.auth import current_identity
from app.extensions import database
from app.models import Notification


def _origin_key(value: str) -> tuple[str, str, int | None] | None:
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
            return None
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        return parsed.scheme.lower(), parsed.hostname.lower(), port
    except ValueError:
        return None


class RealtimeHub:
    """One PostgreSQL LISTEN connection per app worker, shared by its sockets."""

    def __init__(self, app):
        self.app = app
        self._lock = threading.Lock()
        self._subscribers: set[queue.Queue] = set()
        self._thread: threading.Thread | None = None
        self._stopping = threading.Event()
        self._ready = threading.Event()

    def subscribe(self) -> queue.Queue:
        subscriber: queue.Queue = queue.Queue(maxsize=1)
        with self._lock:
            self._subscribers.add(subscriber)
            if self._thread is None or not self._thread.is_alive():
                self._stopping.clear()
                self._thread = threading.Thread(target=self._listen, daemon=True,
                                                name="student-system-pg-listener")
                self._thread.start()
        self._ready.wait(timeout=5)
        return subscriber

    def unsubscribe(self, subscriber: queue.Queue) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def _publish(self) -> None:
        with self._lock:
            subscribers = tuple(self._subscribers)
        for subscriber in subscribers:
            try:
                subscriber.put_nowait(True)
            except queue.Full:
                pass  # A wake-up is only an invalidation; coalesce bursts safely.

    def _listen(self) -> None:
        delay = 1
        while not self._stopping.is_set():
            conn = None
            try:
                with self.app.app_context():
                    engine = database.get_engine()
                    if engine is None:
                        return
                    dsn = engine.url.render_as_string(hide_password=False).replace(
                        "postgresql+psycopg://", "postgresql://", 1)
                    conn = connect(dsn, autocommit=True)
                    conn.execute("LISTEN student_system_events")
                    self._ready.set()
                    delay = 1
                    while not self._stopping.is_set():
                        readable, _, _ = socket_select.select([conn], [], [], 1.0)
                        if readable:
                            for _notification in conn.notifies(timeout=0, stop_after=100):
                                self._publish()
            except Exception as error:  # No DSN or SQL values are logged.
                if not self._stopping.is_set():
                    self.app.logger.warning("realtime listener disconnected error_type=%s",
                                            type(error).__name__, exc_info=True)
                    self._stopping.wait(delay)
                    delay = min(delay * 2, 30)
            finally:
                self._ready.clear()
                if conn is not None:
                    conn.close()


def _notification_page(user_id: int, after_id: int) -> list[dict]:
    factory = current_app.extensions.get("student_system.session_factory")
    if factory is None:
        return []
    db = factory()
    try:
        rows = db.execute(select(Notification.notification_id, Notification.event_type,
            Notification.title, Notification.message, Notification.related_session_id,
            Notification.related_reallocation_id, Notification.created_at, Notification.read_at)
            .where(Notification.user_id == user_id, Notification.notification_id > after_id)
            .order_by(Notification.notification_id.asc()).limit(100)).all()
        return [{"notification_id": row.notification_id, "event_type": row.event_type,
                 "title": row.title, "message": row.message,
                 "class_session_id": row.related_session_id,
                 "reallocation_id": row.related_reallocation_id,
                 "created_at": row.created_at.isoformat(),
                 "read_at": row.read_at.isoformat() if row.read_at else None}
                for row in rows]
    finally:
        db.close()


def register_realtime(app) -> None:
    sock = Sock(app)
    hub = RealtimeHub(app)
    app.extensions["student_system.realtime_hub"] = hub
    app.extensions["student_system.websocket_slots"] = threading.BoundedSemaphore(
        app.config["WS_MAX_CONNECTIONS"])

    @sock.route("/api/v1/ws/events")
    def events(ws):
        origin = request.headers.get("Origin")
        if origin:
            configured = {_origin_key(value) for value in app.config["WEBSOCKET_ALLOWED_ORIGINS"]}
            request_host = urlsplit(f"//{request.host}")
            request_port = request_host.port
            if request_port is None:
                server_port = int(request.environ.get("SERVER_PORT", 443 if request.scheme == "https" else 80))
                request_port = server_port
            request_origin = (request.scheme.lower(), (request_host.hostname or "").lower(), request_port)
            if _origin_key(origin) not in configured | {request_origin}:
                ws.close()
                return
        identity = current_identity(required=False)
        if identity is None:
            ws.close(reason="Authentication required")
            return
        user_id = identity[0].user_id
        raw_db = g.pop("db_session", None)
        if raw_db is not None:
            raw_db.close()
        cookie_value = request.cookies.get(app.config["SESSION_COOKIE_NAME"])
        serializer = app.session_interface.get_signing_serializer(app)
        if not cookie_value or serializer is None:
            ws.close(reason="Session is unavailable")
            return
        try:
            signed_session, issued_at = serializer.loads(
                cookie_value,
                max_age=app.config["AUTH_SESSION_LIFETIME_SECONDS"],
                return_timestamp=True,
            )
        except BadSignature:
            ws.close(reason="Session expired")
            return
        if signed_session.get("user_id") != user_id:
            ws.close(reason="Session identity changed")
            return
        session_deadline = issued_at + timedelta(seconds=app.config["AUTH_SESSION_LIFETIME_SECONDS"])
        try:
            cursor = int(request.args.get("after_id", "0"))
        except ValueError:
            ws.close(reason="Invalid notification cursor")
            return
        if cursor < 0:
            ws.close(reason="Invalid notification cursor")
            return
        slots = app.extensions["student_system.websocket_slots"]
        if not slots.acquire(blocking=False):
            ws.close(reason="Connection capacity reached")
            return
        subscriber = hub.subscribe()
        try:
            ws.send(json.dumps({"type": "connected", "after_id": cursor}))
            # Catch up after LISTEN is active so writes during reconnect are not lost.
            while True:
                page = _notification_page(user_id, cursor)
                for item in page:
                    ws.send(json.dumps({"type": "notification", "data": item}))
                    cursor = item["notification_id"]
                if len(page) < 100:
                    break
            while True:
                try:
                    subscriber.get(timeout=app.config["WS_HEARTBEAT_SECONDS"])
                    woke = True
                except queue.Empty:
                    woke = False
                if datetime.now(timezone.utc) >= session_deadline:
                    ws.send(json.dumps({"type": "session_expired"}))
                    ws.close(reason="Session expired")
                    return
                active_identity = current_identity(required=False)
                active_db = g.pop("db_session", None)
                if active_db is not None:
                    active_db.close()
                if active_identity is None:
                    ws.close(reason="Account is no longer active")
                    return
                page = _notification_page(user_id, cursor)
                for item in page:
                    ws.send(json.dumps({"type": "notification", "data": item}))
                    cursor = item["notification_id"]
                if not page:
                    ws.send(json.dumps({"type": "refresh" if woke else "heartbeat", "cursor": cursor}))
        except Exception as error:
            app.logger.info("websocket closed error_type=%s", type(error).__name__)
            return
        finally:
            hub.unsubscribe(subscriber)
            slots.release()
