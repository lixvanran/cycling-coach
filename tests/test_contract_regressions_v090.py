"""V0.9.0 P0: 契约变更的跨层回归防护

## 这组测试在防什么

2026-10-05 我把 `compute_readiness` / `compute_training_state` 改成
数据不足时返回 `None`（诚实: 不用默认值拼一个看起来合理的分数）。

后端调用方我改了, 诚实性测试全绿, **全量 282 passed**。

但两处真实崩溃从别的方向漏了出来:

- **P0-1 前端**: `TrainingRadarChart` 读 `data.dimensions[k]`, 而零数据时
  后端真的返回 null → 整个「周期化」页面白屏。**类型还写着必填非空,
  tsc 永远不会提醒。**
- **P0-2 后端**: `rec_type = "none"` 被塞进表示"训练强度档位"的字段,
  `_TIER_ORDER.index("none")` → ValueError → 接口 500。

> **共同教训: 改函数契约不是改一个函数。**
> 后端实现 + 后端调用方 + 前端消费者 + 类型声明, 四层一起。
> 漏一层, bug 就搬到下一层, 而且藏得更深。

## 为什么这两条这么值钱

它们各自有**一条会立刻变红的测试**:
- P0-1: 类型必须允许 `| null` —— 谁把它改回必填就红
- P0-2: 零 readiness + 2 维覆盖 → 必须不抛异常
"""
from __future__ import annotations

import pytest


@pytest.fixture()
def db_with_athlete():
    from tests.conftest import use_temp_db
    use_temp_db("v090_contract")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    db = SessionLocal()
    return db, ps.get_or_create_athlete(db)


def test_none_tier_does_not_crash_generation(db_with_athlete, monkeypatch):
    """🔴 P0-2 回归: readiness=None + 2 维覆盖 → 不能抛 ValueError

    触发条件很窄, 所以必须构造出来, 不能指望普通流程撞上:
      1. _data_sufficiency 放行（数据量够）
      2. compute_readiness 返回 None（数据够门槛但关键维度算不出）
      3. 2 维可用 → 命中 MAX_TIER_BY_COVERAGE[2] → 走进封顶逻辑
         → _TIER_ORDER.index("none") → ValueError → HTTP 500

    `"none"` 的意思是"不给强度建议", 它**不是某个强度档位**。
    把"没有档位"塞进"档位"那一列, 就是这个 bug 的根。
    """
    db, athlete = db_with_athlete
    import cycling_coach.core.coaching.recommendations as R

    monkeypatch.setattr(
        R, "_data_sufficiency",
        lambda db, aid: {"sufficient": True, "n_activities": 8,
                         "span_days": 30, "reason": "probe"},
    )
    monkeypatch.setattr(R, "compute_readiness",
                        lambda db, aid: (None, {"rpe": 5, "phase": 8}))

    rec = R.generate_recommendations(db, athlete.id)   # 修复前: ValueError

    assert rec.readiness_score is None, "数据不足时不该有分数"
    assert rec.readiness_label == "数据不足"


def test_cap_still_applies_for_real_tiers(db_with_athlete, monkeypatch):
    """反向: 封顶逻辑对**真档位**必须照常生效

    修 P0-2 时很容易顺手把整个封顶判断删掉 —— 那样接口不崩了,
    但"缺 HRV 的用户被派去做 VO2max"这个原始 bug 就回来了。
    **这条保护的是修 bug 时别修过头。**
    """
    db, athlete = db_with_athlete
    import cycling_coach.core.coaching.recommendations as R

    monkeypatch.setattr(
        R, "_data_sufficiency",
        lambda db, aid: {"sufficient": True, "n_activities": 20,
                         "span_days": 60, "reason": "probe"},
    )
    # 分数极高但只有 2 维 → 会被封到 recovery 档
    monkeypatch.setattr(R, "compute_readiness",
                        lambda db, aid: (100, {"rpe": 10, "phase": 15}))

    rec = R.generate_recommendations(db, athlete.id)

    assert rec.readiness_score == 100
    # 2 维 → MAX_TIER_BY_COVERAGE[2] = "recovery", 而 100 分是 vo2
    # 封顶后不能还是 vo2
    assert "数据有限" in rec.readiness_label, (
        f"2 维数据拿 100 分却没封顶 —— 原始 bug 回来了: {rec.readiness_label}"
    )
    assert "VO2max" not in (rec.recommendations[0].detail if rec.recommendations else "")


def test_tier_order_covers_every_assignable_type(db_with_athlete):
    """结构性防护: 每个可能被赋给 rec_type 的值都必须在 _TIER_ORDER 里

    这是 P0-2 的**根因级**防护 —— 不是逐个 case 试, 而是断言
    "能赋的值 ⊆ 合法档位"。以后加新档位忘了登记, 这里就红。
    """
    import cycling_coach.core.coaching.recommendations as R
    import re
    from pathlib import Path

    src = Path(R.__file__).read_text()
    assigned = set(re.findall(r'rec_type\s*=\s*"(\w+)"', src))
    legal = set(R._TIER_ORDER)

    # "none" 是刻意的例外: 它表示"没有档位", 由 `rec_type != "none"` 排除
    illegal = assigned - legal - {"none"}
    assert not illegal, f"这些值会进 _TIER_ORDER.index() 但没登记: {illegal}"
    assert "none" in assigned, (
        "哨兵值 none 消失了 —— 如果它被换掉, 检查那条 != 'none' 还在不在"
    )


def test_empty_dimensions_does_not_reach_the_chart(db):
    """🔴 P0-1 回归: 后端零数据契约 —— dimensions 必须是 null, 且说清原因

    前端那条测试(phasesZeroData.test.ts)钉的是前端。
    这条钉的是**契约本身** —— 两边都钉住, 契约才跑不掉。
    """
    from cycling_coach.core.metrics.race_prep import compute_training_state
    from fastapi.testclient import TestClient

    # 函数层: 零数据 → None (诚实)
    assert compute_training_state(db, 1) is None

    # API 层: 必须把 None 翻译成结构化的"数据不足", 不能是 500,
    # 也不能是一个 dimensions={} 的假空对象
    from cycling_coach.api.main import app
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    rebind_engine(str(SessionLocal().get_bind().url))

    body = TestClient(app).get("/api/race-prep/training-state").json()
    assert body["data_sufficient"] is False
    assert body["dimensions"] is None, "零数据必须真的返回 null, 不能返回 {}"
    assert body["reason"], "数据不足必须说清为什么"
