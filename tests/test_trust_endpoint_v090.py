"""V0.9.0: /api/trust — 把"我们不编数据"变成用户看得见的东西

## 为什么要做

核心竞争点是「性能齐平 + 开源免费」。**"免费"本身就是最大的不信任理由** ——
用户会想"免费的能靠谱吗"。

而 V0.9.0 这一周在 readiness / insights / race_prep / periodization 里
清掉了 10 处"编造看起来合理的数据"的 bug, **但用户一个都看不见**。
**诚实如果不可见, 就等于不存在。**

这个端点把内部约定摊开: 每个指标依据哪篇公开文献、当前缺什么、为什么缺。

## 关键: 自检页自己必须是真的

这个页面存在的唯一意义是"证明我们不编数据"。
**如果它自己撒谎, 它就证明不了任何东西, 反而成了新的不信任来源。**

所以下面这几条测试保护的自检页自己的准确性, 而不是被检查的业务逻辑。
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta


@pytest.fixture()
def trust_client():
    """一个**真的什么都没有**的库 + TestClient。

    ⚠️ 必须显式 rebind_engine —— TestClient(app) 用的不是 fixture 的库。
    我今天已经踩过两次"测试前提错了"(一次是前端重写被测逻辑,
    一次是 TestClient 没绑到空库), 这次不重复。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_trust")
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    db = SessionLocal()
    rebind_engine(str(db.get_bind().url))
    return TestClient(app), db


def test_self_check_reports_zero_for_empty_user(trust_client):
    """零数据用户: 0/5, 每一项都说清缺什么"""
    c, _db = trust_client
    r = c.get("/api/trust/self-check")
    assert r.status_code == 200
    d = r.json()
    assert d["n_available"] == 0, f"零数据却报 {d['n_available']} 个可用维度"
    assert d["n_total"] == 5
    for dim in d["dimensions"]:
        assert dim["available"] is False
        assert dim["why"], f"{dim['name']} 缺数据但没说为什么"


def test_every_dimension_explains_itself(trust_client):
    """自检页的价值就在于"说清楚", 所以每一项都必须有解释"""
    c, _db = trust_client
    for dim in c.get("/api/trust/self-check").json()["dimensions"]:
        assert dim.get("why"), f"{dim['name']} 没有说明"
        assert dim.get("name"), f"{dim['key']} 没有中文名"
        assert dim.get("weight", 0) > 0, f"{dim['name']} 权重为 0"


def test_policies_are_stated(trust_client):
    """必须明确写出"数据不足时我们会做什么" —— 这是整个自检页的核心"""
    c, _db = trust_client
    pol = c.get("/api/trust/self-check").json()["policies"]
    assert len(pol) >= 3
    joined = " ".join(pol)
    # 逐条核对关键承诺, 防止以后改文案时把承诺悄悄删掉
    assert "不评分" in joined or "不算" in joined
    assert "无数据" in joined
    assert "归一化" in joined
    assert "封顶" in joined


def test_metrics_have_citable_sources(trust_client):
    """开源的意义之一: 这些数字可以被任何人核对, 所以必须有出处"""
    c, _db = trust_client
    metrics = c.get("/api/trust/metrics").json()["metrics"]
    assert len(metrics) == 5
    for m in metrics:
        assert m["source"], f"{m['name']} 没有文献出处"
        assert len(m["source"]) > 15, f"{m['name']} 出处太简略"
        assert m.get("note")


def test_rpe_is_not_hardcoded_false(trust_client):
    """🔴 回归防护: RPE 维度不能写死 available: False

    原实现里它就是写死的 —— 于是用户**明明填了 RPE**, 自检页还是告诉他
    "缺 RPE"。自检页如果自己不准, 反而成了新的不信任来源。

    这条测试的价值: 有人(我)再把它写死时, 会红。
    """
    c, db = trust_client
    from cycling_coach.data.sqlite.models import DailyMetric
    from cycling_coach.core.profile import store as profile_store
    athlete = profile_store.get_or_create_athlete(db)
    today = datetime.utcnow().date()

    # 还没填
    d0 = c.get("/api/trust/self-check").json()
    rpe0 = [x for x in d0["dimensions"] if x["key"] == "rpe"][0]
    assert rpe0["available"] is False, "没填 RPE 却说可用"

    # 填了一条
    db.add(DailyMetric(athlete_id=athlete.id, date=today, tss=0, rpe=5))
    db.commit()
    d1 = c.get("/api/trust/self-check").json()
    rpe1 = [x for x in d1["dimensions"] if x["key"] == "rpe"][0]
    assert rpe1["available"] is True, (
        f"填了 RPE 但自检页说没有 —— 写死了 available: False (原 bug)"
    )
    # 只断言"说清楚了", 不绑死具体措辞 —— 措辞可以改, available 的
    # 正确性不能改。(第一版我断言文案里必须有 "RPE" 字样, 结果实现写的是
    # "已记录主观疲劳" —— 实现更好, 是我测试写歪了。)
    assert rpe1["why"] and rpe1["why"] != rpe0["why"], (
        "可用性翻转了但文案没变, 用户会看到自相矛盾的说明"
    )


def test_load_data_makes_dimensions_available(trust_client):
    """反向: 真有训练数据时, 自检页必须说可用

    自检页不能只会说"缺" —— 那它就跟零数据时一样没信息量。
    """
    import asyncio, tempfile
    from pathlib import Path
    c, db = trust_client
    from cycling_coach.core.profile import store as profile_store
    from cycling_coach.core.services.activity import ActivityService
    from tests.fit_fixtures import build_fit
    athlete = profile_store.get_or_create_athlete(db)
    athlete.ftp = 250
    db.commit()

    tmp = Path(tempfile.mkdtemp(prefix="cc_trust_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        for i in range(8):
            p = tmp / f"a{i}.fit"
            build_fit(p, duration_s=3600, avg_power=200, avg_hr=150, speed_mps=8.5,
                      start=datetime(2026, 9, 20, 6, 0) + timedelta(days=i))
            loop.run_until_complete(svc.upload(filename=p.name, file_bytes=p.read_bytes()))
    finally:
        loop.close()

    d = c.get("/api/trust/self-check").json()
    assert d["n_available"] >= 1, f"有 8 次训练却报 {d['n_available']} 个可用维度"
    tsb = [x for x in d["dimensions"] if x["key"] == "tsb"][0]
    assert tsb["available"] is True, "有带功率的训练却报训练平衡不可用"
