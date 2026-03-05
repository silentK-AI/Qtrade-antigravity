@echo off
chcp 65001 >nul
REM ============================================================
REM  快速重启 Dashboard
REM  杀掉现有进程并重新启动
REM ============================================================

set PROJECT_DIR=C:\Quati-Trade
set PYTHON=python

echo [%date% %time%] 正在重启 Dashboard...

REM 先杀掉占用 8088 端口的进程
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8088" ^| findstr "LISTENING"') do (
    echo 正在关闭旧进程 PID: %%a
    taskkill /F /PID %%a 2>nul
)

timeout /t 2 /nobreak >nul

REM 重新启动 Dashboard
cd /d %PROJECT_DIR%
start "Quati-Dashboard" %PYTHON% main.py dashboard --port 8088

echo [%date% %time%] Dashboard 已重启!
echo 访问: http://localhost:8088
timeout /t 3
