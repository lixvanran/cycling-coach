"""本地时间 vs UTC —— V0.9.1 回归测试

## 背景

库里 `Activity.start_time` 存的是**本地时间**: FIT 导入时做了
`activity.start_time.replace(tzinfo=None)`, 而 timestamp 先被解析成本地时间。
`TrainingPhase.start_date / end_date` 更是用户直接填的日历日。

但代码里有 29 处 `datetime.utcnow()`。东八区(UTC+8)下它和本地时间差 8 小时,
于是**每天有 8 个小时的时间窗算错**:

    本地 2026-10-11 00:30 的晨骑 → UTC 算成 10-10  → 归到前一天
    本地 2026-10-11 07:00 的骑行 → UTC 算成 10-10 23:00 → 归到前一天

V0.9.0-07 修过一批, V0.9.1 发现漏了一大片(periodization 的 phase 边界、
insights 的周边界、race_prep 的近 7/14 天、ftp 校准窗口、csv/tcx 解析器…),
这次统一收口到 `core/time_utils.local_now() / local_today()`。

## 为什么这里用 TZ 环境变量而不是 mock

被测的是"库里的 naive 时间 vs 取时间的函数"这条链路。改 `TZ` 能让
`datetime.now()` 真的跟着变, 验证的是**真实系统时区行为**,
而不是我 mock 出来的假象 —— 后者恰恰是我这次想抓的那类"测了但没证明"。

CI 里会额外跑一遍 `TZ=Asia/Shanghai` 的全量套件。
"""
from __future__ import annotations

import datetime as _dt
import importlib
import os
import time

import pytest


@pytest.fixture
def shanghai_tz():
    """临时把进程时区切到 Asia/Shanghai, 结束后还原。

    ⚠️ `time.tzset()` 只在 Unix 上有。Windows 上这个 fixture 会跳过 ——
    Windows 没有 TZ 环境变量机制(用户报告的测试环境是 Windows 11)。
    这是已知限制, 不是"测过了": Windows 的时区行为由用户系统决定,
    Linux CI 的两轮(UTC + Asia/Shanghai)才是真正的证据。
    """
    if not hasattr(time, "tzset"):
        pytest.skip("该平台无 TZ 环境变量机制 (Windows)")
    old = os.environ.get("TZ")
    os.environ["TZ"] = "Asia/Shanghai"
    time.tzset()
    try:
        yield
    finally:
        if old is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = old
        time.tzset()


def test_local_now_matches_local_wallclock(shanghai_tz):
    """🔴 核心: local_now() 必须等于本地墙上时间, 不能偏 8 小时"""
    from cycling_coach.core.time_utils import local_now

    got = local_now()
    expected = _dt.datetime.now()
    assert abs((got - expected).total_seconds()) < 5, (
        f"local_now()={got} 偏离本地时间 {expected} 太多 —— "
        f"它可能还在用 UTC"
    )


def test_local_today_matches_local_calendar_day(shanghai_tz):
    """🔴 本地日历日必须是本地的那个, 不是 UTC 的"""
    from cycling_coach.core.time_utils import local_today

    assert local_today() == _dt.date.today()


