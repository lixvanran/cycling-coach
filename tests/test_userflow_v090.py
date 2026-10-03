"""V0.9.0: 用户视角实测发现的 5 个问题 — 回归测试

## 来源

不是代码审计, 是**用 Windows 用户的方式走了一遍完整流程** (`--desktop` 静态模式,
导入 4 周训练, 排课, 问 AI) 撞出来的:

1. **AI 从来没见过用户的 PMC 数据**
   `get_pmc_today()` 返回 dict, 但 context.py 用 `getattr(pmc, "ctl")` → 永远 None。
   实测真实 API 是 ctl 34.9 / atl 80.2 / tsb -45.3, AI 拿到的是 0/0/0。
   更糟: AI 会因此反问用户"你的面板是不是显示 CTL=0, 跟说的对不上",
   把我们自己的 bug 甩给用户去检查同步。

2. **零数据用户拿到 82 分"极佳" + VO2max 高强度建议**
   每个维度无数据时都默认给中高分 (ACWR 缺数据默认 1.0 拿满分 25/25,
   TSB=0 拿满分 20/20)。数据越少分越高, 方向完全反了。

3. **Windows 干净模式开箱即坏**
   `start.py --desktop` 找 `apps/web/dist`, 但 vite outDir 是 `cycling_coach/static`。

4. **上传无去重** — 同一个文件传 3 次 = 3 条活动, PMC/TSS 被重复计算。
   (TP 的原话: "often duplicates workouts in calendar view")

5. **W' 平衡图 100% 500** — `profile_store.get_profile()` 这个函数根本不存在。
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, ".")


@pytest.fixture(scope="module")
def fresh_db():
    """全新空库 (模拟零数据新用户)

    module 级: 每个 test 重导 20 个 FIT 太慢。这些测试对数据只读,
    module 内共享一个空库没问题 (function 级会把已插的数据带进下一个 test)。
    """
    from tests.conftest import use_temp_db
    use_temp_db("v090_userflow")
    from cycling_coach.data.sqlite.database import SessionLocal
    db = SessionLocal()
    yield db
    db.close()


@pytest.fixture(scope="module")
def populated_db():
    """有 4 周训练数据的库 (独立于 fresh_db, 因为要写数据)"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_userflow_full")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    from cycling_coach.core.services.activity import ActivityService
    from tests.fit_fixtures import build_fit
    import asyncio

    db = SessionLocal()
    athlete = profile_store.get_or_create_athlete(db)
    athlete.ftp = 250
    db.commit()

    tmp = Path(tempfile.mkdtemp(prefix="cc_pop_"))
    plan = [(0, 60, 0.55), (1, 90, 0.72), (3, 75, 0.90), (4, 60, 1.02), (5, 210, 0.68)]
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    try:
        n = 0
        for w in range(4):
            for dow, mins, pct in plan:
                p = tmp / f"a{n:02d}.fit"
                build_fit(
                    p,
                    duration_s=mins * 60,
                    avg_power=int(250 * pct),
                    avg_hr=int(130 + 45 * pct),
                    speed_mps=7.5 + pct * 2,
                    start=datetime(2026, 9, 7, 6, 0, tzinfo=timezone.utc)
                    + timedelta(days=w * 7 + dow),
                )
                loop.run_until_complete(
                    svc.upload(filename=p.name, file_bytes=p.read_bytes())
                )
                n += 1
    finally:
        loop.close()

    from cycling_coach.core.pmc import recompute_pmc
    recompute_pmc(db, athlete.id)
    yield db
    db.close()


# ================================================================
# 1. AI 上下文必须拿到真实数据
# ================================================================

