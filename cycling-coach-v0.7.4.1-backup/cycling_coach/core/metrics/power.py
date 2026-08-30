"""功率相关指标

参考:
- NP (Normalized Power) — TrainingPeaks / Andrew Coggan 公式
- IF (Intensity Factor) — NP / FTP
- TSS (Training Stress Score) — 经典公式
- W'bal — Skiba 模型(简化版,MVP 可选)
"""
from __future__ import annotations
import math
from typing import Optional

import numpy as np

from cycling_coach.data.parsers.schema import Activity, Sample


def normalized_power(activity: Activity, window_s: int = 30) -> Optional[int]:
    """归一化功率 NP

    V0.7.1 修订: 按真实时间戳 (s.t_offset) 与 Δt 计算
    - 之前 filter 后丢点导致 30s 窗与真实时间不一致
    - 现在每样本 t_offset 知道, 缺失时插零, 时间窗用真实秒

    步骤:
    1. 提取 (t_offset, power) 对, 按 t 排序
    2. 重采样到 1Hz (缺失点插 0, V0.7.1 简化: 实际 1Hz 适配)
    3. 30s 滚动平均
    4. 升 4 次方 → 平均 → 开 4 次方
    """
    pts: list[tuple[int, float]] = []
    for s in activity.samples:
        if s.power is None or s.t_offset is None:
            continue
        pts.append((int(s.t_offset), float(s.power)))
    if not pts:
        return None
    pts.sort(key=lambda x: x[0])

    # 重采样到 1Hz (若缺失点 0 补, 跟 Coggan 训练学一致)
    t_min = pts[0][0]
    t_max = pts[-1][0]
    duration = t_max - t_min + 1
    if duration < window_s:
        # 数据太短, 直接均值
        return int(round(sum(p for _, p in pts) / len(pts)))

    # 1Hz 数组
    arr = np.zeros(duration, dtype=float)
    for t, p in pts:
        idx = t - t_min
        if 0 <= idx < duration:
            arr[idx] = p

    if len(arr) < window_s:
        return int(round(arr.mean()))

    # 30s 滚动平均 (1Hz 步长)
    kernel = np.ones(window_s) / window_s
    smoothed = np.convolve(arr, kernel, mode="valid")
    np_val = (np.mean(smoothed ** 4)) ** 0.25
    return int(round(np_val))


def intensity_factor(np_val: Optional[int], ftp: Optional[int]) -> Optional[float]:
    """IF = NP / FTP"""
    if np_val is None or ftp is None or ftp <= 0:
        return None
    return round(np_val / ftp, 3)


def training_stress_score(
    np_val: Optional[int], if_val: Optional[float], duration_s: int, ftp: Optional[int]
) -> Optional[int]:
    """TSS = (duration_s × NP × IF) / (FTP × 3600) × 100

    当 IF = NP/FTP 时可化简为: duration_s × NP² / (FTP² × 3600) × 100
    """
    if np_val is None or ftp is None or ftp <= 0 or duration_s <= 0:
        return None
    return int(round(duration_s * (np_val ** 2) / (ftp ** 2 * 3600) * 100))


def efficiency_factor(
    np_val: Optional[int], avg_hr: Optional[int]
) -> Optional[float]:
    """EF = NP / avg_HR(简化版,无 LTHR 时用)

    衡量有氧效率:同样功率下心率越低越好
    """
    if np_val is None or avg_hr is None or avg_hr <= 0:
        return None
    return round(np_val / avg_hr, 2)


def variability_index(np_val: Optional[int], avg_power: Optional[int]) -> Optional[float]:
    """VI = NP / avg_power

    衡量输出的稳定性:VI 接近 1.0 越稳,间歇训练会高(>1.05)
    """
    if np_val is None or avg_power is None or avg_power <= 0:
        return None
    return round(np_val / avg_power, 2)


