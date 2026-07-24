"""add manageable prompt capabilities

Revision ID: c47a1e9b520d
Revises: ab27e6c8019d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c47a1e9b520d"
down_revision: str | Sequence[str] | None = "ab27e6c8019d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_capabilities",
        sa.Column("key", sa.String(length=40), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.PrimaryKeyConstraint("key"),
        sa.UniqueConstraint("name", name="uq_prompt_capabilities_name"),
    )
    op.execute(
        """
        INSERT INTO prompt_capabilities (key, name, is_system)
        VALUES
            ('report_generation', '报告生成', TRUE),
            ('general_chat', '普通对话', TRUE),
            ('local_polish', '局部润色', TRUE),
            ('academic_assistant', '学术助手', FALSE)
        """
    )
    op.execute(
        """
        INSERT INTO prompt_capabilities (key, name, is_system)
        SELECT DISTINCT capability, capability, FALSE
        FROM prompt_presets
        WHERE capability NOT IN (
            SELECT key FROM prompt_capabilities
        )
        """
    )


def downgrade() -> None:
    op.drop_table("prompt_capabilities")
