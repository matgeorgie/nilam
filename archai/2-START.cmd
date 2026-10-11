@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\Start-ArchAI.ps1"
if errorlevel 1 (
 echo.
 echo Start failed. Check SEND-TO-FRIEND.md and logs/.
) else (
 echo.
 echo Open http://127.0.0.1:3000/projects when the server is ready.
)
pause
