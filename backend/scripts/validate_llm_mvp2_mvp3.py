import argparse
import json
import re
import secrets
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx
import psycopg
from docx import Document as DocxDocument

from app.core.config import get_settings


def write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:4397/api/v1")
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    progress_path = artifacts / "progress.log"

    def log(message: str) -> None:
        line = f"{datetime.now(UTC).isoformat()} {message}"
        print(line, flush=True)
        with progress_path.open("a", encoding="utf-8") as stream:
            stream.write(line + "\n")

    settings = get_settings()
    expected_model = settings.llm_model
    config_summary = {
        "base_url_configured": bool(settings.llm_base_url),
        "api_key_configured": bool(
            settings.llm_api_key and settings.llm_api_key.get_secret_value()
        ),
        "model": expected_model,
        "validation_api": args.base_url,
        "started_at": datetime.now(UTC).isoformat(),
    }
    write_json(artifacts / "00-config-summary.json", config_summary)
    if not all(
        (
            config_summary["base_url_configured"],
            config_summary["api_key_configured"],
            expected_model,
        )
    ):
        raise RuntimeError("LLM 配置不完整")

    suffix = uuid4().hex[:10]
    email = f"llm-validation-{suffix}@example.com"
    password = f"Val-{secrets.token_urlsafe(18)}"
    report_id: str | None = None
    knowledge_base_id: str | None = None
    summary: dict[str, object] = {
        "status": "running",
        "expected_model": expected_model,
        "preserved": True,
    }

    try:
        with httpx.Client(timeout=420) as client:
            log("注册独立验证账号")
            response = client.post(
                f"{args.base_url}/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "display_name": "LLM Validation",
                },
            )
            response.raise_for_status()
            auth = response.json()
            client.headers["Authorization"] = f"Bearer {auth['access_token']}"
            write_json(
                artifacts / "01-validation-account.json",
                {
                    "user_id": auth["user"]["id"],
                    "email": email,
                    "password": password,
                    "purpose": "保留的 LLM MVP2/MVP3 验证账号",
                },
            )

            log("创建验证知识库并上传两篇真实素材")
            response = client.post(
                f"{args.base_url}/knowledge-bases",
                json={
                    "name": f"LLM MVP2-MVP3 验证 {suffix}",
                    "description": "启用外部 LLM 的保留验收数据",
                },
            )
            response.raise_for_status()
            knowledge_base = response.json()
            knowledge_base_id = knowledge_base["id"]
            material_root = Path(__file__).resolve().parents[2] / "素材"
            material_paths = [
                material_root / "基于RAG架构的学术文献切片与混合检索优化指南.txt",
                material_root / "文献智能检索与查重算法的对比分析与实证研究.md",
            ]
            upload_responses = []
            for material_path in material_paths:
                mime = "text/plain" if material_path.suffix == ".txt" else "text/markdown"
                with material_path.open("rb") as stream:
                    response = client.post(
                        f"{args.base_url}/knowledge-bases/{knowledge_base_id}/documents",
                        files={"file": (material_path.name, stream, mime)},
                    )
                response.raise_for_status()
                upload_responses.append(response.json())
            write_json(artifacts / "02-upload-responses.json", upload_responses)

            for _ in range(120):
                response = client.get(
                    f"{args.base_url}/knowledge-bases/{knowledge_base_id}/documents"
                )
                response.raise_for_status()
                documents = response.json()
                if len(documents) == 2 and all(
                    item["status"] == "succeeded" for item in documents
                ):
                    break
                if any(item["status"] == "failed" for item in documents):
                    raise RuntimeError(f"文档处理失败：{documents}")
                time.sleep(0.5)
            else:
                raise TimeoutError("文档处理超时")
            write_json(artifacts / "03-processed-documents.json", documents)

            log("MVP2：创建报告并等待外部 LLM 完成全部章节")
            response = client.get(f"{args.base_url}/report-templates")
            response.raise_for_status()
            templates = response.json()
            write_json(artifacts / "04-report-templates.json", templates)
            template = next(
                (item for item in templates if item["key"] == "literature_review"),
                templates[0],
            )
            response = client.post(
                f"{args.base_url}/reports",
                json={
                    "knowledge_base_id": knowledge_base_id,
                    "template_key": template["key"],
                    "title": f"LLM 启用验证报告 {suffix}",
                    "inputs": {
                        "topic": "私有文献知识库中的检索增强生成与相似度检测",
                        "research_goal": "验证检索证据约束、引用追溯、相似度检测及学术修改链路",
                    },
                },
            )
            response.raise_for_status()
            created_report = response.json()
            report_id = created_report["report"]["id"]
            write_json(artifacts / "05-report-create-response.json", created_report)

            for poll_index in range(1200):
                response = client.get(f"{args.base_url}/reports/{report_id}")
                response.raise_for_status()
                report = response.json()
                if poll_index % 30 == 0:
                    log(
                        f"MVP2 报告进度：{report['progress']}%，"
                        f"状态 {report['status']}"
                    )
                if report["status"] == "ready":
                    break
                if report["status"] == "failed":
                    raise RuntimeError(f"LLM 报告生成失败：{report}")
                time.sleep(1)
            else:
                raise TimeoutError("LLM 报告生成超时")
            write_json(artifacts / "06-mvp2-report-detail.json", report)

            response = client.get(f"{args.base_url}/reports/{report_id}/versions")
            response.raise_for_status()
            write_json(artifacts / "07-mvp2-report-versions.json", response.json())

            log("读取数据库生成上下文，确认报告章节实际使用外部模型")
            database_url = settings.database_url.replace(
                "postgresql+asyncpg://", "postgresql://", 1
            )
            with psycopg.connect(database_url) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """
                        SELECT result
                        FROM background_jobs
                        WHERE job_type = 'report.generate'
                          AND payload ->> 'report_id' = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (report_id,),
                    )
                    generation_job_result = cursor.fetchone()[0]
                    cursor.execute(
                        """
                        SELECT generation_context
                        FROM report_versions
                        WHERE report_id = %s
                        ORDER BY version DESC
                        LIMIT 1
                        """,
                        (report_id,),
                    )
                    generation_context = cursor.fetchone()[0]
            write_json(
                artifacts / "08-mvp2-generation-model-evidence.json",
                {
                    "background_job_result": generation_job_result,
                    "generation_context": generation_context,
                },
            )
            retrieval_models = {
                item["model"]
                for item in generation_context.get("retrieval", {}).values()
            }
            if generation_job_result.get("model") != expected_model:
                raise AssertionError("报告后台任务没有使用配置的外部模型")
            if retrieval_models != {expected_model}:
                raise AssertionError(f"报告章节模型不一致：{retrieval_models}")

            citation_count = sum(len(section["citations"]) for section in report["sections"])
            if citation_count == 0:
                raise AssertionError("LLM 报告没有保存任何引用")
            for section in report["sections"]:
                markers = set(re.findall(r"\[\d+\]", section["content_markdown"]))
                stored = {citation["marker"] for citation in section["citations"]}
                if not markers.issubset(stored):
                    raise AssertionError(
                        f"章节 {section['key']} 存在无法追溯的引用：{markers - stored}"
                    )

            log("MVP2：导出并重新打开 DOCX")
            response = client.get(f"{args.base_url}/reports/{report_id}/export.docx")
            response.raise_for_status()
            docx_path = artifacts / "09-mvp2-report.docx"
            docx_path.write_bytes(response.content)
            reopened = DocxDocument(docx_path)
            if not any(paragraph.text.strip() for paragraph in reopened.paragraphs):
                raise AssertionError("导出的 DOCX 没有正文")

            log("MVP3：运行私有语料相似度检测")
            response = client.post(
                f"{args.base_url}/reports/{report_id}/similarity",
                json={},
            )
            response.raise_for_status()
            similarity = response.json()
            write_json(artifacts / "10-mvp3-similarity.json", similarity)
            if similarity["status"] != "succeeded":
                raise AssertionError("相似度检测未成功")
            if any(not item["document_name"] for item in similarity["matches"]):
                raise AssertionError("相似度匹配存在无来源证据")

            selected_section = next(
                section
                for section in report["sections"]
                if len(section["content_markdown"]) >= 40
            )
            selected_text = selected_section["content_markdown"][:120]
            polish_previews: dict[str, dict] = {}
            log("MVP3：验证学术严谨、通俗表达、精简三种 LLM 润色")
            for style in ("academic", "plain", "concise"):
                response = client.post(
                    f"{args.base_url}/reports/{report_id}/polish",
                    json={
                        "section_key": selected_section["key"],
                        "text": selected_text,
                        "style": style,
                    },
                )
                response.raise_for_status()
                preview = response.json()
                if preview["model"] != expected_model:
                    raise AssertionError(
                        f"{style} 润色回退到了非预期模型：{preview['model']}"
                    )
                polish_previews[style] = preview
                write_json(
                    artifacts / f"11-mvp3-polish-{style}.json",
                    preview,
                )

            response = client.post(
                f"{args.base_url}/reports/{report_id}/polish/accept",
                json={
                    "section_key": selected_section["key"],
                    "text": selected_text,
                    "polished_text": polish_previews["academic"]["polished_text"],
                    "style": "academic",
                },
            )
            response.raise_for_status()
            accepted_report = response.json()
            write_json(artifacts / "12-mvp3-polish-accepted-report.json", accepted_report)
            if accepted_report["current_version"] <= report["current_version"]:
                raise AssertionError("接受润色后没有创建新版本")

            log("MVP3：验证严谨导师与数据分析专家两种证据型助手")
            assistant_cases = [
                (
                    "rigorous_mentor",
                    "revision",
                    "请指出当前章节论证中需要补强的证据，并给出修改建议。",
                ),
                (
                    "data_analyst",
                    "dialogue",
                    "相似度检测结果应当报告哪些指标和方法参数？",
                ),
            ]
            assistant_results = []
            for role, mode, question in assistant_cases:
                response = client.post(
                    f"{args.base_url}/reports/{report_id}/assistant",
                    json={
                        "role": role,
                        "mode": mode,
                        "question": question,
                        "section_key": selected_section["key"],
                    },
                )
                response.raise_for_status()
                answer = response.json()
                if answer["model"] != expected_model:
                    raise AssertionError(
                        f"{role} 助手回退到了非预期模型：{answer['model']}"
                    )
                if not answer["evidence"]:
                    raise AssertionError(f"{role} 助手没有返回可追溯证据")
                assistant_results.append(answer)
                write_json(
                    artifacts / f"13-mvp3-assistant-{role}.json",
                    answer,
                )

            response = client.get(f"{args.base_url}/reports/{report_id}/versions")
            response.raise_for_status()
            final_versions = response.json()
            write_json(artifacts / "14-final-report-versions.json", final_versions)

            summary.update(
                {
                    "status": "passed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "validation_account": email,
                    "knowledge_base_id": knowledge_base_id,
                    "report_id": report_id,
                    "report_title": accepted_report["title"],
                    "report_sections": len(report["sections"]),
                    "citation_count": citation_count,
                    "generation_models": sorted(retrieval_models),
                    "similarity_overall_ratio": similarity["overall_ratio"],
                    "similarity_match_count": len(similarity["matches"]),
                    "polish_models": {
                        style: preview["model"]
                        for style, preview in polish_previews.items()
                    },
                    "accepted_report_version": accepted_report["current_version"],
                    "assistant_models": {
                        result["role"]: result["model"] for result in assistant_results
                    },
                    "assistant_evidence_counts": {
                        result["role"]: len(result["evidence"])
                        for result in assistant_results
                    },
                    "docx_path": str(docx_path),
                    "database_records_preserved": True,
                }
            )
            write_json(artifacts / "validation-summary.json", summary)
            log("全部 LLM MVP2/MVP3 验证通过，产物与数据库记录已保留")
            return 0
    except Exception as exc:
        summary.update(
            {
                "status": "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "knowledge_base_id": knowledge_base_id,
                "report_id": report_id,
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "database_records_preserved": True,
            }
        )
        write_json(artifacts / "validation-summary.json", summary)
        log(f"验证失败：{exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
