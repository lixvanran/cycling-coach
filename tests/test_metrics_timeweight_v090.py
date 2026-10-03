"""V0.9.0: 指标的时间加权测试 —— 锁死"1 样本 = 1 秒"这一类 bug

## 背景

TP (TrainingPeaks) 用户最常见的投诉之一是:
  "Zones for running are waaayyy off from my actual zones"
  "doesn't import elevation correctly from Garmin and you have to correct it
   after every run"

翻译成工程语言就是**时间/数值在稀疏采样下算错**。

本项目也有同一类问题 —— 审计发现:
- `normalized_power`  零填充 → 10s 采样 NP 只有真值的 1/10
- `power_zones`       `mask.sum()` 数样本当秒 → 少算 10 倍
- `power_zones_detailed` 同上 + `total_kj` 只加功率不加时间
- `hr_zones`          同上
- `pa_hr_decoupling`  `len(valid) < 1800` 门槛 → 1 小时骑行被当 6 分钟拒掉

根因都是同一个隐含假设: **每个样本代表 1 秒**。
1Hz 采样时成立, 任何非 1Hz 设备 / FIT 丢样本都不成立。

## 本文件的策略

对**每个**指标做同一件事: 造一份"1 小时恒定输出"的骑行,
分别用 1Hz / 2s / 5s / 10s 采样生成, 断言**结果完全一致**。
只要任何一处还假设 1Hz, 这个测试就红。
"""
from __future__ import annotations

import sys
from datetime import datetime

import pytest

sys.path.insert(0, ".")

FTP = 250
MAX_HR = 190


def _ride(duration_s: int, power: int, hr: int, interval_s: int, cadence: int = 88):
    from cycling_coach.data.parsers.schema import Activity, Sample

    return Activity(
        source="test",
        start_time=datetime(2026, 8, 1, 6, 0),
        duration_s=duration_s,
        samples=[
            Sample(
                t_offset=t,
                power=power,
                hr=hr,
                cadence=cadence,
                speed=8.5,
                elevation=100.0,
            )
            for t in range(0, duration_s, interval_s)
        ],
    )


# ================================================================
# power_zones
# ================================================================

class TestPowerZonesTimeWeighted:
    @pytest.mark.parametrize("iv", [1, 2, 5, 10])
    def test_zones_same_regardless_of_sample_rate(self, iv):
        """1 小时恒定 250W (=100% FTP, 落在 Z4 threshold 90-105%)

        期望 Z4 = 3600 秒, 其他区 = 0。
        老代码: 10s 采样时 Z4 = 360 (少算 10 倍)
        """
        from cycling_coach.core.metrics.power import power_zones

        a = _ride(3600, FTP, 150, iv)
        z = power_zones(a, FTP)

        assert z["Z4"] == 3600, (
            f"采样 {iv}s: Z4 应为 3600 秒, 实际 {z['Z4']} "
            f"(偏差 {3600 / max(z['Z4'], 1):.1f}×)"
        )
        assert sum(z.values()) == 3600, f"各区秒数之和应等于骑行时长 3600, 实际 {sum(z.values())}"

    @pytest.mark.parametrize("iv", [1, 10])
    def test_z4_dominant_interval_is_accurate(self, iv):
        """Z2 (55-75% FTP) 20 分钟 + Z4 (90-105%) 40 分钟"""
        from cycling_coach.core.metrics.power import power_zones
        from cycling_coach.data.parsers.schema import Activity, Sample

        samples = []
        for t in range(0, 1200):
            samples.append(Sample(t_offset=t, power=int(FTP * 0.65), hr=140))
        for t in range(1200, 3600):
            samples.append(Sample(t_offset=t, power=int(FTP * 1.0), hr=165))
        a = Activity(
            source="test", start_time=datetime(2026, 8, 1, 6, 0),
            duration_s=3600,
            samples=[s for k, s in enumerate(samples) if k % iv == 0],
        )

        z = power_zones(a, FTP)
        assert 1150 <= z["Z2"] <= 1250, f"Z2 应 ≈1200 秒, 实际 {z['Z2']}"
        assert 2350 <= z["Z4"] <= 2450, f"Z4 应 ≈2400 秒, 实际 {z['Z4']}"


# ================================================================
# power_zones_detailed (+ total_kj)
# ================================================================

