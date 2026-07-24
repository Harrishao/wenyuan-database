"""add chat, Credits and storage quotas

Revision ID: aa13d5f72c40
Revises: a6e8b21fc034
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "aa13d5f72c40"
down_revision: str | Sequence[str] | None = "a6e8b21fc034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("storage_quota_bytes", sa.Integer(), nullable=True, server_default="52428800"),
    )
    op.add_column(
        "users",
        sa.Column("monthly_credits", sa.Numeric(18, 6), nullable=True, server_default="300"),
    )
    op.execute("UPDATE users SET storage_quota_bytes = NULL, monthly_credits = NULL WHERE role = 'admin'")

    op.add_column(
        "prompt_presets",
        sa.Column(
            "capability",
            sa.String(length=40),
            nullable=False,
            server_default="report_generation",
        ),
    )
    op.add_column(
        "prompt_presets",
        sa.Column("variant_key", sa.String(length=80), nullable=False, server_default="default"),
    )
    op.create_index("ix_prompt_presets_capability", "prompt_presets", ["capability"])
    op.create_index("ix_prompt_presets_variant_key", "prompt_presets", ["variant_key"])

    for name, column_type, default in (
        ("context_window_tokens", sa.Integer(), "128000"),
        ("max_output_tokens", sa.Integer(), "4096"),
        ("history_turn_limit", sa.Integer(), "12"),
        ("input_credits_per_million_tokens", sa.Numeric(18, 6), "0"),
        ("output_credits_per_million_tokens", sa.Numeric(18, 6), "0"),
        ("usage_mode", sa.String(length=20), "auto"),
    ):
        op.add_column(
            "llm_presets",
            sa.Column(name, column_type, nullable=False, server_default=default),
        )

    op.create_table(
        "chat_conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("report_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False, server_default="新对话"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["report_id"], ["reports.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_conversations_owner_id", "chat_conversations", ["owner_id"])
    op.create_index("ix_chat_conversations_report_id", "chat_conversations", ["report_id"])

    op.create_table(
        "chat_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("capability", sa.String(length=40), nullable=False),
        sa.Column("variant_key", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("usage_estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["chat_conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_chat_records_conversation_id", "chat_records", ["conversation_id"])
    op.create_index("ix_chat_records_created_at", "chat_records", ["created_at"])

    op.create_table(
        "credit_ledger",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=30), nullable=False),
        sa.Column("amount", sa.Numeric(18, 6), nullable=False),
        sa.Column("operation", sa.String(length=80), nullable=False),
        sa.Column("model", sa.String(length=255), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("estimated", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_credit_ledger_user_id", "credit_ledger", ["user_id"])
    op.create_index("ix_credit_ledger_kind", "credit_ledger", ["kind"])
    op.create_index("ix_credit_ledger_operation", "credit_ledger", ["operation"])
    op.create_index("ix_credit_ledger_created_at", "credit_ledger", ["created_at"])


def downgrade() -> None:
    op.drop_table("credit_ledger")
    op.drop_table("chat_records")
    op.drop_table("chat_conversations")
    for name in (
        "usage_mode",
        "output_credits_per_million_tokens",
        "input_credits_per_million_tokens",
        "history_turn_limit",
        "max_output_tokens",
        "context_window_tokens",
    ):
        op.drop_column("llm_presets", name)
    op.drop_index("ix_prompt_presets_variant_key", table_name="prompt_presets")
    op.drop_index("ix_prompt_presets_capability", table_name="prompt_presets")
    op.drop_column("prompt_presets", "variant_key")
    op.drop_column("prompt_presets", "capability")
    op.drop_column("users", "monthly_credits")
    op.drop_column("users", "storage_quota_bytes")
