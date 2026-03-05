' ============================================================
'  后台启动 Dashboard（无窗口，关终端不会停）
'
'  用法: 双击运行，或在 PowerShell 中执行:
'    cscript deploy\start_dashboard_bg.vbs
' ============================================================

Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "C:\Quati-Trade"
WshShell.Run "python main.py dashboard --port 8088", 0, False

WScript.Echo "Dashboard 已在后台启动! 访问: http://localhost:8088"
