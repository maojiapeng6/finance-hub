@echo off
chcp 65001 >nul
title 环球财经雷达 Finance Radar (端口 6789)
cd /d "%~dp0"

echo.
echo   ==================================================
echo    环球财经雷达 正在启动...
echo    浏览器打开: http://localhost:6789
echo    关闭本窗口即可停止服务
echo   ==================================================
echo.

where python >nul 2>nul
if %errorlevel%==0 (
    python server.py
) else (
    "C:\Users\Peng\.workbuddy\binaries\python\envs\default\Scripts\python.exe" server.py
)

pause
