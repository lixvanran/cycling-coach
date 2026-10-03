@echo off
REM ============================================================
REM Cycling Coach - Windows launcher
REM 双击运行 / 命令行: tools\start.bat
REM
REM V0.9.0 行为变更:
REM   默认走"干净模式" —— 只用 Python, 不需要 Node/pnpm,
REM   后端直接伺服前端 build 产物 (cycling_coach/static), 浏览器打开 8765。
REM   Windows 正式用户不该被要求装 Node。
REM
REM   开发模式仍可用:  tools\start.bat --dev
REM   只装依赖:        tools\start.bat --install
REM   只查环境:        tools\start.bat --check
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
  echo         下载: https://www.python.org/downloads/  ^(记得勾选 Add to PATH^)
  pause
  exit /b 1
)

if not exist workspace mkdir workspace
if not exist workspace\.logs mkdir workspace\.logs

REM ---- 默认加 --desktop (干净模式), 用户显式传参时以用户为准 ----
set "ARGS=%*"
echo %ARGS% | findstr /C:"--" >nul
if errorlevel 1 (
  set "ARGS=--desktop %*"
)

python tools\start.py %ARGS%
set RC=%errorlevel%
if not %RC% == 0 (
  echo.
  echo [ERROR] Launcher failed with code %RC%.
  echo         Log: workspace\.logs\start.py.log
  echo         排障: tools\diagnose.bat
  pause
)
exit /b %RC%
