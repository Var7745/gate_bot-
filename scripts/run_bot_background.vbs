' GATE 2027 Telegram Bot Silent Background Launcher
' Runs python scripts/bot_service.py without popping any visible command window

Set WshShell = CreateObject("WScript.Shell")
strPath = "C:\Users\goudv\.gemini\antigravity\scratch\gate-2027-companion\scripts\bot_service.py"
WshShell.Run "python """ & strPath & """", 0, False
Set WshShell = Nothing
