@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0agents.ps1" %*
exit /b %ERRORLEVEL%
