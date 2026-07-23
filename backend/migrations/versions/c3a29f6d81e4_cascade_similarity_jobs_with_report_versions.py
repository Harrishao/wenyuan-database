"""cascade similarity jobs with report versions

Revision ID: c3a29f6d81e4
Revises: b7e2c49a13f0
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c3a29f6d81e4"
down_revision: str | Sequence[str] | None = "b7e2c49a13f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "fk_similarity_jobs_report_version_id_report_versions",
        "similarity_jobs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_similarity_jobs_report_version_id_report_versions",
        "similarity_jobs",
        "report_versions",
        ["report_version_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_similarity_jobs_report_version_id_report_versions",
        "similarity_jobs",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_similarity_jobs_report_version_id_report_versions",
        "similarity_jobs",
        "report_versions",
        ["report_version_id"],
        ["id"],
    )
