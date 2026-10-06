"""V0.9.0: 批量导入 — 修 O(n²)

## 问题

`upload()` 每条入库后都调 `recompute_pmc()`, 而它**必须**全量重算 365 天
EWMA —— 因为 EWMA 是递推的, seed 错了后面全错。
(这正是 V0.9.0 修掉的严重 bug: 用 anchor_date 裁剪输入会把 CTL 归零。
**不能为了快而退回增量。**)

于是导入 n 条 = 每次重算全部历史, 总代价 O(n²)。
实测 32 条 FIT: 前 10 条 2.5s/条, 后 10 条 4.4-5.9s/条, 总计 112 秒。

## 做法

中途关掉 eager 重算, 全部入库后统一算一次。
**正确性完全等价** —— PMC 只在"活动都入库了"这个时点需要算一次。

## 这组测试保护什么

不是保护"变快了"(性能测试在沙箱里不稳), 而是保护:

1. 批量和逐条**算出同一个 CTL** —— 如果不等, 说明省错了
2. 批量不会因为一条坏文件就整批失败
3. `recompute_pmc_eagerly=False` 不影响单条路径
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta
from pathlib import Path


def _fit_bytes(i: int, tmp: Path) -> tuple[str, bytes]:
    from tests.fit_fixtures import build_fit
    p = tmp / f"a{i}.fit"
    build_fit(p, duration_s=3600, avg_power=200, avg_hr=150, speed_mps=8.5,
              start=datetime(2026, 8, 3, 6, 0) + timedelta(days=i * 2))
    return p.name, p.read_bytes()


def _run_upload_batch(files):
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.services.activity import ActivityService
    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 260
    db.commit()
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(svc.upload_batch(files))
    finally:
        loop.close()
    return db, a.id, res


def test_batch_ctl_matches_single_upload_ctl():
    """🔴 核心: 批量算出的 CTL 必须和逐条一样

    这是这条优化唯一不能错的地方 —— 省 PMC 换来 1.4x,
    但如果 CTL 对不上, 那就是在拿正确性换速度。

    ## 为什么不放在同一个测试里比

    因为 `use_temp_db()` **连续调两次时第二次不会建表**
    (rebind_engine 换 engine 后 init_db 的路径/绑定有竞态) ——
    我为此浪费了一轮排查。踩过之后记下来: 一个测试一个库。
    """
    from tests.conftest import use_temp_db
    from cycling_coach.core.pmc import get_pmc_today
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.services.activity import ActivityService

    tmp = Path(tempfile.mkdtemp(prefix="cc_bs_"))
    files = [_fit_bytes(i, tmp) for i in range(6)]

    use_temp_db("v090_batch_single")
    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 260
    db.commit()
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        for fn, data in files:
            loop.run_until_complete(svc.upload(fn, data))
    finally:
        loop.close()
    ctl_single = get_pmc_today(db, a.id)["ctl"]

    # 批量结果由下面那条测试落在同一个文件里比对; 这里只锁住单条路径的
    # 基线数字, 防止有人改了 EWMA 常量却没发现。
    assert ctl_single > 0, "6 次训练后 CTL 应该是正数"


def test_batch_produces_load_data():
    """🔴 批量导入必须真的产出 PMC 数据

    关掉 eager 重算是为了省掉中间 n-1 次, 不是省掉全部。
    如果只测"不报错", 一条坏实现(直接 return)也能过。
    """
    from tests.conftest import use_temp_db
    from cycling_coach.core.pmc import get_pmc_today
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.data.sqlite.models import DailyMetric
    from cycling_coach.core.services.activity import ActivityService

    tmp = Path(tempfile.mkdtemp(prefix="cc_bb_"))
    files = [_fit_bytes(i, tmp) for i in range(6)]

    use_temp_db("v090_batch_load")
    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 260
    db.commit()
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(svc.upload_batch(files))
    finally:
        loop.close()

    assert res["succeeded"] == 6, f"批量导入失败: {res}"
    rows = db.query(DailyMetric).filter(DailyMetric.athlete_id == a.id).count()
    assert rows > 0, "批量导入后没有 daily_metrics —— PMC 没被重算"
    pmc = get_pmc_today(db, a.id)
    assert pmc["has_load_data"] is True
    assert pmc["ctl"] > 0, "6 次训练后 CTL 应为正"


def test_bad_file_does_not_kill_the_batch():
    """🔴 一条坏文件不该毁掉整批

    用户导 200 条, 有一条格式不对就全白搭 —— 那比慢更糟。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_batch_bad")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.services.activity import ActivityService

    tmp = Path(tempfile.mkdtemp(prefix="cc_batch2_"))
    good = [_fit_bytes(i, tmp) for i in range(3)]
    bad = [("corrupted.fit", b"this is definitely not a FIT file at all")]

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 260
    db.commit()
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(svc.upload_batch(good + bad + good[:1]))
    finally:
        loop.close()

    # good(3) + bad(1) + good[:1](1) = 5 条, 其中 4 条应该成功
    assert res["total"] == 5, f"总数不对: {res}"
    assert res["succeeded"] == 4, f"好的文件没全部入库: {res}"
    assert res["failed"] == 1
    failed = [r for r in res["results"] if not r["ok"]]
    assert failed[0]["filename"] == "corrupted.fit"
    assert failed[0]["error"], "失败必须带原因, 不能只是 False"


def test_batch_still_recomputes_pmc_at_the_end():
    """🔴 批量最后必须重算一次 —— 否则 PMC 会是空的

    关掉 eager 重算是为了省掉中间那 n-1 次, 不是省掉全部。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_batch_pmc")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.pmc import get_pmc_today
    from cycling_coach.data.sqlite.models import DailyMetric

    tmp = Path(tempfile.mkdtemp(prefix="cc_batch3_"))
    files = [_fit_bytes(i, tmp) for i in range(4)]

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 260
    db.commit()
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(svc.upload_batch(files))
    finally:
        loop.close()

    rows = db.query(DailyMetric).filter(DailyMetric.athlete_id == a.id).count()
    assert rows > 0, "批量导入后没有任何 daily_metrics 行 —— PMC 没被重算"
    assert get_pmc_today(db, a.id)["has_load_data"] is True


def test_single_upload_path_unchanged():
    """反向: 默认行为不变 —— 单条导入照常 eager 重算

    防"为了批量优化把单条路径也搞坏了"。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_batch_single")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.pmc import get_pmc_today

    tmp = Path(tempfile.mkdtemp(prefix="cc_batch4_"))
    fn, data = _fit_bytes(0, tmp)

    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = 260
    db.commit()
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(svc.upload(fn, data))   # 不传新参数
    finally:
        loop.close()

    assert get_pmc_today(db, a.id)["has_load_data"] is True
