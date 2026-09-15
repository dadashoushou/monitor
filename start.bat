@echo off
setlocal
chcp 65001 >nul

set "SCRIPT_DIR=%~dp0"
set "PYTHON_EXE=%SCRIPT_DIR%.venv\Scripts\python.exe"

if exist "%PYTHON_EXE%" (
  "%PYTHON_EXE%" --version >nul 2>&1
  if errorlevel 1 set "PYTHON_EXE="
)

if not defined PYTHON_EXE set "PYTHON_EXE=D:\software\Python312\python.exe"

if not exist "%PYTHON_EXE%" (
  echo [ERROR] No usable Python interpreter was found.
  echo Checked the project virtual environment and: D:\software\Python312\python.exe
  pause
  exit /b 1
)

cd /d "%SCRIPT_DIR%"
echo Running: "%PYTHON_EXE%" app.py
"%PYTHON_EXE%" app.py

if errorlevel 1 (
  echo.
  echo [ERROR] The app stopped with an error (errorlevel: %errorlevel%)
  echo Check the message above, then press any key to close this window.
  pause
  exit /b 1
)

pause
