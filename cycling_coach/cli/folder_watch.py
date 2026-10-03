"""V0.9.0: `python -m cycling_coach folder-watch` 子命令

子命令:
- start: 启动 daemon (前台 / 后台)
- stop:  停掉 daemon (读 PID 文件)
- status: 查看 daemon 状态 / inbox / 处理数
- once:  扫描 inbox 一次, 处理完退出 (调试 / 手动跑)
- install: 生成 systemd / launchd 配置文件 (V0.9.1+)
"""
from __future__ import annotations
import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from cycling_coach.core.sync.folder_watcher import (
    InboxWatcher,
    ProcessedRegistry,
    default_inbox_dir,
    default_registry_path,
    pid_file_path,
    log_file_path,
    _platform_data_dir,
)

logger = logging.getLogger(__name__)


def _read_pid() -> int | None:
    pf = pid_file_path()
    if not pf.exists():
        return None
    try:
        return int(pf.read_text().strip())
    except (ValueError, OSError):
        return None


def _is_running(pid: int) -> bool:
    """检查 PID 是否真的活着 (跨平台)"""
    if pid <= 0:
        return False
    try:
        if sys.platform == "win32":
            import ctypes
            PROCESS_QUERY_LIMITED = 0x1000
            STILL_ACTIVE = 259
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED, False, pid)
            if not h:
                return False
            code = ctypes.c_ulong()
            ctypes.windll.kernel32.GetExitCodeProcess(h, ctypes.byref(code))
            ctypes.windll.kernel32.CloseHandle(h)
            return code.value == STILL_ACTIVE
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def cmd_start(args) -> int:
    """启动 watcher daemon"""
    pid = _read_pid()
    if pid and _is_running(pid):
        print(f"已在运行 (PID {pid})")
        return 1

    inbox = default_inbox_dir()
    print(f"启动 inbox watcher:")
    print(f"  inbox:  {inbox}")
    print(f"  pid:    {pid_file_path()}")
    print(f"  log:    {log_file_path()}")
    print()

    if args.daemon:
        # 后台模式: fork 一份, 把日志写文件
        log_path = log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        # 用 subprocess.Popen 启动, 而不是 fork — 跨平台
        import subprocess
        # 重新执行自身 (不带 --daemon), 把 stdout/stderr 重定向到 log
        cmd = [sys.executable, "-m", "cycling_coach", "folder-watch", "start"]
        # 重定向到 log 文件, append 模式
        log_f = log_path.open("a", encoding="utf-8")
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            start_new_session=(sys.platform != "win32"),  # detach
        )
        # 写 PID (本子进程退出, 但子子进程被 detach 后 PID 是它)
        # 注意: 这里我们写了子子进程的 PID
        time.sleep(0.5)
        # 检查子子进程是否在跑
        if proc.poll() is None:
            print(f"已在后台启动 (PID {proc.pid})")
            print(f"日志: tail -f {log_path}")
            return 0
        print(f"启动失败 (exit code {proc.returncode})")
        return 1

    # 前台模式: 写 PID + 注册清理 + 跑
    pf = pid_file_path()
    pf.parent.mkdir(parents=True, exist_ok=True)
    pf.write_text(str(os.getpid()))
    print(f"PID 写入 {pf}")

    # V0.9.0: 确保 DB 表存在
    from cycling_coach.data.sqlite import init_db
    init_db()

    def cleanup(*_a):
        logger.info("清理 PID 文件")
        try:
            pf.unlink(missing_ok=True)
        except Exception:
            pass
        sys.exit(0)

    if sys.platform != "win32":
        signal.signal(signal.SIGTERM, cleanup)
        signal.signal(signal.SIGINT, cleanup)

    try:
        watcher = InboxWatcher(inbox_dir=inbox)
        watcher.run_forever()
    finally:
        pf.unlink(missing_ok=True)
    return 0


def cmd_stop(args) -> int:
    """停掉 watcher daemon"""
    pid = _read_pid()
    if not pid:
        print("未运行 (无 PID 文件)")
        return 0
    if not _is_running(pid):
        print(f"stale PID 文件 (PID {pid} 已退出), 清理")
        pid_file_path().unlink(missing_ok=True)
        return 0
    try:
        if sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.TerminateProcess(
                ctypes.windll.kernel32.OpenProcess(1, False, pid), 0
            )
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"已发 SIGTERM 给 PID {pid}")
        # 等 5s
        for _ in range(50):
            time.sleep(0.1)
            if not _is_running(pid):
                pid_file_path().unlink(missing_ok=True)
                print(f"PID {pid} 已退出")
                return 0
        print(f"PID {pid} 没退出, 强 kill")
        os.kill(pid, signal.SIGKILL)
        pid_file_path().unlink(missing_ok=True)
        return 0
    except (OSError, ProcessLookupError) as e:
        print(f"停止失败: {e}")
        return 1


def cmd_status(args) -> int:
    """查看 daemon 状态"""
    pid = _read_pid()
    print(f"=== inbox watcher status ===")
    print(f"  inbox dir:     {default_inbox_dir()}")
    print(f"  registry:      {default_registry_path()}")
    print(f"  PID file:      {pid_file_path()}")
    print(f"  log file:      {log_file_path()}")
    if pid and _is_running(pid):
        print(f"  state:         RUNNING (PID {pid})")
    elif pid:
        print(f"  state:         stale PID ({pid} 已退出)")
    else:
        print(f"  state:         STOPPED")
    # 注册表统计
    reg = ProcessedRegistry(path=default_registry_path())
    reg.load()
    print(f"  processed:     {len(reg._data)} 个文件")
    # inbox 当前文件数
    inbox = default_inbox_dir()
    if inbox.exists():
        n_files = sum(
            1 for p in inbox.iterdir()
            if p.is_file() and p.suffix.lower() in (".fit", ".tcx", ".csv")
        )
        print(f"  inbox files:   {n_files}")
    return 0


def cmd_once(args) -> int:
    """扫描 inbox 一次, 处理完退出 (调试 / cron 用)"""
    from cycling_coach.data.sqlite import init_db
    init_db()  # V0.9.0: 确保 DB 表存在 (CI 跑 / 全新环境)
    inbox = default_inbox_dir()
    watcher = InboxWatcher(inbox_dir=inbox)
    watcher.setup()
    n = watcher.initial_scan()
    print(f"处理完成: {n} 个新文件入库")
    return 0


def cmd_install(args) -> int:
    """生成服务配置文件 (V0.9.1+ 占位)"""
    print("install 子命令待 V0.9.1 实现 (systemd / launchd / Windows Service)")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m cycling_coach folder-watch",
        description="V0.9.0 Inbox folder watcher (Garmin/FIT 自动同步)",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_start = sub.add_parser("start", help="启动 watcher")
    p_start.add_argument("--daemon", action="store_true", help="后台运行")
    p_start.set_defaults(func=cmd_start)

    p_stop = sub.add_parser("stop", help="停止 watcher")
    p_stop.set_defaults(func=cmd_stop)

    p_status = sub.add_parser("status", help="查看状态")
    p_status.set_defaults(func=cmd_status)

    p_once = sub.add_parser("once", help="扫描一次处理完退出 (调试)")
    p_once.set_defaults(func=cmd_once)

    p_install = sub.add_parser("install", help="生成服务配置")
    p_install.set_defaults(func=cmd_install)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
