@echo off
chcp 65001 >nul
REM ============================================================
REM  后台启动 Dashboard（关掉窗口也不会停）
REM ============================================================

set PROJECT_DIR=C:\Quati-Trade

echo [%date% %time%] 正在后台启动 Dashboard...

REM 先杀掉已有的 Dashboard 进程
for /f "tokens=5" %%a in ('netstat -aon ^| findstr ":8088" ^| findstr "LISTENING"') do (
    echo 关闭旧进程 PID: %%a
    taskkill /F /PID %%a 2>nul
)
timeout /t 2 /nobreak >nul

REM 用 pythonw 后台启动（没有窗口，关闭终端也不会停）
cd /d %PROJECT_DIR%
start /b pythonw main.py dashboard --port 8088

echo [%date% %time%] Dashboard 已在后台启动!
echo 访问: http://localhost:8088
echo.
echo 关闭这个窗口不会影响 Dashboard 运行。
echo 如需停止: taskkill /F /IM pythonw.exe
timeout /t 5
