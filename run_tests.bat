@echo off
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"
set "FALLBACK_PYTHON=D:\software\Python312\python.exe"
set "TEST_TEMP=%SCRIPT_DIR%.pytest-temp"

if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" --version >nul 2>&1
  if errorlevel 1 set "PYTHON_EXE="
)

if not defined PYTHON_EXE set "PYTHON_EXE=%FALLBACK_PYTHON%"

if not exist "%PYTHON_EXE%" (
  echo [ERROR] No usable Python interpreter was found.
  echo Checked the project virtual environment and: %FALLBACK_PYTHON%
  pause
  exit /b 1
)

cd /d "%SCRIPT_DIR%"

if exist "%TEST_TEMP%" (
  rmdir /s /q "%TEST_TEMP%" >nul 2>&1
)

echo Running tests with: "%PYTHON_EXE%"
"%PYTHON_EXE%" -m pytest -q --basetemp="%TEST_TEMP%"
set "TEST_EXIT=%ERRORLEVEL%"

if exist "%TEST_TEMP%" (
  rmdir /s /q "%TEST_TEMP%" >nul 2>&1
)

if not "%TEST_EXIT%"=="0" (
  echo.
  echo [ERROR] Tests finished with errorlevel: %TEST_EXIT%
  pause
)

exit /b %TEST_EXIT%
