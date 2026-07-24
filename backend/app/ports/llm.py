from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Literal, Protocol


@dataclass(frozen=True, slots=True)
class ChatMessage:
    role: Literal["system", "user", "assistant"]
    content: str


@dataclass(frozen=True, slots=True)
class ChatOptions:
    temperature: float = 0.2
    max_tokens: int | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class LlmUsage:
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated: bool = False


class LlmResponse(str):
    """String-compatible response with structured model and usage metadata."""

    model: str
    usage: LlmUsage

    def __new__(cls, content: str, model: str, usage: LlmUsage) -> "LlmResponse":
        instance = str.__new__(cls, content)
        instance.model = model
        instance.usage = usage
        return instance

    @property
    def content(self) -> str:
        return str(self)


@dataclass(frozen=True, slots=True)
class LlmStreamChunk:
    delta: str = ""
    usage: LlmUsage | None = None
    model: str | None = None


class LlmPort(Protocol):
    async def chat(self, messages: list[ChatMessage], options: ChatOptions) -> LlmResponse: ...

    def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[LlmStreamChunk]: ...

    async def health_check(self) -> bool: ...
