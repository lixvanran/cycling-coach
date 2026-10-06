"""V0.9.0: 周期化信号不再给零数据用户"训练处方"

## 这是 tools/scan_data_honesty.py 抓出来的

我今天写了个双跑差分扫描器(Verifier 建议的 item B), 它的输出:

    /api/phases/signals .avg_if_28d = 0 (真实数据: 0.49)
    /api/phases/signals .polarized_score_28d = 0 (真实数据: 0.6)

顺着查下去发现完整的一条链:

    PhaseSignals 默认 0.0
      → /api/phases/signals 返回 0.0
      → PhaseSignalsCard 拿 0.00 对照"理想 0.70-0.85" → 红色警告
      → recommendations.py: `if polarized < 0.5` → 命中
      → 零数据用户收到:
            "28d 极化评分 0.00, 偏离 Seiler 80/20"
            "增加 Z1-Z2 比例, 减少 '灰色地带' Z3-Z4"

**一份凭空来的训练处方。** 这正是 V0.9.0 一直在消灭的东西, 漏在这里了。

## 为什么这个特别阴险

用户完全看不出来有问题:
- 0.00 看起来像一个**真实的测量结果**, 不是缺失
- 建议听起来很专业, 引用了 Seiler 2010
- 而零数据用户是**新用户** —— 他们最先看到的就是这个
"""
from __future__ import annotations

import pytest


def test_signals_are_none_not_zero_when_no_data():
    """🔴 核心: 算不出来的信号必须是 None, 不是 0.0"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_sig_zero")
    from cycling_coach.core.metrics.periodization import detect_phase_signals
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    s = detect_phase_signals(db, a.id)

    assert s.avg_if_28d is None, f"零数据给了 IF={s.avg_if_28d}"
    assert s.polarized_score_28d is None, (
        f"零数据给了极化评分={s.polarized_score_28d} —— 这会被判成'极化不足'"
    )
    assert s.freq_7d is None
    assert s.load_achievement_7d is None

    # 但这两个 0 是**诚实**的
    assert s.streak_days == 0, "零训练的人连续天数确实是 0"
    assert s.weeks_since_taper == 0


def test_no_fake_prescription_when_polarization_unknown():
    """🔴 极化评分**算不出来**时, 不能拿 0 去对照阈值开处方

    ## 这条经过四轮才写对, 过程值得留着

    v1: 只测完全零数据 → **假绿**(generate_recommendations 有早退分支,
        走不到极化处方那段代码, 删掉守卫也测不出来)
    v2: 造"有数据但极化算不出" → 前提不成立
    v3: 换功率到 255W → 极化评分 0.6 ≥ 0.5, 仍然走不到
    v4: 换到超高强度 → **终于走到分支了**, 但此时给建议是**正确的**
        (用户真的极化不足), 我却断言它不该出现 → 测试一直红

    最终形态: 用 mock 精确构造"signals.polarized_score_28d is None",
    只测这一件事。**不跟真实数据场景耦合。**
    """
    from types import SimpleNamespace
    from tests.conftest import use_temp_db
    use_temp_db("v090_sig_none")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.coaching import recommendations as R

    # 精确构造"数据够门槛, 但极化评分算不出来"
    fake = SimpleNamespace(
        avg_if_28d=0.8, freq_7d=0.5, streak_days=3, weeks_since_taper=2,
        polarized_score_28d=None,       # ← 就是这个
        load_achievement_7d=0.9, warnings=[], hints=[],
    )
    import cycling_coach.core.coaching.recommendations as RM
    orig = RM.detect_phase_signals
    RM.detect_phase_signals = lambda db, aid: fake
    try:
        recs = RM._phase_signal_recommendations(fake)
    except AttributeError:
        # 处方那段逻辑如果没拆成独立函数, 直接验证判据本身
        assert fake.polarized_score_28d is None
        # None < 0.5 会 TypeError —— 所以任何"不加 None 守卫"的写法都过不了
        with pytest.raises(TypeError):
            _ = fake.polarized_score_28d < 0.5
    finally:
        RM.detect_phase_signals = orig

    # 真正的断言: 生产代码里那行必须带 None 守卫
    import inspect
    src = inspect.getsource(RM)
    for line in src.splitlines():
        if "polarized_score_28d < 0.5" in line and "is not None" not in line \
                and not line.strip().startswith("#"):
            pytest.fail(f"这行没有 None 守卫, 算不出来时会 TypeError: {line.strip()}")


def test_signals_endpoint_reports_insufficiency():
    """🔴 API 层要明说数据不足, 免得前端自己猜 0 是什么意思"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_sig_api")
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    rebind_engine(str(SessionLocal().get_bind().url))

    body = TestClient(app).get("/api/phases/signals").json()
    assert body["data_sufficient"] is False
    assert body["avg_if_28d"] is None
    assert body["polarized_score_28d"] is None


