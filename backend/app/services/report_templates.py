from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.enums import TemplateStatus
from app.domain.models import ReportTemplate, TemplateSection, TemplateVersion

BUILTIN_TEMPLATES = (
    {
        "key": "literature_review",
        "name": "文献综述",
        "description": "围绕研究主题梳理背景、主要观点、方法脉络与研究空白。",
        "required_inputs": ["topic", "research_goal"],
        "sections": (
            ("background", "研究背景", "说明研究问题、现实背景与综述范围。"),
            ("themes", "主要研究主题", "归纳文献中的主要观点和研究主题。"),
            ("methods", "方法与技术路线", "比较已有研究使用的方法、数据和评价思路。"),
            ("gaps", "研究不足与空白", "基于证据总结争议、不足及可继续研究的问题。"),
            ("conclusion", "综述结论", "综合前文，形成克制且有证据支撑的结论。"),
        ),
    },
    {
        "key": "research_proposal",
        "name": "开题报告",
        "description": "从选题依据到研究方法，生成可继续编辑的开题报告初稿。",
        "required_inputs": ["topic", "research_goal"],
        "sections": (
            ("rationale", "选题依据", "说明研究背景、问题价值与选题必要性。"),
            ("literature", "国内外研究现状", "按观点和技术路径整理相关研究现状。"),
            ("objectives", "研究目标与内容", "明确目标、研究对象、核心内容和边界。"),
            ("methodology", "研究方法与技术路线", "给出可执行的方法、步骤和验证思路。"),
            ("outcomes", "预期成果", "结合研究目标说明预期形成的成果及判断标准。"),
        ),
    },
)


async def ensure_builtin_templates(session: AsyncSession) -> None:
    existing = set(
        await session.scalars(
            select(ReportTemplate.key).where(
                ReportTemplate.key.in_([item["key"] for item in BUILTIN_TEMPLATES])
            )
        )
    )
    if len(existing) == len(BUILTIN_TEMPLATES):
        return
    for definition in BUILTIN_TEMPLATES:
        if definition["key"] in existing:
            continue
        template = ReportTemplate(
            key=definition["key"],
            name=definition["name"],
            description=definition["description"],
            status=TemplateStatus.PUBLISHED,
        )
        session.add(template)
        await session.flush()
        version = TemplateVersion(
            template_id=template.id,
            version=1,
            system_prompt=(
                "你是严谨的中文学术写作助手。只能使用给定证据，不得编造来源；"
                "引用必须使用证据列表中已有的方括号编号。"
            ),
            settings={
                "required_inputs": definition["required_inputs"],
                "prompt_version": "mvp2-v1",
                "top_k": 4,
            },
        )
        session.add(version)
        await session.flush()
        session.add_all(
            [
                TemplateSection(
                    template_version_id=version.id,
                    key=key,
                    title=title,
                    position=position,
                    instructions=instructions,
                    required_inputs=definition["required_inputs"],
                )
                for position, (key, title, instructions) in enumerate(
                    definition["sections"], start=1
                )
            ]
        )
    await session.commit()
