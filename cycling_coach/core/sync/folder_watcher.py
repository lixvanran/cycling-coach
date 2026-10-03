"""V0.9.0 Inbox folder watcher — Garmin/FIT 自动同步 (TP 替代品核心闭环)

背景:
- TP / WKO / TrainingPeaks 用户每天训练后从码表 (Garmin/Wahoo/Zwift) 导出 FIT
- 以前手动拖到 web 上传 → 烦
- 现在: 丢进 inbox 文件夹 → 自动解析入库

工作流:
1. 用户启动 daemon: `python -m cycling_coach folder-watch start`
2. Daemon 用 watchdog 监听 inbox 目录
3. 新文件 → 等待大小稳定 (debounce) → 计算 sha256
4. 检查 .processed 注册表: 已处理过跳过
5. 未处理 → 调 ActivityService.upload() 入库
6. 记录到 .processed 防重复

平台适配:
- macOS: ~/Library/Application Support/cycling-coach/inbox
- Linux: ${XDG_DATA_HOME:-~/.local/share}/cycling-coach/inbox
- Windows: %APPDATA%/cycling-coach/inbox
- 覆盖: 环境变量 CYCLING_COACH_INBOX

服务化:
- Linux: systemd --user unit
- macOS: launchd plist
- Windows: NSSM / Task Scheduler
- 用 `python -m cycling_coach folder-watch install` 生成配置文件 (V0.9.1)

设计原则:
- 进程独立: 不绑 FastAPI, 可单独跑 / 重启 / 监控
- PID 文件锁: 防止多实例并发跑 (会重复触发)
- 失败隔离: 一个文件解析失败不影响其他
- Graceful shutdown: SIGTERM 后等当前文件处理完再退
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import platform
import signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

from cycling_coach.config.config import settings

logger = logging.getLogger(__name__)

SUPPORTED_EXTS = (".fit", ".FIT", ".tcx", ".TCX", ".csv", ".CSV")


def _platform_data_dir() -> Path:
    """跨平台用户数据目录 (放 inbox + registry)

    参考: https://docs.platformdirs.org/
    - macOS:   ~/Library/Application Support/<app>
    - Linux:   $XDG_DATA_HOME/<app>  (默认 ~/.local/share/<app>)
    - Windows: %APPDATA%/<app>  (C:\\Users\\<u>\\AppData\\Roaming\\<app>)
    """
    app_name = "cycling-coach"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / app_name
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        if appdata:
            return Path(appdata) / app_name
        return Path.home() / "AppData" / "Roaming" / app_name
    # Linux / 其他 Unix
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        return Path(xdg) / app_name
    return Path.home() / ".local" / "share" / app_name


def default_inbox_dir() -> Path:
    """默认 inbox 目录

    优先级: CYCLING_COACH_INBOX env > settings.inbox_dir > 平台默认
    """
    env_override = os.environ.get("CYCLING_COACH_INBOX")
    if env_override:
        return Path(env_override).expanduser().resolve()
    if settings.inbox_dir:
        return Path(settings.inbox_dir).expanduser().resolve()
    return _platform_data_dir() / "inbox"


def default_registry_path() -> Path:
    """默认 .processed 注册表位置"""
    if settings.inbox_processed_registry:
        return Path(settings.inbox_processed_registry).expanduser().resolve()
    return _platform_data_dir() / "processed.json"


def pid_file_path() -> Path:
    """PID 文件 — `python -m cycling_coach folder-watch status` 用"""
    return _platform_data_dir() / "folder-watcher.pid"


def log_file_path() -> Path:
    """Daemon 日志 — 启动 / 停止 / 错误"""
    return _platform_data_dir() / "folder-watcher.log"


# =============== 注册表 (防重复处理) ===============

@dataclass
class ProcessedRegistry:
    """已处理文件 sha256 → 入库时间的映射

    存储: JSON 文件, 启动时加载, 每次新增 / 清理时落盘
    """
    path: Path
    _data: dict[str, str] = field(default_factory=dict)
    _dirty: bool = field(default=False, init=False)

    def load(self) -> None:
        if not self.path.exists():
            self._data = {}
            return
        try:
            self._data = json.loads(self.path.read_text(encoding="utf-8"))
            logger.info(f"注册表已加载: {len(self._data)} 条记录 ({self.path})")
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"注册表读取失败 ({e}), 重置为空")
            self._data = {}

    def save(self) -> None:
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        self._dirty = False

    def is_processed(self, sha256: str) -> bool:
        return sha256 in self._data

    def mark_processed(self, sha256: str, source_path: str) -> None:
        self._data[sha256] = {
            "imported_at": datetime.now().isoformat(),
            "source": str(source_path),
        }
        self._dirty = True

    def cleanup_orphan(self, valid_sha256: set[str]) -> int:
        """清理: 注册表里但当前不在 inbox 的(用户删了原文件)

        Returns: 清理条数
        """
        keys_to_remove = [k for k in self._data if k not in valid_sha256]
        for k in keys_to_remove:
            del self._data[k]
        if keys_to_remove:
            self._dirty = True
        return len(keys_to_remove)


# =============== 文件稳定性检查 (debounce) ===============

def wait_until_stable(
    path: Path,
    *,
    polls: int = 3,
    interval_ms: int = 200,
    timeout_s: float = 60.0,
) -> bool:
    """等待文件大小稳定 N 次 (防读到正在写入的文件)

    Returns:
        True = 大小稳定 N 次
        False = 超时 / 文件消失
    """
    interval = interval_ms / 1000.0
    last_size = -1
    stable_count = 0
    start = time.monotonic()
    while time.monotonic() - start < timeout_s:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            return False
        if size == last_size and size > 0:
            stable_count += 1
            if stable_count >= polls:
                return True
        else:
            stable_count = 0
            last_size = size
        time.sleep(interval)
    logger.warning(f"等待文件稳定超时: {path} ({timeout_s}s)")
    return False


def compute_sha256(path: Path, *, chunk: int = 65536) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            buf = f.read(chunk)
            if not buf:
                break
            h.update(buf)
    return h.hexdigest()


# =============== 处理单个文件 ===============

@dataclass
class IngestResult:
    """单文件处理结果"""
    file_path: str
    sha256: str
    status: str  # "imported" | "duplicate" | "skipped" | "failed"
    detail: str = ""
    activity_id: Optional[int] = None


def _parse_ext_settings() -> set[str]:
    """从 settings.inbox_extensions 解析扩展名集合 (大小写不敏感)"""
    raw = settings.inbox_extensions or ".fit,.tcx,.csv"
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


async def _ingest_one(
    file_path: Path,
    *,
    registry: ProcessedRegistry,
) -> IngestResult:
    """处理一个 FIT/TCX/CSV 文件 (异步)"""
    path_str = str(file_path)
    allowed = _parse_ext_settings()

    # 1. 扩展名白名单
    if file_path.suffix.lower() not in allowed:
        return IngestResult(
            file_path=path_str, sha256="", status="skipped",
            detail=f"扩展名 {file_path.suffix} 不在白名单 {allowed}",
        )

    # 2. 大小限制 (防异常)
    try:
        size = file_path.stat().st_size
    except FileNotFoundError:
        return IngestResult(file_path=path_str, sha256="", status="failed", detail="文件不存在")
    max_bytes = settings.inbox_max_file_mb * 1024 * 1024
    if size > max_bytes:
        return IngestResult(
            file_path=path_str, sha256="", status="skipped",
            detail=f"超过 {settings.inbox_max_file_mb} MB 限制 ({size} bytes)",
        )

    # 3. 等待文件大小稳定 (正在写入的文件不能读)
    if not wait_until_stable(
        file_path,
        polls=settings.inbox_stable_polls,
        interval_ms=settings.inbox_poll_interval_ms,
        timeout_s=settings.inbox_debounce_seconds * 30,  # 上限 30 倍 debounce
    ):
        return IngestResult(file_path=path_str, sha256="", status="failed", detail="文件大小不稳定 / 超时")

    # 4. 计算 hash 去重
    sha = compute_sha256(file_path)
    if registry.is_processed(sha):
        return IngestResult(
            file_path=path_str, sha256=sha, status="duplicate",
            detail="sha256 已处理过, 跳过",
        )

    # 5. 调 ActivityService.upload() — 同步函数, asyncio.to_thread 避免阻塞
    from cycling_coach.data.sqlite.database import get_db
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.exceptions import AppError

    db_gen = get_db()
    db = next(db_gen)
    try:
        svc = ActivityService(db)
        # 复用 upload 逻辑: 读 bytes → 解析 → 入库
        # upload 接受 filename + file_bytes, 我们用 path 作为 filename
        try:
            file_bytes = file_path.read_bytes()
        except OSError as e:
            return IngestResult(file_path=path_str, sha256=sha, status="failed", detail=f"读取失败: {e}")
        try:
            result = await svc.upload(filename=file_path.name, file_bytes=file_bytes)
            activity_id = result.get("id") if isinstance(result, dict) else None
            registry.mark_processed(sha, path_str)
            registry.save()
            logger.info(f"✓ 已入库: {file_path.name} (sha={sha[:8]}, id={activity_id})")
            return IngestResult(
                file_path=path_str, sha256=sha, status="imported",
                detail=f"→ activity_id={activity_id}", activity_id=activity_id,
            )
        except AppError as e:
            return IngestResult(file_path=path_str, sha256=sha, status="failed", detail=f"AppError: {e}")
        except Exception as e:
            logger.exception(f"解析异常: {file_path}")
            return IngestResult(file_path=path_str, sha256=sha, status="failed", detail=f"Exception: {e}")
    finally:
        try:
            next(db_gen)  # 触发 finally: db.close()
        except StopIteration:
            pass


# =============== Watchdog 事件处理 ===============

class _InboxHandler(FileSystemEventHandler):
    """watchdog 事件 handler — 文件创建 / 移动 / 修改 → 队列"""
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue):
        super().__init__()
        self.loop = loop
        self.queue = queue

    def _enqueue(self, path: str) -> None:
        if not path:
            return
        ext = Path(path).suffix.lower()
        allowed = _parse_ext_settings()
        if ext not in allowed:
            return
        # 用 call_soon_threadsafe 把 watchdog 回调 (sync) 的事件投到 asyncio loop
        try:
            asyncio.run_coroutine_threadsafe(self.queue.put(path), self.loop)
        except RuntimeError:
            # loop 已关闭 (shutdown 中), 忽略
            pass

    def on_created(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            logger.debug(f"created: {event.src_path}")
            self._enqueue(event.src_path)

    def on_moved(self, event: FileSystemEvent) -> None:
        if not event.is_directory:
            logger.debug(f"moved: {event.src_path} → {event.dest_path}")
            # dest_path 是新位置
            self._enqueue(event.dest_path)

    def on_modified(self, event: FileSystemEvent) -> None:
        # 某些编辑器 / 下载器用"先建空文件, 再逐步写入"模式
        # 我们已用 wait_until_stable 处理, 不需要 enqueue
        # 但为了保险, modified 也 enqueue (debounce 会去重)
        if not event.is_directory:
            self._enqueue(event.src_path)


# =============== 主 watcher 类 ===============

class InboxWatcher:
    """Inbox 监听 daemon

    用法:
        watcher = InboxWatcher(inbox_dir=Path("~/inbox"))
        watcher.run_forever()  # 阻塞, SIGTERM/SIGINT 优雅退出
    """
    def __init__(
        self,
        *,
        inbox_dir: Optional[Path] = None,
        registry: Optional[ProcessedRegistry] = None,
    ):
        self.inbox_dir = inbox_dir or default_inbox_dir()
        self.registry = registry or ProcessedRegistry(path=default_registry_path())
        self.queue: asyncio.Queue[str] = asyncio.Queue()
        self.observer: Optional[Observer] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = asyncio.Event()  # type: ignore  # 在 run_forever 内初始化

    def setup(self) -> None:
        """启动前的环境准备

        - 创建 inbox 目录
        - 加载注册表
        - 初次扫描: 把已有文件处理掉 (防漏)
        """
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"inbox 目录: {self.inbox_dir}")
        self.registry.load()

    def initial_scan(self) -> int:
        """启动时扫描一次 inbox, 处理已存在但未入库的文件

        Returns: 入库成功数
        """
        if not self.inbox_dir.exists():
            return 0
        files = [
            p for p in self.inbox_dir.iterdir()
            if p.is_file() and p.suffix.lower() in _parse_ext_settings()
        ]
        logger.info(f"初次扫描发现 {len(files)} 个文件")
        return asyncio.run(self._batch(files))

    async def _batch(self, paths: list[Path]) -> int:
        """处理一批文件 (顺序, 不并发避免 DB 写锁)"""
        n_imported = 0
        for p in paths:
            result = await _ingest_one(p, registry=self.registry)
            logger.info(f"  [{result.status}] {p.name}: {result.detail}")
            if result.status == "imported":
                n_imported += 1
        return n_imported

    async def _worker(self) -> None:
        """异步 worker — 从 queue 取文件 → 处理"""
        while not self._stop_event.is_set():  # type: ignore
            try:
                path_str = await asyncio.wait_for(self.queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            path = Path(path_str)
            if not path.exists():
                logger.debug(f"文件已消失, 跳过: {path}")
                continue
            result = await _ingest_one(path, registry=self.registry)
            logger.info(f"  [{result.status}] {path.name}: {result.detail}")

    def run_forever(self) -> None:
        """阻塞运行, 直到 SIGTERM/SIGINT 或 stop() 调用"""
        self.setup()
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._stop_event = asyncio.Event()
        try:
            # 启动 watchdog observer
            handler = _InboxHandler(self._loop, self.queue)
            self.observer = Observer()
            self.observer.schedule(handler, str(self.inbox_dir), recursive=False)
            self.observer.start()
            logger.info(f"watchdog 监听中: {self.inbox_dir} (recursive=False)")

            # 初次扫描 (在 worker 启动前)
            self.initial_scan()

            # 信号处理 (仅 Unix)
            if sys.platform != "win32":
                def _shutdown(*_a):
                    logger.info("收到 SIGTERM/SIGINT, 准备关闭...")
                    self._loop.call_soon_threadsafe(self._stop_event.set)
                signal.signal(signal.SIGTERM, _shutdown)
                signal.signal(signal.SIGINT, _shutdown)

            # worker 主循环
            try:
                self._loop.run_until_complete(self._worker())
            finally:
                logger.info("worker 退出, 停止 observer...")
                if self.observer:
                    self.observer.stop()
                    self.observer.join(timeout=5)
                self.registry.save()
        finally:
            self._loop.close()
            logger.info("InboxWatcher 已退出")

    def stop(self) -> None:
        """外部触发停止 (signal handler / CLI 调用)"""
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._stop_event.set)
