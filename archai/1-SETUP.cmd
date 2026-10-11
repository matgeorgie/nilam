@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Setup-ArchAI.ps1"
if errorlevel 1 (
 echo.
 echo Setup failed. Read the error above and the troubleshooting notes in SEND-TO-FRIEND.md.
) else (
 echo.
 echo Setup complete. Next run 2-START.cmd.
)
pause
