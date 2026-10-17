"""Student System Flask application factory."""

from __future__ import annotations

import os
import secrets
from uuid import uuid4

from dotenv import load_dotenv
from flask import Flask, g, jsonify, request
from werkzeug.exceptions import HTTPException, InternalServerError

from app.api.v1 import api_v1
from app.config import config_for, normalize_database_url
from app.extensions import database


def create_app(config_override: dict | None = None) -> Flask:
    """Create the API app from environment configuration without a hard-coded secret."""
    load_dotenv(override=False)
    environment = os.environ.get("APP_ENV", "development").lower()
    if environment not in {"development", "testing", "production"}:
        raise ValueError("APP_ENV must be development, testing, or production")

    app = Flask(__name__)
    app.config.from_mapping(config_for(environment))
    if config_override:
        app.config.update(config_override)

    if app.config.get("APP_ENV") != "production" and not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = secrets.token_urlsafe(32)

    if app.config.get("APP_ENV") == "production":
        app.config["SESSION_COOKIE_SECURE"] = True
    app.config["DATABASE_URL"] = normalize_database_url(app.config.get("DATABASE_URL"))
    _validate_production_config(app)
    database.init_app(app)

    app.register_blueprint(api_v1)
    from app.frontend import frontend_bp

    app.register_blueprint(frontend_bp)
    from app.realtime import register_realtime

    register_realtime(app)
    _register_request_metadata(app)
    _register_api_error_handlers(app)
    return app


def _validate_production_config(app: Flask) -> None:
    if app.config.get("APP_ENV") != "production":
        return
    missing = [
        key
        for key in ("SECRET_KEY", "DATABASE_URL")
        if not app.config.get(key)
    ]
    if missing:
        raise RuntimeError(
            "Production configuration is missing required environment values: "
            + ", ".join(missing)
        )


def _register_request_metadata(app: Flask) -> None:
    @app.before_request
    def assign_request_id() -> None:
        g.request_id = str(uuid4())

    @app.after_request
    def attach_request_id(response):
        request_id = getattr(g, "request_id", "")
        response.headers["X-Request-ID"] = request_id
        app.logger.info(
            "request completed request_id=%s method=%s endpoint=%s status=%s",
            request_id,
            request.method,
            request.endpoint or "unmatched",
            response.status_code,
        )
        return response


def _register_api_error_handlers(app: Flask) -> None:
    def is_api_request() -> bool:
        return request.path.startswith("/api/v1/")

    @app.errorhandler(HTTPException)
    def handle_http_exception(error: HTTPException):
        if not is_api_request():
            return error
        return _error_response(
            status=error.code or 500,
            code=(error.name or "http_error").lower().replace(" ", "_"),
            message=error.description,
        )

    @app.errorhandler(Exception)
    def handle_unexpected_exception(error: Exception):
        if not is_api_request():
            return InternalServerError()
        request_id = getattr(g, "request_id", "unknown")
        app.logger.exception("Unhandled API failure request_id=%s", request_id)
        return _error_response(
            status=500,
            code="internal_error",
            message="The request could not be completed.",
        )


def _error_response(status: int, code: str, message: str):
    return (
        jsonify(
            {
                "error": {
                    "code": code,
                    "message": message,
                    "details": [],
                    "request_id": getattr(g, "request_id", None),
                }
            }
        ),
        status,
    )
