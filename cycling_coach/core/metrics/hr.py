"""心率相关指标"""
from __future__ import annotations
from typing import Optional

import numpy as np

from cycling_coach.data.parsers.schema import Activity, Sample
from cycling_coach.core.metrics.power import sample_durations, seconds_in_bins


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
    # V0.9.0: 时间加权分箱 — 老的 mask.sum() 只在完整 1Hz 下等于"秒",
    # 10s 采样时心率区间会少算 10 倍 (同 power_zones 的问题)
    _t, arr, dt = sample_durations(activity, "hr")

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

    secs = seconds_in_bins(pct, dt, bins)
    return {label: int(round(secs[i])) for i, label in enumerate(labels)}


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

    返回 (V0.9.0 订正: 下面这份 docstring 原先写的是扁平的
    first_half_ef / second_half_ef, 但代码实际返回的是**嵌套结构**。
    我照着这份 docstring 写测试, 写了 `res.get("ef1")` —— 恒为 None,
    断言一次都没执行, 测试却一直是绿的。错文档比没文档危险。):
    {
      "applicable": true,          # >= 60min 且 功率+HR 数据齐全
      "duration_s": 3600,
      "decoupling_pct": 8.5,
      "first_half": {
        "duration_s": 1800, "avg_power": 220, "avg_hr": 155,
        "efficiency_factor": 1.42,   # EF = 平均功率 / 平均心率
      },
      "second_half": {
        "duration_s": 1800, "avg_power": 215, "avg_hr": 165,
        "efficiency_factor": 1.30,
      },
      "interpretation": "normal",    # excellent / normal / high / warning
      "interpretation_label": "正常",
      "color": "yellow",
    }

    注意 EF 的真实量级: 骑行 EF = 功率(W) / 心率(bpm), 通常 1.3~1.8。
    0.75~1.10 那是跑步的量级, 拿它当骑行断言会永远失败或永远不执行。
    """
    samples = activity.samples
    if not samples:
        return {"error": "no_samples", "applicable": False}

    # 必须有功率 + 心率
    valid = [s for s in samples if s.power is not None and s.hr is not None]
    if not valid:
        return {
            "error": "insufficient_data",
            "applicable": False,
            "min_samples_required": 1800,
            "actual_samples": 0,
            "duration_s": 0,
        }

    # V0.9.0: 有效时长用**时间加权**, 不再是 len(样本数)。
    # 老代码 `len(valid) < 1800` 隐含"1 样本 = 1 秒", 于是 10s 采样时
    # 1 小时的骑行只有 360 个样本 → 被当成 6 分钟直接拒绝,
    # 明明该算的 decoupling 算不出来。
    _t, _v, dt = sample_durations(activity, "power")
    duration_s = int(round(float(dt.sum()))) if len(dt) else 0

    if duration_s < 3600:
        return {
            "error": "insufficient_data",
            "applicable": False,
            "min_samples_required": 1800,
            "actual_samples": len(valid),
            "duration_s": duration_s,
        }

    # 按**时间中点**切两半 (按样本个数切在稀疏采样下会切偏)
    if len(_t) >= 2:
        t_mid = (_t[0] + _t[-1]) / 2.0
        first_idx = int(np.searchsorted(_t, t_mid, side="left"))
    else:
        first_idx = len(valid) // 2
    first_idx = max(1, min(first_idx, len(valid) - 1))

    first = valid[:first_idx]
    second = valid[first_idx:]

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

    # V0.9.0: 前半段时长按时间中点算, 不再用样本个数
    t_start = float(_t[0]) if len(_t) else 0.0
    t_split = float(_t[first_idx - 1]) if len(_t) else duration_s / 2.0
    first_dur = int(round(t_split - t_start))
    first_dur = max(0, min(first_dur, duration_s))

    return {
        "applicable": True,
        "duration_s": duration_s,
        "decoupling_pct": round(decoupling, 1),
        "first_half": {
            "duration_s": first_dur,
            "avg_power": round(first_power, 0),
            "avg_hr": round(first_hr, 0),
            "efficiency_factor": round(first_ef, 2),
        },
        "second_half": {
            "duration_s": duration_s - first_dur,
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

