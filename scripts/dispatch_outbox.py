"""Dispatch committed outbox rows to PostgreSQL's transient realtime channel."""

from __future__ import annotations

import argparse
import logging
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app import create_app
from app.extensions import database
from app.models import OutboxEvent

logger = logging.getLogger("student_system.outbox")


def dispatch_batch(app) -> int:
    factory = app.extensions.get("student_system.session_factory")
    if factory is None:
        raise RuntimeError("DATABASE_URL is required to dispatch outbox events")
    db = factory()
    rows = []
    try:
        rows = db.scalars(select(OutboxEvent).where(
            OutboxEvent.delivered_at.is_(None),
            OutboxEvent.available_at <= func.now(),
        ).order_by(OutboxEvent.outbox_event_id).limit(app.config["OUTBOX_BATCH_SIZE"])
            .with_for_update(skip_locked=True)).all()
        if not rows:
            db.rollback()
            return 0
        now = datetime.now(timezone.utc)
        for row in rows:
            db.execute(select(func.pg_notify("student_system_events", str(row.outbox_event_id))))
            row.delivered_at = now
            row.attempts += 1
            row.last_error = None
        db.commit()  # PostgreSQL emits these notifications only when this transaction commits.
        logger.info("outbox batch delivered count=%d", len(rows))
        return len(rows)
    except Exception as error:
        ids = [row.outbox_event_id for row in rows]
        db.rollback()
        logger.warning("outbox batch failed count=%d error_type=%s", len(rows), type(error).__name__)
        db.close()
        if ids:
            retry = factory()
            try:
                retry_rows = retry.scalars(select(OutboxEvent).where(
                    OutboxEvent.outbox_event_id.in_(ids), OutboxEvent.delivered_at.is_(None)
                ).with_for_update()).all()
                now = datetime.now(timezone.utc)
                for row in retry_rows:
                    row.attempts += 1
                    row.last_error = type(error).__name__
                    row.available_at = now + timedelta(seconds=min(2 ** min(row.attempts, 8), 300))
                retry.commit()
            except Exception:
                retry.rollback()
                logger.exception("could not persist outbox retry schedule")
            finally:
                retry.close()
        return 0
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true", help="dispatch one due batch and exit")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    app = create_app()
    if app.extensions.get("student_system.database_engine") is None:
        raise SystemExit("DATABASE_URL is required to dispatch outbox events")
    with app.app_context():
        while True:
            count = dispatch_batch(app)
            if args.once:
                return
            if count == 0:
                time.sleep(app.config["OUTBOX_POLL_SECONDS"])


if __name__ == "__main__":
    main()
