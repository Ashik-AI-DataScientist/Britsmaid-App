@echo off
setlocal
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy RemoteSigned -File "%~dp0scripts\Start-Britsmaid.ps1"
if errorlevel 1 (
    echo.
    echo The app could not start. Share the error above for help.
    pause
)
endlocal