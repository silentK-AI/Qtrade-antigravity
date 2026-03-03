@echo off
REM ============================================================
REM  RDP 会话保持脚本
REM  
REM  问题: 远程桌面断开后 GUI 自动化 (easytrader) 会失效
REM  解决: 断开前运行此脚本，将 RDP 会话转到控制台 session
REM  
REM  用法: 断开远程桌面之前，以管理员身份运行此脚本
REM ============================================================

echo 正在将 RDP 会话转移到控制台，保持 GUI 可用...

REM 获取当前 session ID
for /f "tokens=3" %%i in ('query session ^| findstr ">"') do set SESSION_ID=%%i

REM 将当前会话连接到控制台
tscon %SESSION_ID% /dest:console

echo 会话已转移。你可以安全断开远程桌面，easytrader 将继续工作。
pause
