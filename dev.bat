@echo off
chcp 65001 >nul 2>&1
title NovelForge 2.0 Dev

:: ── 配置 ──────────────────────────────────────────
set PYTHON=F:\kelaode\Data\Agents\zqibcc8w9\tools\Python311\python.exe
set NODE=C:\Users\6\.workbuddy\binaries\node\versions\22.22.2\node.exe
set BACKEND_PORT=8000
set FRONTEND_PORT=5173
set ROOT=%~dp0
set BACKEND_DIR=%ROOT%backend
set FRONTEND_DIR=%ROOT%frontend
set LOG_DIR=%BACKEND_DIR%\data\logs

:: ── 创建日志目录 ──────────────────────────────────
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:: ── 杀掉残留进程 ──────────────────────────────────
echo [1/4] 清理残留进程...
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%BACKEND_PORT%.*LISTEN"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%FRONTEND_PORT%.*LISTEN"') do (
    taskkill /PID %%a /F >nul 2>&1
)
timeout /t 2 /nobreak >nul

:: ── 启动后端 ──────────────────────────────────────
echo [2/4] 启动后端 (port %BACKEND_PORT%, --reload) ...
cd /d "%BACKEND_DIR%"
start "NovelForge-Backend" /MIN cmd /c "%PYTHON% -m uvicorn app.main:app --host 127.0.0.1 --port %BACKEND_PORT% --reload --log-level info >> "%LOG_DIR%\backend.log" 2>&1"

:: ── 等后端就绪 ────────────────────────────────────
echo [3/4] 等待后端就绪 ...
set READY=0
for /L %%i in (1,1,30) do (
    if !READY!==0 (
        curl -s http://127.0.0.1:%BACKEND_PORT%/health >nul 2>&1 && set READY=1
        if !READY!==0 timeout /t 1 /nobreak >nul
    )
)
if %READY%==0 (
    echo [ERROR] 后端 30 秒内未就绪，请检查 %LOG_DIR%\backend.log
    pause
    exit /b 1
)
echo       后端已就绪 ✓

:: ── 启动前端 ──────────────────────────────────────
echo [4/4] 启动前端 (port %FRONTEND_PORT%) ...
cd /d "%FRONTEND_DIR%"
start "NovelForge-Frontend" /MIN cmd /c "%NODE% node_modules\vite\bin\vite.js --port %FRONTEND_PORT% --host"

echo.
echo ══════════════════════════════════════════════════
echo   NovelForge 2.0 开发环境已启动
echo   后端: http://127.0.0.1:%BACKEND_PORT%  (日志: %LOG_DIR%\backend.log)
echo   前端: http://127.0.0.1:%FRONTEND_PORT%
echo ══════════════════════════════════════════════════
echo.
echo 关闭此窗口不会停止服务。要停止请运行 stop.bat
pause
