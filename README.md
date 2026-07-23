# 文渊

大学生私有文献知识库、学术报告生成与私有语料相似度检测系统。

当前仓库已完成 MVP 3：在私有知识库与报告生成闭环上，补齐可解释的私有语料相似度检测、定向润色版本和证据型学术助手。

MVP 1 使用透明可复现的本地字符 n-gram 哈希向量作为离线基线；后续可通过既有 Embedding 端口替换为 `BAAI/bge-small-zh-v1.5`，无需改动知识库业务流程。

## 目录

```text
frontend/   React + TypeScript + Vite
backend/    FastAPI + SQLAlchemy + Alembic
reference/  题目原始资料
素材/       MVP 测试文献（不纳入 Git）
```

## 本地启动

Windows 下可在仓库根目录运行 `start_all.bat` 一键启动数据库、后端和前端。前端使用 `7777`，后端使用 `4396`。

### 数据库

```powershell
docker compose up -d db
```

### 后端

```powershell
Set-Location backend
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
Copy-Item ..\.env.example .env
.venv\Scripts\alembic.exe upgrade head
.venv\Scripts\uvicorn.exe app.main:app --reload --port 4396
```

后端地址为 `http://localhost:4396`，OpenAPI 地址为 `http://localhost:4396/docs`。

### 前端

```powershell
Set-Location frontend
npm.cmd install
npm.cmd run dev
```

前端地址为 `http://localhost:7777`。开发服务器会把 `/api` 转发到 FastAPI。

## 验证

```powershell
Set-Location backend
.venv\Scripts\python.exe -m pytest
.venv\Scripts\ruff.exe check .

Set-Location ..\frontend
npm.cmd run typecheck
npm.cmd run build
```

后端启动后可更新前端 OpenAPI 类型：

```powershell
npm.cmd run api:generate
```

## MVP 1 功能

- 注册、登录、HttpOnly 刷新令牌、退出和用户数据隔离；
- 创建与删除知识库，按名称筛选文献；
- PDF、Markdown、TXT 上传，包含大小、重复内容、MIME 与 PDF 文件头校验；
- 保留标题或页码的解析、可配置重叠切片、摘要和关键词提取；
- 文档处理状态、失败原因、重试和删除；
- pgvector Top-K 检索，返回文献、标题或页码、片段和相似度。

## MVP 2 功能

- 内置“文献综述”和“开题报告”两种带版本的结构化模板；
- 按章节构造检索查询，限制证据数量并记录模型、查询、片段和提示词版本；
- 支持 OpenAI 兼容的大模型接口；未配置模型时使用不编造来源的离线证据草稿器；
- 使用 SSE 持久化展示章节生成进度，失败章节可独立重试；
- Markdown 章节编辑、停止输入后自动保存、预览和引用原文核对；
- 报告历史搜索、版本快照、历史版本恢复和 DOCX 导出。

## MVP 3 功能

- 按句切分报告，使用字符 2～4 gram TF-IDF 与余弦相似度在当前用户知识库内匹配；
- 保存每个高相似片段的真实文献、原文、分数和报告偏移区间，汇总“高相似文本占比”；
- 相似度阈值、n-gram 范围和最低句长均可通过环境变量配置；
- 对选中文字提供“学术严谨、通俗表达、精简”三种润色预览；
- 只有用户确认润色后才建立新报告版本，原稿和历史版本不会被覆盖；
- 提供“严谨导师”和“数据分析专家”角色，并区分普通对话与修改建议；
- 学术助手先检索当前知识库，只返回能够映射到真实片段的引用编号。
