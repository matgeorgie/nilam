@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Stop-ArchAI.ps1"
if errorlevel 1 echo Stop failed. Check the error above.
pause
