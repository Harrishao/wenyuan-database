from io import BytesIO

from docx import Document as DocxDocument

from app.domain.models import Report, ReportSection


def render_report_docx(report: Report, sections: list[ReportSection]) -> bytes:
    document = DocxDocument()
    document.add_heading(report.title, level=0)
    for section in sorted(sections, key=lambda item: item.position):
        document.add_heading(section.title, level=1)
        for block in section.content_markdown.split("\n\n"):
            text = block.strip()
            if not text:
                continue
            if text.startswith("### "):
                document.add_heading(text[4:], level=2)
            else:
                document.add_paragraph(text)
    buffer = BytesIO()
    document.save(buffer)
    return buffer.getvalue()
