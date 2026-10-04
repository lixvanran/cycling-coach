"""V0.9.0: derive_phase + AI phase 上下文 — 两处静默 bug

## 坑 1: derive_phase 把"没数据"当成"状态很差"

零数据时它返回 `base / "基础期 (低 CTL)"` —— 理由是 `ctl < 50`。
而 CTL=0 是因为**没有任何记录**, 不是真的低。

方向是反的: 用户需要的不是"你处于基础期", 而是"先去导入训练记录"。

我之前只在 `compute_readiness` 里加了一层守卫挡它。但 `derive_phase`
**还有另外两个调用方**, 其中一个是 AI 上下文 —— 也就是说零数据用户问
AI "我该练什么", 模型会拿到"低 CTL 基础期"当真实信息。
必须在源头修。

## 坑 2: AI phase 上下文恒为 None(字段名写错)

`context.py` 取的是 `_pick(info, "phase_type")` / `_pick(info, "label")`,
而 `PhaseDerivation` 上实际叫 `suggested_type` / `suggested_label`。
**两个都取不到**, 于是 AI 拿到的 phase 上下文恒为:

    {'phase_type': None, 'label': None}

这是**静默**的 —— 没有任何异常, 只是模型永远不知道用户在哪个阶段。
V0.9.0 修 AI 上下文时我只加了 `_pick()` 兼容 dict/object, **没核对字段名**。
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest


def _build_athlete_with_rides(db, n_weeks=5, per_week=3):
    """导入真实 FIT 训练, 走完整上传路径"""
    from cycling_coach.core.services.activity import ActivityService
    from tests.fit_fixtures import build_fit

    tmp = Path(tempfile.mkdtemp(prefix="cc_ph_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    n = 0
    try:
        for w in range(n_weeks):
            for d in range(0, 7, 7 // per_week):
                p = tmp / f"a{n}.fit"
                build_fit(
                    p, duration_s=3600, avg_power=200, avg_hr=150, speed_mps=8.5,
                    start=datetime(2026, 8, 20, 6, 0) + timedelta(days=w * 7 + d),
                )
                loop.run_until_complete(
                    svc.upload(filename=p.name, file_bytes=p.read_bytes())
                )
                n += 1
    finally:
        loop.close()
    return n


@pytest.fixture(scope="module")
def empty_athlete():
    from tests.conftest import use_temp_db
    use_temp_db("v090_phase_empty")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    return db, ath.id


@pytest.fixture(scope="module")
def trained_athlete():
    from tests.conftest import use_temp_db
    use_temp_db("v090_phase_trained")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    n = _build_athlete_with_rides(db)
    return db, ath.id, n


# ---------------------------------------------------------------- derive_phase

def test_zero_data_phase_is_unknown_not_base(empty_athlete):
    """零数据 -> unknown, 不是 '基础期 (低 CTL)'"""
    from cycling_coach.core.metrics.periodization import derive_phase

    db, aid = empty_athlete
    d = derive_phase(db, aid)
    assert d.suggested_type == "unknown", f"零数据被判成 {d.suggested_type!r}"
    assert d.suggested_label != "基础期 (低 CTL)"
    assert d.confidence == 0.0, "没有依据却给了置信度"
    assert d.reasons, "必须说明为什么判断不出来"


def test_real_user_gets_real_phase(trained_athlete):
    """反向: 有数据必须照常推导阶段 (不得修过头)"""
    from cycling_coach.core.metrics.periodization import derive_phase

    db, aid, n = trained_athlete
    d = derive_phase(db, aid)
    assert d.suggested_type != "unknown", (
        f"有 {n} 次训练却判成 unknown —— 修过头了"
    )
    assert d.suggested_type in ("base", "build", "peak", "taper", "recovery", "race")
    assert d.confidence > 0


def test_confidence_and_targets_sane_for_real_user(trained_athlete):
    db, aid, n = trained_athlete
    from cycling_coach.core.metrics.periodization import derive_phase
    d = derive_phase(db, aid)
    assert 0 <= d.confidence <= 1
    assert d.target_weekly_tss > 0, "真实用户应该拿到周目标 TSS"


# ---------------------------------------------------------------- AI 上下文

def test_ai_phase_context_field_names_are_correct(trained_athlete):
    """🔴 字段名写错导致 AI 拿到的 phase 上下文恒为 None

    `context.py` 取 `_pick(info, "phase_type")` / `_pick(info, "label")`,
    而 PhaseDerivation 上叫 `suggested_type` / `suggested_label`。
    这是**静默**的: 没有异常, 只是模型永远不知道用户在哪个阶段。
    """
    from cycling_coach.core.coaching.context import _build_phase_context

    db, aid, n = trained_athlete
    ctx = _build_phase_context(db, aid)
    assert ctx is not None
    assert ctx["phase_type"], f"有 {n} 次训练, AI 拿到的 phase_type 是 None"
    assert ctx["label"], "label 也是 None"
    assert ctx["phase_type"] in ("base", "build", "peak", "taper", "recovery", "race")


def test_ai_phase_context_marks_insufficient(empty_athlete):
    """零数据时不能把 unknown 当成真实阶段喂给模型"""
    from cycling_coach.core.coaching.context import _build_phase_context

    db, aid = empty_athlete
    ctx = _build_phase_context(db, aid)
    assert ctx is not None
    assert ctx.get("data_insufficient") is True, "零数据没标记为数据不足"
    assert ctx["phase_type"] is None
    assert "阶段" in ctx.get("note", "") or "数据" in ctx.get("note", "")
