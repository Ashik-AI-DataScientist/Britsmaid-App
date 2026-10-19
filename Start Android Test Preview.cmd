@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -NoExit -ExecutionPolicy RemoteSigned -File "%~dp0scripts\Start-AndroidTestPreview.ps1"
