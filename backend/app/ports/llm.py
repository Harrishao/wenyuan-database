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


class LlmPort(Protocol):
    async def chat(self, messages: list[ChatMessage], options: ChatOptions) -> str: ...

    def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[str]: ...

    async def health_check(self) -> bool: ...
