import json
from collections.abc import AsyncIterator
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import select

from app.api.dependencies import CurrentUser, SessionDep
from app.core.errors import AppError
from app.db.session import SessionFactory
from app.domain.models import (
    ChatConversation,
    ChatRecord,
    LlmPreset,
    PromptCapability,
    PromptPreset,
    Report,
    ReportSection,
    ReportVersion,
    User,
)
from app.ports.llm import ChatMessage, ChatOptions, LlmUsage
from app.schemas.report import (
    ChatRecordResponse,
    ChatStreamRequest,
    ConversationCreate,
    ConversationResponse,
    ConversationUpdate,
    PromptCapabilityOption,
    PromptVariantOption,
)
from app.services.ai_config import get_prompt_profile, get_runtime_llm, render_prompt_messages
from app.services.quotas import ensure_credits, ensure_storage, record_llm_usage
from app.services.report_generation import retrieve_evidence

router = APIRouter()

DEFAULT_PROMPTS = {
    ("general_chat", "default"): (
        "你是文渊学术报告助手。回答必须基于当前报告和给定证据；"
        "证据不足时明确说明，不得编造来源、数据或结论。"
    ),
    ("academic_assistant", "rigorous_mentor"): (
        "你是严谨导师。你需要检查概念准确性、论证边界、证据充分性和结论强度，"
        "提出可执行的修改意见，不得伪造事实或引用。"
    ),
    ("academic_assistant", "data_analyst"): (
        "你是数据分析专家。你需要关注指标定义、样本、方法、可验证数据、统计限制"
        "和推断边界，不得用缺失数据支撑结论。"
    ),
}


@router.get("/prompt-options", response_model=list[PromptCapabilityOption])
async def list_prompt_options(
    session: SessionDep, current_user: CurrentUser
) -> list[PromptCapabilityOption]:
    del current_user
    rows = (
        await session.execute(
            select(PromptCapability, PromptPreset)
            .join(PromptPreset, PromptPreset.capability == PromptCapability.key)
            .where(PromptPreset.is_active.is_(True))
            .order_by(
                PromptCapability.created_at,
                PromptPreset.name,
                PromptPreset.version.desc(),
            )
        )
    ).all()
    grouped: dict[str, PromptCapabilityOption] = {}
    for capability, preset in rows:
        group = grouped.setdefault(
            capability.key,
            PromptCapabilityOption(
                key=capability.key,
                name=capability.name,
                variants=[],
            ),
        )
        if not any(item.key == preset.variant_key for item in group.variants):
            group.variants.append(
                PromptVariantOption(key=preset.variant_key, label=preset.variant_key)
            )
    return list(grouped.values())


def message_response(item: ChatRecord) -> ChatRecordResponse:
    return ChatRecordResponse(
        id=item.id,
        role=item.role,
        content=item.content,
        capability=item.capability,
        variant_key=item.variant_key,
        model=item.model,
        usage_estimated=item.usage_estimated,
        created_at=item.created_at,
    )


async def owned_conversation(
    session: SessionDep, conversation_id: UUID, owner_id: UUID
) -> ChatConversation:
    item = await session.scalar(
        select(ChatConversation).where(
            ChatConversation.id == conversation_id,
            ChatConversation.owner_id == owner_id,
        )
    )
    if item is None:
        raise AppError("CHAT_NOT_FOUND", "对话不存在", status_code=404)
    return item


@router.get("/{report_id}/conversations", response_model=list[ConversationResponse])
async def list_conversations(
    report_id: UUID, session: SessionDep, current_user: CurrentUser
) -> list[ConversationResponse]:
    report = await session.scalar(
        select(Report).where(Report.id == report_id, Report.owner_id == current_user.id)
    )
    if report is None:
        raise AppError("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    rows = list(
        await session.scalars(
            select(ChatConversation)
            .where(
                ChatConversation.report_id == report_id,
                ChatConversation.owner_id == current_user.id,
            )
            .order_by(ChatConversation.updated_at.desc())
        )
    )
    return [
        ConversationResponse(
            id=item.id,
            report_id=item.report_id,
            title=item.title,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )
        for item in rows
    ]


