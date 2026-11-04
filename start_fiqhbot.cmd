@echo off
setlocal
cd /d "%~dp0"

if defined FIQHBOT_PYTHON (
    call :select_python "%FIQHBOT_PYTHON%"
    if errorlevel 1 goto missing_python
    goto launch
)

call :select_python "backend\venv\Scripts\python.exe"
if not errorlevel 1 goto launch

py -3.11 -I -B -c "import struct,sys; sys.exit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if not errorlevel 1 goto launch_py

call :select_python "python3.11"
if not errorlevel 1 goto launch
call :select_python "python"
if not errorlevel 1 goto launch
goto missing_python

:select_python
"%~1" -I -B -c "import struct,sys; sys.exit(0 if sys.version_info[:2]==(3,11) and struct.calcsize('P')==8 else 1)" >nul 2>&1
if errorlevel 1 exit /b 1
set "BOOTSTRAP_PYTHON=%~1"
exit /b 0

:launch
"%BOOTSTRAP_PYTHON%" -B -u "backend\bootstrap_local.py" %*
goto finished

:launch_py
py -3.11 -B -u "backend\bootstrap_local.py" %*
goto finished

:missing_python
echo FIQHBOT requires a working Python 3.11 installation, 64-bit.
echo Install it with PATH enabled, or set FIQHBOT_PYTHON to its python.exe path.
cmd /c exit 1

:finished
set "FIQHBOT_RESULT=%errorlevel%"
if not "%FIQHBOT_RESULT%"=="0" if not defined FIQHBOT_NO_PAUSE pause
exit /b %FIQHBOT_RESULT%
