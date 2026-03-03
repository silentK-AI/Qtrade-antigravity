@echo off
chcp 65001 >nul
REM ============================================================
REM  Quati-Trade Cloud Startup Script
REM ============================================================

echo [%date% %time%] Starting Quati-Trade...

REM === Config ===
set PROJECT_DIR=C:\Quati-Trade
set PYTHON=python
set THS_EXE_PATH=C:\同花顺软件\同花顺\xiadan.exe
set TRADER_BACKEND=easytrader
set EASYTRADER_BROKER=ths
set ML_ENABLED=false
set LOG_LEVEL=INFO

REM === Step 1: Start Dashboard ===
echo [%date% %time%] Starting Dashboard (port 8088)...
cd /d %PROJECT_DIR%
start "Quati-Dashboard" %PYTHON% main.py dashboard --port 8088
timeout /t 5 /nobreak

REM === Step 2: Start Live Trading ===
echo [%date% %time%] Starting Live Trading (513310 + 513880)...
cd /d %PROJECT_DIR%
start "Quati-Trade-Live" %PYTHON% main.py live --etf 513310 513880

echo ============================================================
echo  Quati-Trade Started!
echo  Dashboard: http://localhost:8088
echo  ETFs: 513310, 513880
echo  Strategy: FuturesETFArbStrategy
echo ============================================================
pause
