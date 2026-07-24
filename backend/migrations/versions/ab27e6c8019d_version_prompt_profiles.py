"""make prompt profile versions immutable

Revision ID: ab27e6c8019d
Revises: aa13d5f72c40
"""

from collections.abc import Sequence

from alembic import op

revision: str = "ab27e6c8019d"
down_revision: str | Sequence[str] | None = "aa13d5f72c40"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_prompt_presets_name", "prompt_presets", type_="unique")
    op.create_unique_constraint(
        "uq_prompt_presets_name_version", "prompt_presets", ["name", "version"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_prompt_presets_name_version", "prompt_presets", type_="unique")
    op.create_unique_constraint("uq_prompt_presets_name", "prompt_presets", ["name"])