def test_real_user_still_gets_real_signals():
    """反向: 有数据的用户必须照常拿到数字

    防"修过头" —— 全改成 None 也能让上面三条全绿, 但产品就废了。
    """
    import asyncio, tempfile
    from pathlib import Path
    from datetime import datetime, timedelta
    from tests.conftest import use_temp_db
    use_temp_db("v090_sig_real")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.metrics.periodization import detect_phase_signals
    from tests.fit_fixtures import build_fit

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 260
    db.commit()
    tmp = Path(tempfile.mkdtemp(prefix="cc_sig_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        for i in range(12):
            p = tmp / f"s{i}.fit"
            build_fit(p, duration_s=3600, avg_power=210, avg_hr=152, speed_mps=8.5,
                      # ⚠️ 必须用**相对今天**的日期: detect_phase_signals 只看
                      # 最近 28 天。我第一版写死 2026-08-01, 结果训练全落在
                      # 28 天窗口之外, daily_rows 里只有零填充行 →
                      # avg_if_28d 算不出来 → 反向测试假红。
                      # **测试数据过期 = 假红**, 和测试前提错了一样的病。
                      start=datetime.utcnow() - timedelta(days=24 - i * 2))
            loop.run_until_complete(svc.upload(filename=p.name, file_bytes=p.read_bytes()))
    finally:
        loop.close()

    s = detect_phase_signals(db, a.id)
    assert s.avg_if_28d is not None, "12 次训练却没算出 IF"
    assert s.avg_if_28d > 0
    assert s.polarized_score_28d is not None
    assert 0 < s.polarized_score_28d <= 1


def test_all_signal_comparisons_guard_none():
    """🔴 每个 signals 字段的比较点都必须带 None 守卫

    ## 为什么加这条

    `avg_if_28d` 的 None 守卫我写过一次, 然后**被自己一次 git checkout
    冲掉了** —— 全量测试立刻报 TypeError 才暴露。

    根因: 这类守卫散落在多处, 没有任何机制保证它们**同时存在**。
    改字段类型时漏一个就是 TypeError, 而 TypeError 是运行时才炸,
    可能在用户面前炸, 也可能根本没跑到那条分支。

    所以改成一条**结构性断言**: 直接扫源码, 任何对这些字段的比较
    都必须带 `is not None`。漏了就红, 而不是等运行时炸。
    """
    import inspect
    import re
    from cycling_coach.core.coaching import recommendations as RM
    from cycling_coach.core.metrics import periodization as PZ

    FIELDS = ["polarized_score_28d", "avg_if_28d", "freq_7d",
              "load_achievement_7d"]
    # 形如  X < 0.5   /   X > 1.0   /   X >= 0.4  —— 比较而不是赋值/格式化
    # ⚠️ 第一版用了 (?<![\w.]) 负向后顾, 结果把 `signals.avg_if_28d > 1.0`
    # 整个排除了(因为 . 出现在字段名之前) —— 断言一次都没触发,
    # 变异注入后测试照样全绿。**这是个哑掉的断言。**
    #
    # 去掉后顾, 靠"整行必须有 is not None"来防误报。
    pattern = re.compile(
        r"(?:\b(?:signals\.)?(?:" + "|".join(FIELDS) + r"))\s*(?:<|>|<=|>=|==)\s*[\d.]+"
    )

    for mod in (RM, PZ):
        for i, line in enumerate(inspect.getsource(mod).splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if not pattern.search(line):
                continue
            assert "is not None" in line, (
                f"{mod.__name__}.py:{i} 这一行比较了 Optional 信号字段但没有 "
                f"None 守卫, 算不出来时会 TypeError:\n  {stripped}"
            )
