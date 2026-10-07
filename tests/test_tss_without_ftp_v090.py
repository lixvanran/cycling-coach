"""V0.9.0: 没测过 FTP 的用户也必须能拿到训练负荷

## 这是 V0.9.0-07 揭开的洞

占位车手不再带假 FTP(=250)之后, 暴露了一条一直存在的路径:

    compute_metrics(ftp=None)
      → intensity_factor(np, None)      -> None
      → training_stress_score(..., None) -> None
      → metrics["tss"] = None
      → PMC 判定 has_load_data = False
      → 界面: "还没有带功率的训练记录"

**用户明明刚导入了一条 200W 的训练。**

## 为什么不能接受"算不出就算了"

FTP 确实是 TSS 的基准(IF = NP/FTP)。但我们本来就会估算 ——
`curve.estimate_ftp()` 一直都在 aggregator 里, 只是一直没接上。

> 铁律的本意是"宁可说算不出来, 也不要自信地给错建议",
> **不是"算不出来就什么都不做"**。
>
> 正确做法: 用估算值算, **并且明确标记这是估算的**。
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


def _import_rides(n: int = 3):
    """用当前 rebind 后的库导入几条训练(不指定 FTP 的场景)"""
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.services.activity import ActivityService
    from tests.fit_fixtures import build_fit
    tmp = Path(tempfile.mkdtemp(prefix="cc_noftp_"))
    svc = ActivityService(SessionLocal())
    loop = asyncio.new_event_loop()
    try:
        for i in range(n):
            p = tmp / f"a{i}.fit"
            build_fit(p, duration_s=3600, avg_power=200, avg_hr=150,
                      speed_mps=8.5,
                      start=datetime.utcnow() - timedelta(days=n - i))
            loop.run_until_complete(svc.upload(p.name, p.read_bytes()))
    finally:
        loop.close()


def test_tss_computed_with_estimated_ftp():
    """🔴 核心: 没测 FTP 也要有 TSS, 并且标明用的是估算值"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_tss_noftp")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.data.sqlite.models import Activity
    from cycling_coach.core.pmc import get_pmc_today

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    assert a.ftp is None, "前提不成立: 占位车手不该再有假 FTP"

    _import_rides(3)

    act = db.query(Activity).first()
    m = act.metrics or {}
    assert m.get("tss") is not None and m.get("tss") > 0, (
        f"FTP 为 None 时 TSS={m.get('tss')} —— 用户导入成功却拿不到训练负荷"
    )
    assert m.get("intensity_factor") is not None
    # 诚实: 必须标明这次用的是估算 FTP
    assert m.get("tss_uses_estimated_ftp") is True
    assert m.get("ftp_used_for_tss"), "应该说清楚实际用了哪个 FTP"


def test_pmc_sees_load_data_without_explicit_ftp():
    """🔴 反向: PMC 必须认这批训练 —— 否则界面说"你没有带功率的训练记录" """
    from tests.conftest import use_temp_db
    use_temp_db("v090_tss_pmc")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.pmc import get_pmc_today

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    _import_rides(4)

    pmc = get_pmc_today(db, a.id)
    assert pmc["has_load_data"] is True, (
        "有 TSS 的训练被判成'无负荷数据' —— 用户会看到"
        "'还没有带功率的训练记录', 而他明明刚导入过"
    )
    assert pmc["ctl"] > 0


def test_real_ftp_takes_precedence():
    """反向: 用户测了真实 FTP 时必须用它, 不能用估算值"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_tss_realftp")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.data.sqlite.models import Activity
    from cycling_coach.core.services.activity import ActivityService
    from tests.fit_fixtures import build_fit

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 300          # 真实 FTP
    db.commit()

    tmp = Path(tempfile.mkdtemp(prefix="cc_realtftp_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        p = tmp / "a.fit"
        build_fit(p, duration_s=3600, avg_power=200, avg_hr=150, speed_mps=8.5,
                  start=datetime.utcnow() - timedelta(days=2))
        loop.run_until_complete(svc.upload(p.name, p.read_bytes()))
    finally:
        loop.close()

    m = db.query(Activity).first().metrics or {}
    assert m.get("ftp_used_for_tss") == 300, "真实 FTP 应该优先于估算值"
    assert m.get("tss_uses_estimated_ftp") is False