def w_prime_balance(
    samples: list[Sample], cp: int, w_prime: int = 20000
) -> list[float]:
    """W'bal 模型(Skiba 2012 简化)

    W'bal(t) = W' - Σ( (W(t) - CP) × Δt )_where W>CP
    恢复时:W'bal 指数恢复,τ=546s

    返回每秒 W'bal 数组
    返回 None if 数据不足
    """
    pwrs = [s.power for s in samples if s.power is not None]
    if not pwrs or cp <= 0:
        return []
    arr = np.array(pwrs, dtype=float)
    bal = np.zeros(len(arr))
    bal[0] = w_prime
    tau = 546.0
    for i in range(1, len(arr)):
        w = arr[i]
        if w > cp:
            # 消耗
            bal[i] = max(0, bal[i - 1] - (w - cp))
        else:
            # 恢复(指数)
            bal[i] = w_prime - (w_prime - bal[i - 1]) * math.exp(-1.0 / tau)
    return bal.tolist()


def power_zones(activity: Activity, ftp: int) -> dict[str, int]:
    """功率区间累计时间(秒)— Coggan 7 区标准

    区间(基于 FTP 百分比):
      Z1: <55%   Active Recovery
      Z2: 55-75% Endurance
      Z3: 76-90% Tempo
      Z4: 91-105% Threshold
      Z5: 106-120% VO2 Max
      Z6: 121-150% Anaerobic
      Z7: >150%  Neuromuscular

    返回 {"Z1": seconds, "Z2": seconds, ..., "Z7": seconds}
    """
    if not ftp or ftp <= 0:
        return {}
    pwrs = [s.power for s in activity.samples if s.power is not None]
    if not pwrs:
        return {}
    arr = np.array(pwrs, dtype=float)
    pct = arr / ftp
    # Coggan 7 区边界
    bins = [-np.inf, 0.55, 0.75, 0.90, 1.05, 1.20, 1.50, np.inf]
    labels = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    result: dict[str, int] = {label: 0 for label in labels}
    for i, label in enumerate(labels):
        lo, hi = bins[i], bins[i + 1]
        mask = (pct >= lo) & (pct < hi)
        result[label] = int(mask.sum())
    return result


# ============================================================
# V0.6 GoldenCheetah 对标 — 增强版 7 区分布 + W'bal 分析
# ============================================================

# Coggan 7 区标准定义 (含训练学标签, 跟 GoldenCheetah 一致)
COGGAN_7_ZONES: list[dict] = [
    {"code": "Z1", "name": "Active Recovery",   "lo": 0.00, "hi": 0.55, "color": "#9ca3af"},
    {"code": "Z2", "name": "Endurance",         "lo": 0.55, "hi": 0.75, "color": "#3b82f6"},
    {"code": "Z3", "name": "Tempo",             "lo": 0.75, "hi": 0.90, "color": "#10b981"},
    {"code": "Z4", "name": "Threshold",         "lo": 0.90, "hi": 1.05, "color": "#f59e0b"},
    {"code": "Z5", "name": "VO2 Max",           "lo": 1.05, "hi": 1.20, "color": "#ef4444"},
    {"code": "Z6", "name": "Anaerobic",         "lo": 1.20, "hi": 1.50, "color": "#dc2626"},
    {"code": "Z7", "name": "Neuromuscular",     "lo": 1.50, "hi": 9.99, "color": "#7c2d12"},
]


