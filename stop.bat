@echo off
chcp 65001 >nul 2>&1
title NovelForge 2.0 - Stop

echo 停止 NovelForge 2.0 开发环境...

:: Kill by window title
taskkill /fi "WINDOWTITLE eq NovelForge-Backend*" /F >nul 2>&1
taskkill /fi "WINDOWTITLE eq NovelForge-Frontend*" /F >nul 2>&1

:: Also kill by port (belt and suspenders)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":8000.*LISTEN"') do (
    taskkill /PID %%a /F >nul 2>&1
)
for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":5173.*LISTEN"') do (
    taskkill /PID %%a /F >nul 2>&1
)

echo 已停止。按任意键退出...
pause >nul
