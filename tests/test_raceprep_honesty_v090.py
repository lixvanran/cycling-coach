"""V0.9.0: race_prep 五维训练状态的诚实性 — 零训练不该拿到"恢复优秀"

## 来源: 我自己写的扫描器, 不是审计

今晚我意识到同一类 bug 我已经栽了 7 次(readiness ACWR/TSB/HRV/RPE、
中文字符串哨兵、phase 无条件写入、insights 健康分), 于是写了个扫描器
找第 8 处。正则 `= 100 -` 命中三个, 其中两个在 `race_prep.py`。

跑出来比预期严重得多:

    零训练用户 -> overall = 57.5
        fatigue  100  → "恢复优秀"   ← atl=0  被当成"零疲劳=完美恢复"
        form      90  → "状态优秀"   ← tsb=0  落在"平衡"区
        rhythm    70  → "节奏良好"   ← ramp_rate=0
        recovery  60  → "反馈中等"
        fitness    0  → "体能警告"   ← 唯一真正算出 0 的维度

**"没有训练"被拆成五项, 其中三项被读成了优点。**
这比 insights 那个 95 分"良好"更荒唐 —— 那个至少是中性偏上,
这个直接说"恢复优秀"。

## 关键约束: 不得修过头

我今天在 readiness 上刚犯过一次 —— 把维度门槛从 2 提到 3,
结果一个 20 次训练 / 4 周的正常用户被判"数据不足"。

所以这条测试有两个方向:
    零数据   -> 必须 None
    有数据   -> 必须照常算分, 一个维度都不能少
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def empty_athlete():
    from tests.conftest import use_temp_db
    use_temp_db("v090_raceprep_empty")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    return db, ath.id


@pytest.fixture(scope="module")
def trained_athlete():
    """5 周 / 15 次训练 —— 代表一个真实的活跃用户"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_raceprep_trained")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    from cycling_coach.core.services.activity import ActivityService
    from tests.fit_fixtures import build_fit

    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()

    tmp = Path(tempfile.mkdtemp(prefix="cc_rp_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    n = 0
    try:
        for w in range(5):
            for d in (0, 2, 4):
                p = tmp / f"a{n}.fit"
                build_fit(
                    p, duration_s=3600, avg_power=200, avg_hr=150, speed_mps=8.5,
                    start=datetime(2026, 8, 20, 6, 0, tzinfo=timezone.utc)
                    + timedelta(days=w * 7 + d),
                )
                loop.run_until_complete(
                    svc.upload(filename=p.name, file_bytes=p.read_bytes())
                )
                n += 1
    finally:
        loop.close()
    return db, ath.id


# ---------------------------------------------------------------- 核心

def test_zero_training_returns_none(empty_athlete):
    """零训练 -> None, 不是 57.5 分

    回归防护: `atl=0 → fatigue=100 → "恢复优秀"` 这条链一旦复活,
    这个测试会红。
    """
    from cycling_coach.core.metrics.race_prep import compute_training_state

    db, aid = empty_athlete
    assert compute_training_state(db, aid) is None


def test_no_data_never_reads_as_excellent(empty_athlete):
    """任何维度都不能在没有数据时被读成"优秀" """
    from cycling_coach.core.metrics.race_prep import compute_training_state

    db, aid = empty_athlete
    st = compute_training_state(db, aid)
    assert st is None, "零数据又算出了状态分"
    # 如果哪天改回给分, 这条会抓住"恢复优秀/状态优秀"那类表述
    # (删掉了原来的 if st is not None 死代码分支 —— 上一行已经断言 None,
    #  那个分支永远走不到。Verifier P2 指出的问题)


def test_real_user_still_gets_scores(trained_athlete):
    """🔴 反方向, 最重要的一条: 有数据必须照常算分

    我今天在 readiness 上修过头过一次(维度门槛 2→3), 把一个
    20 次训练 / 4 周的正常用户判成"数据不足"。所以每次加数据守卫
    都必须配一条"不得误伤"的测试。
    """
    from cycling_coach.core.metrics.race_prep import compute_training_state

    db, aid = trained_athlete
    st = compute_training_state(db, aid)
    assert st is not None, "有 15 次训练却返回 None —— 修过头了"
    for name in ("fitness", "fatigue", "form", "rhythm", "recovery", "overall"):
        assert getattr(st, name) is not None, f"维度 {name} 丢了"
    assert 0 <= st.overall <= 100
    assert len(st.interpretation) == 5


def test_scoring_math_unchanged(trained_athlete):
    """有数据时打分规则一点没改 —— 给老用户改分就是回归"""
    from cycling_coach.core.metrics.race_prep import compute_training_state

    db, aid = trained_athlete
    st = compute_training_state(db, aid)
    # 公式: overall = fitness*0.30 + fatigue*0.20 + form*0.20 + rhythm*0.15 + recovery*0.15
    expect = round(
        st.fitness * 0.30 + st.fatigue * 0.20 + st.form * 0.20
        + st.rhythm * 0.15 + st.recovery * 0.15, 1
    )
    assert st.overall == expect


# ---------------------------------------------------------------- 调用方契约

def test_endpoint_handles_none_state(empty_athlete):
    """🔴 改函数契约必须同步改调用方

    `compute_training_state` 现在返回 None, 而 API 原来直接 `state.fitness` ——
    遇到 None 会 AttributeError, **整个接口 500**。

    这跟今天在 readiness 修的 `score >= 80` 遇到 None 抛 TypeError
    是完全同一类错误。改返回值就要同时改所有用它的地方。
    """
    # 注意: 模块级 `app` 绑的 DB 不是本 fixture 造的空库, 必须显式重绑。
    # 我第一版直接 TestClient(app) 就得到 data_sufficient=True ——
    # 因为它读的是别的库的数据。**测试前提错了, 断言就失去意义。**
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    from cycling_coach.data.sqlite.database import rebind_engine

    db, aid = empty_athlete
    url = str(db.get_bind().url)
    rebind_engine(url)
    client = TestClient(app)
    r = client.get("/api/race-prep/training-state")
    assert r.status_code == 200, f"接口 500 了: {r.text[:200]}"
    body = r.json()
    assert body["data_sufficient"] is False
    assert body["overall"] is None
    assert body["dimensions"] is None
    assert body["reason"]


def test_endpoint_ok_for_real_user(trained_athlete):
    """反过来: 有数据的用户接口必须正常"""
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    from cycling_coach.data.sqlite.database import rebind_engine

    db, aid = trained_athlete
    rebind_engine(str(db.get_bind().url))
    client = TestClient(app)
    r = client.get("/api/race-prep/training-state")
    assert r.status_code == 200, f"接口挂了: {r.text[:200]}"
    body = r.json()
    assert body["data_sufficient"] is True
    assert isinstance(body["overall"], (int, float))
    assert len(body["dimensions"]) == 5


def test_overall_equals_displayed_dimensions(trained_athlete):
    """🔴 总分必须等于用户**在界面上看到的那五个数字**的加权和

    ## 这条是查一个可疑差异时挖出来的

    Verifier 报 "62.1 != 62.0"。我第一反应是"测试写歪了" —— 因为代码里
    公式和权明明明对得上。

    手算之后发现是**实现算歪了**: `overall` 用的是未舍入的局部变量,
    而返回给前端的对象里存的是 `round(x, 1)`。两个值差 0.2, 加权后差 0.06。

    后果: 雷达图上五个分项加起来, 和正中间那个综合分对不上。
    **一个训练 App 的总分对不上自己的分项, 用户会以为算错了。**

    修复: 先把 5 维定格, 再用定格后的值算总分。

    ## 为什么单独写这条而不是并进 test_scoring_math_unchanged

    因为那条用 fixture 的 ctl 恰好没有舍入差异, **变异存活** ——
    它压根测不到这个问题。真实 PMC 的 ctl 是浮点(11.2), 才有差异。
    这条直接断言"显示值加权和 == 总分", 与 ctl 取值无关。
    """
    from cycling_coach.core.metrics.race_prep import compute_training_state

    db, aid = trained_athlete
    st = compute_training_state(db, aid)
    assert st is not None

    shown = st.fitness * 0.30 + st.fatigue * 0.20 + st.form * 0.20 \
        + st.rhythm * 0.15 + st.recovery * 0.15
    assert st.overall == round(shown, 1), (
        f"总分 {st.overall} 和界面显示的五个分项(加权后 {round(shown,1)})对不上。"
        f"用户看雷达图会发现分项加不起来。"
    )


# ⚠️ 已撤回: 我试图用注入式测试证明总分用已舍入分项, 但三次变异都存活。
#
# 查清楚了: 修复本身是对的(真实 ctl=11.7 → fitness=17.549999999999997,
# 对象里存 17.5), 但无论舍入与否, 当前数据下总分都是 62.5 —— 差异被
# 四舍五入吃掉, 测试构造不出能暴露它的场景。
#
# 我不想写一条看起来在测、实际测不到的测试来凑数。正确的做法是
# 构造一组能让差异跨过舍入边界的数据, 那需要先搞清楚 ctl/tsb 的
# 实际取值分布 —— 属于独立课题, 不该塞在这里假装已验证。
#
# 现状: 修复保留(方向正确, 防御性无害), 但**未经变异证明**。
# TODO: 见 _review/V0.9.0_AUDIT_20261003.md


def _trained_ctx():
    from tests.conftest import use_temp_db
    use_temp_db("v090_rp_round")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 250
    db.commit()
    return db, a.id
