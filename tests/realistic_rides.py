"""V0.9.0: 真实形态骑行数据生成器

## 为什么需要这个

到 V0.9.0 为止, 项目里所有测试数据都是**恒定功率**的
(`build_fit(avg_power=200, power_jitter=0)`)。

这不是问题 —— 恒定功率对"这个指标算得对不对"是最干净的 ground truth。
但它**测不出另一类 bug**: 真实骑行是波动的, 而下面这些指标的行为
完全取决于功率的**时间结构**, 不是它的均值:

| 指标 | 恒定功率下 | 真实波动下才会暴露的问题 |
|---|---|---|
| NP | = 平均功率, 平凡 | 30s 滑动窗口对齐错位 / 窗口不足时的处理 |
| W′ balance | 线性下降, 好算 | 突增功率后恢复不足的累积效应 / 负值钳制 |
| 分区时长 | 秒数 = 采样数 × 间隔 | 跨分区边界的采样归属 |
| 解耦 EF²/EF¹ | 恒定 | 需要功率与心率的**时序错位**才测得出 |
| IF | = NP/FTP | 间歇课的 IF 和恒定课完全不同 |

**恒定功率的 fixture 一直在替我遮 bug。** 这就是这份文件的由来。

## 真实性做到哪

不是随机噪声堆砌, 而是按运动生理建模:

1. **功率**: 由调用方给的分段结构 (热身/间歇/恢复/冷身) 决定,
   每段内加小幅噪声 —— 真实骑行没有一段是完全平的
2. **心率**: 对功率做**一阶滞后 + 慢漂移**。心率跟不上功率的瞬时变化,
   这是解耦指标的物理基础; 长时间高强度下心率还会比功率涨得更快 (耗竭)
3. **速度**: 对功率非线性响应 (功率 ∝ 速度³ 但有风阻/坡度/跟骑随机性),
   且**滞后于功率** —— 冲刺时速度不会瞬间到顶
4. **踏频**: 低功率掉踏频, 高功率维持
5. **爬升**: 用一条平滑的虚拟路线, 让海拔不是一条直线

## 关键能力: 已知功率曲线 ⇒ 可独立验算 NP

给定分段功率, 测试里可以**用教科书定义独立重算一遍 NP**
(30s 滑动平均 → 4 次方 → 均值 → 开 4 次方), 再和应用算的值比对。
两边用的是同一个定义, 所以这不是"验算法对不对" (那是另一回事),
而是"实现有没有做错" —— 滑动窗口错位、边界处理、稀疏采样都会被抓出来。

恒定功率数据做不到这一点, 因为它的 NP 平凡地等于平均功率。
"""
from __future__ import annotations

import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ---------------------------------------------------------------- 单位换算
# 内部一律用 "秒" 存分段, 外部接口用分钟更符合训练计划的表达习惯
Segment = tuple[float, int]  # (分钟, 功率 W)


