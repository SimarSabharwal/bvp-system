"""Liveness and database readiness endpoints."""

from flask import jsonify
from sqlalchemy import text

from app.api.v1 import api_v1


@api_v1.get("/health")
def health():
    """Report process liveness without claiming the database is ready."""
    return jsonify({"status": "ok"})


@api_v1.get("/ready")
def ready():
    """Return ready only when the configured PostgreSQL database responds."""
    from app.extensions import database

    engine = database.get_engine()
    if engine is None:
        return jsonify({"status": "not_ready", "dependency": "database"}), 503
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception as error:
        from flask import current_app

        current_app.logger.warning("readiness database check failed error_type=%s",
                                   type(error).__name__)
        return jsonify({"status": "not_ready", "dependency": "database"}), 503
    return jsonify({"status": "ready"})
