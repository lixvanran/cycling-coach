"""Cycling Coach 后端 CLI 入口

直接跑: python -m cycling_coach
或: pyinstaller --name=cycling-coach backend.spec

V0.7.6 Foundation 1.0: 优雅关闭
- SIGTERM/SIGINT 触发时,等现有请求跑完再退出 (uvicorn timeout_graceful_shutdown=10s)
- 显式 Server.should_exit = True → uvicorn Server.run() 退出 → os._exit(0) 兜底
  避免 uvicorn 0.52 asyncio loop 不干净退出的 known issue
- SQLite 单写锁, 多 worker 不启用 (workers=1)
"""
import logging
import os
import signal
import sys

import uvicorn

from cycling_coach.config.config import settings

logger = logging.getLogger(__name__)


# module-level 关闭标志 (供将来 hot path 检查; 当前主要靠 uvicorn 的 graceful timeout)
_shutting_down: bool = False


def _handle_sigterm(signum, frame) -> None:
    """SIGTERM / SIGINT 处理器: 仅打 log + 置 flag, 让 uvicorn 跑完现有请求再退出

    注: uvicorn 在 asyncio loop 里用 loop.add_signal_handler() 注册自己的 handler,
    这个 signal.signal() handler 在 server 模式下不会被实际触发 (uvicorn 抢先捕获).
    但作为兜底, 如果 uvicorn 退出后 Python 仍 hang, 此 handler 会在第二次信号时强退.
    """
    global _shutting_down
    if _shutting_down:
        # 第二次信号 → 立即退出 (用户不耐烦)
        logger.warning("再次收到关闭信号, 立即退出")
        os._exit(1)
    _shutting_down = True
    sig_name = signal.Signals(signum).name if hasattr(signal, "Signals") else str(signum)
    logger.info(f"收到 {sig_name}, 优雅关闭中... (现有请求会跑完, 最长 10s)")
    # 不在这里 sys.exit — 让 uvicorn 接管 shutdown 流程


def main() -> None:
    host = getattr(settings, "backend_host", "127.0.0.1")
    port = int(getattr(settings, "backend_port", 8765))
    log_level = getattr(settings, "log_level", "info")

    # 注册兜底 signal handler (uvicorn 在 server 模式下会自己处理 SIGTERM/SIGINT,
    # 但若 asyncio loop 不干净退出, 这个 handler 会在第二次信号时强退)
    if sys.platform != "win32":
        try:
            signal.signal(signal.SIGTERM, _handle_sigterm)
        except (ValueError, OSError):
            pass  # 非主线程注册会失败, 忽略
    try:
        signal.signal(signal.SIGINT, _handle_sigterm)
    except (ValueError, OSError):
        pass

    logger.info(f"启动 Cycling Coach 后端: {host}:{port} (workers=1, graceful=10s)")

    # 显式用 Server 模式 + serve() 而非 run() — 让我能控制 exit
    config = uvicorn.Config(
        "cycling_coach.api.main:app",
        host=host,
        port=port,
        log_level=log_level,
        reload=False,
        workers=1,  # SQLite 单写锁, 多 worker 会冲突
        timeout_graceful_shutdown=10,  # V0.7.6: 优雅关闭超时 10s
    )
    server = uvicorn.Server(config)
    try:
        server.run()  # 阻塞直到 server.should_exit=True (SIGTERM/SIGINT 触发)
    except KeyboardInterrupt:
        # fallback: 如果用 Ctrl+C 走到了这里, 走 graceful
        server.should_exit = True
    finally:
        # uvicorn 0.52 known issue: server.run() 返回后 asyncio loop 可能未完全关闭
        # 显式 os._exit 避免 zombie / hang
        logger.info("Cycling Coach 后端退出")
        os._exit(0)


if __name__ == "__main__":
    main()
