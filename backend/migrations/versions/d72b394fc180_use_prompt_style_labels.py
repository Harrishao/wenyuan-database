"""use user-facing prompt style labels

Revision ID: d72b394fc180
Revises: c47a1e9b520d
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d72b394fc180"
down_revision: str | Sequence[str] | None = "c47a1e9b520d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        UPDATE prompt_presets
        SET variant_key = CASE
            WHEN capability = 'report_generation' AND variant_key = 'default'
                THEN '默认生成'
            WHEN capability = 'general_chat' AND variant_key = 'default'
                THEN '普通对话'
            WHEN capability = 'local_polish' AND variant_key = 'academic'
                THEN '学术严谨'
            WHEN capability = 'local_polish' AND variant_key = 'plain'
                THEN '通俗表达'
            WHEN capability = 'local_polish' AND variant_key = 'concise'
                THEN '精简'
            WHEN capability = 'academic_assistant' AND variant_key = 'rigorous_mentor'
                THEN '严谨导师'
            WHEN capability = 'academic_assistant' AND variant_key = 'data_analyst'
                THEN '数据专家'
            ELSE variant_key
        END
        """
    )
    op.execute(
        """
        UPDATE chat_records
        SET variant_key = CASE
            WHEN capability = 'general_chat' AND variant_key = 'default'
                THEN '普通对话'
            WHEN capability = 'academic_assistant' AND variant_key = 'rigorous_mentor'
                THEN '严谨导师'
            WHEN capability = 'academic_assistant' AND variant_key = 'data_analyst'
                THEN '数据专家'
            ELSE variant_key
        END
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE prompt_presets
        SET variant_key = CASE
            WHEN capability = 'report_generation' AND variant_key = '默认生成'
                THEN 'default'
            WHEN capability = 'general_chat' AND variant_key = '普通对话'
                THEN 'default'
            WHEN capability = 'local_polish' AND variant_key = '学术严谨'
                THEN 'academic'
            WHEN capability = 'local_polish' AND variant_key = '通俗表达'
                THEN 'plain'
            WHEN capability = 'local_polish' AND variant_key = '精简'
                THEN 'concise'
            WHEN capability = 'academic_assistant' AND variant_key = '严谨导师'
                THEN 'rigorous_mentor'
            WHEN capability = 'academic_assistant' AND variant_key = '数据专家'
                THEN 'data_analyst'
            ELSE variant_key
        END
        """
    )
    op.execute(
        """
        UPDATE chat_records
        SET variant_key = CASE
            WHEN capability = 'general_chat' AND variant_key = '普通对话'
                THEN 'default'
            WHEN capability = 'academic_assistant' AND variant_key = '严谨导师'
                THEN 'rigorous_mentor'
            WHEN capability = 'academic_assistant' AND variant_key = '数据专家'
                THEN 'data_analyst'
            ELSE variant_key
        END
        """
    )