class TestAiContextGetsRealData:
    def test_pmc_context_not_none(self, populated_db):
        """AI 拿到的 PMC 必须是真实数值, 不是 None"""
        from cycling_coach.core.coaching.context import build_pmc_context

        ctx = build_pmc_context(populated_db, 1)

        assert ctx is not None, "PMC 上下文不该是 None"
        assert ctx["ctl"] is not None, f"ctl 应该是真实值, 实际 {ctx['ctl']}"
        assert ctx["atl"] is not None, f"atl 应该是真实值, 实际 {ctx['atl']}"
        assert ctx["tsb"] is not None, f"tsb 应该是真实值, 实际 {ctx['tsb']}"

    def test_pmc_context_matches_api(self, populated_db):
        """AI 看到的 PMC 必须和 API 返回的一致"""
        from cycling_coach.core.coaching.context import build_pmc_context
        from cycling_coach.core.pmc import get_pmc_today

        ctx = build_pmc_context(populated_db, 1)
        api = get_pmc_today(populated_db, 1)

        assert ctx["ctl"] == api["ctl"], (
            f"AI 看到 ctl={ctx['ctl']}, API 返回 {api['ctl']} — 两者必须一致"
        )
        assert ctx["tsb"] == api["tsb"], (
            f"AI 看到 tsb={ctx['tsb']}, API 返回 {api['tsb']} — 两者必须一致"
        )

    def test_acwr_context_not_all_none(self, populated_db):
        """ACWR 上下文也不能全 None (数据在 overview['today'] 里, 不在顶层)"""
        from cycling_coach.core.coaching.context import build_acwr_context

        ctx = build_acwr_context(populated_db, 1)

        assert ctx is not None
        assert ctx["acwr"] is not None, f"acwr 应有值, 实际 {ctx}"
        assert ctx["acute"] is not None

    def test_pick_helper_handles_both_types(self):
        """_pick 对 dict 和对象都要能用"""
        from cycling_coach.core.coaching.context import _pick

        assert _pick({"a": 1}, "a") == 1
        assert _pick({"a": 1}, "missing", "d") == "d"

        class Obj:
            a = 2
        assert _pick(Obj(), "a") == 2
        assert _pick(Obj(), "missing", "d") == "d"
        assert _pick(None, "a", "d") == "d"


# ================================================================
# 2. 数据不足不许给分
# ================================================================

class TestInsufficientDataNoFakeScore:
    def test_zero_data_readiness_is_none(self, fresh_db):
        """零数据 → readiness_score 必须是 None, 不是 0 也不是 82"""
        from cycling_coach.core.coaching.recommendations import generate_recommendations

        rec = generate_recommendations(fresh_db, 1)

        assert rec.readiness_score is None, (
            f"零数据不该给分, 实际给了 {rec.readiness_score} —— "
            f"这是骗用户 (0 会被渲染成'危险', 高分会被渲染成'极佳')"
        )
        assert rec.readiness_label == "数据不足"
        assert rec.recommended_workout_type == "none"
        assert rec.target_tss == 0, "数据不足时不该给 TSS 目标"

    def test_zero_data_no_high_intensity_advice(self, fresh_db):
        """零数据不该推荐高强度训练"""
        from cycling_coach.core.coaching.recommendations import generate_recommendations

        rec = generate_recommendations(fresh_db, 1)

        assert "vo2" not in rec.recommended_workout_type
        assert "高强度" not in rec.recommended_intensity
        assert "VO2max" not in rec.recommended_intensity

    def test_zero_data_tells_user_what_to_do(self, fresh_db):
        """要告诉用户缺什么、怎么补"""
        from cycling_coach.core.coaching.recommendations import generate_recommendations

        rec = generate_recommendations(fresh_db, 1)

        assert len(rec.recommendations) > 0, "应该给'怎么才能算'的指引"
        texts = " ".join(r.title + r.detail + (r.action or "") for r in rec.recommendations)
        assert "训练" in texts or "数据" in texts
        suff = rec.signals_summary.get("data_sufficiency") or {}
        assert suff.get("sufficient") is False
        assert suff.get("n_activities") == 0

    def test_readiness_endpoint_agrees(self, fresh_db):
        """/api/recommendations/readiness 也要返回 null, 不能只改一处"""
        from fastapi.testclient import TestClient
        from cycling_coach.api.main import app

        with TestClient(app) as c:
            r = c.get("/api/recommendations/readiness")

        assert r.status_code == 200
        d = r.json()
        assert d["readiness_score"] is None, f"端点应返回 null, 实际 {d['readiness_score']}"
        assert d["readiness_label"] == "数据不足"

    def test_with_enough_data_score_is_returned(self, populated_db):
        """数据够了就该正常给分 (别把功能改坏了)"""
        from cycling_coach.core.coaching.recommendations import generate_recommendations

        rec = generate_recommendations(populated_db, 1)

        assert rec.readiness_score is not None
        assert isinstance(rec.readiness_score, int)
        assert 0 <= rec.readiness_score <= 100
        assert rec.readiness_label != "数据不足"

    def test_score_not_higher_with_less_data(self, fresh_db, populated_db):
        """核心不变量: 数据越少, 分数不该越高"""
        from cycling_coach.core.coaching.recommendations import generate_recommendations

        empty = generate_recommendations(fresh_db, 1)
        full = generate_recommendations(populated_db, 1)

        # 空数据不是"高分"也不是"低分", 是"算不出"
        assert empty.readiness_score is None
        assert full.readiness_score is not None
        assert full.readiness_score < 100


