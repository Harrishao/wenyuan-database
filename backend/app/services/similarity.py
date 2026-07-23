import re
from dataclasses import dataclass

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity


@dataclass(frozen=True, slots=True)
class TextSpan:
    text: str
    start_offset: int
    end_offset: int


@dataclass(frozen=True, slots=True)
class SimilarityCandidate:
    source: TextSpan
    candidate_index: int
    score: float


def split_report_text(text: str, min_chars: int = 12) -> list[TextSpan]:
    """Split Markdown into traceable sentence/paragraph spans."""
    spans: list[TextSpan] = []
    for match in re.finditer(r"[^。！？!?\n]+[。！？!?]?|[^\n]+$", text):
        raw = match.group(0)
        leading = len(raw) - len(raw.lstrip())
        cleaned = raw.strip()
        cleaned = re.sub(r"^#{1,6}\s*", "", cleaned).strip()
        if len(re.sub(r"\s+", "", cleaned)) < min_chars:
            continue
        start = match.start() + leading
        spans.append(TextSpan(cleaned, start, start + len(cleaned)))
    return spans


def find_similarity_candidates(
    report_text: str,
    candidate_texts: list[str],
    *,
    threshold: float = 0.10,
    ngram_range: tuple[int, int] = (2, 4),
    min_sentence_chars: int = 12,
) -> tuple[list[SimilarityCandidate], float]:
    """Return each report span's best lexical match and a length-weighted ratio."""
    sources = split_report_text(report_text, min_sentence_chars)
    if not sources or not candidate_texts:
        return [], 0.0

    corpus = [item.text for item in sources] + candidate_texts
    matrix = TfidfVectorizer(
        analyzer="char",
        ngram_range=ngram_range,
        lowercase=False,
        sublinear_tf=True,
    ).fit_transform(corpus)
    scores = cosine_similarity(matrix[: len(sources)], matrix[len(sources) :])
    matches: list[SimilarityCandidate] = []
    matched_chars = 0
    total_chars = sum(len(re.sub(r"\s+", "", item.text)) for item in sources)
    for source, row in zip(sources, scores, strict=True):
        index = int(row.argmax())
        score = float(row[index])
        if score < threshold:
            continue
        matches.append(SimilarityCandidate(source, index, score))
        matched_chars += len(re.sub(r"\s+", "", source.text))
    ratio = matched_chars / total_chars if total_chars else 0.0
    return matches, ratio
