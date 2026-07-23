"""add mvp5 content and profile features

Revision ID: f5c1a4d98e21
Revises: e9a4c2d77b31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f5c1a4d98e21"
down_revision: str | None = "e9a4c2d77b31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    moderation_status = postgresql.ENUM(
        "pending", "approved", "restricted", "removed", name="moderation_status"
    )
    moderation_status.create(op.get_bind(), checkfirst=True)
    op.add_column("users", sa.Column("avatar_url", sa.String(500), nullable=True))
    op.add_column("users", sa.Column("bio", sa.String(500), nullable=True))
    for name, column in (
        ("author", sa.Column("author", sa.String(255), nullable=True)),
        ("publication_title", sa.Column("publication_title", sa.String(500), nullable=True)),
        ("publication_year", sa.Column("publication_year", sa.Integer(), nullable=True)),
        ("source", sa.Column("source", sa.String(500), nullable=True)),
        ("category", sa.Column("category", sa.String(80), nullable=True)),
        (
            "tags",
            sa.Column(
                "tags", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default="[]"
            ),
        ),
        (
            "moderation_status",
            sa.Column(
                "moderation_status",
                moderation_status,
                nullable=False,
                server_default="approved",
            ),
        ),
        ("moderation_note", sa.Column("moderation_note", sa.Text(), nullable=True)),
    ):
        op.add_column("documents", column)
    op.create_index("ix_documents_moderation_status", "documents", ["moderation_status"])
    op.add_column(
        "report_versions",
        sa.Column(
            "moderation_status", moderation_status, nullable=False, server_default="approved"
        ),
    )
    op.add_column("report_versions", sa.Column("moderation_note", sa.Text(), nullable=True))
    op.create_index(
        "ix_report_versions_moderation_status", "report_versions", ["moderation_status"]
    )
    op.create_table(
        "announcements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("pinned", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_announcements_pinned", "announcements", ["pinned"])
    op.create_index("ix_announcements_published_at", "announcements", ["published_at"])
    op.create_index("ix_announcements_expires_at", "announcements", ["expires_at"])
    op.create_index("ix_announcements_is_published", "announcements", ["is_published"])


def downgrade() -> None:
    op.drop_table("announcements")
    op.drop_index("ix_report_versions_moderation_status", table_name="report_versions")
    op.drop_column("report_versions", "moderation_note")
    op.drop_column("report_versions", "moderation_status")
    op.drop_index("ix_documents_moderation_status", table_name="documents")
    for name in (
        "moderation_note",
        "moderation_status",
        "tags",
        "category",
        "source",
        "publication_year",
        "publication_title",
        "author",
    ):
        op.drop_column("documents", name)
    op.drop_column("users", "bio")
    op.drop_column("users", "avatar_url")
    postgresql.ENUM(name="moderation_status").drop(op.get_bind(), checkfirst=True)
