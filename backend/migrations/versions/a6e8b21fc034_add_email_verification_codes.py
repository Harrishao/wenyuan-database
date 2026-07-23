"""add email verification codes

Revision ID: a6e8b21fc034
Revises: f5c1a4d98e21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a6e8b21fc034"
down_revision: str | None = "f5c1a4d98e21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("email_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_table(
        "email_codes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("code_hash", sa.String(255), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_email_codes_email", "email_codes", ["email"])
    op.create_index("ix_email_codes_purpose", "email_codes", ["purpose"])
    op.create_index("ix_email_codes_expires_at", "email_codes", ["expires_at"])
    op.create_index("ix_email_codes_created_at", "email_codes", ["created_at"])


def downgrade() -> None:
    op.drop_table("email_codes")
    op.drop_column("users", "email_verified")
