"""V0.9.0: FIT 导入 → 指标计算 端到端测试 (具体数值断言)

## 为什么有这个文件

审计发现 2 个 P0 bug, 而当时 135 个测试全绿:
1. `fit_parser` 把 `total_elapsed_time` (FIT 规范: uint32 毫秒) 当秒用
   → 所有导入活动时长 1000× 虚高 → TSS 约 11× 虚高 → PMC / ACWR /
     dashboard / 周 TSS 全部失真
2. `normalized_power` 把稀疏采样零填充
   → 10s 采样时 30s 窗内 3 真值 + 27 个 0 → NP = 18 而不是 180
3. FIT 缺 session 汇总时静默返回 0 时长, 而 watcher 还报"导入成功"

**根因: 旧测试全部直接 `Activity(duration_s=3600)` 造数据, 完全绕开 parser。**
本文件用 `tests/fit_fixtures.py` 现场合成**数值完全已知**的 FIT,
断言**具体数值**而不是"不为空" —— 这样单位换算错了必然红。
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, ".")

from tests.fit_fixtures import build_fit  # noqa: E402

FTP = 250


@pytest.fixture(scope="module")
def tmpdir():
    d = Path(tempfile.mkdtemp(prefix="cc_fit_e2e_"))
    yield d
    # tmp 由 OS 回收


# ================================================================
# 1. parser 单位换算 (P0-1)
# ================================================================

class TestFitUnitConversion:
    """FIT 规范里的非人类单位必须换算, 否则下游全错"""

    def test_duration_ms_to_seconds(self, tmpdir):
        """total_elapsed_time 是毫秒 → 必须是秒

        60 分钟骑行: FIT 写 3,600,000 ms, parser 必须给 3600 s。
        修之前给 3,600,000 s (1000×)。
        """
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "dur.fit"
        truth = build_fit(p, duration_s=3600, avg_power=200)

        a = FitParser().parse_file(p)

        assert a.duration_s == 3600, (
            f"duration 应为 3600s, 实际 {a.duration_s} "
            f"(偏差 {a.duration_s / 3600:.0f}×)"
        )
        assert a.duration_s == truth["duration_s"]

    def test_lap_duration_ms_to_seconds(self, tmpdir):
        """lap 的 total_elapsed_time 同样是毫秒"""
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "lap.fit"
        build_fit(p, duration_s=1800, avg_power=180, with_session=False)

        a = FitParser().parse_file(p)

        assert len(a.laps) == 1, f"应有 1 个 lap, 实际 {len(a.laps)}"
        assert a.laps[0].duration_s == 1800, (
            f"lap duration 应为 1800s, 实际 {a.laps[0].duration_s}"
        )

    def test_lat_lon_semicircles_to_degrees(self, tmpdir):
        """position_lat/long 是 semicircles → 必须是度

        修之前 Sample.lat 存的是 372593185 (半圆原值),
        任何路线图都会画到地球另一边。
        """
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "gps.fit"
        build_fit(p, duration_s=60, avg_power=150)

        a = FitParser().parse_file(p)

        assert a.samples, "应该有 samples"
        lat = a.samples[0].lat
        lon = a.samples[0].lon
        assert lat is not None and -90 <= lat <= 90, f"纬度应在 ±90, 实际 {lat}"
        assert lon is not None and -180 <= lon <= 180, f"经度应在 ±180, 实际 {lon}"
        assert abs(lat - 31.2304) < 0.01, f"纬度应 ≈31.2304, 实际 {lat}"
        assert abs(lon - 121.4737) < 0.01, f"经度应 ≈121.4737, 实际 {lon}"

    def test_already_scaled_fields_not_double_converted(self, tmpdir):
        """fitparse 已处理 scale 的字段不能重复换算

        speed / altitude / distance / total_ascent 是 profile 里带
        scale+offset 的字段, fitparse 已经给人类单位了。
        """
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "scaled.fit"
        build_fit(p, duration_s=600, avg_power=180, speed_mps=8.0)

        a = FitParser().parse_file(p)

        s = a.samples[10]
        assert abs(s.speed - 8.0) < 0.01, f"speed 应为 8.0 m/s, 实际 {s.speed}"
        assert s.elevation is not None and 99 < s.elevation < 101, (
            f"altitude 应 ≈100m, 实际 {s.elevation}"
        )


# ================================================================
# 2. NP 在稀疏采样下正确 (P0-2)
# ================================================================

class TestNormalizedPowerSampling:
    """NP 必须在任何采样率下都正确"""

    @pytest.mark.parametrize("interval", [1, 2, 5, 10])
    def test_np_same_regardless_of_sample_rate(self, interval):
        """同样 60 分钟恒定 200W, 采样率 1/2/5/10Hz 的 NP 应该几乎一致

        修之前: 1Hz → 200, 10s → 18 (掉一个数量级)
        """
        from cycling_coach.core.metrics.power import normalized_power
        from cycling_coach.data.parsers.schema import Activity, Sample

        a = Activity(
            source="test",
            start_time=datetime(2026, 8, 1, 6, 0),
            duration_s=3600,
            samples=[
                Sample(t_offset=t, power=200)
                for t in range(0, 3600, interval)
            ],
        )
        np_val = normalized_power(a)

        assert np_val == 200, (
            f"恒定 200W 的 NP 应为 200 (采样间隔 {interval}s), 实际 {np_val}"
        )

    def test_np_steady_state_ignores_warmup(self):
        """标准间歇: 前 20 分钟 100W 暖身, 后 40 分钟 300W

        理论值: 4 次方均值中, 300W 段 (2340s) 占主导但 100W 段 (1230s)
        仍贡献 1e8 × 1230。手工算:
            ((1230×100^4 + 30×200^4 + 2340×300^4) / 3600)^0.25 ≈ 270
        这个数远低于 300 —— 正是 4 次方均值的作用: 高段拉高, 低段压低。
        """
        from cycling_coach.core.metrics.power import normalized_power
        from cycling_coach.data.parsers.schema import Activity, Sample

        samples = []
        for t in range(0, 1200):          # 20 min @ 100W
            samples.append(Sample(t_offset=t, power=100))
        for t in range(1200, 3600):       # 40 min @ 300W
            samples.append(Sample(t_offset=t, power=300))

        np_val = normalized_power(Activity(
            source="test", start_time=datetime(2026, 8, 1, 6, 0),
            duration_s=3600, samples=samples,
        ))

        assert 260 <= np_val <= 280, f"NP 应在 260~280 (理论 270), 实际 {np_val}"

    def test_np_4th_power_mean_dominates_peaks(self):
        """NP 用 4 次方均值 → 应该被高段拉高, 而不是等于算术平均

        这正是 NP 存在的意义: 40 分钟 300W + 20 分钟 100W,
        算术平均 200W, 但 NP 应该明显更高 (4 次方被 300 主导)。
        """
        from cycling_coach.core.metrics.power import normalized_power
        from cycling_coach.data.parsers.schema import Activity, Sample

        samples = [Sample(t_offset=t, power=100) for t in range(0, 1200)]
        samples += [Sample(t_offset=t, power=300) for t in range(1200, 3600)]
        a = Activity(
            source="test", start_time=datetime(2026, 8, 1, 6, 0),
            duration_s=3600, samples=samples,
        )

        np_val = normalized_power(a)
        arithmetic = 200  # (100*1200 + 300*2400) / 3600

        assert np_val > arithmetic, (
            f"NP({np_val}) 应高于算术平均({arithmetic}) — "
            f"4 次方均值被高段拉高, 这正是 NP 的意义"
        )
        assert np_val < 300, f"NP({np_val}) 不应超过最高功率 300W"


# ================================================================
# 3. session 缺失时不能静默返回 0 (P1 稳定性)
# ================================================================

class TestMissingSessionFallback:
    """缺 session 汇总的 FIT 必须回算, 不能返回全 0 却报成功"""

    def test_fallback_computes_duration_from_records(self, tmpdir):
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "nosession.fit"
        build_fit(p, duration_s=2400, avg_power=190, with_session=False, with_lap=False)

        a = FitParser().parse_file(p)

        assert a.duration_s > 0, (
            f"缺 session 时应从 record 回算时长, 实际 {a.duration_s}"
        )
        assert a.duration_s == 2400, f"应回算出 2400s, 实际 {a.duration_s}"

    def test_fallback_computes_avg_power_from_records(self, tmpdir):
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "nosession_pwr.fit"
        build_fit(p, duration_s=1200, avg_power=175, with_session=False, with_lap=False)

        a = FitParser().parse_file(p)

        assert a.avg_power is not None, "缺 session 时应回算 avg_power"
        assert a.avg_power == 175, f"应回算出 175W, 实际 {a.avg_power}"

    def test_fallback_computes_distance_from_speed(self, tmpdir):
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "nosession_dist.fit"
        build_fit(
            p, duration_s=1200, avg_power=200, speed_mps=8.0,
            with_session=False, with_lap=False,
        )

        a = FitParser().parse_file(p)

        assert a.distance_m is not None, "缺 session 时应回算距离"
        # 8 m/s × 1200s = 9600 m
        assert abs(a.distance_m - 9600) < 200, (
            f"应回算出 ≈9600m, 实际 {a.distance_m}"
        )

    def test_session_present_does_not_trigger_fallback(self, tmpdir):
        """有 session 时不能用兜底覆盖真实值"""
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "withsession.fit"
        build_fit(p, duration_s=900, avg_power=210)

        a = FitParser().parse_file(p)

        assert a.duration_s == 900
        assert a.avg_power == 210


# ================================================================
# 4. 端到端: FIT → Activity → TSS → PMC
# ================================================================

class TestFitToPmcEndToEnd:
    """完整链路: 解析 → 指标 → TSS → PMC 全部要落在合理区间"""

    def test_tss_in_sane_range(self, tmpdir):
        """1 小时 @ 200W, FTP 250 → TSS 应在 60-80

        公式: TSS = duration_h × NP × IF × 100
            = 1 × 200 × (200/250) × 100 = 80
        修之前 (duration 1000×) 会得到 ~900。
        """
        from cycling_coach.data.parsers.fit_parser import FitParser
        from cycling_coach.core.metrics.aggregator import compute_metrics

        p = tmpdir / "e2e.fit"
        build_fit(p, duration_s=3600, avg_power=200, avg_hr=150, speed_mps=8.5)

        a = FitParser().parse_file(p)
        a.avg_power = 200
        metrics = compute_metrics(a, FTP)
        tss = metrics.get("tss")

        assert tss is not None, f"应有 TSS, 实际 metrics={metrics}"
        assert 60 <= tss <= 85, f"TSS 应在 60~85 (理论 80), 实际 {tss}"

    def test_dashboard_volume_sane(self, tmpdir):
        """单次 2 小时骑行 → 时长 2.0h, 不是 2000h"""
        from cycling_coach.data.parsers.fit_parser import FitParser

        p = tmpdir / "twohour.fit"
        build_fit(p, duration_s=7200, avg_power=170)

        a = FitParser().parse_file(p)

        hours = a.duration_s / 3600
        assert hours == 2.0, f"2 小时骑行应算 2.0h, 实际 {hours}"

    def test_pmcurve_builds_from_fit_imports(self, tmpdir):
        """真端到端: FIT 文件 → ingest → DB → PMC

        这是最关键的一个测试 —— 之前所有测试都直接造 `Activity` 对象,
        整条 "文件 → parser → 指标 → 入库 → PMC" 链路零覆盖,
        所以 NP 零填充 / 缺 session 静默失败 这类 bug 才能一路绿灯。

        用 conftest.use_temp_db() 拿隔离 DB, 走真实的 ActivityService。
        """
        import asyncio

        from tests.conftest import use_temp_db

        # 顺序很重要: 必须先 rebind 再 import SessionLocal。
        # SessionLocal 是 module 级单例, 提前 import 会拿到旧 engine
        # (by-value import 陷阱 —— rebind_engine 只能补 sys.modules 上的引用,
        #  补不了本函数内的局部名字)。
        use_temp_db("fit_e2e_pmc")

        from cycling_coach.core.services.activity import ActivityService
        from cycling_coach.data.sqlite.database import SessionLocal
        from cycling_coach.core.pmc import recompute_pmc

        db = SessionLocal()

        # 设一个确定的 FTP, 让 TSS 可预测 (200W/250W → IF 0.8)
        from cycling_coach.core.profile import store as profile_store
        a = profile_store.get_or_create_athlete(db)
        a.ftp = FTP
        db.commit()

        svc = ActivityService(db)
        for day in range(3):
            p = tmpdir / f"e2e_{day}.fit"
            build_fit(
                p,
                duration_s=3600,
                avg_power=200,
                avg_hr=150,
                speed_mps=8.5,
                start=datetime(2026, 8, 1, 6, 0, tzinfo=timezone.utc)
                + timedelta(days=day),
            )
            asyncio.new_event_loop().run_until_complete(
                svc.upload(filename=f"e2e_{day}.fit", file_bytes=p.read_bytes())
            )

        athlete_id = a.id
        from cycling_coach.data.sqlite.models import Activity as Activity_DB
        rows = db.query(Activity_DB).filter_by(athlete_id=athlete_id).all()
        assert len(rows) == 3, f"应入库 3 条活动, 实际 {len(rows)}"

        # 逐条核对入库值 —— 不为空的断言没有意义
        for r in rows:
            assert r.duration_s == 3600, f"入库时长应为 3600s, 实际 {r.duration_s}"
            assert r.avg_power == 200, f"入库 avg_power 应为 200, 实际 {r.avg_power}"
            assert r.normalized_power == 200, (
                f"入库 NP 应为 200, 实际 {r.normalized_power}"
            )
            assert r.tss is not None and 60 <= r.tss <= 90, (
                f"入库 TSS 应在 60~90 (理论 80), 实际 {r.tss}"
            )

        # PMC 必须算出非零且在合理量级
        updated = recompute_pmc(db, athlete_id)
        assert updated > 0, "recompute_pmc 应更新 daily_metrics 行"

        from cycling_coach.data.sqlite.models import DailyMetric
        metrics = db.query(DailyMetric).filter_by(athlete_id=athlete_id).all()
        nonzero = [m for m in metrics if (m.ctl or 0) > 0]
        assert len(nonzero) >= 3, (
            f"3 天训练后至少 3 天 CTL 应 > 0, 实际 {len(nonzero)}"
        )
        for m in nonzero[:3]:
            assert 0 < m.ctl < 100, f"CTL 应在 0~100, 实际 {m.ctl}"
            # TSB = CTL - ATL。连续 3 天训练无休息, ATL 涨得比 CTL 快,
            # 所以 TSB **应该**是负的 (这正是"该加休息了"的信号)。
            # TrainingPeaks 上正常范围约 -50 ~ +30。
            assert -50 <= m.tsb <= 30, (
                f"TSB 应在 -50~30 (连续训练应为负), 实际 {m.tsb}"
            )
        db.close()

