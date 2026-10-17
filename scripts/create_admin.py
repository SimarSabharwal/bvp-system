"""Interactively provision the first active administrator account."""

from __future__ import annotations

import getpass
import sys

from sqlalchemy import select
from werkzeug.security import generate_password_hash

from app import create_app
from app.extensions import database
from app.models import User, UserRole


def main() -> int:
    app = create_app()
    if not app.config.get("DATABASE_URL"):
        print("DATABASE_URL must point to the intended PostgreSQL database.", file=sys.stderr)
        return 2
    login_id = input("Administrator login ID: ").strip()
    if not login_id or len(login_id) > 100:
        print("Login ID must contain 1 to 100 characters.", file=sys.stderr)
        return 2
    password = getpass.getpass("Administrator password (minimum 12 characters): ")
    confirmation = getpass.getpass("Confirm password: ")
    if len(password) < 12 or password != confirmation:
        print("Passwords must match and contain at least 12 characters.", file=sys.stderr)
        return 2
    with app.app_context():
        db = database.get_session()
        existing_admin = db.scalar(
            select(UserRole.user_id)
            .join(User, User.user_id == UserRole.user_id)
            .where(UserRole.role == "ADMIN", User.is_active.is_(True))
            .limit(1)
        )
        if existing_admin is not None:
            print("An administrator role already exists; use the authenticated admin API to provision users.", file=sys.stderr)
            return 2
        user = User(login_id=login_id, password_hash=generate_password_hash(password))
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.user_id, role="ADMIN"))
        db.commit()
        print(f"Administrator account created (user_id={user.user_id}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
