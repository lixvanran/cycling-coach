@echo off
REM ============================================================
REM Cycling Coach - 自检工具 (Windows)
REM 双击运行 / 命令行: tools\diagnose.bat
REM
REM 报告写到: %USERPROFILE%\.cycling-coach\workspace\.logs\selfcheck.txt
REM (和你的训练数据放在一起, 卸载时不会被一起删掉)
REM
REM 退出码: 0 = 没有失败项; 1 = 有失败项
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
  echo         https://www.python.org/downloads/
  pause
  exit /b 1
)

REM 自检会把完整结果打到 stdout, 同时写一份到 selfcheck.txt。
REM 之前这个脚本把 stdout 重定向成 diagnose.log 再用记事本打开那个文件,
REM 而 diagnose.py 真正写的是别处的 diagnose.txt —— 用户打开的是一行
REM "报告已写入: xxx", 排障工具本身是坏的。
python tools\diagnose.py
set RC=%errorlevel%

set "REPORT=%USERPROFILE%\.cycling-coach\workspace\.logs\selfcheck.txt"
if exist "%REPORT%" (
  echo.
  if %RC% == 0 (
    echo [OK] 自检通过, 没有发现失败项。
  ) else (
    echo [FAIL] 自检发现失败项, 上面标 [FAIL] 的就是问题。
  )
  echo.
  echo 完整报告: %REPORT%
  echo 打开它: notepad "%REPORT%"
  start "" notepad "%REPORT%"
) else (
  echo.
  echo [WARN] 没找到报告文件, 上面就是全部输出。
)

echo.
pause
exit /b %RC%