def power_zones_detailed(activity: Activity, ftp: int) -> dict:
    """Coggan 7 区分布详细分析 (对标 GoldenCheetah / TrainingPeaks)

    返回结构:
    {
      "ftp": 250,
      "total_seconds": 3600,
      "total_distance_km": 42.5,
      "zones": [
        {
          "code": "Z1",
          "name": "Active Recovery",
          "color": "#9ca3af",
          "seconds": 600,
          "percent_time": 16.7,
          "percent_distance": 12.3,    # 该区距离占总距离的百分比 (如果有 distance)
          "avg_power": 110,             # 区间内平均功率
          "max_power": 130,             # 区间内最大功率
          "kj": 66,                     # 该区做功 kJ
        },
        ...
      ],
      "summary": {
        "polarization_index": 0.85,    # Z1+Z2 + Z5+Z6+Z7 占比 (0-1, 越高越极化)
        "sweet_spot_seconds": 180,     # 88-94% FTP 区间 (甜蜜点)
        "above_ftp_seconds": 240,      # >FTP 总时间
      }
    }

    训练学解读 (前端展示用):
    - polarization_index > 0.75 → 极化训练 (Seiler 2008 推荐)
    - sweet_spot_seconds > 180 → 含 SS 训练, 通常 1-2h 骑行常见
    - above_ftp_seconds > 600 → 高强度日 (VO2max / Threshold)
    """
    if not ftp or ftp <= 0:
        return {"error": "no_ftp", "ftp": 0, "total_seconds": 0, "zones": []}

    pwrs = [s.power for s in activity.samples if s.power is not None]
    if not pwrs:
        return {"error": "no_power_data", "ftp": ftp, "total_seconds": 0, "zones": []}

    arr = np.array(pwrs, dtype=float)
    total_seconds = len(arr)
    total_distance_m = activity.distance_m or 0.0

    # 距离数组 (按时间加权, 用于区间距离占比)
    # 简单近似: distance_per_sample = total_distance / total_seconds
    if total_seconds > 0 and total_distance_m > 0:
        dist_per_sec = total_distance_m / total_seconds
    else:
        dist_per_sec = 0.0

    zones_out = []
    for z in COGGAN_7_ZONES:
        lo_pct, hi_pct = z["lo"], z["hi"]
        mask = (arr >= ftp * lo_pct) & (arr < ftp * hi_pct)
        seconds = int(mask.sum())
        if seconds == 0:
            zones_out.append({
                "code": z["code"],
                "name": z["name"],
                "color": z["color"],
                "lo_pct": lo_pct,
                "hi_pct": hi_pct,
                "seconds": 0,
                "percent_time": 0.0,
                "percent_distance": 0.0,
                "avg_power": None,
                "max_power": None,
                "kj": 0.0,
            })
            continue

        seg = arr[mask]
        avg_pwr = int(round(seg.mean()))
        max_pwr = int(seg.max())
        kj = float(seg.sum() / 1000.0)  # 1 W × 1 s = 1 J
        distance_m = dist_per_sec * seconds
        pct_time = round(seconds * 100.0 / total_seconds, 2) if total_seconds else 0.0
        pct_dist = round(distance_m * 100.0 / total_distance_m, 2) if total_distance_m else 0.0

        zones_out.append({
            "code": z["code"],
            "name": z["name"],
            "color": z["color"],
            "lo_pct": lo_pct,
            "hi_pct": hi_pct,
            "seconds": seconds,
            "percent_time": pct_time,
            "percent_distance": pct_dist,
            "avg_power": avg_pwr,
            "max_power": max_pwr,
            "kj": round(kj, 1),
        })

    # Summary metrics (GoldenCheetah-style 极化指数 + 甜蜜点)
    easy_secs = sum(z["seconds"] for z in zones_out if z["code"] in ("Z1", "Z2"))
    hard_secs = sum(z["seconds"] for z in zones_out if z["code"] in ("Z5", "Z6", "Z7"))
    polarized_secs = easy_secs + hard_secs

    # Sweet spot: 88-94% FTP (介于 Z3 顶部和 Z4 底部之间)
    ss_mask = (arr >= ftp * 0.88) & (arr < ftp * 0.94)
    sweet_spot_seconds = int(ss_mask.sum())

    # Above FTP
    above_mask = arr >= ftp
    above_ftp_seconds = int(above_mask.sum())

    polarization_index = round(polarized_secs / total_seconds, 3) if total_seconds else 0.0

    return {
        "ftp": ftp,
        "total_seconds": total_seconds,
        "total_distance_km": round(total_distance_m / 1000.0, 2) if total_distance_m else 0.0,
        "total_kj": round(float(arr.sum() / 1000.0), 1),
        "zones": zones_out,
        "summary": {
            "polarization_index": polarization_index,
            "sweet_spot_seconds": sweet_spot_seconds,
            "above_ftp_seconds": above_ftp_seconds,
            "easy_seconds": easy_secs,
            "hard_seconds": hard_secs,
        },
    }


