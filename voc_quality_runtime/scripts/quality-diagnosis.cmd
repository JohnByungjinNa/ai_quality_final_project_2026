@echo off
setlocal
set "PROJECT_ROOT=%~dp0.."
set "PYTHON=%PROJECT_ROOT%\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=%PROJECT_ROOT%\..\.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"
"%PYTHON%" "%PROJECT_ROOT%\quality_diagnosis\run_quality_diagnosis.py" %*
exit /b %ERRORLEVEL%
