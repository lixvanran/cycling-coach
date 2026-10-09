@echo off
REM ============================================================
REM  Cycling Coach - 验收清单 (Windows)
REM  双击运行。每一步都告诉你该看什么, 不需要自己判断哪里坏了。
REM
REM  用法: 把项目解压到 C:\cc, 然后双击本文件。
REM ============================================================
setlocal
cd /d "%~dp0\.."
set "ROOT=%CD%"
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

echo ==========================================================
echo   Cycling Coach 验收清单
echo   目录: %ROOT%
echo ==========================================================
echo.

echo [1/6] 检查 Python
where python >nul 2>&1
if errorlevel 1 (
  echo   [停] 没找到 Python。
  echo        下载安装 3.11 或更高: https://www.python.org/downloads/
  echo        安装时务必勾选 "Add Python to PATH"。
  echo.
  pause
  exit /b 1
)
python -c "import sys;print('   Python', sys.version.split()[0])"
echo   [OK] Python 在。
echo.

echo [2/6] 安装依赖（第一次较慢, 请等 2-5 分钟）
python -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple --quiet
if errorlevel 1 (
  echo   [停] 依赖安装失败。通常是网络问题, 换个网络重试。
  echo.
  pause
  exit /b 1
)
echo   [OK] 依赖装好了。
echo.

echo [3/6] 自检（端口 / 数据库 / 前端文件 / 中文字体）
python tools\diagnose.py
if errorlevel 1 (
  echo.
  echo   [注意] 自检发现失败项。上面标 [FAIL] 的就是问题。
  echo          报告在 %%USERPROFILE%%\.cycling-coach\workspace\.logs\selfcheck.txt
  echo          把那个文件发给我, 我照着修。
  echo.
  pause
  exit /b 1
)
echo   [OK] 自检通过。
echo.

echo [4/6] 启动服务
echo   浏览器会自动打开 http://127.0.0.1:8765
echo   这个黑窗口要保持打开, 关掉窗口 = 服务停止。
echo.
echo   启动中... 15 秒后自动继续检查。
start "" python tools\start.py --desktop
timeout /t 15 >nul

echo [5/6] 接口连通性检查
python -c "import urllib.request,json;r=urllib.request.urlopen('http://127.0.0.1:8765/api/pmc/today',timeout=10);d=json.load(r);print('   [OK] 后端活着。has_load_data =',d.get('has_load_data'))" 2>nul
if errorlevel 1 (
  echo   [停] 连不上后端。可能是端口 8765 被别的程序占用。
  echo.
  pause
  exit /b 1
)
echo.
echo ==========================================================
echo   浏览器里请确认这 5 件事
echo ==========================================================
echo.
echo   1. 首页同时有「导入 FIT」和「先看示例」两个按钮
echo.
echo   2. 点「先看示例」后, 页面出现图表和训练数据
echo.
echo   3. 打开任意一条训练详情, 找 IF 那一行
echo      不应该出现 "基于 FTP 250W" 之类的字样
echo.
echo   4. 打开「数据 -> 数据可信度」
echo      页面应明确说明哪些数据有、哪些缺
echo
echo   5. 找一条早上 8 点前记录的训练
echo      它应出现在当天, 不是前一天
echo.
echo ==========================================================
echo.
echo [6/6] 停止服务
echo   回到刚才那个黑窗口, 按 Ctrl+C 停止。
echo.
echo 测完告诉我这 5 项里哪几个没过。
echo 如果第 3 项看到 "FTP 250", 那是我们的 bug, 截图发我。
echo.
pause