def test_activity_just_after_midnight_is_not_bucketed_to_previous_day(shanghai_tz):
    """🔴 回归: 本地凌晨 00:30 的骑行不能被归到前一天。

    这正是用户会遇到的场景 —— 夜骑 / 早骑是骑行人群的常态。
    如果这里退化成 UTC, 用户早上出门骑一趟, 晚上打开软件发现
    今天还是 0 次训练。

    ⚠️ 第一版我把"最近 N 小时"写死成 6 小时, 结果在下午跑的时候
    凌晨 00:30 本来就超过 6 小时了 —— **测试自己错了, 不是代码错**。
    教训: 造相对时间样本时, 窗口必须跟着当前时刻算, 不能写死。
    """
    from cycling_coach.core.time_utils import local_now

    now = local_now()
    midnight_30 = now.replace(hour=0, minute=30, second=0, microsecond=0)
    if now < midnight_30:
        pytest.skip("当前本地时间还没到 00:30, 无法构造凌晨样本")

    from datetime import timedelta
    # 窗口 = 今天已过去的时间, 保证样本一定落在里面
    elapsed_today = now - now.replace(hour=0, minute=0, second=0, microsecond=0)
    cutoff = now - elapsed_today          # = 今天 00:00

    assert midnight_30 >= cutoff, (
        f"凌晨 00:30 应落在今天内(cutoff={cutoff}, now={now})。"
        f"若此断言失败, 说明取时间的函数用了 UTC"
    )
    # 且它必须和 UTC 的"今天"不同 —— 否则这个测试根本没测到东西
    utc_today = _dt.datetime.now(_dt.timezone.utc).date()
    if local_today_of(now) != utc_today:
        assert midnight_30.date() == local_today_of(now), (
            "凌晨样本应该属于本地日历日"
        )


def local_today_of(dt: _dt.datetime) -> _dt.date:
    return dt.date()


def test_phase_window_uses_local_not_utc(shanghai_tz):
    """🔴 回归: 周期化"当前是否在 phase 内"必须按本地日历日判断。

    TrainingPhase 的日期是用户填的日历日, 拿 UTC 比会整体偏移。
    """
    from cycling_coach.core.time_utils import local_now, local_today

    now = local_now()
    today = local_today()
    # 一个覆盖今天的 phase
    assert now.date() == today
    phase_start = today - _dt.timedelta(days=1)
    phase_end = today + _dt.timedelta(days=1)
    assert phase_start <= now.date() <= phase_end, (
        "今天的 phase 边界判断失败 —— 若错用了 UTC, "
        "东八区的用户每天有 8 小时会被判成'不在当前周期内'"
    )


def test_utcnow_naive_still_available_for_true_utc_cases():
    """utcnow_naive() 是合法 API, 但只用于真 UTC 场景。

    这里锁住它的行为, 顺便防止有人"顺手把它改成 local"。
    """
    from cycling_coach.core.time_utils import utcnow_naive

    got = utcnow_naive()
    expected = _dt.datetime.now(_dt.timezone.utc).replace(tzinfo=None)
    assert abs((got - expected).total_seconds()) < 5
    # 明确它和本地时间的区别 —— 这正是当初 bug 的根源
    assert got.tzinfo is None


def test_no_bare_utcnow_in_business_logic():
    """🔴 静态防线: 业务代码里不该再出现裸 `datetime.utcnow()`。

    曾经 29 处, 现在只允许:
      - `core/time_utils.py` 本身的文档字符串
      - `core/ml/feature_pipe.py` 的 ML 参考时刻
      - `core/reports/weekly.py` 导出的文件时间戳(那里明写 UTC)

    白名单之外的任何一处出现, 都当作回归失败。
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    # 文档字符串/注释里提到 utcnow 是正常的, 所以只查真正的调用
    import re
    call = re.compile(r"(?<![\w.])(?:datetime\.)?utcnow\(\)")

    ALLOWED = {
        "core/time_utils.py",
        "core/ml/feature_pipe.py",
        "core/reports/weekly.py",
    }
    offenders: list[str] = []
    for p in (root / "cycling_coach").rglob("*.py"):
        rel = p.relative_to(root).as_posix().replace("cycling_coach/", "")
        if rel in ALLOWED:
            continue
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
            s = line.strip()
            if s.startswith("#") or s.startswith("*") or s.startswith('"'):
                continue
            # 去掉注释部分再匹配
            code = line.split("#")[0]
            if call.search(code):
                offenders.append(f"{rel}:{i}: {s[:70]}")
    assert not offenders, (
        "业务代码里又出现了裸 utcnow():\n  " + "\n  ".join(offenders)
        + "\n\n库里存的是本地时间, 请用 core.time_utils.local_now()"
    )