@router.post(
    "/{report_id}/conversations",
    response_model=ConversationResponse,
    status_code=201,
)
async def create_conversation(
    report_id: UUID,
    payload: ConversationCreate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ConversationResponse:
    report = await session.scalar(
        select(Report).where(Report.id == report_id, Report.owner_id == current_user.id)
    )
    if report is None:
        raise AppError("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    item = ChatConversation(
        owner_id=current_user.id,
        report_id=report.id,
        title=payload.title.strip(),
    )
    session.add(item)
    await session.commit()
    await session.refresh(item)
    return ConversationResponse(
        id=item.id,
        report_id=item.report_id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
async def get_conversation(
    conversation_id: UUID, session: SessionDep, current_user: CurrentUser
) -> ConversationResponse:
    item = await owned_conversation(session, conversation_id, current_user.id)
    records = list(
        await session.scalars(
            select(ChatRecord)
            .where(ChatRecord.conversation_id == item.id)
            .order_by(ChatRecord.created_at)
        )
    )
    return ConversationResponse(
        id=item.id,
        report_id=item.report_id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
        messages=[message_response(record) for record in records],
    )


@router.patch("/conversations/{conversation_id}", response_model=ConversationResponse)
async def rename_conversation(
    conversation_id: UUID,
    payload: ConversationUpdate,
    session: SessionDep,
    current_user: CurrentUser,
) -> ConversationResponse:
    item = await owned_conversation(session, conversation_id, current_user.id)
    item.title = payload.title.strip()
    await session.commit()
    await session.refresh(item)
    return ConversationResponse(
        id=item.id,
        report_id=item.report_id,
        title=item.title,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.delete("/conversations/{conversation_id}", status_code=204)
async def delete_conversation(
    conversation_id: UUID, session: SessionDep, current_user: CurrentUser
) -> None:
    item = await owned_conversation(session, conversation_id, current_user.id)
    await session.delete(item)
    await session.commit()


@router.post("/conversations/{conversation_id}/stream")
async def stream_conversation(
    conversation_id: UUID,
    payload: ChatStreamRequest,
    session: SessionDep,
    current_user: CurrentUser,
) -> StreamingResponse:
    conversation = await owned_conversation(session, conversation_id, current_user.id)
    user = await session.get(User, current_user.id)
    if user is None:
        raise AppError("USER_NOT_FOUND", "用户不存在", status_code=404)
    await ensure_credits(session, user)
    preset = await session.scalar(
        select(LlmPreset).where(LlmPreset.is_active.is_(True)).limit(1)
    )
    output_reserve = (preset.max_output_tokens if preset else 1200) * 4
    await ensure_storage(
        session,
        user,
        len(payload.question.encode("utf-8")) + output_reserve,
    )
    report = await session.get(Report, conversation.report_id)
    if report is None:
        raise AppError("REPORT_NOT_FOUND", "报告不存在", status_code=404)
    version = await session.scalar(
        select(ReportVersion).where(
            ReportVersion.report_id == report.id,
            ReportVersion.version == report.current_version,
        )
    )
    if version is None:
        raise AppError("REPORT_VERSION_NOT_FOUND", "报告版本不存在", status_code=404)
    section_text = ""
    if payload.section_key:
        section = await session.scalar(
            select(ReportSection).where(
                ReportSection.report_version_id == version.id,
                ReportSection.key == payload.section_key,
            )
        )
        if section is None:
            raise AppError("REPORT_SECTION_NOT_FOUND", "报告章节不存在", status_code=404)
        section_text = section.content_markdown
    evidence = await retrieve_evidence(
        session,
        report,
        f"{report.title} {section_text} {payload.question}",
        4,
    )
    evidence_payload = [
        {
            "marker": index,
            "document": name,
            "heading": chunk.heading,
            "page_number": chunk.page_number,
            "content": chunk.content,
            "similarity": similarity,
        }
        for index, (chunk, name, similarity) in enumerate(evidence, start=1)
    ]
    turn_limit = preset.history_turn_limit if preset else 12
    history_desc = list(
        await session.scalars(
            select(ChatRecord)
            .where(ChatRecord.conversation_id == conversation.id)
            .order_by(ChatRecord.created_at.desc())
            .limit(turn_limit * 2)
        )
    )
    history = list(reversed(history_desc))
    profile = await get_prompt_profile(session, payload.capability, payload.variant_key)
    if profile is None:
        raise AppError(
            "PROMPT_PRESET_NOT_AVAILABLE",
            "该功能或风格未开放，请刷新选项后重试",
            status_code=409,
        )
    system_prompt = DEFAULT_PROMPTS.get(
        (payload.capability, payload.variant_key),
        DEFAULT_PROMPTS[("general_chat", "default")],
    )
    context_payload = json.dumps(
        {
            "current_report": version.content_markdown,
            "current_section": section_text,
            "evidence": evidence_payload,
            "question": payload.question,
            "citation_rule": "仅可引用 evidence 中存在的 [1]、[2] 等编号。",
        },
        ensure_ascii=False,
    )
    fallback = [
        ChatMessage("system", system_prompt),
        *[ChatMessage(record.role, record.content) for record in history],
        ChatMessage("user", context_payload),
    ]
    messages = render_prompt_messages(
        profile,
        {
            "report": version.content_markdown,
            "section": section_text,
            "evidence": evidence_payload,
            "question": payload.question,
            "history": [{"role": record.role, "content": record.content} for record in history],
        },
        fallback,
    )
    user_record = ChatRecord(
        conversation_id=conversation.id,
        role="user",
        content=payload.question,
        capability=payload.capability,
        variant_key=payload.variant_key,
    )
    session.add(user_record)
    await session.commit()

    async def events() -> AsyncIterator[str]:
        content: list[str] = []
        usage = LlmUsage(0, 0, 0, True)
        model = "unknown"
        try:
            async with SessionFactory() as stream_session:
                llm = await get_runtime_llm(stream_session)
                model = llm.model_name
                async for chunk in llm.stream_chat(
                    messages,
                    ChatOptions(
                        temperature=0.2,
                        max_tokens=preset.max_output_tokens if preset else 1200,
                        metadata={"conversation_id": str(conversation_id)},
                    ),
                ):
                    if chunk.delta:
                        content.append(chunk.delta)
                        delta_data = json.dumps(
                            {"delta": chunk.delta}, ensure_ascii=False
                        )
                        yield f"event: delta\ndata: {delta_data}\n\n"
                    if chunk.usage:
                        usage = chunk.usage
                    if chunk.model:
                        model = chunk.model
                answer = "".join(content)
                assistant_record = ChatRecord(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=answer,
                    capability=payload.capability,
                    variant_key=payload.variant_key,
                    model=model,
                    input_tokens=usage.input_tokens,
                    output_tokens=usage.output_tokens,
                    usage_estimated=usage.estimated,
                )
                stream_session.add(assistant_record)
                await record_llm_usage(
                    stream_session,
                    current_user.id,
                    usage,
                    model,
                    f"chat.{payload.capability}",
                )
                await stream_session.commit()
                await stream_session.refresh(assistant_record)
                yield (
                    "event: complete\ndata: "
                    + json.dumps(
                        {
                            "message_id": str(assistant_record.id),
                            "model": model,
                            "usage_estimated": usage.estimated,
                        },
                        ensure_ascii=False,
                    )
                    + "\n\n"
                )
        except Exception as exc:
            yield f"event: error\ndata: {json.dumps({'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
