from app.domain.enums import ProcessingStatus
from app.domain.models import DocumentChunk, User


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