def wbal_analysis(
    samples: list[Sample],
    cp: int,
    w_prime: int = 20000,
) -> dict:
    """W'bal 详细分析 (对标 GoldenCheetah W'bal + Skiba Critical Power 模型)

    V0.7.1 修订:
    - 按真实 t_offset 与 Δt 计算 (非 1Hz 时 Δt 乘进来)
    - 简化模型: 固定 tau=546s, UI/接口已注明 (非完整 Skiba differential)
    - 恢复: 指数衰减, 跟 Skiba 2012 一致

    返回:
    {
      "cp": 280, "w_prime": 20000,
      "wbal_curve": [20000, 19950, 19800, ...],
      "min_wbal": 3200, "min_wbal_at_s": 1820, "min_wbal_pct": 16.0,
      "depleted": False, "depletion_at_s": None,
      "critical_events": [...],
      "match_potential": 0.65,
    }

    参考:
    - Skiba et al. (2012) — W'bal 模型 (完整 differential 形式)
    - 本实现是简化版 (固定 τ=546s), UI/接口已注明
    - W'bal < 30% W' 进入"红色区", 难以再发起高强度
    """
    if cp <= 0 or w_prime <= 0:
        return {"error": "invalid_cp_or_wprime", "cp": cp, "w_prime": w_prime}

    # 提取 (t_offset, power) 对
    pts: list[tuple[int, float]] = []
    for s in samples:
        if s.power is None or s.t_offset is None:
            continue
        pts.append((int(s.t_offset), float(s.power)))
    if not pts:
        return {"error": "no_power_data", "cp": cp, "w_prime": w_prime}

    pts.sort(key=lambda x: x[0])

    tau = 546.0  # 恢复时间常数 (秒, 固定简化)

    # 用 t_offset 当 x 轴, 增量 Δt 处理丢点 / 非 1Hz
    # 重采样到 1Hz, 缺失补 0 (功率 0 = 滑行 / 休息)
    t_min = pts[0][0]
    t_max = pts[-1][0]
    duration = t_max - t_min + 1
    if duration < 1:
        return {"error": "no_power_data", "cp": cp, "w_prime": w_prime}

    arr = np.zeros(duration, dtype=float)
    for t, p in pts:
        idx = t - t_min
        if 0 <= idx < duration:
            arr[idx] = p
    n = len(arr)
    bal = np.zeros(n)
    bal[0] = float(w_prime)

    depleted = False
    depletion_at_s: int | None = None

    for i in range(1, n):
        w = arr[i]
        if w > cp:
            # 消耗: 乘 Δt (恒为 1s 简化, 但语义保留)
            bal[i] = max(0.0, bal[i - 1] - (w - cp))
            if bal[i] <= 0 and not depleted:
                depleted = True
                depletion_at_s = i
        else:
            # 指数恢复 (Skiba 简化版)
            bal[i] = w_prime - (w_prime - bal[i - 1]) * math.exp(-1.0 / tau)
        if not math.isfinite(bal[i]):
            bal[i] = 0.0

    min_wbal = float(bal.min())
    min_idx = int(bal.argmin())
    min_wbal_pct = round(min_wbal * 100.0 / w_prime, 1) if w_prime else 0.0

    # 临界事件: 连续 W'bal < 30% W' 的段
    threshold = w_prime * 0.30
    critical_events: list[dict] = []
    in_event = False
    event_start = 0
    event_min = w_prime

    for i, b in enumerate(bal):
        if b < threshold:
            if not in_event:
                in_event = True
                event_start = i
                event_min = b
            else:
                event_min = min(event_min, b)
        else:
            if in_event:
                critical_events.append({
                    "start_s": event_start,
                    "end_s": i - 1,
                    "duration_s": i - event_start,
                    "min_wbal": int(round(event_min)),
                    "min_wbal_pct": round(event_min * 100.0 / w_prime, 1),
                })
                in_event = False
                event_min = w_prime

    if in_event:
        critical_events.append({
            "start_s": event_start,
            "end_s": n - 1,
            "duration_s": n - event_start,
            "min_wbal": int(round(event_min)),
            "min_wbal_pct": round(event_min * 100.0 / w_prime, 1),
        })

    # 比赛匹配潜力: W' 用了多少
    match_potential = round(1.0 - min_wbal / w_prime, 3) if w_prime else 0.0

    return {
        "cp": cp,
        "w_prime": w_prime,
        "wbal_curve": [round(float(x), 1) for x in bal.tolist()],
        "min_wbal": int(round(min_wbal)),
        "min_wbal_at_s": min_idx,
        "min_wbal_pct": min_wbal_pct,
        "depleted": depleted,
        "depletion_at_s": depletion_at_s,
        "critical_events": critical_events,
        "match_potential": match_potential,
        "tau_s": tau,
    }


