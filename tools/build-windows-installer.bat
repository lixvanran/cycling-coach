@echo off
REM ============================================================
REM Cycling Coach - Windows 桌面端一键打包
REM 用法: tools\build-windows-installer.bat
REM
REM 流程:
REM   1. 检查环境 (Python / Node / pnpm)
REM   2. 后端: pyinstaller -> dist\CyclingCoach-backend.exe
REM   3. 前端: pnpm build -> apps\web\dist\
REM   4. 把 backend binary 复制到 apps\desktop\build-resources\backend
REM   5. electron-builder -> apps\desktop\dist-electron\CyclingCoach-Setup-x.y.z-x64.exe
REM ============================================================
setlocal enabledelayedexpansion
chcp 65001 > nul
set "PROJECT_ROOT=%~dp0.."
cd /d "%PROJECT_ROOT%"
set "PROJECT_ROOT=%CD%"

echo.
echo ============================================================
echo  Cycling Coach 桌面端打包 (Windows)
echo  项目: %PROJECT_ROOT%
echo ============================================================
echo.

REM ---- 1. 环境检查 ----
echo [1/6] 检查环境...
where python >nul 2>&1
if errorlevel 1 ( echo [X] Python 未找到 && exit /b 1 )
for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PYVER=%%v"
echo   - Python !PYVER!

where node >nul 2>&1
if errorlevel 1 ( echo [X] Node.js 未找到 && exit /b 1 )
for /f "tokens=1" %%v in ('node --version 2^>^&1') do set "NODEVER=%%v"
echo   - Node !NODEVER!

where pnpm >nul 2>&1
if errorlevel 1 ( echo [X] pnpm 未找到, 跑: npm install -g pnpm && exit /b 1 )
for /f "tokens=1" %%v in ('pnpm --version 2^>^&1') do set "PNPMVER=%%v"
echo   - pnpm !PNPMVER!

where pyinstaller >nul 2>&1
if errorlevel 1 (
  echo [!] PyInstaller 未找到, 安装中...
  pip install pyinstaller || exit /b 1
)
echo.

REM ---- 1.5 Node 依赖 (monorepo 根装) ----
echo [1.5/6] Node 依赖 (pnpm install)...
if not exist "node_modules" (
  pnpm install || exit /b 1
)
echo   - node_modules\ OK

REM ---- 2. Python 依赖 ----
echo [2/6] Python 依赖...
if not exist ".venv" (
  echo   创建 .venv ...
  python -m venv .venv || exit /b 1
)
call .venv\Scripts\activate.bat
echo   pip install ...
pip install -r requirements.txt || exit /b 1
pip install pyinstaller || exit /b 1
echo.

REM ---- 3. PyInstaller: 后端 .exe ----
echo [3/6] 打包后端 (PyInstaller)...
echo   清理 dist ...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
echo   跑 pyinstaller (大约 3-5 分钟) ...
pyinstaller apps\desktop\build\pyinstaller-backend.spec --noconfirm --clean || exit /b 1
if not exist "dist\CyclingCoach-backend-dist\CyclingCoach-backend.exe" (
  echo [X] 后端 binary 没生成
  exit /b 1
)
echo   后端 binary OK: dist\CyclingCoach-backend-dist\
echo.

REM ---- 4. 前端 build ----
echo [4/6] 构建前端 (Vite)...
cd /d "%PROJECT_ROOT%\apps\web"
if not exist "node_modules" ( pnpm install || exit /b 1 )
pnpm build || exit /b 1
if not exist "dist\index.html" ( echo [X] 前端 dist 缺失 && exit /b 1 )
echo   前端 build OK: apps\web\dist\
cd /d "%PROJECT_ROOT%"
echo.

REM ---- 5. 准备 electron-builder 资源 ----
echo [5/6] 准备 Electron 资源...
if not exist "apps\desktop\build-resources" mkdir "apps\desktop\build-resources"
if exist "apps\desktop\build-resources\backend" rmdir /s /q "apps\desktop\build-resources\backend"
mkdir "apps\desktop\build-resources\backend"
xcopy /E /I /Y "dist\CyclingCoach-backend-dist\*" "apps\desktop\build-resources\backend\" || exit /b 1
echo   - apps\desktop\build-resources\backend\ 准备完毕

REM 训练百科 (kb_source) — 首次启动解压到 %APPDATA%\CyclingCoach\kb\
if exist "kb_source" (
  echo   - kb_source/ 已就绪
) else (
  echo   [!] kb_source/ 不存在, 用户首次启动会从空 KB 开始
)

if not exist "apps\desktop\node_modules" (
  echo   apps\desktop\node_modules 缺失, 重新 pnpm install ...
  cd /d "%PROJECT_ROOT%"
  pnpm install || exit /b 1
)
echo   - apps\desktop\node_modules\ OK (symlink 指向 monorepo 根)
echo.

REM ---- 6. electron-builder ----
echo [6/6] electron-builder (NSIS)...
cd /d "%PROJECT_ROOT%\apps\desktop"
echo   跑 electron-builder (大约 2-4 分钟) ...
call npx electron-builder --win nsis --x64 || exit /b 1
cd /d "%PROJECT_ROOT%"

if not exist "apps\desktop\dist-electron\CyclingCoach-Setup-0.5.3-x64.exe" (
  echo [X] Setup.exe 没生成
  exit /b 1
)
echo.
echo ============================================================
echo  打包完成!
echo.
echo  输出: apps\desktop\dist-electron\CyclingCoach-Setup-0.5.3-x64.exe
echo  大小:
for %%A in ("apps\desktop\dist-electron\CyclingCoach-Setup-0.5.3-x64.exe") do echo    %%~zA bytes
echo ============================================================

REM 打开输出目录
explorer "apps\desktop\dist-electron\"
endlocal
