@echo off
REM ============================================================
REM Cycling Coach - 一键卸载 (dev 模式清理)
REM
REM 默认保留用户数据 (workspace + KB):
REM   - workspace\cycling_coach.sqlite (活动/计划/PMC)
REM   - workspace\.logs (日志)
REM   - workspace\input (FIT 文件)
REM
REM 选项:
REM   --purge-data   连用户数据一并删除 (不可恢复)
REM   --keep-venv    保留 .venv (重新 build 用)
REM
REM 用法:
REM   tools\uninstall.bat             (清 build, 保留数据)
REM   tools\uninstall.bat --purge-data (全清)
REM   tools\uninstall.bat --keep-venv  (清 build, 保 venv)
REM ============================================================
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0\.."
set "ROOT=%CD%"

set "PURGE_DATA=0"
set "KEEP_VENV=0"
for %%a in (%*) do (
  if /i "%%a"=="--purge-data" set "PURGE_DATA=1"
  if /i "%%a"=="--keep-venv" set "KEEP_VENV=1"
)

echo.
echo ============================================================
echo  Cycling Coach - 一键卸载
echo  Root: %ROOT%
echo ============================================================
echo.
echo  即将清理以下内容:
if "%KEEP_VENV%"=="0" echo    - .venv\                  (Python 虚拟环境, ~200 MB)
echo    - apps\desktop\dist-electron\   (Setup.exe 构建产物)
echo    - apps\desktop\node_modules\    (如果存在)
echo    - dist\                          (PyInstaller 临时输出)
echo    - build\                         (PyInstaller 临时输出)
echo    - cycling_coach\static\          (前端 build 软链)
echo    - apps\web\dist\                 (前端 build 产物)
echo    - apps\web\node_modules\         (如果存在)
if "%PURGE_DATA%"=="1" (
  echo.
  echo    !! 警告 --purge-data !!:
  echo    - workspace\                      (用户数据: 活动/计划/PMC)
  echo    - workspace\input\                (FIT 原始文件)
  echo    - workspace\.logs\                (日志)
)
echo.
set /p CONFIRM="确认卸载? (y/N): "
if /i not "%CONFIRM%"=="y" (
  echo 已取消.
  pause
  exit /b 0
)

echo.
echo 清理中...

REM 1. 杀进程
echo   - 杀 cycling_coach 相关进程...
taskkill /F /IM CyclingCoach.exe /T 2>nul
taskkill /F /IM CyclingCoach-backend.exe /T 2>nul
taskkill /F /IM electron.exe /T 2>nul
taskkill /F /IM node.exe /T 2>nul
taskkill /F /FI "WINDOWTITLE eq Cycling Coach*" /T 2>nul

REM 2. 删 venv
if "%KEEP_VENV%"=="0" (
  if exist .venv (
    echo   - 删除 .venv ...
    rmdir /s /q .venv
  )
)

REM 3. 删 build artifacts
for %%d in (dist build) do (
  if exist %%d (
    echo   - 删除 %%d ...
    rmdir /s /q %%d
  )
)
if exist cycling_coach\static (
  echo   - 删除 cycling_coach\static ...
  rmdir /s /q cycling_coach\static
)
if exist apps\web\dist (
  echo   - 删除 apps\web\dist ...
  rmdir /s /q apps\web\dist
)
if exist apps\web\node_modules (
  if not exist apps\web\node_modules\. (
    echo   - 删除 apps\web\node_modules ...
    rmdir /s /q apps\web\node_modules
  )
)
if exist apps\desktop\dist-electron (
  echo   - 删除 apps\desktop\dist-electron ...
  rmdir /s /q apps\desktop\dist-electron
)
if exist apps\desktop\node_modules (
  if not exist apps\desktop\node_modules\. (
    echo   - 删除 apps\desktop\node_modules ...
    rmdir /s /q apps\desktop\node_modules
  )
)
if exist apps\desktop\build-resources\backend (
  echo   - 删除 apps\desktop\build-resources\backend ...
  rmdir /s /q apps\desktop\build-resources\backend
)

REM 4. 沙盒残留
if exist cc-desktop-debug.log (
  echo   - 删除 cc-desktop-debug.log ...
  del /q cc-desktop-debug.log
)
if exist diagnose.txt (
  echo   - 删除 diagnose.txt ...
  del /q diagnose.txt
)
if exist cycling-coach-*.zip (
  echo   - 删除 cycling-coach-*.zip ...
  del /q cycling-coach-*.zip
)
if exist cycling-coach-*.tar.gz (
  echo   - 删除 cycling-coach-*.tar.gz ...
  del /q cycling-coach-*.tar.gz
)

REM 5. 用户数据 (可选)
if "%PURGE_DATA%"=="1" (
  if exist workspace (
    echo   - 删除 workspace (用户数据) ...
    rmdir /s /q workspace
  )
) else (
  echo   - 保留 workspace (用户数据: workspace\cycling_coach.sqlite)
)

echo.
echo ============================================================
echo  卸载完成!
if "%PURGE_DATA%"=="1" (
  echo  用户数据已删除.
) else (
  echo  用户数据保留在: %ROOT%\workspace
  echo  彻底清:  tools\uninstall.bat --purge-data
)
echo ============================================================
echo.
pause
endlocal
