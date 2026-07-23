import asyncio
import re
from collections import Counter
from pathlib import Path
from uuid import UUID

from sqlalchemy import delete

from app.adapters.local_file_storage import LocalFileStorage
from app.core.config import get_settings
from app.db.session import SessionFactory
from app.domain.enums import ModerationStatus, ProcessingStatus
from app.domain.models import BackgroundJob, Document, DocumentChunk
from app.services.ai_config import get_runtime_embedding
from app.services.chunking import chunk_blocks
from app.services.document_parser import parse_document
from app.services.sensitive_scan import scan_sensitive_text

settings = get_settings()
storage = LocalFileStorage(settings.storage_root)
STOP_WORDS = {"本文", "研究", "系统", "方法", "通过", "进行", "基于", "以及", "中的", "可以"}


def extract_keywords(text: str, limit: int = 8) -> list[str]:
    candidates: list[str] = []
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}", text):
        if re.fullmatch(r"[\u4e00-\u9fff]+", token):
            candidates.extend(token[index : index + 4] for index in range(max(1, len(token) - 3)))
        else:
            candidates.append(token.lower())
    counts = Counter(word for word in candidates if word not in STOP_WORDS)
    return [word for word, _ in counts.most_common(limit)]


async def process_document(document_id: UUID, job_id: UUID) -> None:
    async with SessionFactory() as session:
        document = await session.get(Document, document_id)
        job = await session.get(BackgroundJob, job_id)
        if document is None or job is None:
            return
        document.status = ProcessingStatus.RUNNING
        job.status = ProcessingStatus.RUNNING
        job.progress = 5
        job.attempts += 1
        await session.commit()

    try:
        suffix = Path(document.original_filename).suffix
        path = storage.resolve(document.storage_key)
        blocks = await asyncio.to_thread(parse_document, path, suffix)
        chunks = chunk_blocks(
            blocks,
            target_size=settings.chunk_target_chars,
            overlap=settings.chunk_overlap_chars,
        )
        if not chunks:
            raise ValueError("文档没有产生有效片段")
        async with SessionFactory() as config_session:
            embedding = await get_runtime_embedding(config_session)
        vectors = await embedding.embed_documents([chunk.content for chunk in chunks])
        full_text = "\n".join(block.text for block in blocks)

        async with SessionFactory() as session:
            document = await session.get(Document, document_id)
            job = await session.get(BackgroundJob, job_id)
            if document is None or job is None:
                return
            await session.execute(
                delete(DocumentChunk).where(DocumentChunk.document_id == document_id)
            )
            session.add_all(
                [
                    DocumentChunk(
                        document_id=document_id,
                        position=chunk.position,
                        content=chunk.content,
                        heading=chunk.heading,
                        page_number=chunk.page_number,
                        char_count=len(chunk.content),
                        embedding=vector,
                        embedding_model=embedding.model_name,
                        processing_version=(
                            f"mvp1-v1:target={settings.chunk_target_chars}:"
                            f"overlap={settings.chunk_overlap_chars}"
                        ),
                    )
                    for chunk, vector in zip(chunks, vectors, strict=True)
                ]
            )
            document.summary = re.sub(r"\s+", " ", full_text).strip()[:360]
            document.keywords = extract_keywords(full_text)
            document.sensitive_hits = await scan_sensitive_text(session, full_text)
            document.moderation_status = (
                ModerationStatus.PENDING if document.sensitive_hits else ModerationStatus.APPROVED
            )
            document.parser_version = "mvp1-v1"
            document.status = ProcessingStatus.SUCCEEDED
            document.error_message = None
            job.status = ProcessingStatus.SUCCEEDED
            job.progress = 100
            job.result = {"document_id": str(document_id), "chunk_count": len(chunks)}
            await session.commit()
    except Exception as exc:
        async with SessionFactory() as session:
            document = await session.get(Document, document_id)
            job = await session.get(BackgroundJob, job_id)
            if document:
                document.status = ProcessingStatus.FAILED
                document.error_message = str(exc)[:1000]
            if job:
                job.status = ProcessingStatus.FAILED
                job.error_message = str(exc)[:1000]
            await session.commit()
