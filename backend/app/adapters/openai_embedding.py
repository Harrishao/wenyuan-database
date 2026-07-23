import httpx


class OpenAICompatibleEmbedding:
    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        dimensions: int,
        parameters: dict | None = None,
        timeout_seconds: float = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._model_name = model
        self._dimensions = dimensions
        self.parameters = parameters or {}
        self.timeout_seconds = timeout_seconds

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def dimensions(self) -> int:
        return self._dimensions

    async def _embed(self, texts: list[str]) -> list[list[float]]:
        payload = {**self.parameters, "model": self.model_name, "input": texts}
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/embeddings",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json=payload,
            )
        response.raise_for_status()
        rows = sorted(response.json()["data"], key=lambda item: item["index"])
        vectors = [list(map(float, item["embedding"])) for item in rows]
        if any(len(vector) != self.dimensions for vector in vectors):
            raise ValueError(f"向量维度与预设不一致，期望 {self.dimensions}")
        return vectors

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return await self._embed(texts)

    async def embed_query(self, text: str) -> list[float]:
        return (await self._embed([text]))[0]