class TestPowerZonesDetailedTimeWeighted:
    @pytest.mark.parametrize("iv", [1, 10])
    def test_total_seconds_and_kj(self, iv):
        """1 小时 250W:
        - total_seconds = 3600
        - total_kj = 250W × 3600s / 1000 = 900 kJ
        """
        from cycling_coach.core.metrics.power import power_zones_detailed

        a = _ride(3600, FTP, 150, iv)
        a.distance_m = 30600.0
        r = power_zones_detailed(a, FTP)

        assert r["total_seconds"] == 3600, (
            f"采样 {iv}s: total_seconds 应为 3600, 实际 {r['total_seconds']}"
        )
        # 功 = 功率 × 时间。老代码 sum(功率)/1000, 10s 采样只算到 90 kJ。
        assert 890 <= r["total_kj"] <= 910, (
            f"total_kj 应 ≈900 (250W×1h), 实际 {r['total_kj']} "
            f"— 焦耳必须 = 功率 × 时间, 不能只加功率"
        )

    @pytest.mark.parametrize("iv", [1, 10])
    def test_sweet_spot_and_above_ftp(self, iv):
        """甜区 (88-94% FTP) 20 分钟 + 高于 FTP 40 分钟"""
        from cycling_coach.core.metrics.power import power_zones_detailed
        from cycling_coach.data.parsers.schema import Activity, Sample

        samples = []
        for t in range(0, 1200):
            samples.append(Sample(t_offset=t, power=int(FTP * 0.90), hr=150))
        for t in range(1200, 3600):
            samples.append(Sample(t_offset=t, power=int(FTP * 1.10), hr=170))
        a = Activity(
            source="test", start_time=datetime(2026, 8, 1, 6, 0),
            duration_s=3600, distance_m=30000.0,
            samples=[s for k, s in enumerate(samples) if k % iv == 0],
        )

        r = power_zones_detailed(a, FTP)
        ss = r["summary"]["sweet_spot_seconds"]
        above = r["summary"]["above_ftp_seconds"]
        assert 1150 <= ss <= 1250, f"甜区应 ≈1200 秒, 实际 {ss}"
        assert 2350 <= above <= 2450, f"高于 FTP 应 ≈2400 秒, 实际 {above}"


# ================================================================
# hr_zones
# ================================================================

class TestHrZonesTimeWeighted:
    @pytest.mark.parametrize("iv", [1, 10])
    def test_hr_zones_same_regardless_of_sample_rate(self, iv):
        """1 小时恒定 165 bpm

        Coggan 5 区边界 (max_hr 兜底模式, 不传 lthr):
            Z1 <60% / Z2 60-70% / Z3 70-80% / Z4 80-90% / Z5 >90%
        165/190 = 86.8% → Z4 (阈值区)
        """
        from cycling_coach.core.metrics.hr import hr_zones

        a = _ride(3600, 200, 165, iv)
        z = hr_zones(a, max_hr=MAX_HR)

        # 86.8% 落在 Z4 (阈值区)
        assert z["Z4"] == 3600, (
            f"采样 {iv}s: Z4 应为 3600 秒, 实际 {z['Z4']} "
            f"(偏差 {3600 / max(z['Z4'], 1):.1f}×)"
        )
        assert sum(z.values()) == 3600, f"各区秒数之和应 = 3600, 实际 {sum(z.values())}"


# ================================================================
# pa_hr_decoupling
# ================================================================

class TestDecouplingTimeWeighted:
    @pytest.mark.parametrize("iv", [1, 10])
    def test_one_hour_ride_is_eligible(self, iv):
        """1 小时骑行应该**能**算 decoupling

        老代码门槛是 `len(valid) < 1800` (隐含 1 样本 = 1 秒),
        10s 采样时 1 小时只有 360 个样本 → 被拒。
        这正是"数据明明够了却算不出来"的典型。
        """
        from cycling_coach.core.metrics.hr import pa_hr_decoupling

        a = _ride(3600, 200, 150, iv)
        r = pa_hr_decoupling(a)

        assert r.get("error") != "insufficient_data", (
            f"采样 {iv}s: 1 小时骑行不该被判定为数据不足: {r}"
        )
        assert r.get("applicable") is True, f"应标为可计算: {r}"
        assert r.get("duration_s", 0) >= 3600, (
            f"应识别出 ≥3600 秒时长, 实际 {r.get('duration_s')}"
        )

    @pytest.mark.parametrize("iv", [1, 10])
    def test_short_ride_still_rejected(self, iv):
        """30 分钟仍应被拒 (门槛是 60 分钟) —— 别把门槛也一起放松了"""
        from cycling_coach.core.metrics.hr import pa_hr_decoupling

        a = _ride(1800, 200, 150, iv)
        r = pa_hr_decoupling(a)

        assert r.get("applicable") is False, f"30 分钟不该可计算: {r}"


# ================================================================
# 共享工具本身的自检
# ================================================================

class TestSampleDurationsHelper:
    def test_dt_is_1_for_1hz(self):
        from cycling_coach.core.metrics.power import sample_durations

        a = _ride(100, 200, 150, 1)
        _t, _v, dt = sample_durations(a, "power")
        assert (dt == 1.0).all(), f"1Hz 采样每个样本应代表 1 秒, 实际 {dt[:5]}"

    def test_dt_is_10_for_10hz_interval(self):
        from cycling_coach.core.metrics.power import sample_durations

        a = _ride(100, 200, 150, 10)
        _t, _v, dt = sample_durations(a, "power")
        # 首尾各取一半间隔 → 5 + 5 = 10
        assert abs(dt.sum() - 100) < 1e-6, (
            f"dt 之和应等于骑行时长 100 秒, 实际 {dt.sum()}"
        )

    def test_dt_sum_equals_ride_duration(self):
        from cycling_coach.core.metrics.power import sample_durations

        for iv in (1, 2, 5, 10):
            a = _ride(3600, 200, 150, iv)
            _t, _v, dt = sample_durations(a, "power")
            assert abs(dt.sum() - 3600) < 1.0, (
                f"采样 {iv}s: dt 之和 {dt.sum()} 应 ≈3600"
            )

    def test_missing_channel_yields_empty(self):
        from cycling_coach.core.metrics.power import sample_durations

        a = _ride(60, 200, 150, 1)
        # lat/lon 这类通道 ride 里没填
        _t, v, dt = sample_durations(a, "lat")
        assert len(v) == 0
        assert len(dt) == 0
