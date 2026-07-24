import asyncio
import json
import re
from collections.abc import AsyncIterator

import httpx

from app.ports.llm import (
    ChatMessage,
    ChatOptions,
    LlmResponse,
    LlmStreamChunk,
    LlmUsage,
)


def estimate_usage(messages: list[ChatMessage], content: str) -> LlmUsage:
    # 未知 OpenAI 兼容渠道无法可靠获知 tokenizer。中英文混排按字符近似，
    # 并在流水中明确标记 estimated，避免冒充渠道返回值。
    input_tokens = max(1, sum(len(item.content) for item in messages) // 2)
    output_tokens = max(1, len(content) // 2)
    return LlmUsage(input_tokens, output_tokens, input_tokens + output_tokens, True)


def parse_usage(payload: dict, messages: list[ChatMessage], content: str) -> LlmUsage:
    usage = payload.get("usage") or {}
    input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
    output_tokens = usage.get("completion_tokens") or usage.get("output_tokens")
    if input_tokens is None or output_tokens is None:
        return estimate_usage(messages, content)
    return LlmUsage(
        int(input_tokens),
        int(output_tokens),
        int(usage.get("total_tokens") or int(input_tokens) + int(output_tokens)),
        False,
    )


class LocalEvidenceDraftLlm:
    model_name = "local-evidence-draft-v1"

    async def chat(self, messages: list[ChatMessage], options: ChatOptions) -> LlmResponse:
        payload = json.loads(messages[-1].content)
        evidence = payload.get("evidence", [])
        if not evidence:
            content = "本节暂无足够的知识库证据，建议补充相关文献后重新生成。"
            return LlmResponse(content, self.model_name, LlmUsage(0, 0, 0))
        paragraphs = []
        for index, item in enumerate(evidence[:4], start=1):
            text = re.sub(r"\s+", " ", item["content"]).strip()
            excerpt = text[:260].rstrip("，。；; ")
            paragraphs.append(f"{excerpt}。[{index}]")
        if payload.get("question"):
            lead = f"针对“{payload['question']}”，依据当前知识库证据作如下回答。"
        else:
            lead = (
                f"围绕“{payload.get('topic', '当前报告')}”，本节依据当前知识库资料，对"
                f"{payload.get('section_title', '相关内容')}作如下归纳。"
            )
        content = "\n\n".join([lead, *paragraphs])
        return LlmResponse(content, self.model_name, LlmUsage(0, 0, 0))

    async def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[LlmStreamChunk]:
        result = await self.chat(messages, options)
        yield LlmStreamChunk(delta=result.content, model=result.model)
        yield LlmStreamChunk(usage=result.usage, model=result.model)

    async def health_check(self) -> bool:
        return True


class OpenAICompatibleLlm:
    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: float = 300,
        parameters: dict | None = None,
        max_retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model_name = model
        self.timeout_seconds = timeout_seconds
        self.parameters = parameters or {}
        self.max_retries = max_retries

    def _payload(
        self, messages: list[ChatMessage], options: ChatOptions, *, stream: bool = False
    ) -> dict:
        payload = {
            **self.parameters,
            "model": self.model_name,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "temperature": options.temperature,
        }
        if options.max_tokens is not None:
            payload["max_tokens"] = options.max_tokens
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def chat(self, messages: list[ChatMessage], options: ChatOptions) -> LlmResponse:
        payload = self._payload(messages, options)
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(
                        f"{self.base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        json=payload,
                    )
                response.raise_for_status()
                body = response.json()
                content = str(body["choices"][0]["message"]["content"])
                return LlmResponse(
                    content,
                    str(body.get("model") or self.model_name),
                    parse_usage(body, messages, content),
                )
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    raise
                await asyncio.sleep(0.5 * (2**attempt))
        raise RuntimeError("LLM 请求失败") from last_error

    async def stream_chat(
        self, messages: list[ChatMessage], options: ChatOptions
    ) -> AsyncIterator[LlmStreamChunk]:
        payload = self._payload(messages, options, stream=True)
        collected: list[str] = []
        usage: LlmUsage | None = None
        model = self.model_name
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    body = json.loads(data)
                    model = str(body.get("model") or model)
                    choices = body.get("choices") or []
                    delta = ""
                    if choices:
                        delta = str((choices[0].get("delta") or {}).get("content") or "")
                    if delta:
                        collected.append(delta)
                        yield LlmStreamChunk(delta=delta, model=model)
                    if body.get("usage"):
                        usage = parse_usage(body, messages, "".join(collected))
        yield LlmStreamChunk(
            usage=usage or estimate_usage(messages, "".join(collected)),
            model=model,
        )

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