# ================================================================
# 3. Windows 静态路径
# ================================================================

class TestWindowsDesktopStaticPath:
    def test_start_py_covers_vite_outdir(self):
        """start.py 的静态目录候选必须覆盖 vite 的 outDir

        这是之前开箱即坏的根因: vite build 输出到 cycling_coach/static,
        而 start.py --desktop 只找 apps/web/dist。
        """
        vite = Path("apps/web/vite.config.ts").read_text(encoding="utf-8")
        start = Path("tools/start.py").read_text(encoding="utf-8")
        assert "../../cycling_coach/static" in vite, "vite outDir 变了?"
        assert "_STATIC_CANDIDATES" in start, "start.py 应定义多候选路径"
        assert "cycling_coach" in start and "static" in start, (
            "start.py 的候选路径没覆盖 cycling_coach/static (vite 实际输出位置)"
        )
        assert 'FRONTEND_DIR / "dist"' in start, (
            "应保留 apps/web/dist 作为兼容候选"
        )
        assert "def find_frontend_dist" in start

    def test_start_py_no_longer_uses_hardcoded_dist_only(self):
        """--desktop 的两处校验都该走 find_frontend_dist(), 而不是各自硬编码路径"""
        src = Path("tools/start.py").read_text(encoding="utf-8")
        assert src.count("find_frontend_dist()") >= 3, (
            "install 校验、启动校验、列表处都该用 find_frontend_dist()"
        )
        # 两处 --desktop 校验应该都是 frontend_dist = find_frontend_dist()
        assert src.count("frontend_dist = find_frontend_dist()") >= 2
        assert "frontend_dist = FRONTEND_DIR" not in src, (
            "还有地方硬编码 FRONTEND_DIR/dist, 会重现开箱即坏"
        )

    def test_start_bat_defaults_to_desktop(self):
        """start.bat 默认应走干净模式 (不要求用户装 Node)"""
        bat = Path("tools/start.bat").read_text(encoding="utf-8", errors="replace")
        assert "--desktop" in bat, (
            "start.bat 默认应加 --desktop, 否则 Windows 用户被迫装 Node/pnpm"
        )


# ================================================================
# 4. 上传去重
# ================================================================

