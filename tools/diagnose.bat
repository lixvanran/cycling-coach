@echo off
REM ============================================================
REM Cycling Coach - diagnostic tool (Windows)
REM 双击运行 / 命令行: tools\diagnose.bat
REM 输出到 workspace\.logs\diagnose.log
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

if not exist workspace mkdir workspace
if not exist workspace\.logs mkdir workspace\.logs

python tools\diagnose.py > workspace\.logs\diagnose.log 2>&1
set RC=%errorlevel%
if %RC% == 0 (
  echo [OK] Diagnostic complete. Report: workspace\.logs\diagnose.log
  start "" workspace\.logs\diagnose.log
) else (
  echo [ERROR] Diagnostic failed. See workspace\.logs\diagnose.log
)
pause
exit /b %RC%
