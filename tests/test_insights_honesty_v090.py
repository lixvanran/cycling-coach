"""V0.9.0: insights 健康分的诚实性 — 零数据不许给"看起来不错"的分数

## 来源: Windows 真机验证, 不是猜的

本地 Agent 在真实 Windows 11 上打 `/api/insights/today` 打出来的:

    "summary": {"health_score": 95, "health_label": "良好", "warning": 1}
    "insights": [{"severity": "warning", "title": "过去 14 天无训练活动"}]

**系统自己说 warning, 同时给 95 分"良好"。**

复现后比报告更极端: 零数据时 insights 列表其实是**空的**, 却仍然 95 分 ——
因为 `100 - alert*20 - warning*5` 的基数写死 100, 零警告就是满分。

前端会把它渲染成 "训练健康分 95/100 良好", 下面还跟一行
"CTL 0 · TSB 0 · ramp 0"。给零数据用户**最直白的虚假肯定** ——
比 readiness 那个更刺眼, 那个至少还显示"数据不足"。

## 和 readiness 那三个 P0 是同一株病

    越没有数据 -> 扣分项越少 -> 分数越高

readiness 那边叫"编造默认值", 这边叫"扣分基数写死 100"。
同一���错误方向, 两个模块各长一只。所以判据统一用
`get_pmc_today` 的 `has_load_data`, 不各自发明"什么算有数据"。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def empty_athlete():
    """一个**真的什么都没有**的库。

    注意不能用别的模块的 fixture —— 之前踩过: 用了一个已经被导入过训练
    数据的库去测"零数据", 断言报出来的是误导性的结果。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_insights_honesty")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    return db, ath.id


# ---------------------------------------------------------------- 纯函数

def test_zero_data_returns_none_not_a_nice_score():
    """核心: 没有真实数据时给 None, 不给分数"""
    from cycling_coach.core.metrics.insights import compute_health_score

    score = compute_health_score({"alert": 0, "warning": 0}, has_load_data=False)
    assert score is None, f"零数据拿到 {score} 分"
    assert score != 95


def test_old_formula_would_have_given_95():
    """复现旧行为, 确认测试没写歪 —— 旧公式确实是 95"""
    old = 100 - 0 * 20 - 1 * 5
    assert old == 95
    # 而新逻辑在**有数据**时仍然保留这个规则(不在本轮改动范围)
    from cycling_coach.core.metrics.insights import compute_health_score
    assert compute_health_score({"alert": 0, "warning": 1}, True) == 95


def test_less_data_never_means_higher_score():
    """方向不能反: 没数据不是"满分", 是"算不出来" """
    from cycling_coach.core.metrics.insights import compute_health_score

    none = compute_health_score({"alert": 0, "warning": 0}, False)
    full = compute_health_score({"alert": 0, "warning": 0}, True)
    assert none is None
    assert full == 100
    assert none != full  # 不是"没数据=满分"


def test_scoring_unchanged_when_data_exists():
    """不得给老用户改分: 有数据时规则原样"""
    from cycling_coach.core.metrics.insights import compute_health_score

    assert compute_health_score({"alert": 0, "warning": 0}, True) == 100
    assert compute_health_score({"alert": 1, "warning": 0}, True) == 80
    assert compute_health_score({"alert": 0, "warning": 1}, True) == 95
    assert compute_health_score({"alert": 2, "warning": 2}, True) == 50
    assert compute_health_score({"alert": 10, "warning": 0}, True) == 0


def test_label_thresholds_unchanged():
    from cycling_coach.core.metrics.insights import _health_label

    assert _health_label(59) == "需要关注"
    assert _health_label(60) == "一般"
    assert _health_label(84) == "一般"
    assert _health_label(85) == "良好"
    assert _health_label(100) == "良好"


def test_label_handles_none():
    """None 必须有明确档位, 不能 `None < 60` 抛 TypeError

    原来那个 label 三元表达式是**内联**在返回 dict 里的, 在
    health_score 为 None 时会直接崩 —— 这是修完 None 之后**必然**会踩到的坑。
    """
    from cycling_coach.core.metrics.insights import _health_label

    assert _health_label(None) == "数据不足"
    assert _health_label(None) != "良好"


# ---------------------------------------------------------------- 端到端

def test_zero_data_athlete_endpoint_honest(empty_athlete):
    """端到端: 零数据运动员跑完整 compute_today_insights"""
    from cycling_coach.core.metrics.insights import compute_today_insights

    db, aid = empty_athlete
    bundle = compute_today_insights(db, aid)

    assert bundle.summary["health_score"] is None
    assert bundle.summary["health_label"] == "数据不足"
    # pcm 必须带上 has_load_data, 否则前端只能照着 0 显示
    assert bundle.pcm["has_load_data"] is False


def test_pcm_carries_has_load_data_flag(empty_athlete):
    """前端要靠这个标志决定要不要显示 "CTL x · TSB y" 那一行

    没有它的话, 零数据时 ctl/atl/tsb 都是 0, 前端会印出
    "CTL 0 · TSB 0" —— 用户读到的是"我的 CTL 是 0"(听起来像坏了),
    而不是"没有数据"。
    """
    from cycling_coach.core.metrics.insights import compute_today_insights

    db, aid = empty_athlete
    bundle = compute_today_insights(db, aid)
    assert "has_load_data" in bundle.pcm


# ---------------------------------------------------------------- 周复盘

def test_weekly_advice_direction_for_zero_data(empty_athlete):
    """零训练用户的"下周建议"不能是"累积 Z2 耐力"

    扫描器找到的第三处。`ctl=0` 会掉进 `elif ctl < 30` 分支, 于是对
    一个**从未训练过**的人说"重点是累积 Z2 耐力"。

    方向是反的: 他需要的不是"累积耐力", 而是"先去导入训练记录"。
    和 race_prep 57.5 分、insights 95 分是同一株病 ——
    缺失值退化成了具体值, 然后被当成真实信号。
    """
    from cycling_coach.core.metrics.insights import compute_weekly_review

    db, aid = empty_athlete
    advice = compute_weekly_review(db, aid)["next_week_advice"]
    assert "Z2 耐力" not in advice, f"零数据却建议累积耐力: {advice!r}"
    assert "CTL 偏低" not in advice, f"零数据却说 CTL 偏低: {advice!r}"
    assert "训练数据" in advice


def test_weekly_advice_unchanged_for_real_user():
    """反向: 有数据的用户建议必须照常给 (不得修过头)"""
    import asyncio
    import tempfile
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from tests.conftest import use_temp_db
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.metrics.insights import compute_weekly_review
    from tests.fit_fixtures import build_fit

    use_temp_db("v090_weekly_real")
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    tmp = Path(tempfile.mkdtemp(prefix="cc_wk_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    n = 0
    try:
        for w in range(3):
            for d in (0, 2, 4):
                p = tmp / f"a{n}.fit"
                build_fit(p, duration_s=3600, avg_power=200, avg_hr=150,
                          speed_mps=8.5,
                          start=datetime.now(timezone.utc).replace(tzinfo=None)
                          - timedelta(days=w * 7 + d))
                loop.run_until_complete(
                    svc.upload(filename=p.name, file_bytes=p.read_bytes()))
                n += 1
    finally:
        loop.close()

    advice = compute_weekly_review(db, ath.id)["next_week_advice"]
    assert "还没有真实训练数据" not in advice, (
        f"有 {n} 次训练却报无数据 —— 修过头了"
    )
    # 建议应该落在真实的 CTL 判断上
    assert advice and advice not in ("", "None")
