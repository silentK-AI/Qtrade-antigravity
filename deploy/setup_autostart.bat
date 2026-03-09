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

echo.
echo ============================================================
echo  正在注册 Quati-Trade 自启动任务...
echo ============================================================
echo.

REM === 1. 注册 Dashboard 自启 ===
echo [1/3] 注册 Dashboard (port 8088) 开机自启...
schtasks /Create /TN "Quati-Dashboard" ^
    /TR "wscript.exe %PROJECT_DIR%\deploy\start_dashboard_bg.vbs" ^
    /SC ONSTART ^
    /DELAY 0000:30 ^
    /RL HIGHEST ^
    /F
if %errorlevel%==0 (
    echo    [OK] Dashboard 自启任务已注册
) else (
    echo    [FAIL] Dashboard 注册失败，请确认以管理员身份运行
)

echo.

REM === 2. 注册 Scheduler 自启 ===
echo [2/3] 注册 Scheduler (交易调度器) 开机自启...
schtasks /Create /TN "Quati-Scheduler" ^
    /TR "cmd /c cd /d %PROJECT_DIR% && python scripts\scheduler.py >> logs\scheduler_schtask.log 2>&1" ^
    /SC ONSTART ^
    /DELAY 0001:00 ^
    /RL HIGHEST ^
    /F
if %errorlevel%==0 (
    echo    [OK] Scheduler 自启任务已注册
) else (
    echo    [FAIL] Scheduler 注册失败，请确认以管理员身份运行
)

echo.

REM === 3. 注册 Stock Scheduler 自启 ===
echo [3/3] 注册 Stock Scheduler (个股技术分析调度器) 开机自启...
schtasks /Create /TN "Quati-Stock-Scheduler" ^
    /TR "cmd /c cd /d %PROJECT_DIR% && python scripts\stock_scheduler.py >> logs\stock_scheduler_schtask.log 2>&1" ^
    /SC ONSTART ^
    /DELAY 0001:00 ^
    /RL HIGHEST ^
    /F
if %errorlevel%==0 (
    echo    [OK] Stock Scheduler 自启任务已注册
) else (
    echo    [FAIL] Stock Scheduler 注册失败，请确认以管理员身份运行
)

echo.
echo ============================================================
echo  注册完成！
echo.
echo  已创建的计划任务:
echo    - Quati-Dashboard        : 开机30秒后自动启动 Dashboard
echo    - Quati-Scheduler        : 开机60秒后自动启动交易调度器 (T+0 ETF)
echo    - Quati-Stock-Scheduler  : 开机60秒后自动启动技术分析监控调度器 (股票)
echo.
echo  管理命令:
echo    手动启动: schtasks /Run /TN "Quati-Dashboard"
echo    查看状态: schtasks /Query /TN "Quati-Dashboard"
echo    删除任务: schtasks /Delete /TN "Quati-Dashboard" /F
echo ============================================================
pause
