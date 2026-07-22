from dataclasses import dataclass

from app.services.document_parser import ParsedBlock


@dataclass(frozen=True, slots=True)
class TextChunk:
    position: int
    content: str
    heading: str | None
    page_number: int | None


def split_with_overlap(text: str, target_size: int, overlap: int) -> list[str]:
    parts: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + target_size, len(text))
        if end < len(text):
            floor = start + int(target_size * 0.6)
            punctuation = max(text.rfind(mark, floor, end) for mark in "。！？；.!?;")
            if punctuation >= floor:
                end = punctuation + 1
        parts.append(text[start:end].strip())
        if end >= len(text):
            break
        start = max(start + 1, end - overlap)
    return [part for part in parts if part]


def chunk_blocks(
    blocks: list[ParsedBlock], target_size: int = 650, overlap: int = 100
) -> list[TextChunk]:
    if target_size <= overlap:
        raise ValueError("分块长度必须大于重叠长度")
    chunks: list[TextChunk] = []
    position = 0
    for block in blocks:
        for content in split_with_overlap(block.text.strip(), target_size, overlap):
            chunks.append(TextChunk(position, content, block.heading, block.page_number))
            position += 1
    return chunks
