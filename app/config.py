"""Environment-backed app configuration."""

from __future__ import annotations

import os
from datetime import timedelta


def _integer_setting(name: str, default: int, *, minimum: int = 0) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer") from error
    if parsed < minimum:
        raise RuntimeError(f"{name} must be at least {minimum}")
    return parsed


def normalize_database_url(value: str | None) -> str | None:
    if not value:
        return None
    if value.startswith("postgres://"):
        value = "postgresql+psycopg://" + value[len("postgres://") :]
    elif value.startswith("postgresql://"):
        value = "postgresql+psycopg://" + value[len("postgresql://") :]
    if not value.startswith("postgresql+psycopg://"):
        raise RuntimeError("DATABASE_URL must use PostgreSQL with the Psycopg 3 driver")
    return value


class BaseConfig:
    INSTITUTION_TIMEZONE = "Asia/Kolkata"
    JSON_SORT_KEYS = False
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_NAME = "student_system_session"
    MAX_CONTENT_LENGTH = 1_048_576
    SOCK_SERVER_OPTIONS = {"ping_interval": 25, "max_message_size": 1024}
    AUTH_LOGIN_MAX_FAILURES = 5
    AUTH_LOGIN_WINDOW_SECONDS = 900
    AUTH_LOGIN_LOCK_SECONDS = 900
    API_MAX_PAGE_SIZE = 100


class DevelopmentConfig(BaseConfig):
    DEBUG = False


class TestingConfig(BaseConfig):
    TESTING = True


class ProductionConfig(BaseConfig):
    DEBUG = False


CONFIGS = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def config_for(environment: str) -> dict:
    """Build a fresh config mapping from the environment at app creation time."""
    config_class = CONFIGS[environment]
    config = {}
    for base in reversed(config_class.__mro__):
        config.update(
            {
                key: value
                for key, value in vars(base).items()
                if key.isupper()
            }
        )
    config.update(
        APP_ENV=environment,
        SECRET_KEY=os.environ.get("SECRET_KEY") or None,
        DATABASE_URL=os.environ.get("DATABASE_URL") or None,
        DB_POOL_SIZE=_integer_setting("DB_POOL_SIZE", 5, minimum=1),
        DB_MAX_OVERFLOW=_integer_setting("DB_MAX_OVERFLOW", 5),
        DB_POOL_TIMEOUT=_integer_setting("DB_POOL_TIMEOUT", 30, minimum=1),
        DB_POOL_RECYCLE=_integer_setting("DB_POOL_RECYCLE", 1800, minimum=1),
        OUTBOX_BATCH_SIZE=min(_integer_setting("OUTBOX_BATCH_SIZE", 100, minimum=1), 500),
        OUTBOX_POLL_SECONDS=_integer_setting("OUTBOX_POLL_SECONDS", 1, minimum=1),
        WS_HEARTBEAT_SECONDS=_integer_setting("WS_HEARTBEAT_SECONDS", 25, minimum=5),
        WS_MAX_CONNECTIONS=_integer_setting("WS_MAX_CONNECTIONS", 300, minimum=1),
        AUTH_SESSION_LIFETIME_SECONDS=_integer_setting("AUTH_SESSION_LIFETIME_SECONDS", 28800, minimum=300),
        WEBSOCKET_ALLOWED_ORIGINS=tuple(filter(None, (
            item.strip().rstrip("/") for item in os.environ.get("WEBSOCKET_ALLOWED_ORIGINS", "").split(",")
        ))),
        SESSION_COOKIE_SECURE=environment == "production",
        AUTH_LOGIN_MAX_FAILURES=_integer_setting("AUTH_LOGIN_MAX_FAILURES", 5, minimum=1),
        AUTH_LOGIN_WINDOW_SECONDS=_integer_setting("AUTH_LOGIN_WINDOW_SECONDS", 900, minimum=1),
        AUTH_LOGIN_LOCK_SECONDS=_integer_setting("AUTH_LOGIN_LOCK_SECONDS", 900, minimum=1),
        API_MAX_PAGE_SIZE=min(_integer_setting("API_MAX_PAGE_SIZE", 100, minimum=1), 100),
        MAX_CONTENT_LENGTH=_integer_setting("API_MAX_CONTENT_LENGTH", 1_048_576, minimum=1024),
        PERMANENT_SESSION_LIFETIME=timedelta(seconds=_integer_setting(
            "AUTH_SESSION_LIFETIME_SECONDS", 28800, minimum=300)),
    )
    return config
