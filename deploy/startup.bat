@echo off
REM ============================================================
REM  Quati-Trade 云端自启脚本
REM  功能: 启动同花顺 → 等待登录 → 启动策略引擎 + Dashboard
REM  用法: 放入 Windows 任务计划程序，开机自动运行
REM ============================================================

echo [%date% %time%] Quati-Trade 启动中...

REM === 配置区 ===
set PROJECT_DIR=C:\Quati-Trade
set PYTHON=python
set THS_EXE=C:\同花顺\xiadan.exe
set TRADER_BACKEND=easytrader
set EASYTRADER_BROKER=ths
set ML_ENABLED=false
set LOG_LEVEL=INFO

REM === Step 1: 启动同花顺下单客户端 ===
echo [%date% %time%] 启动同花顺下单客户端...
if exist "%THS_EXE%" (
    start "" "%THS_EXE%"
    echo [%date% %time%] 等待同花顺启动和登录 (60秒)...
    timeout /t 60 /nobreak
) else (
    echo [%date% %time%] 警告: 同花顺路径不存在: %THS_EXE%
    echo [%date% %time%] 请手动启动同花顺并登录后，再运行此脚本
    pause
    exit /b 1
)

REM === Step 2: 启动 Dashboard 监控后台 (后台运行) ===
echo [%date% %time%] 启动 Dashboard...
cd /d %PROJECT_DIR%
start "Quati-Dashboard" %PYTHON% main.py dashboard --port 8088

REM 等待 Dashboard 启动
timeout /t 5 /nobreak

REM === Step 3: 启动实盘交易引擎 ===
echo [%date% %time%] 启动实盘交易引擎 (513310 + 513880)...
cd /d %PROJECT_DIR%
start "Quati-Trade-Live" %PYTHON% main.py live --etf 513310 513880

echo ============================================================
echo  Quati-Trade 已启动
echo  Dashboard: http://localhost:8088
echo  交易标的: 513310 (中韩半导体), 513880 (日经ETF)
echo  策略: FuturesETFArbStrategy (期货+折价 专属模式)
echo ============================================================
echo.
echo 请勿关闭此窗口。按 Ctrl+C 可停止所有服务。
pause
