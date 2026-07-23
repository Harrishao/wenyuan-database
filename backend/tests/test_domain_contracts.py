from app.domain.enums import ProcessingStatus
from app.domain.models import Citation, DocumentChunk, SimilarityJob, SimilarityMatch, User


def test_core_tables_are_declared() -> None:
    assert User.__tablename__ == "users"
    assert DocumentChunk.__tablename__ == "document_chunks"


def test_job_state_contract_is_stable() -> None:
    assert [status.value for status in ProcessingStatus] == [
        "pending",
        "running",
        "succeeded",
        "failed",
        "cancelled",
    ]


def test_document_deletion_preserves_citation_snapshots() -> None:
    chunk_reference = next(iter(Citation.__table__.c.document_chunk_id.foreign_keys))
    similarity_reference = next(
        iter(SimilarityMatch.__table__.c.document_chunk_id.foreign_keys)
    )

    assert Citation.__table__.c.document_chunk_id.nullable is True
    assert chunk_reference.ondelete == "SET NULL"
    assert Citation.__table__.c.document_name_snapshot.nullable is False
    assert Citation.__table__.c.content_snapshot.nullable is False
    assert similarity_reference.ondelete == "CASCADE"


def test_report_deletion_cascades_similarity_jobs() -> None:
    report_version_reference = next(
        iter(SimilarityJob.__table__.c.report_version_id.foreign_keys)
    )
    assert report_version_reference.ondelete == "CASCADE"
