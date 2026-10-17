"""Group reallocation chains for atomic cascade decisions.

Revision ID: 0003_reallocation_cascade_groups
Revises: 0002_login_attempts
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0003_reallocation_cascade_groups"
down_revision = "0002_login_attempts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reallocations",
        sa.Column("cascade_group_id", postgresql.UUID(as_uuid=True), nullable=False, server_default=sa.text("gen_random_uuid()")),
    )
    op.add_column(
        "reallocations",
        sa.Column("cascade_depth", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "reallocations",
        sa.Column("parent_reallocation_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_reallocation_parent", "reallocations", "reallocations",
        ["parent_reallocation_id"], ["reallocation_id"], ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "reallocation_cascade_depth_range", "reallocations", "cascade_depth BETWEEN 0 AND 2",
    )
    op.create_check_constraint(
        "reallocation_cascade_root_depth", "reallocations",
        "parent_reallocation_id IS NOT NULL OR cascade_depth = 0",
    )
    op.create_index(
        "ix_reallocations_cascade_group_depth", "reallocations", ["cascade_group_id", "cascade_depth"],
    )


def downgrade() -> None:
    op.drop_index("ix_reallocations_cascade_group_depth", table_name="reallocations")
    op.drop_constraint("reallocation_cascade_root_depth", "reallocations", type_="check")
    op.drop_constraint("reallocation_cascade_depth_range", "reallocations", type_="check")
    op.drop_constraint("fk_reallocation_parent", "reallocations", type_="foreignkey")
    op.drop_column("reallocations", "parent_reallocation_id")
    op.drop_column("reallocations", "cascade_depth")
    op.drop_column("reallocations", "cascade_group_id")
