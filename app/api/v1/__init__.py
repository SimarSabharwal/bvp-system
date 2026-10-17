"""Version 1 JSON API routes."""

from flask import Blueprint

api_v1 = Blueprint("api_v1", __name__, url_prefix="/api/v1")

from app.api.v1 import health  # noqa: E402,F401
from app.api.v1 import auth, master_data, scheduling, reallocation, schedule_queries  # noqa: E402,F401
from app.api.v1 import attendance, communications, reports  # noqa: E402,F401
from app.api.v1 import smart_timetable  # noqa: E402,F401
from app.api.v1 import mock_data  # noqa: E402,F401