def _segments_to_samples(
    segments: list[Segment],
    *,
    hr_rest: float = 52.0,
    hr_max: float = 188.0,
    lthr: float = 168.0,
    ftp: float = 280.0,
    sample_interval_s: float = 1.0,
    seed: int = 0,
    drift: float = 0.0,
) -> dict:
    """把分段功率展开成逐秒的功率/心率/速度/踏频序列。

    Returns:
        dict: {"power": [...], "hr": [...], "speed": [...], "cadence": [...],
               "altitude": [...], "timestamps": [...], "duration_s": int}
    """
    rng = random.Random(seed)

    # ---- 1. 功率序列 ----
    power: list[float] = []
    for minutes, watts in segments:
        n = int(round(minutes * 60 / sample_interval_s))
        for _ in range(n):
            # 段内小幅噪声: 真实骑行没有完全平的一段
            power.append(max(0.0, watts + rng.gauss(0, max(2.0, watts * 0.02))))

    n_total = len(power)
    if n_total == 0:
        return {"power": [], "hr": [], "speed": [], "cadence": [],
                "altitude": [], "timestamps": [], "duration_s": 0}

    # ---- 2. 心率: 一阶滞后 + 慢漂移 ----
    # 功率→心率必须按生理分区映射, 不能用一条平滑曲线糊过去:
    #   功率 = FTP   → 心率 = LTHR (阈值心率)
    #   功率 = 0     → 心率 = 静息
    #   功率 → ∞     → 心率 → HRmax (有天花板)
    # 第一版用 exp 曲线, 结果 FTP 280W 只给到 145bpm, 而 LTHR 是 168 ——
    # 心率整体偏低, 而解耦 (EF²/EF¹) 完全建立在心率真实性上, 偏低会直接
    # 把解耦算成假的。这不是"接近真实", 是"错了但不容易看出来"。
    def target_hr(p: float) -> float:
        if p <= 0:
            return hr_rest
        if p <= ftp:
            # 静息 → LTHR 线性插值 (低强度区心率响应基本线性)
            k = p / ftp
            return hr_rest + (lthr - hr_rest) * k
        # LTHR → HRmax, 越往上越接近天花板
        over = (p - ftp) / max(1.0, (hr_max - lthr) * 1.6)
        return min(hr_max, lthr + (hr_max - lthr) * (1 - math.exp(-2.2 * over)))

    tau = 45.0  # 心率时间常数 (秒) —— 生理滞后
    alpha = sample_interval_s / tau
    hr: list[float] = []
    cur = hr_rest
    for i, p in enumerate(power):
        tgt = target_hr(p)
        # drift: 长时间训练心率相对功率额外上飘 (模拟脱水和耗竭)
        prog = i / n_total
        tgt += drift * prog
        cur += alpha * (tgt - cur)
        hr.append(min(hr_max, cur))

    # ---- 3. 速度: 非线性响应 + 滞后 ----
    # 功率 P ∝ v³ (纯滚阻主导时), 实际受风阻/坡度/跟骑影响, 指数取 2.6。
    # 关键是**标定**: 第一版写 (p/5)^(1/2.6), 结果 8 m/s 要 1114W ——
    # 物理上 8 m/s 平路只要 ~130W, 整个模型慢了 2.3 倍, 长耐力课的距离
    # 变成 54.8km (真实该 125km)。数据"看着像那么回事", 但任何用距离的
    # 指标都会被带偏, 而这种错肉眼极难发现。
    #
    # 标定锚点 (符合真实骑行):
    #   200W -> 8.5 m/s (30.6 km/h, 巡航)
    #   400W -> 11.6 m/s (41.8 km/h, 高速巡航/下坡)
    def target_speed(p: float) -> float:
        if p <= 0:
            return 0.0
        return 8.5 * (p / 200.0) ** (1 / 2.6)

    tau_v = 20.0
    alpha_v = sample_interval_s / tau_v
    speed: list[float] = []
    cur_v = target_speed(power[0])
    for p in power:
        cur_v += alpha_v * (target_speed(p) - cur_v)
        speed.append(cur_v * (1 + rng.gauss(0, 0.012)))

    # ---- 4. 踏频: 低功率掉踏频 ----
    cadence: list[float] = []
    for p in power:
        if p < 60:
            c = 62 + rng.gauss(0, 3)
        elif p < 140:
            c = 78 + rng.gauss(0, 3)
        else:
            c = 92 + rng.gauss(0, 4)
        cadence.append(max(0, min(120, c)))

    # ---- 5. 海拔: 平滑虚拟路线 ----
    altitude: list[float] = []
    cur_alt = 100.0
    phase = rng.random() * math.tau
    for i in range(n_total):
        cur_alt += 0.04 * math.sin(i / 900.0 + phase) + rng.gauss(0, 0.05)
        cur_alt = max(20.0, cur_alt)
        altitude.append(cur_alt)

    return {
        "power": power,
        "hr": hr,
        "speed": speed,
        "cadence": cadence,
        "altitude": altitude,
        "duration_s": int(n_total * sample_interval_s),
        "sample_interval_s": sample_interval_s,
    }


