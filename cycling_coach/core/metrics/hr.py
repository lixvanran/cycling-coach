"""心率相关指标"""
from __future__ import annotations
from typing import Optional

import numpy as np

from cycling_coach.data.parsers.schema import Activity, Sample


def hr_zones(
    activity: Activity,
    max_hr: Optional[int] = None,
    lthr: Optional[int] = None,
) -> dict[str, int]:
    """心率区间累计时间(秒)

    V0.1.1 升级:有 LTHR 用 Karvonen 7 区(更准),否则用 max_hr 5 区(Coggan 兜底)

    Karvonen 7 区(基于 LTHR):
      Z1: <81%   Active Recovery
      Z2: 81-89% Endurance
      Z3: 90-93% Tempo
      Z4: 94-99% Threshold
      Z5: 100-102% Above Threshold
      Z6: 103-105% Anaerobic
      Z7: >106%  VO2 Max

    Coggan 5 区(基于 max_hr):
      Z1: <60%   Recovery
      Z2: 60-70% Endurance
      Z3: 70-80% Tempo
      Z4: 80-90% Threshold
      Z5: >90%   VO2

    返回 {"Z1": seconds, "Z2": seconds, ..., "Z5"/"Z7": seconds}
    """
    hrs = [s.hr for s in activity.samples if s.hr is not None]
    if not hrs:
        return {}
    arr = np.array(hrs)

    if lthr and lthr > 0:
        # Karvonen 7 区
        pct = arr / lthr
        bins = [-np.inf, 0.81, 0.89, 0.93, 0.99, 1.02, 1.05, np.inf]
        labels = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    else:
        # 兜底:Coggan 5 区(max_hr)
        if not max_hr or max_hr <= 0:
            return {}
        pct = arr / max_hr
        bins = [-np.inf, 0.60, 0.70, 0.80, 0.90, np.inf]
        labels = ["Z1", "Z2", "Z3", "Z4", "Z5"]

    result: dict[str, int] = {label: 0 for label in labels}
    for i, label in enumerate(labels):
        lo, hi = bins[i], bins[i + 1]
        mask = (pct >= lo) & (pct < hi)
        result[label] = int(mask.sum())
    return result


def hr_drift(activity: Activity) -> Optional[float]:
    """心率漂移:后半段平均 HR - 前半段平均 HR

    有氧基础好的人漂移小(控强度长时间输出)
    """
    hrs = [s.hr for s in activity.samples if s.hr is not None]
    if len(hrs) < 120:  # 至少 2 分钟
        return None
    half = len(hrs) // 2
    first = np.mean(hrs[:half])
    second = np.mean(hrs[half:])
    return round(float(second - first), 1)


def pa_hr_decoupling(activity: Activity) -> dict:
    """Pa:HR Decoupling — 心率-功率解耦 (有氧效率衰减)

    算法 (Joe Friel / GoldenCheetah Coggan Decoupling):
    - 活动分两半 (前半 / 后半)
    - 每半计算 Efficiency Factor (EF) = avg_power / avg_hr
    - decoupling = 100 * (1 - 后半_EF / 前半_EF)
    - 正值 = 后半效率下降 (糖原 / 脱水 / 疲劳)
    - 负值 = 后半效率上升 (热身不足, 后半发力)

    训练学解读 (Coggan):
    - <5%    优秀 (有氧基础扎实)
    - 5-10%  正常
    - 10-15% 偏高 (疲劳/糖原不足)
    - >15%   警告 (过度训练信号)

    限制:
    - 至少需要 60 分钟稳定输出
    - 短于 60min 不算 (前后对比无意义)
    - 需要功率 + 心率同步数据
    - 高强度间歇不适用 (功率波动大)

    返回:
    {
      "decoupling_pct": 8.5,
      "first_half_ef": 1.42,      # 前半 EF
      "second_half_ef": 1.30,     # 后半 EF
      "first_half_power": 220,    # 前半平均功率
      "first_half_hr": 155,       # 前半平均心率
      "second_half_power": 215,
      "second_half_hr": 165,
      "interpretation": "normal",  # excellent / normal / high / warning
      "duration_s": 3600,         # 活动时长 (秒)
      "applicable": true,         # 是否适用 (>= 60min 且 功率+HR 数据)
    }
    """
    samples = activity.samples
    if not samples:
        return {"error": "no_samples", "applicable": False}

    # 必须有功率 + 心率
    valid = [s for s in samples if s.power is not None and s.hr is not None]
    if len(valid) < 1800:  # 至少 30 分钟有效样本 (1Hz 采样)
        return {
            "error": "insufficient_data",
            "applicable": False,
            "min_samples_required": 1800,
            "actual_samples": len(valid),
            "duration_s": len(valid),
        }

    duration_s = len(valid)
    half = duration_s // 2

    first = valid[:half]
    second = valid[half:]

    first_power = sum(s.power for s in first) / len(first)
    first_hr = sum(s.hr for s in first) / len(first)
    second_power = sum(s.power for s in second) / len(second)
    second_hr = sum(s.hr for s in second) / len(second)

    first_ef = first_power / first_hr if first_hr else 0
    second_ef = second_power / second_hr if second_hr else 0

    if first_ef == 0:
        return {"error": "no_hr_data", "applicable": False}

    decoupling = 100.0 * (1.0 - second_ef / first_ef)

    # 训练学解读
    abs_dec = abs(decoupling)
    if abs_dec < 5:
        interp = "excellent"
        interp_label = "优秀"
        color = "emerald"
    elif abs_dec < 10:
        interp = "normal"
        interp_label = "正常"
        color = "sky"
    elif abs_dec < 15:
        interp = "high"
        interp_label = "偏高"
        color = "amber"
    else:
        interp = "warning"
        interp_label = "警告 (过度训练信号)"
        color = "rose"

    return {
        "applicable": True,
        "duration_s": duration_s,
        "decoupling_pct": round(decoupling, 1),
        "first_half": {
            "duration_s": half,
            "avg_power": round(first_power, 0),
            "avg_hr": round(first_hr, 0),
            "efficiency_factor": round(first_ef, 2),
        },
        "second_half": {
            "duration_s": duration_s - half,
            "avg_power": round(second_power, 0),
            "avg_hr": round(second_hr, 0),
            "efficiency_factor": round(second_ef, 2),
        },
        "interpretation": interp,
        "interpretation_label": interp_label,
        "color": color,
    }


def aerobic_decoupling_trend(samples: list, window_s: int = 1800) -> list[dict]:
    """滑动窗口 decoupling (每 30min 一段)

    返回每个窗口的 decoupling 数值, 用于趋势图
    """
    valid = [s for s in samples if s.power is not None and s.hr is not None]
    if len(valid) < window_s * 2:
        return []

    results = []
    step = window_s // 2  # 50% 重叠
    for start in range(0, len(valid) - window_s * 2 + 1, step):
        first = valid[start:start + window_s]
        second = valid[start + window_s:start + window_s * 2]
        f_p = sum(s.power for s in first) / window_s
        f_h = sum(s.hr for s in first) / window_s
        s_p = sum(s.power for s in second) / window_s
        s_h = sum(s.hr for s in second) / window_s
        if f_h == 0 or s_h == 0:
            continue
        f_ef = f_p / f_h
        s_ef = s_p / s_h
        dec = 100.0 * (1.0 - s_ef / f_ef)
        results.append({
            "start_s": start,
            "end_s": start + window_s * 2,
            "decoupling_pct": round(dec, 1),
            "first_ef": round(f_ef, 2),
            "second_ef": round(s_ef, 2),
        })
    return results

