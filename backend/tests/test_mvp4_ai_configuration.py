import httpx
import pytest

from app.adapters.openai_embedding import OpenAICompatibleEmbedding
from app.adapters.report_llm import OpenAICompatibleLlm
from app.domain.models import PromptPreset
from app.ports.llm import ChatMessage, ChatOptions
from app.schemas.admin import SensitiveGroupInput
from app.services.ai_config import (
    decrypt_secret,
    encrypt_secret,
    render_macro_text,
    render_prompt_messages,
)


def test_secret_round_trip_is_encrypted_at_rest() -> None:
    plaintext = "provider-secret-value"
    ciphertext = encrypt_secret(plaintext)

    assert ciphertext
    assert ciphertext != plaintext
    assert plaintext not in ciphertext
    assert decrypt_secret(ciphertext) == plaintext


def test_nested_macros_and_missing_values_are_rendered() -> None:
    rendered = render_macro_text(
        "课题={{inputs.topic}}；证据={{evidence}}；缺失={{unknown}}",
        {"inputs": {"topic": "光伏预测"}, "evidence": [{"id": 1}]},
    )

    assert rendered == '课题=光伏预测；证据=[{"id": 1}]；缺失='


def test_complete_prompt_messages_preserve_role_order_and_enabled_state() -> None:
    preset = PromptPreset(
        name="学术章节",
        messages=[
            {
                "name": "用户任务",
                "role": "user",
                "content": "章节：{{section_title}}",
                "enabled": True,
                "position": 2,
            },
            {
                "name": "停用消息",
                "role": "assistant",
                "content": "不应出现",
                "enabled": False,
                "position": 1,
            },
            {
                "name": "系统约束",
                "role": "system",
                "content": "仅使用{{source}}",
                "enabled": True,
                "position": 0,
            },
        ],
    )

    messages = render_prompt_messages(
        preset,
        {"section_title": "研究背景", "source": "知识库证据"},
        [ChatMessage(role="user", content="fallback")],
    )

    assert [(message.role, message.content) for message in messages] == [
        ("system", "仅使用知识库证据"),
        ("user", "章节：研究背景"),
    ]


def test_sensitive_group_normalizes_name_and_deduplicates_terms() -> None:
    group = SensitiveGroupInput(
        name="  学术规范  ",
        terms=["  代写  ", "抄袭", "代写", ""],
        enabled=False,
    )

    assert group.name == "学术规范"
    assert group.terms == ["代写", "抄袭"]
    assert group.enabled is False


@pytest.mark.asyncio
async def test_llm_custom_parameters_cannot_replace_model_or_messages(monkeypatch) -> None:
    captured: dict = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"choices": [{"message": {"content": "完成"}}]}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            captured["client"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, **kwargs):
            captured["url"] = url
            captured["request"] = kwargs
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    llm = OpenAICompatibleLlm(
        "https://llm.example/v1",
        "secret",
        "configured-model",
        parameters={
            "model": "injected-model",
            "messages": [{"role": "user", "content": "injected"}],
            "top_p": 0.8,
        },
    )

    result = await llm.chat(
        [ChatMessage(role="user", content="真实输入")],
        ChatOptions(temperature=0.2),
    )

    assert result == "完成"
    assert captured["request"]["json"]["model"] == "configured-model"
    assert captured["request"]["json"]["messages"][0]["content"] == "真实输入"
    assert captured["request"]["json"]["top_p"] == 0.8


@pytest.mark.asyncio
async def test_external_embedding_validates_configured_dimensions(monkeypatch) -> None:
    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {"data": [{"index": 0, "embedding": [0.1, 0.2]}]}

    class FakeClient:
        def __init__(self, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args) -> None:
            return None

        async def post(self, url: str, **kwargs):
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    embedding = OpenAICompatibleEmbedding(
        base_url="https://embedding.example/v1",
        api_key="secret",
        model="embedding-model",
        dimensions=3,
    )

    with pytest.raises(ValueError, match="期望 3"):
        await embedding.embed_query("测试")
