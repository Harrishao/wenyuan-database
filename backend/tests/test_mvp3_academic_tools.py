import pytest

from app.services import academic_tools
from app.services.academic_tools import answer_with_evidence, polish_text
from app.services.similarity import find_similarity_candidates, split_report_text


def test_similarity_scores_copy_rewrite_and_unrelated_in_layers() -> None:
    source = "短期光伏功率预测可以为电网调度提供可靠的决策依据。"
    candidates = [
        source,
        "光伏短期出力预测能够为电力系统调度提供决策支持。",
        "车辆悬架系统主要用于缓冲路面冲击并改善乘坐舒适性。",
    ]
    matches, ratio = find_similarity_candidates(
        source,
        candidates,
        threshold=0,
        min_sentence_chars=8,
    )
    assert len(matches) == 1
    assert matches[0].candidate_index == 0
    assert matches[0].score == pytest.approx(1.0)
    assert ratio == pytest.approx(1.0)

    rewrite, _ = find_similarity_candidates(
        source,
        candidates[1:],
        threshold=0,
        min_sentence_chars=8,
    )
    unrelated, _ = find_similarity_candidates(
        source,
        candidates[2:],
        threshold=0,
        min_sentence_chars=8,
    )
    assert rewrite[0].score > unrelated[0].score
    assert rewrite[0].score >= 0.10
    assert unrelated[0].score < 0.10


def test_similarity_spans_keep_offsets_for_highlighting() -> None:
    text = "## 背景\n\n第一句用于说明研究背景和现实意义。\n第二句用于说明研究目标和验证方法。"
    spans = split_report_text(text, min_chars=8)
    assert [span.text for span in spans] == [
        "第一句用于说明研究背景和现实意义。",
        "第二句用于说明研究目标和验证方法。",
    ]
    assert all(text[span.start_offset : span.end_offset] == span.text for span in spans)


@pytest.mark.asyncio
async def test_offline_polish_preserves_citation_and_does_not_mutate_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(academic_tools, "_external_llm", lambda: None)
    source = "我们觉得这个方法非常有效，所以可以看出结果很好。[1]"
    polished, model = await polish_text(source, "academic")
    assert source == "我们觉得这个方法非常有效，所以可以看出结果很好。[1]"
    assert polished != source
    assert "[1]" in polished
    assert model == "local-rule-polisher-v1"


@pytest.mark.asyncio
async def test_offline_assistant_distinguishes_revision_and_returns_real_markers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(academic_tools, "_external_llm", lambda: None)
    answer, markers, model = await answer_with_evidence(
        role="rigorous_mentor",
        mode="revision",
        question="如何增强论证？",
        report_context="当前章节",
        evidence=[
            {"content": "固定样例能够用于校准相似度阈值。"},
            {"content": "高相似片段应保存真实匹配来源。"},
        ],
    )
    assert answer.startswith("修改建议：")
    assert markers == [1, 2]
    assert "[1]" in answer and "[2]" in answer
    assert model == "local-evidence-assistant-v1"
