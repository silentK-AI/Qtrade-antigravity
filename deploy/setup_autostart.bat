@echo off
chcp 65001 >nul
REM ============================================================
REM  Quati-Trade 开机自启注册脚本
REM  
REM  功能: 将 Dashboard 和 Scheduler 注册到 Windows 任务计划程序
REM        服务器重启后自动拉起，无需手动启动
REM  
REM  用法: 以管理员身份运行一次即可
REM ============================================================

set PROJECT_DIR=C:\Quati-Trade
set PYTHON_PATH=python

echo.
echo ============================================================
echo  正在注册 Quati-Trade 自启动任务...
echo ============================================================
echo.

REM === 1. 注册 Dashboard 自启 ===
echo [1/2] 注册 Dashboard (port 8088) 开机自启...
schtasks /Create /TN "Quati-Dashboard" ^
    /TR "cmd /c cd /d %PROJECT_DIR% && %PYTHON_PATH% main.py dashboard --port 8088 >> logs\dashboard_schtask.log 2>&1" ^
    /SC ONSTART ^
    /RU SYSTEM ^
    /RL HIGHEST ^
    /F
if %errorlevel%==0 (
    echo    [OK] Dashboard 自启任务已注册
) else (
    echo    [FAIL] Dashboard 注册失败，请确认以管理员身份运行
)

echo.

REM === 2. 注册 Scheduler 自启 ===
echo [2/2] 注册 Scheduler (交易调度器) 开机自启...
schtasks /Create /TN "Quati-Scheduler" ^
    /TR "cmd /c cd /d %PROJECT_DIR% && %PYTHON_PATH% scripts\scheduler.py >> logs\scheduler_schtask.log 2>&1" ^
    /SC ONSTART ^
    /RU SYSTEM ^
    /RL HIGHEST ^
    /F
if %errorlevel%==0 (
    echo    [OK] Scheduler 自启任务已注册
) else (
    echo    [FAIL] Scheduler 注册失败，请确认以管理员身份运行
)

echo.
echo ============================================================
echo  注册完成！
echo.
echo  已创建的计划任务:
echo    - Quati-Dashboard  : 开机自动启动 Dashboard (8088端口)
echo    - Quati-Scheduler  : 开机自动启动交易调度器
echo.
echo  管理命令:
echo    查看任务: schtasks /Query /TN "Quati-Dashboard"
echo    手动启动: schtasks /Run /TN "Quati-Dashboard"
echo    手动停止: schtasks /End /TN "Quati-Dashboard"
echo    删除任务: schtasks /Delete /TN "Quati-Dashboard" /F
echo ============================================================
pause
