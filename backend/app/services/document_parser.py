import re
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader


class DocumentParseError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ParsedBlock:
    text: str
    heading: str | None = None
    page_number: int | None = None


def decode_text(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise DocumentParseError("文本编码无法识别，请使用 UTF-8 编码")


def parse_markdown(text: str) -> list[ParsedBlock]:
    blocks: list[ParsedBlock] = []
    heading: str | None = None
    buffer: list[str] = []

    def flush() -> None:
        content = "\n".join(buffer).strip()
        if content:
            blocks.append(ParsedBlock(text=content, heading=heading))
        buffer.clear()

    for line in text.splitlines():
        match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
        if match:
            flush()
            heading = match.group(1).strip()
        else:
            buffer.append(line)
    flush()
    return blocks


def parse_plain_text(text: str) -> list[ParsedBlock]:
    return [ParsedBlock(text=part.strip()) for part in re.split(r"\n\s*\n", text) if part.strip()]


def parse_pdf(path: Path) -> list[ParsedBlock]:
    try:
        reader = PdfReader(path)
    except Exception as exc:
        raise DocumentParseError("PDF 文件无法读取") from exc
    blocks: list[ParsedBlock] = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise DocumentParseError(f"PDF 第 {index} 页解析失败") from exc
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        if text:
            blocks.append(ParsedBlock(text=text, page_number=index))
    if not blocks:
        raise DocumentParseError("PDF 不包含可提取文本，扫描件暂不支持")
    return blocks


def parse_document(path: Path, suffix: str) -> list[ParsedBlock]:
    normalized_suffix = suffix.lower()
    if normalized_suffix == ".pdf":
        return parse_pdf(path)
    content = path.read_bytes()
    text = decode_text(content)
    if normalized_suffix == ".md":
        blocks = parse_markdown(text)
    elif normalized_suffix == ".txt":
        blocks = parse_plain_text(text)
    else:
        raise DocumentParseError("仅支持 PDF、Markdown 和 TXT")
    if not blocks:
        raise DocumentParseError("文档中没有可归档的正文")
    return blocks
