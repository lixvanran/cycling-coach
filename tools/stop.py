#!/usr/bin/env python3
"""停止 Cycling Coach 后端 + 前端"""
from __future__ import annotations
import os
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
WORKSPACE_DIR = ROOT / "workspace"
PID_FILE = WORKSPACE_DIR / ".sidecar.pid"
PORT_BACKEND = int(os.environ.get("BACKEND_PORT", "8765"))
PORT_FRONTEND = int(os.environ.get("FRONTEND_PORT", "1420"))


def log(msg: str, level: str = "info") -> None:
    # Windows cmd 不识别 ANSI 颜色,关掉
    _use_color = sys.platform != "win32"
    if _use_color:
        color_map = {
            "info": "\033[36m", "ok": "\033[32m",
            "warn": "\033[33m", "err": "\033[31m", "reset": "\033[0m",
        }
        c = color_map.get(level, "")
        r = color_map["reset"] if c else ""
        prefix = f"{c}[{level.upper()}]{r}"
    else:
        prefix = f"[{level.upper()}]"
    print(f"{prefix} {msg}", flush=True)


def kill_port(port: int) -> None:
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    log(f"释放端口 {port}: kill PID {pid}", "warn")
                    subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
        else:
            out = subprocess.run(["lsof", "-ti", f":{port}"], capture_output=True, text=True).stdout.strip()
            for pid in out.splitlines():
                if pid:
                    log(f"释放端口 {port}: kill PID {pid}", "warn")
                    subprocess.run(["kill", "-9", pid], capture_output=True)
    except Exception as e:
        log(f"端口清理失败: {e}", "warn")


def main() -> int:
    log("停止 Cycling Coach ...", "info")
    if PID_FILE.exists():
        pid = int(PID_FILE.read_text().strip())
        try:
            if platform.system() == "Windows":
                subprocess.run(["taskkill", "/F", "/PID", str(pid)], capture_output=True)
            else:
                subprocess.run(["kill", "-9", str(pid)], capture_output=True)
            log(f"已停止后端 PID {pid}", "ok")
        except Exception as e:
            log(f"停止失败: {e}", "warn")
        PID_FILE.unlink(missing_ok=True)
    kill_port(PORT_BACKEND)
    kill_port(PORT_FRONTEND)
    log("停止完成", "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
