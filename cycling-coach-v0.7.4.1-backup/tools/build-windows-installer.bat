@echo off
REM ============================================================
REM Cycling Coach - Windows 桌面端一键打包
REM
REM V0.7.2 状态: 桌面端仍 V0.5.3 (闪退搁置), 建议用 dev 模式 + 浏览器
REM              本脚本可用, 但产物是 V0.5.3 桌面端
REM              当前推荐: tools\start.bat
REM
REM V0.7.2 重新打包: 输出 source/kb zip 到 workspace\dist\
REM   python tools\build_release.py
REM
REM 流程 (V0.5.3 桌面):
REM   1. 检查环境 (Python / Node / pnpm)
REM   2. 后端: pyinstaller -> dist\CyclingCoach-backend.exe
REM   3. 前端: pnpm build -> apps\web\dist\
REM   4. 复制 backend binary -> apps\desktop\build-resources\backend
REM   5. electron-builder -> apps\desktop\dist-electron\CyclingCoach-Setup-x.y.z-x64.exe
REM ============================================================
setlocal enabledelayedexpansion
chcp 65001 > nul
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"
set "PROJECT_ROOT=%CD%"

echo.
echo ============================================================
echo  Cycling Coach - V0.7.2 桌面端打包
echo ============================================================
echo.
echo [注意] 桌面端代码仍 V0.5.3, V0.7.2 推荐用 dev 模式 (tools\start.bat)
echo.
echo 选择操作:
echo   1. 打 V0.7.2 source/kb zip (推荐, 沙箱已生成, 你可以重打)
echo   2. 打 V0.5.3 桌面端 NSIS Setup.exe (闪退风险)
echo   3. 退出
echo.
set /p "CHOICE=输入选项 (1/2/3): "

if "%CHOICE%"=="1" goto :build_release
if "%CHOICE%"=="2" goto :build_desktop
if "%CHOICE%"=="3" exit /b 0

:build_release
echo.
echo [1/3] 打 V0.7.2 source zip...
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found
  pause
  exit /b 1
)
python tools\build_release.py
if errorlevel 1 (
  echo [ERROR] Build failed
  pause
  exit /b 1
)
echo.
echo [OK] Release zip 在 workspace\dist\
echo   - cycling-coach-v0.7.2-source.zip
echo   - cycling-coach-v0.7.2-kb.zip
echo.
pause
exit /b 0

:build_desktop
echo.
echo [1/5] 检查环境...
where python >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Python not found
  pause
  exit /b 1
)
where node >nul 2>&1
if errorlevel 1 (
  echo [ERROR] Node.js not found
  pause
  exit /b 1
)
where pnpm >nul 2>&1
if errorlevel 1 (
  echo [WARN] pnpm not found, installing...
  npm install -g pnpm
)

echo [2/5] 后端 pyinstaller...
if not exist .venv (
  python -m venv .venv
  call .venv\Scripts\activate.bat
  pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -e .
  pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pyinstaller
) else (
  call .venv\Scripts\activate.bat
)
pyinstaller cycling_coach\backend.spec --clean --noconfirm
if errorlevel 1 (
  echo [ERROR] pyinstaller failed
  pause
  exit /b 1
)

echo [3/5] 前端 vite build...
cd apps\web
if not exist node_modules (
  pnpm install
)
pnpm run build
if errorlevel 1 (
  echo [ERROR] vite build failed
  pause
  exit /b 1
)
cd ..\..

echo [4/5] 复制 backend 到 desktop...
if not exist apps\desktop\build-resources mkdir apps\desktop\build-resources
if not exist apps\desktop\build-resources\backend mkdir apps\desktop\build-resources\backend
copy /Y dist\CyclingCoach-backend.exe apps\desktop\build-resources\backend\ >nul

echo [5/5] electron-builder...
cd apps\desktop
pnpm install
pnpm run build:win
if errorlevel 1 (
  echo [ERROR] electron-builder failed
  pause
  exit /b 1
)
cd ..\..

echo.
echo ============================================================
echo  [OK] 桌面端 Setup.exe 生成:
echo   apps\desktop\dist-electron\CyclingCoach-Setup-0.5.3-x64.exe
echo ============================================================
echo.
pause
exit /b 0
