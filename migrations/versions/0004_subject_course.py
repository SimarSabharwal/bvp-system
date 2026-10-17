"""Associate subject catalog entries with their course.

Revision ID: 0004_subject_course
Revises: 0003_reallocation_cascade_groups
"""
from alembic import op
import sqlalchemy as sa

revision = "0004_subject_course"
down_revision = "0003_reallocation_cascade_groups"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable for legacy catalog rows whose course has not yet been mapped.
    op.add_column("subjects", sa.Column("course_id", sa.Integer(), nullable=True))
    op.add_column("subjects", sa.Column("semester", sa.Integer(), nullable=True))
    op.add_column("subjects", sa.Column("curriculum_version", sa.String(length=40), nullable=True))
    op.add_column("subjects", sa.Column("subject_type", sa.String(length=40), nullable=True))
    op.create_foreign_key("fk_subject_course", "subjects", "courses", ["course_id"], ["course_id"], ondelete="RESTRICT")
    op.create_index("ix_subjects_course_id", "subjects", ["course_id"])
    op.create_check_constraint("subject_positive_semester", "subjects", "semester IS NULL OR semester > 0")


def downgrade() -> None:
    op.drop_constraint("subject_positive_semester", "subjects", type_="check")
    op.drop_index("ix_subjects_course_id", table_name="subjects")
    op.drop_constraint("fk_subject_course", "subjects", type_="foreignkey")
    op.drop_column("subjects", "subject_type")
    op.drop_column("subjects", "curriculum_version")
    op.drop_column("subjects", "semester")
    op.drop_column("subjects", "course_id")
