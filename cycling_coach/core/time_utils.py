"""时间工具 (V0.8.3.1 P1: 统一 UTC naive 时间戳)

Python 3.12 起 `datetime.utcnow()` 已 deprecated, 会出 DeprecationWarning.
但 SQLAlchemy 默认 DateTime 是 naive (没 tzinfo), 不能直接换 `datetime.now(timezone.utc)`.

用法:
    from cycling_coach.core.time_utils import utcnow_naive

    now: datetime = utcnow_naive()  # UTC naive, 跟 SQLAlchemy DateTime 兼容
"""
from __future__ import annotations
from datetime import datetime, timezone


def utcnow_naive() -> datetime:
    """当前 UTC 时间 (naive) — 替代 deprecated datetime.utcnow()

    等价于:
        datetime.now(timezone.utc).replace(tzinfo=None)

    跟 SQLAlchemy DateTime (默认 naive UTC) 完全对齐, 比较 / 存储 OK.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)