def detect_cp_3param(samples: list[Sample]) -> dict:
    """CP 3 参数模型自动检测 (对标 GoldenCheetah CP 3-Parameter Model)

    通过 MMP (Mean Maximal Power) 曲线拟合:
    - Critical Power (CP)  = 1-3 分钟全力输出的稳态上限
    - W\' (W prime)         = 曲线下的总做功能力 (J)
    - Tau (τ)              = W\' 恢复时间常数 (默认 546s)

    简化版 (MVP):
    - CP ≈ MMP(180s) (3 分钟全力均值)
    - W\' ≈ 60s + 180s 段超 CP 部分的做功
    - 详细 3 参数拟合用 least-squares, 留 v0.6 后续迭代

    返回:
    {
      "cp_estimated": 285,
      "w_prime_estimated": 22500,   # J
      "method": "simplified_3min_mmp",
      "confidence": 0.78,
      "p60_watts": 380,
      "p180_watts": 290,
    }
    """
    pwrs = [s.power for s in samples if s.power is not None]
    if not pwrs or len(pwrs) < 180:
        return {"error": "insufficient_data", "min_samples_required": 180}

    arr = np.array(pwrs, dtype=float)
    # 内部算 MMP (不用 Activity wrapper, 避免 pydantic 必填字段问题)
    durations_s = [60, 120, 180, 300, 600]
    durations_s = [d for d in durations_s if d <= len(pwrs)]
    if not durations_s:
        return {"error": "insufficient_data"}

    cs = np.concatenate([[0.0], arr.cumsum()])
    mmp: dict[str, int] = {}
    for d in durations_s:
        rolling = (cs[d:] - cs[:-d]) / d
        mmp[f"{d}s"] = int(round(float(rolling.max())))

    # 3 分钟 MMP 估算 CP
    cp_est = mmp.get("180s")
    if cp_est is None or cp_est <= 0:
        return {"error": "mmp_180s_unavailable"}

    # W\' 估算: 60s + 180s 段超 CP 的做功
    p60 = mmp.get("60s") or cp_est
    p180 = cp_est
    w_prime_est = max(0, (p60 - cp_est) * 60) + max(0, (p180 - cp_est) * 120)
    w_prime_est = int(round(w_prime_est))

    # 置信度: 数据长度 + W\' 合理性
    confidence = 0.5
    if len(pwrs) >= 600:  # ≥ 10 min
        confidence += 0.15
    if len(pwrs) >= 1800:  # ≥ 30 min
        confidence += 0.15
    if 5000 <= w_prime_est <= 50000:  # 合理 W\' 范围 5-50 kJ
        confidence += 0.10
    confidence = min(confidence, 0.95)

    return {
        "cp_estimated": int(cp_est),
        "w_prime_estimated": w_prime_est,
        "method": "simplified_3min_mmp",
        "confidence": round(confidence, 2),
        "p60_watts": p60,
        "p180_watts": p180,
        "mmp": mmp,
    }
