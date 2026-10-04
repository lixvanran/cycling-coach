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
