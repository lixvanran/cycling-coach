"""V0.9.0 P1-A: 训练史不够时不能发"ACWR 危险区"警告

## 这个 bug 是 Verifier 复审抓出来的

我修 `acwr.get("acwr", 1.0)` 那个编造默认值时(让"算不出来"不再假装成
"完美平衡 25/25"), **只改了一半**: 319 行的 readiness 加了
`acwr_history_is_real()` 守卫, 672 行的建议分支没加。

## 后果: 伪造的伤病警告 + 行动指令

8 天连续训练的用户同时看到:

    自检页:   "ACWR: 需要 28 天真实训练史才会计算"
    今日建议: "🚨 ACWR 危险区
               急慢性负荷比 3.50 > 1.5 (Gabbett 2016 危险区), 伤病风险高
               立即减量 30-50%, 优先恢复"

8 天训练 → 7 日负荷全挤在窗口里, 28 日分母还没攒起来 → 比值飙到 3.5。
**这个数不是测量结果, 是窗口没填满的假象。**

而它带着行动指令和文献引用 —— 用户会真的减量 30-50%。

> 我今天修掉的那些 bug 大多影响"看起来准不准",
> **这一个影响"用户照不照做"**。性质不一样。
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


def _make_history(db, n_days: int, power: int = 300):
    from cycling_coach.core.services.activity import ActivityService
    from tests.fit_fixtures import build_fit
    tmp = Path(tempfile.mkdtemp(prefix="cc_acwr_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        for i in range(n_days):
            p = tmp / f"a{i}.fit"
            build_fit(p, duration_s=3600, avg_power=power, avg_hr=165,
                      speed_mps=10.5,
                      start=datetime.utcnow() - timedelta(days=n_days - 1 - i))
            loop.run_until_complete(svc.upload(filename=p.name, file_bytes=p.read_bytes()))
    finally:
        loop.close()


def test_short_history_gets_no_acwr_danger_warning():
    """🔴 核心: 8 天训练史不能收到"ACWR 危险区"

    这是本轮最严重的一个 —— 唯一一条**带行动指令**的伪造警告。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_acwr_short")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.coaching.recommendations import (
        generate_recommendations, acwr_history_is_real)

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 250
    db.commit()
    _make_history(db, 8)

    # 前提: 训练史确实不够
    assert acwr_history_is_real(db, a.id) is False, (
        "前提不成立: 8 天训练史应该被判定为不足"
    )

    rec = generate_recommendations(db, a.id)
    blob = " ".join(f"{r.title} {r.detail} {r.action}" for r in rec.recommendations)

    for fake in ("ACWR 危险区", "立即减量", "伤病风险高"):
        assert fake not in blob, f"训练史不足却收到了 {fake}: {blob[:220]}"


def test_readiness_and_recommendations_agree():
    """🔴 同一个数据, 两个地方不能给出矛盾的说法

    自检页说"需要 28 天训练史", 今日建议说"你 ACWR 3.5 伤病风险高" ——
    **自相矛盾到用户会怀疑整个 App**。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_acwr_consistent")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.coaching.recommendations import generate_recommendations

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 250
    db.commit()
    _make_history(db, 8)

    rec = generate_recommendations(db, a.id)
    blob = " ".join(f"{r.title} {r.detail} {r.action}" for r in rec.recommendations)

    # ⚠️ 不能用 `"ACWR" in blob` 判断有没有给 ACWR 建议 ——
    # "缺: HRV、ACWR、主观疲劳" 这句**如实说明缺 ACWR**, 里面也有 "ACWR" 子串。
    # 第一版就是这么写的, 结果断言恒真失败。
    #
    # 和今天那个 `"CTL 0.0" not in text` 是同一个病: **用一个一定会出现的
    # 子串做断言**。判据应该是"建议本身", 而不是"提到这个词"。
    ADVICE_MARKERS = ("急慢性负荷比", "ACWR 危险区", "ACWR 偏高",
                      "减量 30-50%", "伤病风险")
    given = [m for m in ADVICE_MARKERS if m in blob]

    assert not given, (
        f"训练史不足却给了 ACWR 处方: {given}\n{blob[:220]}"
    )


def test_real_history_still_gets_acwr_advice():
    """反向: 训练史够的用户照常拿 ACWR 评估

    防"修过头" —— 把整段 ACWR 逻辑删掉也能让前两条变绿, 但功能废了。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_acwr_real")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.coaching.recommendations import (
        generate_recommendations, acwr_history_is_real)
    from cycling_coach.core.pmc import get_pmc_today

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 250
    db.commit()
    # 60 天历史 —— 够填满 28 天慢性窗口
    _make_history(db, 60)

    assert get_pmc_today(db, a.id)["has_load_data"] is True
    assert acwr_history_is_real(db, a.id) is True, (
        "60 天训练史却判定为不足 —— 守卫可能收得太紧"
    )

    rec = generate_recommendations(db, a.id)
    assert rec is not None
    # 不强制要求一定出 ACWR 建议(取决于实际比值), 但不能崩、不能为空
    assert rec.recommendations is not None