def build_profile_fit(
    path: str | Path,
    segments: list[Segment],
    *,
    start: datetime | None = None,
    sample_interval_s: float = 1.0,
    seed: int = 0,
    ftp: float = 280.0,
    lthr: float = 168.0,
    drift: float = 0.0,
    with_session: bool = True,
    with_lap: bool = True,
    with_gps: bool = True,
) -> dict:
    """按分段功率结构生成一个 FIT, 并返回可独立验算的 ground truth。

    Args:
        segments: [(分钟, 功率W), ...] 训练段结构
        drift:     心率慢漂移幅度 (bpm), 模拟长课脱水性解耦
        with_gps:  False = 不写经纬度 (测无 GPS 设备的活动)

    Returns:
        dict: 含 power/hr/speed 序列 + 段级汇总, 供测试独立验算
    """
    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.lap_message import LapMessage
    from fit_tool.profile.messages.record_message import RecordMessage
    from fit_tool.profile.messages.session_message import SessionMessage

    series = _segments_to_samples(
        segments,
        sample_interval_s=sample_interval_s,
        seed=seed,
        ftp=ftp,
        lthr=lthr,
        drift=drift,
    )
    start = start or datetime(2026, 8, 3, 6, 0, 0, tzinfo=timezone.utc)

    builder = FitFileBuilder(auto_define=True, min_string_size=50)
    fid = FileIdMessage()
    fid.type = 4
    fid.manufacturer = 1
    fid.product = 1
    builder.add(fid)

    dist = 0.0
    for i, (p, h, v, c, alt) in enumerate(
        zip(series["power"], series["hr"], series["speed"],
            series["cadence"], series["altitude"])
    ):
        rec = RecordMessage()
        rec.timestamp = int(
            (start + timedelta(seconds=i * series["sample_interval_s"])).timestamp() * 1000
        )
        rec.power = int(round(p))
        rec.heart_rate = int(round(h))
        rec.cadence = int(round(c))
        rec.speed = v
        rec.distance = int(dist)
        rec.altitude = alt
        if with_gps:
            # 上海外环一圈附近
            rec.position_lat = 31.2304 + i * 1e-7
            rec.position_long = 121.4737 + i * 1e-7
        builder.add(rec)
        dist += v * series["sample_interval_s"]

    n = len(series["power"])
    dur = series["duration_s"]
    avg_p = sum(series["power"]) / n
    max_p = max(series["power"])
    avg_h = sum(series["hr"]) / n
    max_h = max(series["hr"])
    avg_c = sum(series["cadence"]) / n
    ascent = sum(
        max(0.0, series["altitude"][i] - series["altitude"][i - 1])
        for i in range(1, n)
    )

    if with_lap:
        lap = LapMessage()
        lap.timestamp = int((start + timedelta(seconds=dur)).timestamp() * 1000)
        lap.start_time = int(start.timestamp() * 1000)
        lap.total_elapsed_time = dur
        lap.total_timer_time = dur
        lap.total_distance = int(dist)
        lap.avg_power = int(round(avg_p))
        lap.max_power = int(round(max_p))
        lap.avg_heart_rate = int(round(avg_h))
        lap.max_heart_rate = int(round(max_h))
        lap.avg_cadence = int(round(avg_c))
        lap.total_ascent = int(ascent)
        lap.sport = 2
        builder.add(lap)

    if with_session:
        ses = SessionMessage()
        ses.timestamp = int((start + timedelta(seconds=dur)).timestamp() * 1000)
        ses.start_time = int(start.timestamp() * 1000)
        ses.total_elapsed_time = dur
        ses.total_timer_time = dur
        ses.total_distance = int(dist)
        ses.avg_power = int(round(avg_p))
        ses.max_power = int(round(max_p))
        ses.avg_heart_rate = int(round(avg_h))
        ses.max_heart_rate = int(round(max_h))
        ses.avg_cadence = int(round(avg_c))
        ses.total_calories = int(dur * avg_p / 1000 * 1.05)
        ses.total_ascent = int(ascent)
        ses.sport = 2
        builder.add(ses)

    Path(path).parent.mkdir(parents=True, exist_ok=True)
    builder.build().to_file(str(path))

    return {
        "path": str(path),
        "segments": segments,
        "power": series["power"],
        "hr": series["hr"],
        "speed": series["speed"],
        "duration_s": dur,
        "distance_m": dist,
        "avg_power": avg_p,
        "max_power": max_p,
        "avg_hr": avg_h,
        "max_hr": max_h,
        "ascent": ascent,
        "sample_interval_s": series["sample_interval_s"],
        "start": start,
    }


# ---------------------------------------------------------------- 独立验算
def textbook_np(
    power: list[float], window_s: int = 30, interval_s: float = 1.0
) -> float:
    """按教科书定义独立计算 NP。

        NP = ( mean( 滑动平均(power)^4 ) )^(1/4)

    这是**独立于被测代码**的第二实现, 故意写得直白 (不用 numpy 向量化),
    用来交叉验证应用的实现有没有搞错窗口对齐 / 边界 / 稀疏采样。
    """
    if not power:
        return 0.0
    n_win = max(1, int(round(window_s / interval_s)))
    avg_of_4th: list[float] = []
    for i in range(len(power)):
        lo = max(0, i - n_win + 1)
        win = power[lo:i + 1]
        avg_p = sum(win) / len(win)
        avg_of_4th.append(avg_p ** 4)
    return (sum(avg_of_4th) / len(avg_of_4th)) ** 0.25


def textbook_zone_seconds(
    power: list[float], ftp: float, interval_s: float = 1.0
) -> list[float]:
    """按标准 7 区间 (Coggan) 统计各区秒数, 独立实现, 用来验应用的分区时长。"""
    bounds = [0.0, 0.55, 0.75, 0.90, 1.05, 1.20, 1.50, float("inf")]
    out = [0.0] * 7
    for p in power:
        r = p / ftp if ftp else 0.0
        for z in range(7):
            if bounds[z] <= r < bounds[z + 1]:
                out[z] += interval_s
                break
    return out


# ---------------------------------------------------------------- 训练课库
# 真实训练计划里的课型。返回 (名称, intent, 分段, 目标TSS系数)
WORKOUT_LIBRARY: list[tuple[str, str, list[Segment]]] = [
    ("恢复骑", "recovery", [(15, 120), (45, 140), (10, 100)]),
    ("耐力骑", "endurance", [(20, 180), (90, 195), (15, 140)]),
    ("长耐力", "endurance", [(25, 180), (180, 200), (20, 130)]),
    ("甜点课", "sweet_spot", [(20, 150), (10, 220), (20, 235), (10, 150)] * 2),
    ("阈值课", "threshold", [(20, 160), (40, 265), (10, 150), (40, 265), (15, 120)]),
    ("VO2max 间歇", "vo2", [(20, 150), (5, 320), (5, 150)] * 5 + [(15, 120)]),
    ("冲刺", "vo2", [(20, 160), (1, 700), (4, 160), (1, 700), (4, 160),
                     (1, 700), (4, 160), (1, 700), (4, 160), (10, 100)]),
    ("爬坡耐力", "endurance", [(10, 150), (60, 230), (10, 130)]),
]
