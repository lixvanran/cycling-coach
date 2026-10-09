@echo off
REM ============================================================
REM  Cycling Coach - 明晚验收清单
REM  双击运行。每一步都会告诉你该看什么, 不需要你自己判断。
REM
REM  用法: 把整个项目解压到 C:\cc, 然后双击这个文件。
REM ============================================================
setlocal
cd /d "%~dp0\.."
set "ROOT=%CD%"
set "PYTHONUTF8=1"

echo ==========================================================
echo   Cycling Coach - ACCEPTANCE CHECKLIST
echo   目录: %ROOT%
echo ==========================================================
echo.

REM ---------------------------------------------------------
echo [1/6] Check Python
REM ---------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
  echo   [停] 没找到 Python。
  echo        去 https://www.python.org/downloads/ 装 3.11 或更高。
  echo        安装时务必勾选 "Add Python to PATH"。
  echo.
  pause
  exit /b 1
)
python -c "import sys;print('   Python', sys.version.split()[0])"
echo   [OK] Python 在。
echo.

REM ---------------------------------------------------------
echo [2/6] Install dependencies (slow on first run)
REM ---------------------------------------------------------
echo   正在装依赖, 国内网络可能需要 2-5 分钟...
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
if errorlevel 1 (
  echo   [停] 依赖安装失败。通常是网络问题。
  echo        换个网络, 或者直接重跑这个文件。
  echo.
  pause
  exit /b 1
)
echo   [OK] 依赖装好了。
echo.

REM ---------------------------------------------------------
echo [3/6] Self-check (ports / database / frontend / CJK font)
REM ---------------------------------------------------------
python tools\diagnose.py
if errorlevel 1 (
  echo.
  echo   [注意] 自检发现有失败项。上面标 [FAIL] 的就是问题,
  echo          报告在 %%USERPROFILE%%\.cycling-coach\workspace\.logs\selfcheck.txt
  echo          把那个文件发给我, 我照着修。
  echo.
  pause
  exit /b 1
)
echo   [OK] 自检通过。
echo.

REM ---------------------------------------------------------
echo [4/6] Start server
REM ---------------------------------------------------------
echo   启动后浏览器会自动打开 http://127.0.0.1:8765
echo   这个窗口要**保持打开**, 关掉窗口 = 服务停止。
echo.
start "" python tools\start.py
echo   已启动。等待 15 秒后按任意键继续检查...
timeout /t 15 >nul
pause >nul

REM ---------------------------------------------------------
echo [5/6] API connectivity
REM ---------------------------------------------------------
python -c "import urllib.request,json;r=urllib.request.urlopen('http://127.0.0.1:8765/api/pmc/today',timeout=10);d=json.load(r);print('   [OK] 后端活着。has_load_data =',d.get('has_load_data'))" 2>nul
if errorlevel 1 (
  echo   [停] 连不上后端。可能端口 8765 被别的程序占了。
  echo        换端口试: set BACKEND_PORT=8800 然后重新运行
  echo.
  pause
  exit /b 1
)
echo.
echo ==========================================================
echo   Please confirm these 5 things in your browser:
echo ==========================================================
echo.
echo   [ ] 1. Home shows BOTH "导入 FIT" and "先看示例" buttons
echo.
echo   [ ] 2. Click "先看示例" - charts and sample data should appear
echo.
echo   [ ] 3. 打开任意一条训练详情 - Find the IF row,
echo          It must NOT say "基于 FTP 250W" or similar
echo.
echo   [ ] 4. Open 数据 -> 数据可信度 - it should tell you
echo          which data exists / is missing (no confusing 0s or blanks)
echo.
echo   [ ] 5. Find a ride recorded before 8am,
echo          it should appear on THAT day, not the previous day
echo.
echo ==========================================================
echo.

REM ---------------------------------------------------------
echo [6/6] Stop server
REM ---------------------------------------------------------
echo To stop: go back to the black window, press Ctrl+C
echo.
echo When done, tell me which of the 5 checks failed.
echo If check #3 shows "FTP 250", that is our bug - send me a screenshot.
echo.
pause
