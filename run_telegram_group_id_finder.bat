@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0telegram_group_id_finder.ps1"

if errorlevel 1 (
    echo.
    echo The script exited with an error.
)

echo.
pause
