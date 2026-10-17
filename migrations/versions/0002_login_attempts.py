"""Persist authentication throttling state.

Revision ID: 0002_login_attempts
Revises: 0001_initial_schema
"""
from alembic import op
import sqlalchemy as sa

revision = "0002_login_attempts"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("uq_users_login_id_ci", "users", [sa.text("lower(login_id)")], unique=True)
    op.create_table(
        "login_attempts",
        sa.Column("login_id", sa.String(length=100), nullable=False),
        sa.Column("failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("failures >= 0", name="login_attempts_nonnegative_failures"),
        sa.PrimaryKeyConstraint("login_id"),
    )


def downgrade() -> None:
    op.drop_table("login_attempts")
    op.drop_index("uq_users_login_id_ci", table_name="users")
