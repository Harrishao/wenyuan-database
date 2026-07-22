import hashlib
import math
import re


class LocalHashingEmbedding:
    """无需外部模型文件的可复现字符 n-gram 向量化基线。"""

    def __init__(self, dimensions: int = 512) -> None:
        self._dimensions = dimensions

    @property
    def model_name(self) -> str:
        return "local-char-ngram-hashing-v1"

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def _embed(self, text: str) -> list[float]:
        normalized = re.sub(r"\s+", "", text.lower())
        vector = [0.0] * self._dimensions
        for size in (1, 2, 3):
            for index in range(max(0, len(normalized) - size + 1)):
                gram = normalized[index : index + size].encode("utf-8")
                digest = hashlib.blake2b(gram, digest_size=8).digest()
                bucket = int.from_bytes(digest[:4], "big") % self._dimensions
                sign = 1.0 if digest[4] & 1 else -1.0
                vector[bucket] += sign
        norm = math.sqrt(sum(value * value for value in vector))
        if norm:
            return [value / norm for value in vector]
        return vector

    async def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)