@pytest.fixture()
def write_db():
    """可写的干净库 (去重测试要插数据, 不能用 module 级共享库)"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_dedup")
    from cycling_coach.data.sqlite.database import SessionLocal
    db = SessionLocal()
    yield db
    db.close()


class TestUploadDeduplication:
    def test_same_file_twice_creates_one_activity(self, write_db):
        from cycling_coach.core.profile import store as profile_store
        from cycling_coach.core.services.activity import ActivityService
        from cycling_coach.data.sqlite.models import Activity as DBActivity
        from tests.fit_fixtures import build_fit
        import asyncio

        profile_store.get_or_create_athlete(write_db)
        p = Path(tempfile.mkdtemp()) / "dup.fit"
        build_fit(p, duration_s=3600, avg_power=200)

        svc = ActivityService(write_db)
        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(
                svc.upload(filename="dup.fit", file_bytes=p.read_bytes())
            )
            r2 = loop.run_until_complete(
                svc.upload(filename="dup.fit", file_bytes=p.read_bytes())
            )
        finally:
            loop.close()

        n = write_db.query(DBActivity).count()
        assert n == 1, f"同一个文件传两次应只有 1 条活动, 实际 {n} 条"
        assert r2.get("duplicate") is True, "第二次应标记 duplicate"
        assert r2["id"] == r1["id"], "duplicate 应指向原活动"
        assert r2.get("message"), "duplicate 应给用户一句说明"

    def test_different_files_both_kept(self, write_db):
        from cycling_coach.core.profile import store as profile_store
        from cycling_coach.core.services.activity import ActivityService
        from cycling_coach.data.sqlite.models import Activity as DBActivity
        from tests.fit_fixtures import build_fit
        from datetime import datetime as dt, timezone as tz
        import asyncio

        profile_store.get_or_create_athlete(write_db)
        tmp = Path(tempfile.mkdtemp())
        p1 = tmp / "a.fit"
        p2 = tmp / "b.fit"
        build_fit(p1, duration_s=3600, avg_power=200)
        build_fit(p2, duration_s=3600, avg_power=200,
                  start=dt(2026, 9, 8, 6, 0, tzinfo=tz.utc))

        svc = ActivityService(write_db)
        loop = asyncio.new_event_loop()
        try:
            r1 = loop.run_until_complete(svc.upload(filename="a.fit", file_bytes=p1.read_bytes()))
            r2 = loop.run_until_complete(svc.upload(filename="b.fit", file_bytes=p2.read_bytes()))
        finally:
            loop.close()

        assert write_db.query(DBActivity).count() == 2
        assert r2.get("duplicate") is not True, "不同文件不该被判为重复"

    def test_sha256_stored(self, populated_db):
        from cycling_coach.data.sqlite.models import Activity as DBActivity

        rows = populated_db.query(DBActivity).all()
        assert rows, "应该有活动"
        for r in rows[:3]:
            assert r.file_sha256, f"活动 {r.id} 没存 sha256"
            assert len(r.file_sha256) == 64

    def test_frontend_handles_duplicate_flag(self):
        """前端要认 duplicate 响应, 否则用户点了没反应"""
        api = Path("apps/web/src/lib/api.ts").read_text(encoding="utf-8")
        page = Path("apps/web/src/pages/ImportPage.tsx").read_text(encoding="utf-8")
        assert "duplicate" in api, "api.ts 类型里该有 duplicate"
        assert "r.duplicate" in page, "ImportPage 该处理 duplicate 响应"


# ================================================================
# 5. W' 平衡图不 500
# ================================================================

class TestWbalDoesNotCrash:
    def test_get_profile_does_not_exist(self):
        """确认根因: store 里确实没有 get_profile (否则我改错方向了)"""
        from cycling_coach.core.profile import store
        assert not hasattr(store, "get_profile"), (
            "store.get_profile 又出现了, 那 get_wbal 的调用方式要重新看"
        )

    def test_wbal_endpoint_returns_200(self, populated_db):
        from fastapi.testclient import TestClient
        from cycling_coach.api.main import app

        with TestClient(app) as c:
            r = c.get("/api/activities/1/wbal")

        assert r.status_code == 200, f"wbal 不该 500: {r.status_code} {r.text[:200]}"
        d = r.json()
        assert "wbal_curve" in d
        assert d.get("cp", 0) > 0, "应该能定出 CP"

    def test_wbal_with_explicit_cp_still_works(self, populated_db):
        from fastapi.testclient import TestClient
        from cycling_coach.api.main import app

        with TestClient(app) as c:
            r = c.get("/api/activities/1/wbal?cp=260&w_prime=20000")

        assert r.status_code == 200
        assert r.json()["cp"] == 260
