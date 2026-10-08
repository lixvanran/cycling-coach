"""V0.9.0-07: 整个产品必须只有一个"今天"

## 背景: 我犯了方向性的错误

全量测试反复红 4 条, 根因是"今天"的定义不一致:

    get_pmc_today()   用  date.today()          (本地)
    测试原来用         utcnow().date()          (UTC)

我当时的修法是**把测试改成跟生产代码对齐**。
Verifier 复审指出: **方向错了** —— 真实 bug 是生产代码在混用两个基准,
把测试对齐只是**掩盖**了它, 不是消除分歧。

他是对的。而查下去发现比那更深:

    pmc 写入侧 _day_key()   做 astimezone(UTC) 再取 date  -> UTC 归档
    pmc 读取侧 get_pmc_today()  date.today()              -> 本地查询

**写和读在同一个文件里用了两个时区。** 后果:

    上海凌晨 1:00 骑的车 -> 归档到"昨天" -> 用户看"今天"是空的

UTC+8 每天 **8 小时** (00:00-07:59) 落在这个缝里。

## 现在的规则

- **日历日**语义 (今天/本周/距今天几天) -> 一律本地日期
- **时间戳**语义 (created_at/completed_at) -> 一律 `utcnow_naive()` (UTC)

这两件事以前被混为一谈, 所以才同时错了 10 处。
"""
from __future__ import annotations

import ast
import pathlib
from datetime import date, datetime, timedelta, timezone

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------- _day_key
# ⚠️ 这两条只在 **非 UTC 时区**下有意义。
# 在 UTC 机器上两种实现结果相同, 测试会变成恒真 —— 那是假绿。
# 所以显式声明"需要在有偏移的时区下跑", 而不是假装它到处都有效。
NEEDS_EASTERN_TZ = datetime.now().astimezone().utcoffset() != timedelta(0)


@pytest.mark.skipif(
    not NEEDS_EASTERN_TZ,
    reason="UTC 时区下本地日 == UTC 日, 本修复不可观测 (换 UTC+8/+12 再跑)",
)
def test_day_key_uses_local_calendar_day():
    """🔴 核心: 上海凌晨 1 点的骑行必须归档到当天, 不是昨天

    FIT 存的是 UTC 17:00 (= 上海次日 01:00)。入库剥掉 tzinfo 后仍是
    naive 17:00。旧实现取 `.date()` 得到 10-08 —— **比用户认知早一天**。
    """
    from cycling_coach.core.pmc import _day_key
    # 上海 2026-10-09 01:00 == UTC 2026-10-08 17:00
    assert _day_key(datetime(2026, 10, 8, 17, 0)) == date(2026, 10, 9)


@pytest.mark.skipif(
    not NEEDS_EASTERN_TZ,
    reason="同上",
)
def test_day_key_keeps_calendar_day_across_the_whole_day():
    """同一天里的各时段都应落在同一个本地日历日"""
    from cycling_coach.core.pmc import _day_key
    # 上海 2026-10-09 全天 = UTC [10-08 16:00, 10-09 15:59]
    # (第一版我用 "+ timedelta(hours=h-16)" 算, 跨天界时算错, 自己把自己测红了)
    utc_moments = [
        datetime(2026, 10, 8, 16, 0),   # 上海 10-09 00:00
        datetime(2026, 10, 8, 17, 0),   # 上海 10-09 01:00  <- 原来错成 10-08
        datetime(2026, 10, 9, 4, 0),    # 上海 10-09 12:00
        datetime(2026, 10, 9, 11, 0),   # 上海 10-09 19:00
        datetime(2026, 10, 9, 15, 59),  # 上海 10-09 23:59
    ]
    for m in utc_moments:
        got = _day_key(m)
        assert got == date(2026, 10, 9), f"UTC {m} 应归档到 10-09, 实得 {got}"

    # 边界外: 上海 10-08 全天 = UTC [10-07 16:00, 10-08 15:59]
    for m in (datetime(2026, 10, 7, 16, 0), datetime(2026, 10, 8, 15, 59)):
        assert _day_key(m) == date(2026, 10, 8), f"UTC {m} 应归档到 10-08"


def test_day_key_preserves_explicit_tz_aware_semantics():
    """带时区的输入按其真实时刻换算, 不受实现影响 —— 防回归护栏"""
    from cycling_coach.core.pmc import _day_key
    aware = datetime(2026, 10, 9, 1, 0, tzinfo=timezone(timedelta(hours=8)))
    assert _day_key(aware) == aware.astimezone().date()


# ---------------------------------------------------- 生产代码不得再混用
def test_no_production_code_computes_calendar_day_from_utc():
    """🔴 全仓: 任何 `utcnow().date()` 出现在生产代码里都是 bug

    时间戳该走 `utcnow_naive()`, 日历日该走 `date.today()`。
    以前两者被混为一谈, 所以同时错了 10 处。
    """
    offenders: list[str] = []
    for p in (ROOT / "cycling_coach").rglob("*.py"):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            # 只看真实的代码节点, 注释不在 AST 里 ——
            # 否则我写的"这里原来是 utcnow().date()"说明文字会把自己测红
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "date"
                    and isinstance(node.func.value, ast.Call)
                    and isinstance(node.func.value.func, ast.Attribute)
                    and node.func.value.func.attr == "utcnow"):
                offenders.append(f"{p.relative_to(ROOT)}:{node.lineno}")
    assert not offenders, (
        "这些地方还在用 UTC 算日历日, 会和本地日期的读取侧差一天:\n  "
        + "\n  ".join(offenders)
    )


def test_timestamps_still_use_utcnow_naive():
    """反向: 真时间戳必须继续用 UTC, 不能被这次修复带偏

    防止"矫枉过正" —— 把时间戳也改成本地, 那会比原 bug 更糟。
    """
    import cycling_coach.core.time_utils as tu
    n = tu.utcnow_naive()
    assert n.tzinfo is None, "时间戳要保持 naive, 跟 SQLAlchemy 对齐"
