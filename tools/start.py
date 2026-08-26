#!/usr/bin/env python3
"""Cycling Coach 一键启动器(跨平台)

参考 Photographer-Copilot/start.py 风格:
- 自动装 venv / 镜像源
- 跨平台 shim(避免 Windows .cmd 找不到)
- 端口兜底
- stdout 直接继承给用户
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

# 关键:Windows 上 Python 默认 cp936(GBK)解码子进程 stdout
# Vite / pnpm / Node 经常输出非 GBK 字节,会直接挂掉
# 这里强制用 UTF-8 + 容错(避免 v0.1.0 的 "GBK decode 错误" 故障)
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    os.environ.setdefault("PYTHONUTF8", "1")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

ROOT = Path(__file__).parent.parent.resolve()
BACKEND_PKG = "cycling_coach.api"
FRONTEND_DIR = ROOT / "apps" / "web"
WORKSPACE_DIR = ROOT / "workspace"
LOG_DIR = WORKSPACE_DIR / ".logs"
PORT_FILE = WORKSPACE_DIR / ".sidecar-port"
PID_FILE = WORKSPACE_DIR / ".sidecar.pid"

BACKEND_PORT = int(os.environ.get("BACKEND_PORT", "8765"))
FRONTEND_PORT = int(os.environ.get("FRONTEND_PORT", "1420"))


# ---------- 工具 ----------

# Windows ANSI 颜色检测:cmd.exe 默认不识别,Windows Terminal / PowerShell 5.1+ 支持
# 通过环境变量 + 探针判断
def _detect_color_support() -> bool:
    if sys.platform == "win32":
        # Windows Terminal / VS Code / 现代 PowerShell 都设了这些变量
        if os.environ.get("WT_SESSION") or os.environ.get("TERM_PROGRAM"):
            return True
        # cmd.exe 的现代版本支持 ANSI(win10 1607+),但默认关闭,通过 ENABLE_VIRTUAL_TERMINAL_PROCESSING 开启
        # 这里保险起见只在已知终端开启
        return False
    return True  # macOS / Linux 默认有


_USE_COLOR = _detect_color_support()

color_map = {
    "info": "\033[36m",     # cyan
    "ok": "\033[32m",       # green
    "warn": "\033[33m",     # yellow
    "err": "\033[31m",      # red
    "hint": "\033[35m",     # magenta
    "dim": "\033[90m",      # gray
    "bold": "\033[1m",
    "reset": "\033[0m",
}
level_tag = {
    "info": "●",
    "ok": "✓",
    "warn": "▲",
    "err": "✗",
    "hint": "→",
}


# 简单 spinner(后台任务时显示)
class Spinner:
    """上下文管理器:长时间操作时显示动画"""

    FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"

    def __init__(self, msg: str):
        self.msg = msg
        self._thread = None
        self._stop = False

    def _run(self):
        i = 0
        while not self._stop:
            frame = self.FRAMES[i % len(self.FRAMES)]
            sys.stdout.write(f"\r\033[36m  {frame}\033[0m {self.msg}")
            sys.stdout.flush()
            i += 1
            time.sleep(0.08)
        # 清除 spinner 行
        sys.stdout.write("\r" + " " * (len(self.msg) + 6) + "\r")
        sys.stdout.flush()

    def __enter__(self):
        if _USE_COLOR:
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()
        else:
            sys.stdout.write(f"  ... {self.msg}\n")
            sys.stdout.flush()
        return self

    def __exit__(self, *args):
        self._stop = True
        if self._thread:
            self._thread.join(timeout=0.5)


def banner() -> None:
    """启动横幅"""
    art = r"""
  ╔══════════════════════════════════════╗
  ║     🚴  Cycling Coach  v0.5.0        ║
  ║     AI 教练 · 训练管理 · 数据驱动    ║
  ╚══════════════════════════════════════╝
