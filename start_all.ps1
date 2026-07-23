<#
文渊系统PowerShell一键启动脚本
功能等同于start_all.bat，适用于PowerShell环境
#>

# 设置控制台输出编码为UTF-8
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "==============================================" -ForegroundColor Cyan
Write-Host "文渊系统一键启动脚本" -ForegroundColor Cyan
Write-Host "==============================================" -ForegroundColor Cyan

Write-Host "`n[1/3] 启动PostgreSQL数据库服务..." -ForegroundColor Yellow
docker compose -p wenyuan up -d db

if ($LASTEXITCODE -ne 0) {
    Write-Host "数据库启动失败，请确保Docker Desktop已运行" -ForegroundColor Red
    Read-Host "按任意键退出"
    exit 1
}
Write-Host "数据库启动成功" -ForegroundColor Green

Write-Host "`n[2/3] 启动后端服务..." -ForegroundColor Yellow
$backendScript = @"
cd backend
if (-not (Test-Path ".venv")) {
    Write-Host "首次启动，创建虚拟环境并安装依赖..." -ForegroundColor Yellow
    python -m venv .venv
    .\.venv\Scripts\python.exe -m pip install -e .[dev]
}
if (-not (Test-Path ".env")) {
    Write-Host "复制环境变量配置文件..." -ForegroundColor Yellow
    Copy-Item ..\.env.example .env
}
Write-Host "执行数据库迁移..." -ForegroundColor Yellow
.\.venv\Scripts\alembic.exe upgrade head
Write-Host "启动后端服务..." -ForegroundColor Green
.\.venv\Scripts\uvicorn.exe app.main:app --reload --port 4396
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $backendScript -WindowStyle Normal -Title "文渊后端服务"

Write-Host "`n[3/3] 启动前端服务..." -ForegroundColor Yellow
$frontendScript = @"
cd frontend
if (-not (Test-Path "node_modules")) {
    Write-Host "首次启动，安装前端依赖..." -ForegroundColor Yellow
    npm install
}
Write-Host "启动前端服务..." -ForegroundColor Green
npm run dev
"@
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontendScript -WindowStyle Normal -Title "文渊前端服务"

Write-Host "`n==============================================" -ForegroundColor Cyan
Write-Host "所有服务启动中，请等待各窗口初始化完成" -ForegroundColor Cyan
Write-Host "前端地址: http://localhost:7777" -ForegroundColor Green
Write-Host "后端接口: http://localhost:4396" -ForegroundColor Green
Write-Host "接口文档: http://localhost:4396/docs" -ForegroundColor Green
Write-Host "==============================================" -ForegroundColor Cyan

Read-Host "`n按任意键退出启动脚本" | Out-Null