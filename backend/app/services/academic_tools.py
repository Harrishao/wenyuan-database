import json
import re
from typing import Literal

from app.adapters.report_llm import OpenAICompatibleLlm
from app.core.config import get_settings
from app.ports.llm import ChatMessage, ChatOptions
from app.services.report_generation import validate_citation_markers

PolishStyle = Literal["academic", "plain", "concise"]
AssistantRole = Literal["rigorous_mentor", "data_analyst"]
AssistantMode = Literal["dialogue", "revision"]

STYLE_LABELS: dict[PolishStyle, str] = {
    "academic": "学术严谨",
    "plain": "通俗表达",
    "concise": "精简",
}

ROLE_PROMPTS: dict[AssistantRole, str] = {
    "rigorous_mentor": "你是严谨导师，检查论证边界、概念准确性与证据充分性。",
    "data_analyst": "你是数据分析专家，关注指标、样本、方法、可验证数据与推断限制。",
}


def _external_llm() -> OpenAICompatibleLlm | None:
    settings = get_settings()
    if settings.llm_base_url and settings.llm_api_key and settings.llm_model:
        return OpenAICompatibleLlm(
            settings.llm_base_url,
            settings.llm_api_key.get_secret_value(),
            settings.llm_model,
            settings.llm_timeout_seconds,
        )
    return None


def _offline_polish(text: str, style: PolishStyle) -> str:
    cleaned = re.sub(r"[ \t]+", " ", text).strip()
    if style == "academic":
        replacements = {
            "我们觉得": "本研究认为",
            "可以看出": "结果表明",
            "很多": "较多",
            "非常": "显著",
            "所以": "因此",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        return cleaned
    if style == "plain":
        replacements = {
            "综上所述": "总的来说",
            "基于上述分析": "根据前面的分析",
            "具有重要意义": "很有价值",
            "因此": "所以",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        return cleaned
    sentences = [item.strip() for item in re.split(r"(?<=[。！？!?])", cleaned) if item.strip()]
    deduplicated = list(dict.fromkeys(sentences))
    return "".join(deduplicated).replace("在一定程度上", "").replace("需要指出的是，", "")


async def polish_text(text: str, style: PolishStyle) -> tuple[str, str]:
    llm = _external_llm()
    if llm is None:
        return _offline_polish(text, style), "local-rule-polisher-v1"
    prompt = (
        f"按“{STYLE_LABELS[style]}”风格润色下列文字。保持事实、数字和 [数字] 引用不变，"
        "只输出润色后的正文：\n\n"
        f"{text}"
    )
    result = await llm.chat(
        [ChatMessage(role="system", content="你是学术文本编辑。不得补充原文没有的事实。"),
         ChatMessage(role="user", content=prompt)],
        ChatOptions(temperature=0.35, max_tokens=1200),
    )
    return result.strip(), llm.model_name


async def answer_with_evidence(
    *,
    role: AssistantRole,
    mode: AssistantMode,
    question: str,
    report_context: str,
    evidence: list[dict],
) -> tuple[str, list[int], str]:
    llm = _external_llm()
    if not evidence:
        return "当前知识库没有足够证据回答该问题，请补充相关文献。", [], "no-evidence"
    payload = json.dumps(
        {
            "mode": mode,
            "question": question,
            "report_context": report_context[-4000:],
            "evidence": evidence,
            "output": "引用只能使用本次 evidence 中的 [1]、[2] 编号；修改建议须明确标注。",
        },
        ensure_ascii=False,
    )
    if llm is None:
        prefix = "修改建议：" if mode == "revision" else "回答："
        excerpts = []
        for index, item in enumerate(evidence[:3], start=1):
            text = re.sub(r"\s+", " ", item["content"]).strip()[:220].rstrip("，。；; ")
            excerpts.append(f"{text}。[{index}]")
        answer = f"{prefix}{ROLE_PROMPTS[role]}\n\n" + "\n\n".join(excerpts)
        return answer, list(range(1, len(excerpts) + 1)), "local-evidence-assistant-v1"
    answer = await llm.chat(
        [ChatMessage(role="system", content=ROLE_PROMPTS[role]),
         ChatMessage(role="user", content=payload)],
        ChatOptions(temperature=0.2, max_tokens=1200),
    )
    cleaned, markers = validate_citation_markers(answer, len(evidence))
    return cleaned, markers, llm.model_name
