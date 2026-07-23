import json
import re
from collections.abc import AsyncIterator

import httpx

from app.ports.llm import ChatMessage, ChatOptions


class LocalEvidenceDraftLlm:
    model_name = "local-evidence-draft-v1"

    async def chat(self, messages: list[ChatMessage], options: ChatOptions) -> str:
        payload = json.loads(messages[-1].content)
        evidence = payload.get("evidence", [])
        if not evidence:
            return "本节暂无足够的知识库证据，建议补充相关文献后重新生成。"
        paragraphs = []
        for index, item in enumerate(evidence[:4], start=1):
            text = re.sub(r"\s+", " ", item["content"]).strip()
            excerpt = text[:260].rstrip("，。；; ")
            paragraphs.append(f"{excerpt}。[{index}]")
        lead = (
            f"围绕“{payload['topic']}”，本节依据当前知识库资料，对"
            f"{payload['section_title']}作如下归纳。"
        )
        return "\n\n".join([lead, *paragraphs])

    async def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[str]:
        yield await self.chat(messages, options)

    async def health_check(self) -> bool:
        return True


class OpenAICompatibleLlm:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 300,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model
        self.timeout_seconds = timeout_seconds

    async def chat(self, messages: list[ChatMessage], options: ChatOptions) -> str:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": message.role, "content": message.content}
                        for message in messages
                    ],
                    "temperature": options.temperature,
                    "max_tokens": options.max_tokens,
                },
            )
        response.raise_for_status()
        return str(response.json()["choices"][0]["message"]["content"])

    async def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[str]:
        yield await self.chat(messages, options)

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    f"{self.base_url}/models",
                    headers={"Authorization": f"Bearer {self.api_key}"},
                )
            return response.is_success
        except httpx.HTTPError:
            return False