"""
    if _USE_COLOR:
        # 渐变:绿→青
        print(f"\033[1m\033[36m{art}\033[0m")
    else:
        print(art)


def phase(num: int, total: int, title: str) -> None:
    """阶段标识:PHASE 1/4 · 标题"""
    if _USE_COLOR:
        bar = f"\033[1m\033[36m[PHASE {num}/{total}]\033[0m"
        line = f"\033[1m{title}\033[0m"
    else:
        bar = f"[PHASE {num}/{total}]"
        line = title
    print()
    print(f"  {bar}  {line}")
    print(f"  {'─' * 50}")


def divider() -> None:
    """分隔线"""
    if _USE_COLOR:
        print(f"  \033[90m{'─' * 50}\033[0m")
    else:
        print(f"  {'─' * 50}")


def log(msg: str, level: str = "info") -> None:
    """统一日志输出(带颜色 / icon)"""
    icon = level_tag.get(level, "·")
    if _USE_COLOR:
        c = color_map.get(level, "")
        r = color_map["reset"] if c else ""
        prefix = f"  {c}{icon}{r}"
    else:
        prefix = f"  [{level_tag.get(level, level)}]"
    print(f"{prefix} {msg}", flush=True)


def success(msg: str) -> None:
    log(msg, "ok")


def warn(msg: str) -> None:
    log(msg, "warn")


def info(msg: str) -> None:
    log(msg, "info")


def error(msg: str) -> None:
    log(msg, "err")


def ready_banner(backend_url: str, frontend_url: str) -> None:
    """就绪横幅"""
    if _USE_COLOR:
        box = (
            f"\033[1m\033[32m"
            f"  ╔══════════════════════════════════════╗\n"
            f"  ║         ✨  应用已就绪               ║\n"
            f"  ╚══════════════════════════════════════╝\033[0m"
        )
        print()
        print(box)
        print()
        print(f"  \033[1m前端 UI\033[0m  \033[36m{frontend_url}\033[0m")
        print(f"  \033[1m后端 API\033[0m  \033[36m{backend_url}\033[0m")
        print()
        print(f"  \033[90m按 Ctrl+C 停止\033[0m")
    else:
        print()
        print("  ╔══════════════════════════════════════╗")
        print("  ║         应用已就绪                    ║")
        print("  ╚══════════════════════════════════════╝")
        print()
        print(f"  前端 UI  {frontend_url}")
        print(f"  后端 API  {backend_url}")
        print()
        print("  按 Ctrl+C 停止")


def _wrap_windows_cmd(cmd: list[str]) -> list[str]:
    """Windows: 如果第一个是 .cmd/.bat, 包装成 ['cmd', '/c', 原 cmd...]

    CreateProcessW 不能直接执行 .cmd/.bat(需要 cmd.exe 解释)
    但用 ['cmd', '/c', path, ...args] 形式 + subprocess shell=False,
    Python 内部会用正确转义(走 list2cmdline 给我们处理),不破坏引号。
    """
    if sys.platform != "win32":
        return cmd
    if not cmd:
        return cmd
    first = cmd[0]
    if first.lower().endswith((".cmd", ".bat")):
        return ["cmd", "/c", *cmd]
    return cmd


def run(cmd: list[str], cwd: Path | None = None, env: dict | None = None,
        check: bool = True, capture: bool = False,
        tolerate_exit_codes: tuple[int, ...] = ()) -> subprocess.CompletedProcess:
    """执行命令(带日志)

    V0.3.3 关键修复:Windows 下不再用 `cmd /c 字符串` 模式
    (原版在路径含空格时会触发 [WinError 123] —— cmd 解释器把 cwd
    的绝对路径错误地拼到了引号外,变成 "...G\\cycling-coach\\"D:" 这种畸形)

    新策略:
    1. Windows 下用 subprocess.run(cmd, shell=False, cwd=cwd)
    2. 如果第一个是 .cmd/.bat(典型:pnpm.CMD, npm.CMD),自动包成 ['cmd', '/c', ...]
    3. Python 内部用 list2cmdline 处理引号,正确支持路径含空格
    """
    cwd_str = str(cwd) if cwd else None
    log(f"$ {' '.join(cmd)}" + (f"  (cwd={cwd_str})" if cwd_str else ""))

    if sys.platform == "win32":
        wrapped = _wrap_windows_cmd(cmd)
        return subprocess.run(
            wrapped, shell=False, cwd=cwd_str, env=env, check=check,
            capture_output=capture, text=True,
        )

    # 非 Windows: 原始 list 方式
    return subprocess.run(
        cmd, cwd=cwd_str, env=env, check=check,
        capture_output=capture, text=True,
    )


def run_pnpm_install(pnpm_args: list[str], cwd: Path, env: dict) -> bool:
    """跑 pnpm install 并对 [ERR_PNPM_IGNORED_BUILDS] 软失败做容忍

    pnpm 9-11 在白名单已生效时,仍可能输出:
        [ERR_PNPM_IGNORED_BUILDS] Ignored build scripts: esbuild@...
    并返回 exit 1。只要 esbuild binary 真的安装好了,我们就认为成功。
    """
    try:
        run(pnpm_args, cwd=cwd, env=env)
        return True
    except subprocess.CalledProcessError as e:
        # 软失败:exit 1 但实际已安装好
        log(f"  pnpm 退出码 {e.returncode},检查关键 binary 是否到位...", "warn")
        return False


# ---------- 环境检查 ----------

# 找 Python 解释器(优先 stdlib 别名,其次 PATH,最后常见安装路径)
_PY_CANDIDATE_NAMES = ["python3", "python", "python3.11", "python3.12", "python3.13"]

# Windows 常见 Python 安装路径(微软 Store stub 路径会被过滤)
_WIN_PY_COMMON_PATHS = [
    r"C:\Python313\python.exe",
    r"C:\Python312\python.exe",
    r"C:\Python311\python.exe",
    r"C:\Python310\python.exe",
    Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python313" / "python.exe",
    Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python312" / "python.exe",
    Path.home() / "AppData" / "Local" / "Programs" / "Python" / "Python311" / "python.exe",
]

# macOS/Linux 常见安装路径
_UNIX_PY_COMMON_PATHS = [
    "/opt/homebrew/bin/python3",
    "/usr/local/bin/python3",
    "/usr/bin/python3",
    "/usr/bin/python3.11",
    "/usr/bin/python3.12",
    "/usr/bin/python3.13",
]


def _is_real_python(p: str) -> bool:
    """是真 Python(不是 MS Store stub)"""
    if not p or not os.path.isabs(p):
        return False
    if sys.platform == "win32" and "WindowsApps" in p:
        return False
    if not Path(p).exists():
        return False
    try:
        out = subprocess.run(
            [p, "--version"], capture_output=True, text=True, timeout=5
        )
        ver = (out.stdout + out.stderr).strip()
        return bool(ver) and ver.startswith("Python ")
    except Exception:
        return False


def check_python() -> str:
    """找 Python 解释器

    找不到时:**自动装**(不妥协原则),策略:
      - Windows: winget → 微软商店 CLI → 失败则让用户手动装
      - macOS:   brew → 失败则让用户手动装
      - Linux:   apt / dnf / yum → 失败则让用户手动装
    """
    # 1. PATH 里的候选
    candidates: list[str] = []
    for name in _PY_CANDIDATE_NAMES:
        p = shutil.which(name)
        if p and _is_real_python(p):
            candidates.append(p)

    # 2. 常见安装路径兜底
    common = _WIN_PY_COMMON_PATHS if sys.platform == "win32" else _UNIX_PY_COMMON_PATHS
    for p in common:
        p_str = str(p)
        if p_str not in candidates and _is_real_python(p_str):
            candidates.append(p_str)

    if not candidates:
        log("Python 3.11+ 未找到,自动安装...", "warn")
        installed = _auto_install_python()
        if not installed:
            log("自动安装失败,请手动装 Python 3.11+", "err")
            log("下载:https://www.python.org/downloads/", "hint")
            log("安装时务必勾选 'Add Python to PATH'", "hint")
            sys.exit(1)
        # 重试
        for name in _PY_CANDIDATE_NAMES:
            p = shutil.which(name)
            if p and _is_real_python(p) and p not in candidates:
                candidates.append(p)
        for p in common:
            p_str = str(p)
            if p_str not in candidates and _is_real_python(p_str):
                candidates.append(p_str)
        if not candidates:
            log("Python 安装完成但 PATH 未刷新,请重启终端后再试", "err")
            log("或手动执行: python --version 确认", "hint")
            sys.exit(1)

    py = candidates[0]
    out = subprocess.run([py, "--version"], capture_output=True, text=True, timeout=5)
    log(f"Python: {(out.stdout or out.stderr).strip()} ({py})", "ok")
    return py


def _auto_install_python() -> bool:
    """自动装 Python(跨平台)

    Returns: True 装好, False 失败
    """
    system = platform.system()
    try:
        if system == "Windows":
            # 优先 winget(Win10 1809+ 内置,几乎所有现代 Win 都有)
            winget = shutil.which("winget")
            if winget:
                log("  尝试 winget install Python.Python.3.13 ...", "info")
                r = subprocess.run(
                    [winget, "install", "-e", "--id", "Python.Python.3.13",
                     "--source", "winget", "--accept-package-agreements",
                     "--accept-source-agreements"],
                    capture_output=True, text=True, timeout=600,
                )
                if r.returncode == 0:
                    log("  ✓ Python 3.13 安装完成", "ok")
                    return True
                log(f"  winget 失败(退出码 {r.returncode}),尝试备用方案", "warn")
            # 兜底:用微软官方 embeddable zip
            log("  提示:可手动从 https://www.python.org/downloads/ 下载安装", "hint")
            log("  安装时务必勾选 'Add Python to PATH'", "hint")
            return False

        elif system == "Darwin":
            brew = shutil.which("brew")
            if brew:
                log("  尝试 brew install python@3.13 ...", "info")
                r = subprocess.run(
                    [brew, "install", "python@3.13"],
                    capture_output=True, text=True, timeout=900,
                )
                if r.returncode == 0:
                    log("  ✓ Python 3.13 安装完成", "ok")
                    return True
                log(f"  brew 失败(退出码 {r.returncode})", "warn")
            return False

        else:  # Linux
            # root 运行时不需要 sudo
            is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
            sudo_prefix = [] if is_root else (
                ["sudo"] if shutil.which("sudo") else []
            )
            if not is_root and not sudo_prefix:
                log("  非 root 且无 sudo,无法自动装 Python", "warn")
                return False
            for cmd in (["apt-get", "install", "-y", "python3.11"],
                        ["dnf", "install", "-y", "python3.11"],
                        ["yum", "install", "-y", "python3.11"]):
                if shutil.which(cmd[0]):
                    log(f"  尝试 {' '.join(sudo_prefix + cmd)} ...", "info")
                    r = subprocess.run(
                        sudo_prefix + cmd, capture_output=True, text=True, timeout=900,
                    )
                    if r.returncode == 0:
                        log("  ✓ Python 3.11 安装完成", "ok")
                        return True
                    log(f"  {cmd[0]} 失败(退出码 {r.returncode})", "warn")
            return False
    except subprocess.TimeoutExpired:
        log("  自动安装超时(可能需要交互),请手动安装", "err")
        return False
    except Exception as e:
        log(f"  自动安装异常: {e}", "err")
        return False


def _auto_install_node() -> bool:
    """自动装 Node.js(跨平台)"""
    system = platform.system()
    try:
        if system == "Windows":
            winget = shutil.which("winget")
            if winget:
                log("  尝试 winget install OpenJS.NodeJS.LTS ...", "info")
                r = subprocess.run(
                    [winget, "install", "-e", "--id", "OpenJS.NodeJS.LTS",
                     "--source", "winget", "--accept-package-agreements",
                     "--accept-source-agreements"],
                    capture_output=True, text=True, timeout=900,
                )
                if r.returncode == 0:
                    log("  ✓ Node.js LTS 安装完成", "ok")
                    return True
                log(f"  winget 失败(退出码 {r.returncode})", "warn")
            return False
        elif system == "Darwin":
            brew = shutil.which("brew")
            if brew:
                log("  尝试 brew install node ...", "info")
                r = subprocess.run(
                    [brew, "install", "node"],
                    capture_output=True, text=True, timeout=900,
                )
                if r.returncode == 0:
                    return True
            return False
        else:  # Linux
            is_root = (os.geteuid() == 0) if hasattr(os, "geteuid") else False
            sudo_prefix = [] if is_root else (
                ["sudo"] if shutil.which("sudo") else []
            )
            if not is_root and not sudo_prefix:
                return False
            for cmd in (["apt-get", "install", "-y", "nodejs", "npm"],
                        ["dnf", "install", "-y", "nodejs", "npm"]):
                if shutil.which(cmd[0]):
                    log(f"  尝试 {' '.join(sudo_prefix + cmd)} ...", "info")
                    r = subprocess.run(
                        sudo_prefix + cmd, capture_output=True, text=True, timeout=900,
                    )
                    if r.returncode == 0:
                        return True
            return False
    except Exception as e:
        log(f"  自动安装 Node 异常: {e}", "err")
        return False


def check_node() -> str | None:
    """检测 Node.js + npm;缺失则自动装(不妥协原则)"""
    node = shutil.which("node")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if node and npm:
        out = subprocess.run([node, "--version"], capture_output=True, text=True)
        log(f"Node: {out.stdout.strip()}", "ok")
        return npm
    log("Node.js 未找到,自动安装...", "warn")
    if not _auto_install_node():
        log("Node.js 自动安装失败", "err")
        log("请手动装 Node.js 20+:https://nodejs.org/", "hint")
        return None
    # 重新检测
    node = shutil.which("node")
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not node or not npm:
        log("Node.js 安装完成但 PATH 未刷新,请重启终端", "err")
        return None
    out = subprocess.run([node, "--version"], capture_output=True, text=True)
    log(f"Node: {out.stdout.strip()} (新装)", "ok")
    return npm


def ensure_pnpm(npm: str) -> str | None:
    """确保 pnpm 可用;缺失则自动装(不妥协原则)"""
    pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    if pnpm:
        log("pnpm: 已安装", "ok")
        return pnpm
    if not npm:
        log("pnpm 未安装,但 npm 也缺失,跳过前端", "err")
        return None
    log("pnpm 未安装,自动安装...", "info")
    r = subprocess.run(
        [npm, "install", "-g", "pnpm", "--registry=https://registry.npmmirror.com"],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        log(f"pnpm 安装失败: {r.stderr[:200]}", "err")
        return None
    pnpm = shutil.which("pnpm") or shutil.which("pnpm.cmd")
    if not pnpm:
        log("pnpm 安装完成但 PATH 未刷新", "err")
        return None
    log("pnpm 安装完成", "ok")
    return pnpm


# ---------- 依赖安装 ----------

def ensure_venv(py: str) -> Path:
    """创建/复用 .venv,返回 python 解释器路径

    V0.3.3 修复:cd=ROOT + 相对路径 ".venv",避开路径含空格时的 [WinError 123]
    """
    venv = ROOT / ".venv"
    if platform.system() == "Windows":
        py_bin = venv / "Scripts" / "python.exe"
    else:
        py_bin = venv / "bin" / "python"
    if not py_bin.exists():
        log("创建 Python 虚拟环境 .venv ...", "info")
        # 用相对路径 + cwd=ROOT,而不是 str(venv) 含空格的绝对路径
        run([py, "-m", "venv", ".venv"], cwd=ROOT)
    return py_bin


def install_backend(py_bin: Path) -> None:
    """V0.3.3 修复:用相对路径 "requirements.txt" 避免路径含空格问题"""
    info("安装后端依赖 (FastAPI / uvicorn / pydantic / fitparse / numpy / pandas / scipy ...)...")
    env = os.environ.copy()
    env["PIP_INDEX_URL"] = "https://pypi.tuna.tsinghua.edu.cn/simple"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    # 用相对路径, cwd=ROOT(没有空格污染)
    run([str(py_bin), "-m", "pip", "install", "--upgrade", "pip"], cwd=ROOT, env=env)
    run([str(py_bin), "-m", "pip", "install", "-r", "requirements.txt"], cwd=ROOT, env=env)
    success("后端依赖安装完成")


def _esbuild_ready() -> bool:
    """校验 esbuild 真实可用(pnpm workspace 模式)

    关键洞察:esbuild 是 vite 的间接依赖,在 pnpm workspace 模式下
    不会 hoist 到 apps/web/node_modules/.bin/。
    实际位置: workspace 根 node_modules/.pnpm/esbuild@*/node_modules/esbuild/bin/esbuild
    """
    # 1. 在 workspace 根的 .pnpm 找
    pnpm_dir = ROOT / "node_modules" / ".pnpm"
    if pnpm_dir.exists():
        for entry in pnpm_dir.iterdir():
            if entry.name.startswith("esbuild@"):
                # esbuild 自己(JS wrapper)
                esbuild = entry / "node_modules" / "esbuild" / "bin" / "esbuild"
                if esbuild.exists():
                    # 同时检查 platform binary(@esbuild/linux-x64 或 windows-64)
                    for plat in entry.iterdir():
                        if plat.name.startswith("@esbuild") and "linux" in plat.name.lower() or "windows" in plat.name.lower() or "darwin" in plat.name.lower():
                            plat_bin = plat / "node_modules"
                            if plat_bin.exists():
                                return True
                    # 即便没找到 platform binary,JS wrapper 存在也算(vite 会用 node 跑)
                    return True
    # 2. 兼容:npm 模式 esbuild 直接在 apps/web/node_modules
    legacy = FRONTEND_DIR / "node_modules" / "esbuild" / "bin" / "esbuild"
    if legacy.exists():
        return True
    return False


def _frontend_node_modules_ready() -> bool:
    """前端 node_modules 整体可用性(vite 必须能跑)"""
    vite_bin = (
        FRONTEND_DIR / "node_modules" / ".bin" /
        ("vite.cmd" if platform.system() == "Windows" else "vite")
    )
    return vite_bin.exists()


def _clear_frontend_modules() -> None:
    """强制清空前端的 node_modules(含 workspace 根 + 虚拟 store 配置)"""
    targets = [FRONTEND_DIR / "node_modules", ROOT / "node_modules"]
    for target in targets:
        if not target.exists():
            continue
        try:
            if sys.platform == "win32":
                subprocess.run(
                    ["cmd", "/c", "rmdir", "/s", "/q", str(target)],
                    capture_output=True, text=True, timeout=60,
                )
            else:
                shutil.rmtree(target, ignore_errors=True)
            success(f"已清空: {target.relative_to(ROOT)}")
        except Exception as e:
            warn(f"清空 {target} 失败: {e}")


def install_frontend(pnpm: str) -> None:
    """安装前端依赖

    策略:
      - 全部就绪:跳过
      - 首次(都没装):直接 install(干净环境无需清空)
      - 半装(node_modules 存在但 esbuild 缺失):清空重装 + --force
        (这种情况是 ERR_PNPM_VIRTUAL_STORE_DIR_MAX_LENGTH_DIFF 等)
    """
    env = os.environ.copy()
    env["npm_config_registry"] = "https://registry.npmmirror.com"

    # 校验 1:全好 → 跳过
    if _frontend_node_modules_ready() and _esbuild_ready():
        success("前端依赖已就绪,跳过")
        return

    apps_nm_exists = (FRONTEND_DIR / "node_modules").exists()
    root_nm_exists = (ROOT / "node_modules").exists()

    # 校验 2:半装(node_modules 存在但 esbuild 缺失)→ 清空 + 重装
    if (apps_nm_exists or root_nm_exists) and not _esbuild_ready():
        warn("检测到半装状态(可能是旧版 pnpm store 配置残留),清空重装...")
        _clear_frontend_modules()
        force = True
    else:
        # 全新环境:直接 install
        force = False
        info("首次安装前端依赖 (React 18 + Vite 5 + Recharts + Tailwind)...")

    pnpm_args = [
        pnpm, "install",
        "--filter", "cycling-coach-frontend...",
        "--config.confirmModulesPurge=false",
    ]
    if force:
        pnpm_args.append("--force")
    run_pnpm_install(pnpm_args, cwd=ROOT, env=env)

    # 校验 3:install 后还不行 → 二次清空 + --force 重装
    if not _esbuild_ready() or not _frontend_node_modules_ready():
        warn("install 后仍不齐,二次清空 + --force 重装...")
        _clear_frontend_modules()
        run_pnpm_install(
            [pnpm, "install",
             "--config.confirmModulesPurge=false",
             "--force"],
            cwd=ROOT, env=env,
        )

    # 最终校验
    if not _frontend_node_modules_ready():
        raise RuntimeError(
            f"前端 node_modules 仍未就绪({FRONTEND_DIR / 'node_modules'});"
            "请检查 pnpm install 输出"
        )
    if not _esbuild_ready():
        raise RuntimeError(
            f"esbuild 二进制仍未生成(workspace 根 node_modules/.pnpm/ 下没有 esbuild@*),"
            "请手动执行:\n"
            f"  cd {FRONTEND_DIR}\n"
            f"  {pnpm} install --force\n"
            f"  {pnpm} rebuild esbuild"
        )
    success("前端依赖安装完成")


# ---------- 端口清理 ----------

def kill_port(port: int) -> None:
    """兜底杀掉占用端口的进程"""
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.run(
                ["netstat", "-ano"], capture_output=True, text=True
            ).stdout
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    parts = line.split()
                    pid = parts[-1]
                    log(f"释放端口 {port}: kill PID {pid}", "warn")
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        else:
            # macOS / Linux
            out = subprocess.run(
                ["lsof", "-ti", f":{port}"], capture_output=True, text=True
            ).stdout.strip()
            for pid in out.splitlines():
                if pid:
                    log(f"释放端口 {port}: kill PID {pid}", "warn")
                    subprocess.run(["kill", "-9", pid], capture_output=True)
    except Exception as e:
        log(f"端口清理失败(可忽略): {e}", "warn")


# ---------- 启动 ----------

def start_backend(py_bin: Path) -> subprocess.Popen:
    log(f"启动后端 Sidecar(端口 {BACKEND_PORT})...", "info")
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    # 以 cycling_coach.api.main:app 启动,让 backend 作为包被加载,相对导入才能用
    proc = subprocess.Popen(
        [str(py_bin), "-m", "uvicorn", "cycling_coach.api.main:app",
         "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=ROOT, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1, encoding="utf-8", errors="replace",
    )
    # 写 PID + 端口(给前端用)
    PID_FILE.write_text(str(proc.pid))
    PORT_FILE.write_text(str(BACKEND_PORT))
    return proc


def start_frontend(pnpm: str) -> subprocess.Popen | None:
    """启动 Vite(直接调 node_modules/.bin/vite,避免 pnpm + 中文路径的兼容问题)"""
    # 找 node_modules/.bin/vite
    vite_bin = FRONTEND_DIR / "node_modules" / ".bin" / "vite"
    if platform.system() == "Windows":
        vite_bin = vite_bin.with_suffix(".cmd")

    if not vite_bin.exists():
        warn(f"找不到 {vite_bin},回退到 pnpm dev")
        vite_bin = Path(pnpm)
        if platform.system() == "Windows" and not str(vite_bin).endswith(".cmd"):
            vite_bin = vite_bin.with_suffix(".cmd")
        use_shell = True
        cmd = [str(vite_bin), "dev", "--port", str(FRONTEND_PORT), "--strictPort"]
    else:
        use_shell = False
        cmd = [str(vite_bin), "--port", str(FRONTEND_PORT), "--strictPort", "--host", "127.0.0.1"]

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env["FORCE_COLOR"] = "0"  # 避免 ANSI 颜色码让 stream reader 解析错

    try:
        proc = subprocess.Popen(
            cmd,
            cwd=FRONTEND_DIR, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, bufsize=1, shell=use_shell,
            encoding="utf-8", errors="replace",
        )
    except Exception as e:
        error(f"Vite 启动失败: {e}")
        return None
    return proc


def stream_output(proc: subprocess.Popen, prefix: str) -> None:
    """持续打印子进程输出(在独立线程里)

    关键:任何 IO 异常都不能让主线程误判进程退出
    """
    import threading
    # 子进程 tag 颜色
    if _USE_COLOR:
        tag_colors = {
            "backend": "\033[34m",   # 蓝
            "frontend": "\033[35m",  # 紫
        }
        tag_color = tag_colors.get(prefix.lower(), color_map["dim"])
        reset = color_map["reset"]
    else:
        tag_color = ""
        reset = ""

    def _reader():
        try:
            for line in iter(proc.stdout.readline, ""):
                if not line:
                    break
                # 处理一行可能有 BOM 或 \r
                line = line.replace("\r\n", "\n").rstrip("\n").rstrip("\r")
                if line:
                    # 关键行(info / warn / error)高亮
                    lower = line.lower()
                    if "error" in lower or "exception" in lower or "traceback" in lower:
                        line_prefix = f"{color_map['err']}✗{reset}" if _USE_COLOR else "[ERR]"
                    elif "warning" in lower or "warn" in lower:
                        line_prefix = f"{color_map['warn']}▲{reset}" if _USE_COLOR else "[WARN]"
                    else:
                        line_prefix = f"{tag_color}│{reset}" if _USE_COLOR else "│"
                    print(f"    {line_prefix} {tag_color}[{prefix}]{reset} {line}", flush=True)
        except (ValueError, OSError):
            pass
        except Exception as e:
            try:
                print(f"    [{prefix}] output reader error: {e}", flush=True)
            except Exception:
                pass
    t = threading.Thread(target=_reader, daemon=True)
    t.start()


# ---------- main ----------

def main() -> int:
    parser = argparse.ArgumentParser(description="Cycling Coach 一键启动")
    parser.add_argument("--check", action="store_true", help="只检查环境")
    parser.add_argument("--install", action="store_true", help="只装依赖")
    parser.add_argument("--no-frontend", action="store_true", help="不启动前端 (Vite)")
    parser.add_argument("--desktop", action="store_true", help="桌面模式: 后端 serve 静态前端,不开 Vite,直接访问 8765")
    args = parser.parse_args()

    banner()

    # ===== PHASE 1/4: 环境检查 =====
    phase(1, 4, "环境检查")
    py = check_python()
    npm = check_node()
    pnpm = ensure_pnpm(npm) if npm else None

    if args.check:
        success("环境检查完成")
        return 0

    # ===== PHASE 2/4: 依赖安装 =====
    phase(2, 4, "依赖安装")
    WORKSPACE_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    try:
        with Spinner("创建 Python 虚拟环境 .venv ..."):
            py_bin = ensure_venv(py)
        success(f"虚拟环境就绪: {py_bin}")
        install_backend(py_bin)
    except Exception as e:
        error(f"后端依赖安装失败: {e}")
        info("可手动执行: cd 项目根 && .venv/bin/pip install -r requirements.txt")
        return 1

    if pnpm and not args.desktop:
        try:
            install_frontend(pnpm)
        except Exception as e:
            error(f"前端依赖安装失败: {e}")
            info("可手动执行: cd apps/web && pnpm install")
            log_file = ROOT / "workspace" / ".logs" / "start.py.log"
            if log_file.exists():
                error("--- 启动器日志最后 20 行 ---")
                try:
                    lines = log_file.read_text(encoding="utf-8", errors="replace").splitlines()
                    for ln in lines[-20:]:
                        print(f"    {ln}", flush=True)
                except Exception as ee:
                    error(f"读日志失败: {ee}")
            return 1
    elif args.desktop:
        # 桌面模式不需要前端 dev 依赖, 只要 build 产物在 apps/web/dist
        # 注意: 我们不调用 pnpm/vite (需要联网), 直接要求 build 产物已存在
        success("桌面模式: 跳过前端 dev 依赖安装 (只需 build 产物)")
        frontend_dist = FRONTEND_DIR / "dist"
        if not (frontend_dist / "index.html").exists():
            error("桌面模式需要 apps/web/dist (前端 build 产物), 但不存在")
            info("解决办法 (二选一):")
            info("  1) 在开发机器上跑: cd apps/web && pnpm install && pnpm exec vite build")
            info("  2) 用 dev 模式: python tools/start.py (不用 --desktop)")
            return 1

    if args.install:
        success("依赖安装完成")
        return 0

    # ===== PHASE 3/4: 端口清理 =====
    phase(3, 4, "端口清理")
    kill_port(BACKEND_PORT)
    if pnpm:
        kill_port(FRONTEND_PORT)
    success(f"端口 {BACKEND_PORT} + {FRONTEND_PORT} 准备就绪")

    # ===== PHASE 4/4: 启动 =====
    phase(4, 4, "启动服务")
    try:
        # 桌面模式: 后端 serve 前端 (lifespan mount 静态),用户开浏览器访问 8765
        if args.desktop:
            # 校验前端已 build
            frontend_dist = FRONTEND_DIR / "dist"
            if not (frontend_dist / "index.html").exists():
                warn("桌面模式需要前端 build 产物, 但 apps/web/dist 不存在")
                info("先跑前端 build: cd apps/web && pnpm exec vite build")
                info("  或: python tools/start.py --install (会自动 build)")
                return 1
            os.environ["STATIC_DIR"] = str(frontend_dist)
            os.environ["IS_DESKTOP"] = "true"
            # 走用户文档目录 (跟 Electron 桌面版一致)
            desktop_workspace = Path.home() / ".cycling-coach" / "workspace"
            desktop_workspace.mkdir(parents=True, exist_ok=True)
            os.environ["WORKSPACE_DIR"] = str(desktop_workspace)
            os.environ.setdefault("KB_DOWNLOAD_URL", "")  # 桌面模式走内嵌 KB
            success(f"桌面模式: 后端将 serve 前端  (workspace={desktop_workspace})")

        with Spinner("启动后端 uvicorn ..."):
            backend_proc = start_backend(py_bin)
            time.sleep(1)
        success(f"后端就绪  (PID {backend_proc.pid})  →  http://127.0.0.1:{BACKEND_PORT}")
        stream_output(backend_proc, "backend")

        frontend_proc = None
        if pnpm and not args.no_frontend and not args.desktop:
            # 最终兜底:启动前端前再校验,缺失就清空重装
            if not _esbuild_ready() or not _frontend_node_modules_ready():
                warn("启动前端前发现依赖不齐,清空重装...")
                _clear_frontend_modules()
                try:
                    run(
                        [pnpm, "install",
                         "--filter", "cycling-coach-frontend...",
                         "--config.confirmModulesPurge=false",
                         "--force"],
                        cwd=ROOT, env=os.environ.copy(),
                    )
                except Exception as e:
                    warn(f"  install 失败: {e}")
                if not _esbuild_ready():
                    error("esbuild 仍未到位,前端可能无法启动")
            with Spinner("启动前端 Vite ..."):
                frontend_proc = start_frontend(pnpm)
                time.sleep(1)
            if frontend_proc:
                success(f"前端就绪  (PID {frontend_proc.pid})  →  http://localhost:{FRONTEND_PORT}")
                stream_output(frontend_proc, "frontend")

        ready_banner(
            backend_url=f"http://127.0.0.1:{BACKEND_PORT}",
            frontend_url=(f"http://127.0.0.1:{BACKEND_PORT}" if args.desktop else f"http://localhost:{FRONTEND_PORT}"),
        )

        # 阻塞,直到任一进程退出
        try:
            while True:
                time.sleep(1)
                if backend_proc.poll() is not None:
                    rc = backend_proc.poll()
                    error(f"后端进程退出 (exit code {rc})")
                    info("查看 workspace/.logs/sidecar.log 获取详细错误")
                    break
                if frontend_proc and frontend_proc.poll() is not None:
                    rc = frontend_proc.poll()
                    error(f"前端进程退出 (exit code {rc})")
                    info("尝试手动启动:cd apps/web && node_modules/.bin/vite --port 1420")
                    break
        except KeyboardInterrupt:
            info("正在停止...")
            for p in [backend_proc, frontend_proc]:
                if p and p.poll() is None:
                    p.terminate()
    except Exception as e:
        error(f"启动失败: {e}")
        return 1
    finally:
        if sys.platform == "win32" and sys.stdin.isatty():
            try:
                input("按 Enter 退出...")
            except EOFError:
                pass

    return 0


if __name__ == "__main__":
    sys.exit(main())
