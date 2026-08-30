@echo off
REM ============================================================
REM Cycling Coach - dev mode stopper (Windows)
REM 双击运行 / 命令行: tools\stop.bat
REM ============================================================
chcp 65001 >nul
setlocal
cd /d "%~dp0\.."
set "ROOT=%CD%"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"
set "PYTHONUNBUFFERED=1"

where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found in PATH.
  pause
  exit /b 1
)

python tools\stop.py %*
set RC=%errorlevel%
if not %RC% == 0 (
  echo [ERROR] Stopper failed with code %RC%. Log: workspace\.logs\stop.py.log
  pause
)
exit /b %RC%
