"""Student System frontend blueprint.

Serves the single-page application shell for Student, Teacher, and Admin interfaces.
"""

from __future__ import annotations

from flask import Blueprint, render_template

frontend_bp = Blueprint("frontend", __name__, template_folder="templates", static_folder="static")


@frontend_bp.route("/", methods=["GET"])
@frontend_bp.route("/login", methods=["GET"])
@frontend_bp.route("/student", methods=["GET"])
@frontend_bp.route("/teacher", methods=["GET"])
@frontend_bp.route("/admin", methods=["GET"])
def index() -> str:
    """Serve the single-page application entry point."""
    return render_template("index.html")
