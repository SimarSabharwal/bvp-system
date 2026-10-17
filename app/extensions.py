"""Shared database engine and request-scoped SQLAlchemy sessions."""

from __future__ import annotations

from flask import current_app, g
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


class DatabaseExtension:
    def init_app(self, app) -> None:
        database_url = app.config.get("DATABASE_URL")
        engine: Engine | None = None
        make_session = None

        if database_url:
            engine = create_engine(
                database_url,
                pool_pre_ping=True,
                pool_size=app.config["DB_POOL_SIZE"],
                max_overflow=app.config["DB_MAX_OVERFLOW"],
                pool_timeout=app.config["DB_POOL_TIMEOUT"],
                pool_recycle=app.config["DB_POOL_RECYCLE"],
            )
            make_session = sessionmaker(
                bind=engine,
                class_=Session,
                autoflush=False,
                expire_on_commit=False,
            )

        app.extensions["student_system.database_engine"] = engine
        app.extensions["student_system.session_factory"] = make_session
        app.teardown_request(self._close_request_session)

    @staticmethod
    def _close_request_session(error: BaseException | None = None) -> None:
        session: Session | None = g.pop("db_session", None)
        if session is None:
            return
        if error is not None:
            session.rollback()
        session.close()

    @staticmethod
    def get_session() -> Session:
        """Return this request's session; callers own explicit transactions."""
        session: Session | None = g.get("db_session")
        if session is None:
            factory = current_app.extensions.get("student_system.session_factory")
            if factory is None:
                raise RuntimeError("PostgreSQL is not configured for this environment")
            session = factory()
            g.db_session = session
        return session

    @staticmethod
    def get_engine() -> Engine | None:
        return current_app.extensions.get("student_system.database_engine")


database = DatabaseExtension()
