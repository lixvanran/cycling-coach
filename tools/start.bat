@echo off
REM ============================================================
REM Cycling Coach - dev mode launcher (Windows)
REM 双击运行 / 命令行: tools\start.bat
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
  echo [ERROR] Python not found in PATH. Install Python 3.11+ first.
  pause
  exit /b 1
)

if not exist workspace mkdir workspace
if not exist workspace\.logs mkdir workspace\.logs

python tools\start.py %*
set RC=%errorlevel%
if not %RC% == 0 (
  echo [ERROR] Launcher failed with code %RC%. Log: workspace\.logs\start.py.log
  pause
)
exit /b %RC%
