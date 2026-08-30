"""统一日志格式

参考 Photographer-Copilot 风格:启动器继承 stdout,文件 log 落盘
"""
from __future__ import annotations
import logging
import sys
from pathlib import Path

_LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)-30s | %(message)s"


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """初始化日志(所有子模块通过 logging.getLogger(__name__) 自动继承)"""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))
    # 清掉已有 handler,避免重复
    for h in list(root.handlers):
        root.removeHandler(h)

    formatter = logging.Formatter(_LOG_FORMAT)

    # stdout(被启动器继承,实时显示给用户)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(formatter)
    root.addHandler(sh)

    # 文件(可 tail -f)
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        fh = logging.FileHandler(log_file, encoding="utf-8")
        fh.setFormatter(formatter)
        root.addHandler(fh)
