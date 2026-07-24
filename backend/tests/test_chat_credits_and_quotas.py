from decimal import Decimal

from app.adapters.report_llm import parse_usage
from app.domain.models import User
from app.ports.llm import ChatMessage
from app.schemas.admin import LlmPresetInput


def test_student_defaults_have_storage_and_monthly_credits() -> None:
    user = User(
        email="student@example.com",
        password_hash="hash",
        display_name="Student",
    )
    assert user.storage_quota_bytes is None or user.storage_quota_bytes == 50 * 1024 * 1024
    assert user.monthly_credits is None or Decimal(user.monthly_credits) == Decimal("300")


def test_llm_pricing_distinguishes_input_and_output() -> None:
    payload = LlmPresetInput(
        name="test",
        base_url="https://example.test/v1",
        model="model",
        input_credits_per_million_tokens=Decimal("2.5"),
        output_credits_per_million_tokens=Decimal("7.5"),
    )
    assert payload.input_credits_per_million_tokens == Decimal("2.5")
    assert payload.output_credits_per_million_tokens == Decimal("7.5")
    assert payload.history_turn_limit == 12


def test_usage_is_marked_estimated_when_channel_omits_usage() -> None:
    messages = [ChatMessage("user", "请分析当前章节")]
    usage = parse_usage(
        {"choices": [{"message": {"content": "结论"}}]},
        messages,
        "结论",
    )
    assert usage.estimated is True
    assert usage.input_tokens > 0
    assert usage.output_tokens > 0


def test_channel_usage_is_preserved_without_estimation() -> None:
    usage = parse_usage(
        {
            "usage": {
                "prompt_tokens": 120,
                "completion_tokens": 30,
                "total_tokens": 150,
            }
        },
        [ChatMessage("user", "test")],
        "done",
    )
    assert usage.input_tokens == 120
    assert usage.output_tokens == 30
    assert usage.estimated is False
