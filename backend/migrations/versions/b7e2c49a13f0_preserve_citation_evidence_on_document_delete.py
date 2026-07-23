"""preserve citation evidence on document delete

Revision ID: b7e2c49a13f0
Revises: d4186c2c9f7f
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b7e2c49a13f0"
down_revision: str | Sequence[str] | None = "d4186c2c9f7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "citations",
        sa.Column("document_name_snapshot", sa.String(length=255), nullable=True),
    )
    op.add_column("citations", sa.Column("content_snapshot", sa.Text(), nullable=True))
    op.add_column(
        "citations",
        sa.Column("heading_snapshot", sa.String(length=500), nullable=True),
    )
    op.add_column("citations", sa.Column("page_number_snapshot", sa.Integer(), nullable=True))
    op.execute(
        """
        UPDATE citations AS citation
        SET document_name_snapshot = document.original_filename,
            content_snapshot = chunk.content,
            heading_snapshot = chunk.heading,
            page_number_snapshot = chunk.page_number
        FROM document_chunks AS chunk
        JOIN documents AS document ON document.id = chunk.document_id
        WHERE citation.document_chunk_id = chunk.id
        """
    )
    op.alter_column("citations", "document_name_snapshot", nullable=False)
    op.alter_column("citations", "content_snapshot", nullable=False)
    op.alter_column("citations", "document_chunk_id", existing_type=sa.Uuid(), nullable=True)
    op.drop_constraint(
        "fk_citations_document_chunk_id_document_chunks",
        "citations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_citations_document_chunk_id_document_chunks",
        "citations",
        "document_chunks",
        ["document_chunk_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint(
        "fk_similarity_matches_document_chunk_id_document_chunks",
        "similarity_matches",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_similarity_matches_document_chunk_id_document_chunks",
        "similarity_matches",
        "document_chunks",
        ["document_chunk_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_similarity_matches_document_chunk_id_document_chunks",
        "similarity_matches",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_similarity_matches_document_chunk_id_document_chunks",
        "similarity_matches",
        "document_chunks",
        ["document_chunk_id"],
        ["id"],
    )
    op.execute("DELETE FROM citations WHERE document_chunk_id IS NULL")
    op.drop_constraint(
        "fk_citations_document_chunk_id_document_chunks",
        "citations",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "fk_citations_document_chunk_id_document_chunks",
        "citations",
        "document_chunks",
        ["document_chunk_id"],
        ["id"],
    )
    op.alter_column("citations", "document_chunk_id", existing_type=sa.Uuid(), nullable=False)
    op.drop_column("citations", "page_number_snapshot")
    op.drop_column("citations", "heading_snapshot")
    op.drop_column("citations", "content_snapshot")
    op.drop_column("citations", "document_name_snapshot")
