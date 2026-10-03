"""V0.9.0: PMC 增量重算回归测试

## 这个 bug 有多严重

`recompute_pmc(anchor_date=新活动日期)` 原来用 anchor_date 裁剪了**输入**:
只加载该日之后的活动, 前面最多 365 天全按 TSS=0 处理, EWMA 从全零起算,
然后把之前算对的 daily_metrics 行**全部覆盖**。

实测 (2026-10-03, 8 周演示数据):
- 逐次导入 45 次训练后, 366 行 daily_metrics 里 **365 行 TSS=0**
- CTL = 0.3, ATL = 1.5 —— 一个认真训练了 8 周的人被告知体能 0.3
- 手动全量重算一次: CTL 56.1 / ATL 61.5 / TSB -5.4 (合理值)

这不是"新用户没数据"的小毛病。**每个用户每天导入训练都会中招**:
早上骑完导入, 应用就告诉你体能清零。

## 修法

anchor_date 只控制"写回哪些行"(省 IO), 不控制"读哪些活动"。
EWMA 是递推的, seed 错了后面全错, 所以历史必须全量加载。

## 本文件锁死的行为

1. 增量导入不能抹掉历史
2. 增量重算的结果必须和全量重算一致
3. 单条活动的日常使用不会让 CTL 归零
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest


@pytest.fixture(scope="module", autouse=True)
def _db():
    from tests.conftest import use_temp_db
    use_temp_db("pmc_incremental")


def _make_athlete(db, name="测试车手"):
    from cycling_coach.data.sqlite.models import Athlete
    a = Athlete(name=name, ftp=280, lthr=168, max_hr=188, weight_kg=68.0)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _add_activity(db, a, day: date, tss: float, dur_s: int = 3600, name: str = "ride"):
    from cycling_coach.data.sqlite.models import Activity
    act = Activity(
        athlete_id=a.id,
        source="test",
        file_name=name,
        start_time=datetime.combine(day, datetime.min.time()) + timedelta(hours=6),
        duration_s=dur_s,
        distance_m=float(dur_s) * 8.0,
        avg_power=int(200 * (tss / 50) ** 0.5) if tss else 0,
        metrics={"tss": tss},
    )
    db.add(act)
    db.commit()
    db.refresh(act)
    return act


def _history(db, athlete_id: int) -> dict:
    from cycling_coach.data.sqlite.models import DailyMetric
    rows = db.query(DailyMetric).filter(DailyMetric.athlete_id == athlete_id).all()
    return {
        "n": len(rows),
        "tss_days": sum(1 for r in rows if (r.tss or 0) > 0),
        "ctl": max((r.ctl or 0) for r in rows) if rows else 0.0,
        "last": rows[-1] if rows else None,
    }


# ======================================================================

def test_增量导入不抹掉历史():
    """核心回归: 逐条导入 20 次训练, 历史 TSS 不能归零"""
    from cycling_coach.core.pmc import recompute_pmc
    from cycling_coach.data.sqlite import database as D

    db = D.SessionLocal()
    try:
        a = _make_athlete(db, "增量测试")
        base = date.today() - timedelta(days=40)
        # 逐条导入, 每次都按真实代码路径调用 recompute_pmc(anchor=该活动日期)
        for i in range(20):
            day = base + timedelta(days=i * 2)
            act = _add_activity(db, a, day, tss=60 + (i % 4) * 10)
            recompute_pmc(db, a.id, anchor_date=day)
        db.commit()

        h = _history(db, a.id)
        assert h["tss_days"] == 20, (
            f"应有 20 天带 TSS, 实际 {h['tss_days']} 天 —— "
            f"增量重算把历史抹掉了 (这就是原 bug)"
        )
    finally:
        db.close()


def test_增量结果与全量重算一致():
    """anchor_date 只该影响写回范围, 不该影响算出来的数"""
    from cycling_coach.core.pmc import recompute_pmc
    from cycling_coach.data.sqlite import database as D

    db = D.SessionLocal()
    try:
        a = _make_athlete(db, "一致性测试")
        base = date.today() - timedelta(days=30)
        for i in range(12):
            _add_activity(db, a, base + timedelta(days=i * 2), tss=70)
        # 全量
        recompute_pmc(db, a.id)
        db.commit()
        full = {r.date: round(r.ctl or 0, 4)
                for r in db.query(__import__(
                    "cycling_coach.data.sqlite.models", fromlist=["DailyMetric"]
                ).DailyMetric).filter_by(athlete_id=a.id).all()}

        # 增量: 从最后一天开始写回
        last = base + timedelta(days=22)
        recompute_pmc(db, a.id, anchor_date=last)
        db.commit()
        inc = {r.date: round(r.ctl or 0, 4)
               for r in db.query(__import__(
                   "cycling_coach.data.sqlite.models", fromlist=["DailyMetric"]
               ).DailyMetric).filter_by(athlete_id=a.id).all()}

        for d in sorted(set(full) & set(inc)):
            if d >= last:
                continue
            assert abs(full[d] - inc[d]) < 1e-6, (
                f"{d}: 增量重算把历史 CTL 改了 {full[d]} -> {inc[d]}"
            )
    finally:
        db.close()


def test_日常单条导入不归零():
    """模拟真实用法: 已积累 8 周, 今天又导入一次, CTL 必须保持在合理区间"""
    from cycling_coach.core.pmc import recompute_pmc
    from cycling_coach.data.sqlite import database as D

    db = D.SessionLocal()
    try:
        a = _make_athlete(db, "日常使用")
        base = date.today() - timedelta(days=56)
        for w in range(8):
            for d in range(5):          # 每周练 5 次
                day = base + timedelta(days=w * 7 + d)
                _add_activity(db, a, day, tss=55 + (d % 3) * 15)
        recompute_pmc(db, a.id)
        db.commit()
        before = _history(db, a.id)["ctl"]

        assert before > 30, f"8 周训练后 CTL 应 >30, 实际 {before:.1f}"

        # 今天早上又骑了一次 —— 这是最容易触发 bug 的时刻
        today = date.today()
        _add_activity(db, a, today, tss=80, name="today")
        recompute_pmc(db, a.id, anchor_date=today)
        db.commit()
        after = _history(db, a.id)["ctl"]

        assert after > before * 0.7, (
            f"导入今天的训练后 CTL 从 {before:.1f} 掉到 {after:.1f} —— "
            f"增量重算把 8 周历史抹了 (原 bug)"
        )
    finally:
        db.close()


def test_TSB等于CTL减ATL():
    """自洽性: 每个点 TSB 必须 = CTL - ATL"""
    from cycling_coach.data.sqlite import database as D
    from cycling_coach.data.sqlite.models import DailyMetric

    db = D.SessionLocal()
    try:
        rows = db.query(DailyMetric).all()
        bad = [r for r in rows
               if r.ctl is not None and r.atl is not None
               and r.tsb is not None and abs((r.ctl - r.atl) - r.tsb) > 0.01]
        assert not bad, f"{len(bad)} 行的 TSB != CTL - ATL"
    finally:
        db.close()
