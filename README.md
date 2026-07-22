# 文渊

大学生私有文献知识库、学术报告生成与私有语料相似度检测系统。

当前仓库已完成 MVP 0：React 前端骨架、FastAPI 后端骨架、领域数据模型、首个数据库迁移、端口适配器契约、健康检查和统一错误结构。

## 目录

```text
frontend/   React + TypeScript + Vite
backend/    FastAPI + SQLAlchemy + Alembic
reference/  题目原始资料
```

## 本地启动

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
