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


# ─────────────────────────────────────────────────────────────
# V0.9.0 P0-3: derive_phase 的调用方补漏
#
# 我改了 derive_phase 让它零数据返回 unknown, 但它有 4 个调用方,
# 我只处理了 context.py 一个。于是另外三处照样把 unknown / 0
# 当成真值发给用户。
#
# 关键教训: **改一个函数的契约, 要找齐它所有调用方。**
# grep 一次不算找齐 —— 还要问"这个值最后流到哪儿, 谁会渲染它"。
# ─────────────────────────────────────────────────────────────


def test_unknown_phase_numbers_are_none_not_zero(empty_athlete):
    """🔴 阶段推导的处方数字: 算不出来必须是 None, 不是 0

    0 是个**看起来合法的训练学数值** —— "目标 TSS 0 / 建议 0 周"
    看起来像一份很极端的训练处方, 而不是"我不知道"。
    """
    from cycling_coach.core.metrics.periodization import derive_phase
    db, aid = empty_athlete
    d = derive_phase(db, aid)
    assert d.suggested_type == "unknown"
    assert d.target_weekly_tss is None, (
        f"数据不足却给了 TSS 处方 {d.target_weekly_tss} —— 这是编数据"
    )
    assert d.target_weekly_tss_range is None
    assert d.weeks_recommended is None, (
        f"数据不足却建议练 {d.weeks_recommended} 周"
    )


def test_suggest_endpoint_does_not_500_on_empty(empty_athlete):
    """🔴 /api/phases/suggest 零数据不能 500

    改完类型后 `list(None)` 会 TypeError —— 这是**修一半的经典形态**:
    后端字段改诚实了, 序列化代码没跟上。
    """
    # ⚠️ 必须 rebind: TestClient(app) 用的不是 empty_athlete 那个库。
    #    empty_athlete 和 trained_athlete 都是 module 作用域, 共用
    #    scope="module" 的引擎 —— 不 rebind 就会读到 trained 的数据,
    #    于是 data_sufficient 变成 True, 测试假红。
    #    (这是我今天第四次犯"测试前提错了")
    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import rebind_engine
    from cycling_coach.api.main import app
    rebind_engine(str(empty_athlete[0].get_bind().url))

    r = TestClient(app).get("/api/phases/suggest")
    assert r.status_code == 200, f"零数据 500 了: {r.text[:200]}"
    j = r.json()
    assert j["data_sufficient"] is False
    assert j["target_weekly_tss"] is None
    assert j["target_weekly_tss_range"] is None
    assert j["weeks_recommended"] is None


def _all_texts(bundle) -> list[str]:
    """把 InsightsBundle 里所有会显示给用户的文字抓出来"""
    out = []
    for attr in ("insights", "recommendations", "alerts", "highlights"):
        for i in (getattr(bundle, attr, None) or []):
            out.append(f"{getattr(i, 'description', '')} {getattr(i, 'recommendation', '')} "
                       f"{getattr(i, 'title', '')}")
    return out


def test_insights_never_say_unknown_as_advice(empty_athlete):
    """🔴 洞察不能把 unknown 当建议发给用户

    曾经的输出:
      "考虑调整下一阶段类型为 unknown, 建议周目标 TSS = 0。"
    —— 把"算不出来"包装成一条建议, 还附了个很具体的数字。
    """
    # ⚠️ 目标函数是 compute_today_insights —— phase_mismatch 洞察在那里,
    #    不在 compute_weekly_review。我第一版一直在测错的函数, 所以怎么造
    #    数据都是 0 insights, 变异也杀不掉。**函数名对不上, 测的就是空气。**
    from cycling_coach.core.metrics.insights import compute_today_insights
    db, aid = empty_athlete
    bundle = compute_today_insights(db, aid)
    blob = " ".join(_all_texts(bundle))
    assert "unknown" not in blob, f"把 unknown 当建议发给了用户: {blob[:200]}"

    # ↓ 关键补充 (变异测试逼出来的)
    #
    # 第一版这条是**假绿**: 零数据时 compute_weekly_review 压根不生成任何
    # insights, 所以把守卫删掉它照样全绿 —— 测的是一个走不到的分支。
    #
    # 真正会踩到的是**部分数据**用户: 有一个 TrainingPhase 记录, 于是进入
    # phase_mismatch 分支, 但 derive_phase 因缺负荷数据返回 unknown。
    # 守卫只在这里才真正起作用。
    from datetime import datetime, timedelta
    from cycling_coach.data.sqlite.models import TrainingPhase
    now = datetime.utcnow()
    db.add(TrainingPhase(
        athlete_id=aid, name="基础期", phase_type="build",
        start_date=now - timedelta(days=7), end_date=now + timedelta(days=21),
        target_tss_week=300,
    ))
    db.commit()

    bundle2 = compute_today_insights(db, aid)
    blob2 = " ".join(_all_texts(bundle2))
    assert "unknown" not in blob2, (
        "有阶段记录但缺负荷数据时, 仍把 unknown 当建议发给了用户: " + blob2[:200]
    )


def test_real_user_still_gets_real_numbers(trained_athlete):
    """反向: 有数据的用户处方数字必须照常给出来

    防"修过头" —— 把所有数字都改成 None 也能让上面三条全绿, 但产品就废了。
    """
    from cycling_coach.core.metrics.periodization import derive_phase
    db, aid, _n = trained_athlete
    d = derive_phase(db, aid)
    assert d.suggested_type != "unknown", "多次训练却判成阶段不明"
    assert d.target_weekly_tss and d.target_weekly_tss > 0, "真实用户没拿到 TSS 处方"
    assert d.weeks_recommended and d.weeks_recommended > 0
