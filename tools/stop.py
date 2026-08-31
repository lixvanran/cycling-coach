#!/usr/bin/env python3
"""停止 Cycling Coach 后端 + 前端 (V0.7.6 优雅停止)

流程:
1. TERM (signal 15)  → 等 8s (uvicorn timeout_graceful_shutdown=10s)
2. 还在跑 → KILL (-9 / taskkill /F) 强杀
3. 端口兜底清理 (lsof / netstat)
"""
from __future__ import annotations
import os
import platform
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
WORKSPACE_DIR = ROOT / "workspace"
PID_FILE = WORKSPACE_DIR / ".sidecar.pid"
PORT_BACKEND = int(os.environ.get("BACKEND_PORT", "8765"))
PORT_FRONTEND = int(os.environ.get("FRONTEND_PORT", "1420"))

# 优雅等待时间 (秒) — 比 uvicorn timeout_graceful_shutdown 略小, 给它一点 buffer
GRACEFUL_WAIT = 8


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


def _pid_alive(pid: int) -> bool:
    """检查 PID 是否还在跑"""
    if pid <= 0:
        return False
    try:
        if platform.system() == "Windows":
            # tasklist 会比较慢, 用 /FI 过滤更快
            out = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in out.stdout
        else:
            os.kill(pid, 0)  # signal 0 = 只检查存在
            return True
    except (ProcessLookupError, OSError, subprocess.TimeoutExpired):
        return False


def _send_term(pid: int) -> bool:
    """发 TERM / 优雅 taskkill, 返回是否成功发送"""
    try:
        if platform.system() == "Windows":
            # Windows 无 SIGTERM 概念; taskkill 不带 /F = 优雅 (发 WM_CLOSE 给 GUI / 关进程)
            # 对 console 进程: taskkill 仍会要求确认 (除非带 /F) — 加 /T 关子进程
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T"],
                capture_output=True, text=True, timeout=5,
            )
            ok = result.returncode == 0
            if not ok:
                log(f"taskkill 优雅失败 (rc={result.returncode}): {result.stderr.strip()}", "warn")
            return ok
        else:
            os.kill(pid, signal.SIGTERM)  # noqa: F821
            return True
    except ProcessLookupError:
        return False  # 已经不在了
    except PermissionError as e:
        log(f"无权限发送 TERM 到 PID {pid}: {e}", "err")
        return False
    except Exception as e:
        log(f"发送 TERM 失败: {e}", "err")
        return False


def _send_kill(pid: int) -> None:
    """强杀: SIGKILL / taskkill /F"""
    try:
        if platform.system() == "Windows":
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid), "/T"],
                capture_output=True, timeout=5,
            )
        else:
            subprocess.run(["kill", "-9", str(pid)], capture_output=True, timeout=5)
    except Exception as e:
        log(f"强杀失败: {e}", "err")


def _stop_pid_graceful(pid: int) -> bool:
    """优雅停止单个 PID: TERM → 等 GRACEFUL_WAIT → KILL fallback

    返回: True=成功停止, False=失败
    """
    if not _pid_alive(pid):
        log(f"PID {pid} 已不在", "info")
        return True

    if platform.system() == "Windows":
        log(f"[GRACEFUL] 优雅停止 PID {pid} (taskkill → 等 {GRACEFUL_WAIT}s)", "info")
    else:
        log(f"[GRACEFUL] 优雅停止 PID {pid} (SIGTERM → 等 {GRACEFUL_WAIT}s)", "info")
    if not _send_term(pid):
        log(f"PID {pid} TERM 发送失败, 直接强杀", "warn")
        _send_kill(pid)
        return True  # 反正不在了就算成功

    # 等待退出
    waited = 0.0
    poll_interval = 0.5
    while waited < GRACEFUL_WAIT:
        time.sleep(poll_interval)
        waited += poll_interval
        if not _pid_alive(pid):
            log(f"[GRACEFUL] PID {pid} 已优雅退出 (等 {waited:.1f}s)", "ok")
            return True

    # 超时 → 强杀
    log(f"[GRACEFUL] PID {pid} 超时 {GRACEFUL_WAIT}s 未退出, 强杀", "warn")
    _send_kill(pid)
    # 再等一下
    for _ in range(4):
        time.sleep(0.5)
        if not _pid_alive(pid):
            log(f"PID {pid} 已强杀", "ok")
            return True
    log(f"PID {pid} 强杀后仍在? 残留 zombie", "err")
    return False


def kill_port(port: int) -> None:
    """端口兜底清理 (TERM → KILL, 但端口用 lsof/tasklist 找 PID)"""
    system = platform.system()
    try:
        if system == "Windows":
            out = subprocess.run(["netstat", "-ano"], capture_output=True, text=True).stdout
            pids = set()
            for line in out.splitlines():
                if f":{port}" in line and "LISTENING" in line:
                    pid = line.split()[-1]
                    if pid.isdigit():
                        pids.add(int(pid))
            for pid in pids:
                log(f"释放端口 {port}: TERM PID {pid}", "warn")
                _stop_pid_graceful(pid)
        else:
            out = subprocess.run(
                ["lsof", "-ti", f":{port}"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            for pid_str in out.splitlines():
                if pid_str.isdigit():
                    pid = int(pid_str)
                    log(f"释放端口 {port}: TERM PID {pid}", "warn")
                    _stop_pid_graceful(pid)
    except Exception as e:
        log(f"端口清理失败: {e}", "warn")


def main() -> int:
    log("停止 Cycling Coach ...", "info")
    if PID_FILE.exists():
        try:
            pid = int(PID_FILE.read_text().strip())
        except (ValueError, OSError) as e:
            log(f"PID 文件读取失败: {e}", "warn")
            pid = 0
        if pid > 0:
            _stop_pid_graceful(pid)
        try:
            PID_FILE.unlink(missing_ok=True)
        except OSError:
            pass
    kill_port(PORT_BACKEND)
    kill_port(PORT_FRONTEND)
    log("停止完成", "ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
