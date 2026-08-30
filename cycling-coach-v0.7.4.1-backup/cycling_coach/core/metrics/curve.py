"""功率曲线(MMP / Mean Maximal Power)

各时长的最大平均功率 — 评估运动员各维度能力的关键
- 5s: 冲刺(神经肌肉)
- 60s: 重复冲刺 / 1 分钟能力
- 5min: FTP 附近
- 60min: ≈ FTP
"""
from __future__ import annotations
from typing import Optional

import numpy as np

from cycling_coach.data.parsers.schema import Activity, Sample


def mean_maximal_power(
    activity: Activity, durations_s: list[int] | None = None
) -> dict[str, int]:
    """MMP 功率曲线

    默认输出: 5, 10, 30, 60, 120, 300, 600, 1200, 3600 秒
    """
    pwrs = [s.power for s in activity.samples if s.power is not None]
    if not pwrs:
        return {}
    if durations_s is None:
        durations_s = [5, 10, 30, 60, 120, 300, 600, 1200, 3600]
    durations_s = [d for d in durations_s if d <= len(pwrs)]
    if not durations_s:
        return {}

    arr = np.array(pwrs, dtype=float)
    # 用 cumulative sum 加速:max_avg(d) = max( (cs[i+d] - cs[i]) / d )
    cs = np.concatenate([[0], arr.cumsum()])
    result: dict[str, int] = {}
    for d in durations_s:
        rolling = (cs[d:] - cs[:-d]) / d
        result[f"{d}s"] = int(round(rolling.max()))
    return result


def estimate_ftp(activity: Activity) -> Optional[int]:
    """从 20 分钟最佳功率估算 FTP(×0.95)

    经典 Coggan 公式:FTP ≈ 95% of 20-min power
    """
    mmp = mean_maximal_power(activity, durations_s=[1140, 1200, 1260])  # ~20min
    if not mmp:
        return None
    # 优先用 20min(1200s),退而求其次
    best_20 = max(mmp.values())
    return int(round(best_20 * 0.95))


def cadence_zones(activity: Activity) -> dict[str, int]:
    """踏频区间时间分布(秒)— 4 区训练学标准

      <60:    极慢(可能掉链 / 上大坡)
      60-79:  低踏频(爬坡)
      80-94:  优化区(平路经济踏频)
      ≥95:    高踏频(冲刺 / 摇车)

    训练学建议:平路 80-94 rpm 最经济;爬坡 70-80 rpm
    """
    cads = [s.cadence for s in activity.samples if s.cadence is not None]
    if not cads:
        return {}
    arr = np.array(cads)
    bins = [-np.inf, 60, 80, 95, np.inf]
    labels = ["<60", "60-79", "80-94", "≥95"]
    return {
        label: int(((arr >= lo) & (arr < hi)).sum())
        for label, lo, hi in zip(labels, bins[:-1], bins[1:])
    }
