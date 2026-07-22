import json
import re
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.local_hashing_embedding import LocalHashingEmbedding
from app.adapters.report_llm import LocalEvidenceDraftLlm, OpenAICompatibleLlm
from app.core.config import get_settings
from app.db.session import SessionFactory
from app.domain.enums import ProcessingStatus, ReportStatus
from app.domain.models import (
    BackgroundJob,
    Citation,
    Document,
    DocumentChunk,
    Report,
    ReportSection,
    ReportVersion,
    TemplateSection,
    TemplateVersion,
)
from app.ports.llm import ChatMessage, ChatOptions

settings = get_settings()
embedding = LocalHashingEmbedding(settings.embedding_dimensions)
PROMPT_VERSION = "mvp2-v1"


def get_report_llm() -> LocalEvidenceDraftLlm | OpenAICompatibleLlm:
    if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
        return OpenAICompatibleLlm(
            settings.llm_base_url,
            settings.llm_api_key.get_secret_value(),
            settings.llm_model,
        )
    return LocalEvidenceDraftLlm()


async def retrieve_evidence(
    session: AsyncSession, report: Report, query: str, top_k: int
) -> list[tuple[DocumentChunk, str, float]]:
    query_vector = await embedding.embed_query(query)
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    rows = (
        await session.execute(
            select(DocumentChunk, Document.original_filename, distance.label("distance"))
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(
                Document.knowledge_base_id == report.knowledge_base_id,
                Document.uploaded_by == report.owner_id,
                Document.status == ProcessingStatus.SUCCEEDED,
                DocumentChunk.embedding.is_not(None),
            )
            .order_by(distance)
            .limit(top_k)
        )
    ).all()
    return [
        (chunk, name, max(0.0, 1.0 - float(distance_value)))
        for chunk, name, distance_value in rows
    ]


def validate_citation_markers(content: str, evidence_count: int) -> tuple[str, list[int]]:
    used: set[int] = set()

    def replace(match: re.Match[str]) -> str:
        marker = int(match.group(1))
        if 1 <= marker <= evidence_count:
            used.add(marker)
            return match.group(0)
        return ""

    cleaned = re.sub(r"\[(\d+)\]", replace, content)
    return cleaned.strip(), sorted(used)


async def rebuild_version_markdown(session: AsyncSession, version: ReportVersion) -> None:
    sections = (
        await session.scalars(
            select(ReportSection)
            .where(ReportSection.report_version_id == version.id)
            .order_by(ReportSection.position)
        )
    ).all()
    version.content_markdown = "\n\n".join(
        f"## {section.title}\n\n{section.content_markdown}" for section in sections
    )


async def generate_report_sections(
    report_id: UUID, job_id: UUID, section_keys: list[str] | None = None
) -> None:
    llm = get_report_llm()
    try:
        async with SessionFactory() as session:
            report = await session.get(Report, report_id)
            job = await session.get(BackgroundJob, job_id)
            if report is None or job is None:
                return
            report.status = ReportStatus.GENERATING
            job.status = ProcessingStatus.RUNNING
            job.progress = 1
            job.attempts += 1
            await session.commit()

        async with SessionFactory() as session:
            report = await session.get(Report, report_id)
            if report is None:
                return
            version = await session.scalar(
                select(ReportVersion).where(
                    ReportVersion.report_id == report.id,
                    ReportVersion.version == report.current_version,
                )
            )
            template_version = await session.get(TemplateVersion, report.template_version_id)
            job = await session.get(BackgroundJob, job_id)
            if version is None or template_version is None or job is None:
                return
            inputs = version.generation_context.get("inputs", {})
            template_sections = (
                await session.scalars(
                    select(TemplateSection)
                    .where(TemplateSection.template_version_id == template_version.id)
                    .order_by(TemplateSection.position)
                )
            ).all()
            if section_keys:
                wanted = set(section_keys)
                template_sections = [item for item in template_sections if item.key in wanted]
            total = len(template_sections)
            completed: list[str] = []

            for index, template_section in enumerate(template_sections, start=1):
                job.result = {
                    "current_section": template_section.key,
                    "completed_sections": completed,
                    "model": llm.model_name,
                    "prompt_version": PROMPT_VERSION,
                }
                job.progress = max(5, int((index - 1) / max(1, total) * 90))
                await session.commit()

                topic = inputs.get("topic", report.title)
                research_goal = inputs.get("research_goal", "")
                query = " ".join(
                    part
                    for part in (
                        topic,
                        research_goal,
                        template_section.title,
                        template_section.instructions,
                    )
                    if part
                )
                top_k = int(template_version.settings.get("top_k", 4))
                evidence = await retrieve_evidence(session, report, query, top_k)
                evidence_payload = [
                    {
                        "marker": number,
                        "document": document_name,
                        "heading": chunk.heading,
                        "page_number": chunk.page_number,
                        "content": chunk.content,
                        "similarity": similarity,
                    }
                    for number, (chunk, document_name, similarity) in enumerate(evidence, start=1)
                ]
                prompt = json.dumps(
                    {
                        "topic": topic,
                        "research_goal": research_goal,
                        "section_title": template_section.title,
                        "section_instructions": template_section.instructions,
                        "evidence": evidence_payload,
                        "output": "中文 Markdown 正文；引用只能写为 [1]、[2] 等已有编号。",
                    },
                    ensure_ascii=False,
                )
                content = await llm.chat(
                    [
                        ChatMessage(role="system", content=template_version.system_prompt),
                        ChatMessage(role="user", content=prompt),
                    ],
                    ChatOptions(
                        temperature=0.2,
                        max_tokens=1200,
                        metadata={"report_id": str(report.id), "section": template_section.key},
                    ),
                )
                content, used_markers = validate_citation_markers(content, len(evidence))
                section = await session.scalar(
                    select(ReportSection).where(
                        ReportSection.report_version_id == version.id,
                        ReportSection.key == template_section.key,
                    )
                )
                if section is None:
                    continue
                section.content_markdown = content
                await session.execute(
                    delete(Citation).where(Citation.report_section_id == section.id)
                )
                session.add_all(
                    [
                        Citation(
                            report_section_id=section.id,
                            document_chunk_id=evidence[marker - 1][0].id,
                            marker=f"[{marker}]",
                        )
                        for marker in used_markers
                    ]
                )
                context = dict(version.generation_context)
                retrieval = dict(context.get("retrieval", {}))
                retrieval[template_section.key] = {
                    "query": query,
                    "chunk_ids": [str(item[0].id) for item in evidence],
                    "model": llm.model_name,
                    "embedding_model": embedding.model_name,
                    "prompt_version": PROMPT_VERSION,
                    "top_k": top_k,
                }
                context["retrieval"] = retrieval
                version.generation_context = context
                completed.append(template_section.key)
                await rebuild_version_markdown(session, version)
                await session.commit()

            report.status = ReportStatus.READY
            job.status = ProcessingStatus.SUCCEEDED
            job.progress = 100
            job.result = {
                "completed_sections": completed,
                "current_section": None,
                "model": llm.model_name,
                "prompt_version": PROMPT_VERSION,
            }
            await session.commit()
    except Exception as exc:
        async with SessionFactory() as session:
            report = await session.get(Report, report_id)
            job = await session.get(BackgroundJob, job_id)
            if report:
                report.status = ReportStatus.FAILED
            if job:
                job.status = ProcessingStatus.FAILED
                job.error_message = str(exc)[:1000]
            await session.commit()
