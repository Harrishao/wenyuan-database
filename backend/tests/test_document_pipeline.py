from pathlib import Path

import pytest

from app.adapters.local_hashing_embedding import LocalHashingEmbedding
from app.services.chunking import chunk_blocks
from app.services.document_parser import parse_document

MATERIALS = Path(__file__).parents[2] / "素材"


@pytest.mark.parametrize(
    "filename",
    [
        "基于RAG架构的学术文献切片与混合检索优化指南.txt",
        "分布式光伏发电出力短期预测的高级时序模型研究.md",
        "基于变频调速与转矩控制的异步电机高效运行优化.pdf",
    ],
)
def test_materials_can_be_parsed_and_chunked(filename: str) -> None:
    path = MATERIALS / filename
    blocks = parse_document(path, path.suffix)
    chunks = chunk_blocks(blocks, target_size=650, overlap=100)

    assert blocks
    assert chunks
    assert all(0 < len(chunk.content) <= 650 for chunk in chunks)
    assert [chunk.position for chunk in chunks] == list(range(len(chunks)))


@pytest.mark.asyncio
async def test_hashing_embedding_is_stable_and_query_sensitive() -> None:
    model = LocalHashingEmbedding(512)
    vectors = await model.embed_documents(["光伏功率预测", "异步电机转矩控制"])
    repeated = await model.embed_query("光伏功率预测")

    assert vectors[0] == repeated
    assert len(vectors[0]) == 512
    assert vectors[0] != vectors[1]
    assert sum(value * value for value in vectors[0]) == pytest.approx(1.0)
