' ============================================================
'  后台启动 Stock Scheduler（无窗口，关终端不会停）
'
'  用法: 双击运行，或在 PowerShell 中执行:
'    wscript deploy\start_stock_scheduler_bg.vbs
' ============================================================

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Quati-Trade"
WshShell.Run "python scripts\stock_scheduler.py", 0, False
