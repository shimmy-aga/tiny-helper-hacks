@echo off
:: Check for admin rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo Requesting administrative privileges...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb runAs"
    exit /b
)

:: Force 64-bit PowerShell even if running from 32-bit Steam
set "PWSH64=%SystemRoot%\System32\WindowsPowerShell\v1.0\powershell.exe"

"%PWSH64%" -NoProfile -ExecutionPolicy Bypass -File "%~dp0toggle_shell.ps1"
pause