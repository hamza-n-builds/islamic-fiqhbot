@echo off
setlocal
cd /d "%~dp0"

if not exist "backend\venv\Scripts\python.exe" (
    echo First run: creating the Python environment and installing FIQHBOT dependencies.
    py -3.11 -m venv "backend\venv" 2>nul
    if errorlevel 1 python -m venv "backend\venv"
    if errorlevel 1 goto setup_failed
    "backend\venv\Scripts\python.exe" -m pip install -r "backend\requirements.txt"
    if errorlevel 1 goto setup_failed
)

if not exist "backend\.env" (
    echo FIQHBOT needs your Gemini API key in backend\.env.
    echo Copy backend\.env.example to backend\.env and fill in GEMINI_API_KEY.
    pause
    exit /b 1
)

"backend\venv\Scripts\python.exe" -u "backend\start_local.py" %*
if errorlevel 1 pause
exit /b %errorlevel%

:setup_failed
echo Setup did not finish. Check the error above, then run this file again.
pause
exit /b 1
