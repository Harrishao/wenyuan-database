@echo off
chcp 65001 >nul
echo ==============================================
echo 文渊系统一键启动脚本
echo ==============================================

echo [1/3] 启动PostgreSQL数据库服务...
docker compose -p wenyuan up -d db
if %errorlevel% neq 0 (
    echo 数据库启动失败，请确保Docker Desktop已运行
    pause
    exit /b 1
)
echo 数据库启动成功

echo.
echo [2/3] 启动后端服务...
start "文渊后端服务" cmd /k "cd backend && (if not exist .venv (python -m venv .venv && .venv\Scripts\python.exe -m pip install -e .[dev])) & (if not exist .env copy ..\.env.example .env) & .venv\Scripts\alembic.exe upgrade head & .venv\Scripts\uvicorn.exe app.main:app --reload --port 4396"

echo.
echo [3/3] 启动前端服务...
start "文渊前端服务" cmd /k "cd frontend && (if not exist node_modules npm install) & npm run dev"

echo.
echo ==============================================
echo 所有服务启动中，请等待各窗口初始化完成
echo 前端地址: http://localhost:7777
echo 后端接口: http://localhost:4396
echo 接口文档: http://localhost:4396/docs
echo ==============================================
echo 按任意键退出启动脚本...
pause >nul