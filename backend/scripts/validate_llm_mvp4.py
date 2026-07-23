import argparse
import json
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import httpx

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
    parser.add_argument("--admin-email", default="harrishao7@admin.com")
    parser.add_argument("--admin-password", default="password")
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)
    settings = get_settings()
    suffix = uuid4().hex[:10]
    summary: dict[str, object] = {"status": "running", "preserved": True}

    try:
        if not settings.llm_base_url or not settings.llm_api_key or not settings.llm_model:
            raise RuntimeError("backend/.env 中的 LLM 配置不完整")
        with httpx.Client(timeout=420) as client:
            login = client.post(
                f"{args.base_url}/auth/login",
                json={"email": args.admin_email, "password": args.admin_password},
            )
            login.raise_for_status()
            auth = login.json()
            if auth["user"]["role"] != "admin":
                raise RuntimeError("验证账号不是管理员")
            client.headers["Authorization"] = f"Bearer {auth['access_token']}"

            prompt = client.post(
                f"{args.base_url}/admin/prompt-presets",
                json={
                    "name": f"MVP4 完整消息验收 {suffix}",
                    "description": "验证完整 messages、宏替换与软绑定",
                    "messages": [
                        {
                            "name": "证据约束",
                            "role": "system",
                            "content": (
                                "你是学术报告撰写助手。只能依据用户消息提供的证据写作，"
                                "每个事实使用证据编号 [n] 引用；证据不足时明确说明。"
                            ),
                            "enabled": True,
                            "position": 0,
                        },
                        {
                            "name": "章节装配",
                            "role": "user",
                            "content": (
                                "课题：{{topic}}\n研究目标：{{research_goal}}\n"
                                "章节：{{section_title}}\n章节要求：{{section_instructions}}\n"
                                "用户输入：{{user_input}}\n证据清单：{{evidence_json}}"
                            ),
                            "enabled": True,
                            "position": 1,
                        },
                    ],
                },
            )
            prompt.raise_for_status()
            prompt_data = prompt.json()

            embedding = client.post(
                f"{args.base_url}/admin/embedding-presets",
                json={
                    "name": f"MVP4 本地向量验收 {suffix}",
                    "provider": "local_hashing",
                    "model": "local-char-ngram-hashing-v1",
                    "dimensions": settings.embedding_dimensions,
                    "parameters": {},
                },
            )
            embedding.raise_for_status()
            embedding_data = embedding.json()

            llm = client.post(
                f"{args.base_url}/admin/llm-presets",
                json={
                    "name": f"MVP4 LLM 验收 {suffix}",
                    "base_url": settings.llm_base_url,
                    "api_key": settings.llm_api_key.get_secret_value(),
                    "model": settings.llm_model,
                    "parameters": {
                        "timeout_seconds": settings.llm_timeout_seconds,
                        "max_retries": 2,
                    },
                    "bound_prompt_preset_id": prompt_data["id"],
                    "bound_embedding_preset_id": embedding_data["id"],
                },
            )
            llm.raise_for_status()
            llm_data = llm.json()
            if "api_key" in llm_data or not llm_data["has_api_key"]:
                raise RuntimeError("LLM 密钥响应脱敏验证失败")

            models = client.get(
                f"{args.base_url}/admin/llm-presets/{llm_data['id']}/models"
            )
            models.raise_for_status()
            model_data = models.json()
            if not model_data["models"]:
                raise RuntimeError("模型列表为空")

            activated = client.post(
                f"{args.base_url}/admin/llm-presets/{llm_data['id']}/activate",
                json={"sync_bindings": True},
            )
            activated.raise_for_status()
            runtime = activated.json()
            expected_runtime = {
                "llm_preset_id": llm_data["id"],
                "prompt_preset_id": prompt_data["id"],
                "embedding_preset_id": embedding_data["id"],
            }
            if any(runtime[key] != value for key, value in expected_runtime.items()):
                raise RuntimeError("LLM 预设绑定同步结果不正确")

            independent = client.post(
                f"{args.base_url}/admin/prompt-presets/{prompt_data['id']}/activate"
            )
            independent.raise_for_status()
            if independent.json()["llm_preset_id"] != llm_data["id"]:
                raise RuntimeError("提示词独立切换意外改变了 LLM 预设")

            term = client.post(
                f"{args.base_url}/admin/sensitive-terms",
                json={
                    "term": f"MVP4-SCAN-{suffix}",
                    "category": "验收标记",
                    "enabled": True,
                },
            )
            term.raise_for_status()
            term_data = term.json()

            governed_client = httpx.Client(timeout=60)
            governed_auth = governed_client.post(
                f"{args.base_url}/auth/register",
                json={
                    "email": f"mvp4-governance-{suffix}@example.com",
                    "password": f"Mvp4-{uuid4().hex}",
                    "display_name": "MVP4 Governance Validation",
                },
            )
            governed_auth.raise_for_status()
            governed = governed_auth.json()
            governed_client.headers["Authorization"] = (
                f"Bearer {governed['access_token']}"
            )
            disabled = client.patch(
                f"{args.base_url}/admin/users/{governed['user']['id']}",
                json={"status": "disabled"},
            )
            disabled.raise_for_status()
            denied = governed_client.get(f"{args.base_url}/auth/me")
            if denied.status_code != 403:
                raise RuntimeError("禁用用户仍可访问受保护接口")
            enabled = client.patch(
                f"{args.base_url}/admin/users/{governed['user']['id']}",
                json={"status": "active"},
            )
            enabled.raise_for_status()

            knowledge_base = governed_client.post(
                f"{args.base_url}/knowledge-bases",
                json={
                    "name": f"MVP4 敏感词验收 {suffix}",
                    "description": "验证上传后扫描结果",
                },
            )
            knowledge_base.raise_for_status()
            marker_path = artifacts / "03-sensitive-scan-input.txt"
            marker_path.write_text(
                f"普通研究文本。{term_data['term']} 在此出现，并再次出现 {term_data['term']}。",
                encoding="utf-8",
            )
            with marker_path.open("rb") as stream:
                uploaded = governed_client.post(
                    (
                        f"{args.base_url}/knowledge-bases/"
                        f"{knowledge_base.json()['id']}/documents"
                    ),
                    files={"file": (marker_path.name, stream, "text/plain")},
                )
            uploaded.raise_for_status()
            documents: list[dict] = []
            for _ in range(60):
                listed = governed_client.get(
                    f"{args.base_url}/knowledge-bases/"
                    f"{knowledge_base.json()['id']}/documents"
                )
                listed.raise_for_status()
                documents = listed.json()
                if documents and documents[0]["status"] in {"succeeded", "failed"}:
                    break
                time.sleep(0.25)
            governed_client.close()
            if not documents or documents[0]["status"] != "succeeded":
                raise RuntimeError("敏感词扫描文档处理未成功")
            matching_hits = [
                hit
                for hit in documents[0]["sensitive_hits"]
                if hit["term"] == term_data["term"]
            ]
            if not matching_hits or matching_hits[0]["count"] != 2:
                raise RuntimeError("敏感词命中次数不正确")
            write_json(
                artifacts / "04-governance-and-sensitive-scan.json",
                {
                    "disabled_access_status": denied.status_code,
                    "reenabled_status": enabled.json()["status"],
                    "document": documents[0],
                },
            )

            audits = client.get(f"{args.base_url}/admin/audit-logs", params={"limit": 50})
            audits.raise_for_status()
            audit_data = audits.json()
            required_actions = {
                "prompt_preset.create",
                "embedding_preset.create",
                "llm_preset.create",
                "llm_preset.activate",
            }
            observed_actions = {item["action"] for item in audit_data}
            if not required_actions.issubset(observed_actions):
                raise RuntimeError("管理员关键操作审计不完整")

            write_json(
                artifacts / "01-admin-runtime.json",
                {
                    "llm_preset": llm_data,
                    "prompt_preset": prompt_data,
                    "embedding_preset": embedding_data,
                    "runtime": runtime,
                    "model_count": len(model_data["models"]),
                    "configured_model_available": settings.llm_model in model_data["models"],
                    "api_key_exposed": "api_key" in llm_data,
                },
            )
            write_json(artifacts / "02-admin-audit.json", audit_data)
            summary.update(
                {
                    "status": "passed",
                    "completed_at": datetime.now(UTC).isoformat(),
                    "llm_preset_id": llm_data["id"],
                    "prompt_preset_id": prompt_data["id"],
                    "embedding_preset_id": embedding_data["id"],
                    "model_count": len(model_data["models"]),
                    "soft_binding_verified": True,
                    "secret_redaction_verified": True,
                    "audit_verified": True,
                    "disabled_user_denied": True,
                    "sensitive_scan_count": matching_hits[0]["count"],
                    "database_records_preserved": True,
                }
            )
            write_json(artifacts / "validation-summary.json", summary)
            return 0
    except Exception as exc:
        summary.update(
            {
                "status": "failed",
                "completed_at": datetime.now(UTC).isoformat(),
                "error": str(exc),
                "traceback": traceback.format_exc(),
                "database_records_preserved": True,
            }
        )
        write_json(artifacts / "validation-summary.json", summary)
        return 1


if __name__ == "__main__":
    sys.exit(main())
