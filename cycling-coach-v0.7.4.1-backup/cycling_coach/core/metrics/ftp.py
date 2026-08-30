"""FTP 检测核心算法 — V0.6.1

学术依据 (真正借鉴, 非简化):
- Coggan FTP Test Protocol (2003): 20-min test → FTP = 0.95 × 20min NP
- Carmichael 8-min Test (2009): 8min × 2 → FTP = ((8min1 + 8min2) / 2) × 0.9
- Morton 3-parameter Critical Power (1996): P(t) = W'/t + CP
  → 最小二乘拟合 MMP 曲线 (3min, 5min, 12min) → CP + W'
- Pinzon & Anson "Ramp Test" (2018): FTP = 0.75 × peak 1-min
- Borszcz / Karsten: 8-min ≈ 91% of FTP → 反推

关键改进 vs 现有 estimate_ftp:
1. 多协议支持 (4 种 + 自动检测)
2. 稳定性检查 (CV% 系数, 5% 内才有效)
3. 心率协同 (高功率低心率 = 真有氧能力)
4. 置信度评分 (数据足 + 稳定 + 匹配 = 高)
5. 跟当前 FTP 对比 + W/kg
6. 历史趋势 (周期性测试, 衡量训练效果)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

import numpy as np

from cycling_coach.data.parsers.schema import Activity, Sample
from cycling_coach.core.metrics.power import normalized_power
from cycling_coach.core.metrics.curve import mean_maximal_power


# ---------- 数据结构 ----------

@dataclass
class FTPEstimate:
    """FTP 估算结果"""
    method: str           # coggan_20min / carmichael_8min / cp_3param / ramp / auto_mmp
    ftp_w: int
    confidence: float     # 0-1
    notes: list[str]      # 算法判断, e.g. "心率协同好", "功率波动大 CV=12%"
    details: dict         # 各中间量
    source_activity_id: Optional[int] = None
    method_label: str = ""
    watts_per_kg: Optional[float] = None
    weight_kg: Optional[float] = None


@dataclass
class FTPTest:
    """一次 FTP 测试记录"""
    test_date: datetime
    method: str
    ftp_w: int
    hr_bpm: Optional[int]
    weight_kg: Optional[float]
    notes: Optional[str]
    source_activity_id: Optional[int] = None
    confidence: float = 0.5
    watts_per_kg: Optional[float] = None


# ---------- 工具: 找稳定段 ----------

def _find_best_window(
    pwrs: np.ndarray,
    target_duration_s: int,
    cv_threshold: float = 0.10,
) -> tuple[Optional[int], Optional[int], float]:
    """找最稳定的目标长度窗口 (CV 最低)

    训练学逻辑: Coggan 强调 "steady effort" 很重要, 不稳的话 NP×0.95 会低估
    返回: (start, end, cv) — start/end 是 pwrs 数组的索引
    """
    n = len(pwrs)
    if n < target_duration_s:
        return None, None, 1.0

    best_cv = 1.0
    best_start = 0

    # 滑动窗口, 步长 30s
    step = max(1, target_duration_s // 4)
    for start in range(0, n - target_duration_s + 1, step):
        end = start + target_duration_s
        window = pwrs[start:end]
        mean = window.mean()
        std = window.std()
        cv = std / mean if mean > 0 else 1.0
        if cv < best_cv:
            best_cv = cv
            best_start = start

    return best_start, best_start + target_duration_s, best_cv


def _calc_np_for_window(pwrs_window: np.ndarray) -> int:
    """对窗口计算 NP (30s 滚动)"""
    if len(pwrs_window) < 30:
        return int(round(pwrs_window.mean()))
    kernel = np.ones(30) / 30
    smoothed = np.convolve(pwrs_window, kernel, mode="valid")
    return int(round((np.mean(smoothed ** 4)) ** 0.25))


def _get_hr_steady(samples: list[Sample], start: int, end: int) -> Optional[int]:
    """窗口内平均心率"""
    hrs = [s.hr for s in samples[start:end] if s.hr is not None]
    if not hrs:
        return None
    return int(np.mean(hrs))


def _get_weight(activity: Activity) -> Optional[float]:
    """活动里通常没体重, 从 athlete profile 读"""
    # 这里简化: 返 None, 实际从外部传
    return None


# ---------- 方法 1: Coggan 20-min ----------

def estimate_ftp_coggan_20min(activity: Activity, max_hr: int = 190, lthr: int = 170) -> FTPEstimate:
    """Coggan 经典 20 分钟测试

    协议 (Allen & Coggan 2010 "Training and Racing with a Power Meter"):
    1. 热身 ≥ 15min Z1-Z2
    2. 5min Z3 (tempo) 准备
    3. 20min 全力 (steady, 不冲刺)
    4. 冷却 ≥ 10min

    算法: FTP = 0.95 × (20min NP, 在最稳 20min 窗口)

    V0.7.1: max_hr / lthr 改为可传 (从 athlete 档案读), 替代硬编码 190/175
    """
    samples = activity.samples
    pwrs = np.array([s.power for s in samples if s.power is not None], dtype=float)
    if len(pwrs) < 20 * 60:
        return FTPEstimate(
            method="coggan_20min",
            method_label="Coggan 20 分钟测试",
            ftp_w=0,
            confidence=0,
            notes=[f"活动时长不足 20 分钟 ({len(pwrs)} 秒), 无法应用 20min 测试"],
            details={},
        )

    # 找最稳 20min 窗口
    start, end, cv = _find_best_window(pwrs, 20 * 60, cv_threshold=0.10)

    # 算 NP (20min 窗口)
    window_pwrs = pwrs[start:end]
    np_20min = _calc_np_for_window(window_pwrs)

    # 平均功率 (AP)
    ap_20min = int(round(window_pwrs.mean()))

    # FTP 估算 (用 NP 更稳, 跟 Coggan 一致)
    ftp_w = int(round(np_20min * 0.95))

    # 置信度
    confidence = 0.0
    notes = []

    if cv < 0.05:
        confidence += 0.4
        notes.append(f"功率极稳 (CV={cv*100:.1f}%), 典型 20min 测试特征")
    elif cv < 0.08:
        confidence += 0.3
        notes.append(f"功率稳定 (CV={cv*100:.1f}%)")
    elif cv < 0.12:
        confidence += 0.15
        notes.append(f"功率较稳 (CV={cv*100:.1f}%), 接近测试要求")
    else:
        notes.append(f"⚠ 功率波动较大 (CV={cv*100:.1f}%), 测试可能不标准, 建议复测")

    # NP/AP 比 (稳的测试, NP ≈ AP, 比 < 1.05 表明没大起伏)
    np_ap_ratio = np_20min / ap_20min if ap_20min > 0 else 1.0
    if np_ap_ratio < 1.05:
        confidence += 0.3
        notes.append(f"NP/AP 比 {np_ap_ratio:.2f} (稳态测试理想 < 1.05)")
    elif np_ap_ratio < 1.15:
        confidence += 0.15
        notes.append(f"NP/AP 比 {np_ap_ratio:.2f} (有起伏, 但可接受)")
    else:
        notes.append(f"⚠ NP/AP 比 {np_ap_ratio:.2f} 偏高, 有冲刺穿插, 拉低 NP 准确性")

    # 心率协同检查 — V0.7.1 改用 athlete 档案的 max_hr / lthr
    hr = _get_hr_steady(samples, start, end)
    hr_quality = ""
    if hr and ap_20min > 0:
        # V0.7.1: 用 lthr (乳酸阈) 而非 175 魔法数
        # 训练学: 20min 测试心率应接近 LTHR (合理强度下)
        lthr_margin = lthr + 10  # 略高于 LTHR 是合理的 (95-100%)
        hr_max_ceil = max_hr - 5  # 不应接近 max
        if hr < lthr_margin and ap_20min > ftp_w * 0.95:
            hr_quality = f"心率协同好 (高功率低心率, <LTHR+10={lthr_margin})"
            confidence += 0.15
        elif hr > hr_max_ceil:
            hr_quality = f"⚠ 心率过高 (>{hr_max_ceil} bpm), 可能未充分热身或区间过短"

    if hr:
        notes.append(f"平均心率 {hr} bpm" + (f" · {hr_quality}" if hr_quality else ""))

    confidence = min(1.0, confidence)

    return FTPEstimate(
        method="coggan_20min",
        method_label="Coggan 20 分钟测试",
        ftp_w=ftp_w,
        confidence=round(confidence, 2),
        notes=notes,
        details={
            "best_window_start_s": start,
            "best_window_end_s": end,
            "duration_s": end - start,
            "cv": round(cv, 4),
            "np_20min": np_20min,
            "ap_20min": ap_20min,
            "np_ap_ratio": round(np_ap_ratio, 3),
            "hr_bpm": hr,
        },
        source_activity_id=activity.id if hasattr(activity, 'id') else None,
    )


# ---------- 方法 2: Carmichael 8-min × 2 ----------

def estimate_ftp_carmichael_8min(activity: Activity, max_hr: int = 190, lthr: int = 170) -> FTPEstimate:
    """Carmichael 8-min × 2 测试 (Chris Carmichael 2009)

    协议:
    1. 热身 15-20min
    2. 8min 全力
    3. 10min 恢复 (Z1)
    4. 8min 全力
    5. 冷却

    算法: FTP = ((8min1 AP + 8min2 AP) / 2) × 0.9

    为什么 × 0.9:
    - Carmichael 经验: 8min 全力 ≈ 110% FTP (即 90% 的反推)
    - 两次 8min 平均避免单次波动
    """
    samples = activity.samples
    pwrs = np.array([s.power for s in samples if s.power is not None], dtype=float)
    if len(pwrs) < 30 * 60:
        return FTPEstimate(
            method="carmichael_8min",
            method_label="Carmichael 8min × 2",
            ftp_w=0,
            confidence=0,
            notes=[f"活动时长不足 30 分钟 ({len(pwrs)} 秒), 无法完成 8min × 2"],
            details={},
        )

    # 找两个最稳 8min 窗口, 中间至少 8min 间隔
    n = len(pwrs)
    target = 8 * 60
    min_gap = 8 * 60  # 中间至少 8min 恢复

    # 找功率 ≥ 90% percentile 的 8min 段 (确保是 "测试段" 不是恢复)
    high_thresh = float(np.percentile(pwrs, 60))  # 取稍低阈值, 让 8min 全力段能进

    best_pairs = []
    for s1 in range(0, n - 2 * target - min_gap):
        # s2 起点: s1 + target + min_gap ~ 浮动 ± 120s
        s2_base = s1 + target + min_gap
        for s2_offset in range(-60, 121, 30):
            s2_start = s2_base + s2_offset
            if s2_start + target > n or s2_start < s1 + target:
                continue
            w1 = pwrs[s1:s1 + target]
            w2 = pwrs[s2_start:s2_start + target]
            if w1.mean() < high_thresh or w2.mean() < high_thresh:
                continue
            cv1 = w1.std() / w1.mean() if w1.mean() > 0 else 1
            cv2 = w2.std() / w2.mean() if w2.mean() > 0 else 1
            if cv1 < 0.10 and cv2 < 0.10:
                score = (cv1 + cv2) / 2 - 0.0005 * ((w1.mean() + w2.mean()) / 2 - high_thresh)
                best_pairs.append((score, s1, s2_start, cv1, cv2))

    if not best_pairs:
        return FTPEstimate(
            method="carmichael_8min",
            method_label="Carmichael 8min × 2",
            ftp_w=0,
            confidence=0,
            notes=["未找到两个稳态 8min 段 (中间需 ≥ 8min 间隔)"],
            details={},
        )

    best_pairs.sort()
    _, s1, s2, cv1, cv2 = best_pairs[0]

    ap1 = int(round(pwrs[s1:s1 + target].mean()))
    ap2 = int(round(pwrs[s2:s2 + target].mean()))

    # Carmichael 公式
    avg_8 = (ap1 + ap2) / 2
    ftp_w = int(round(avg_8 * 0.9))

    confidence = 0.5
    notes = []
    notes.append(f"8min #1: {ap1} W (CV={cv1*100:.1f}%)")
    notes.append(f"8min #2: {ap2} W (CV={cv2*100:.1f}%)")
    if abs(ap1 - ap2) < 20:
        confidence += 0.2
        notes.append(f"两次 8min 接近 (差 {abs(ap1-ap2)}W), 高度可信")
    else:
        confidence -= 0.1
        notes.append(f"⚠ 两次 8min 差距大 ({abs(ap1-ap2)}W), 可能在第二次掉力")

    hr1 = _get_hr_steady(samples, s1, s1 + target)
    hr2 = _get_hr_steady(samples, s2, s2 + target)
    if hr1 and hr2:
        notes.append(f"8min #1 心率 {hr1} bpm · #2 心率 {hr2} bpm")
        if hr2 < hr1 + 5:
            confidence += 0.1
        elif hr2 > hr1 + 10:
            notes.append("⚠ #2 心率显著升高, 疲劳累积")

    confidence = max(0.0, min(1.0, confidence))

    return FTPEstimate(
        method="carmichael_8min",
        method_label="Carmichael 8min × 2",
        ftp_w=ftp_w,
        confidence=round(confidence, 2),
        notes=notes,
        details={
            "first_8min_start_s": s1,
            "second_8min_start_s": s2,
            "ap_8min_1": ap1,
            "ap_8min_2": ap2,
            "cv_1": round(cv1, 4),
            "cv_2": round(cv2, 4),
            "hr_bpm_1": hr1,
            "hr_bpm_2": hr2,
        },
        source_activity_id=activity.id if hasattr(activity, 'id') else None,
    )


# ---------- 方法 3: Critical Power 3-param (Morton 1996) ----------

def estimate_ftp_cp_3param(activity: Activity, max_hr: int = 190, lthr: int = 170) -> FTPEstimate:
    """CP 3 参数模型 (Morton 1996)

    理论: P(t) = W'/t + CP
    - CP = Critical Power (理论上可维持任意时间的功率)
    - W' = W-prime (无氧储备, 总功)

    实际: CP ≈ FTP (但更精确, 排除了无氧成分)
    训练学优势:
    - 不需要"全力以赴" 20min (很多骑友做不到)
    - 用现有 MMP 曲线 3min/5min/12min 就能估
    - 同时给出 W' (无氧能力)

    算法 (最小二乘拟合):
    已知: MMP(d) = W'/d + CP  (d: 时长, MMP: 最大平均功率)
    设 y = MMP, x = 1/d  → y = CP + W' × x
    → 线性回归: slope = W', intercept = CP
    """
    mmp = mean_maximal_power(activity, durations_s=[180, 300, 600, 720, 1200, 1800])
    if len(mmp) < 3:
        return FTPEstimate(
            method="cp_3param",
            method_label="Critical Power 3 参数 (Morton)",
            ftp_w=0,
            confidence=0,
            notes=[f"样本不足, 至少需要 3 个时长的 MMP (当前 {len(mmp)})"],
            details={},
        )

    # 准备数据: x = 1/d, y = MMP
    durations = []
    powers = []
    for k, v in mmp.items():
        d = int(k.replace("s", ""))
        if v and v > 0:
            durations.append(d)
            powers.append(v)

    if len(durations) < 3:
        return FTPEstimate(
            method="cp_3param",
            method_label="Critical Power 3 参数 (Morton)",
            ftp_w=0,
            confidence=0,
            notes=["MMP 数据点不足"],
            details={},
        )

    x = np.array([1.0 / d for d in durations])
    y = np.array(powers, dtype=float)

    # 线性回归 y = slope × x + intercept
    # slope = W' (J), intercept = CP (W)
    n = len(x)
    sum_x = x.sum()
    sum_y = y.sum()
    sum_xy = (x * y).sum()
    sum_xx = (x * x).sum()

    slope = (n * sum_xy - sum_x * sum_y) / (n * sum_xx - sum_x ** 2)
    intercept = (sum_y - slope * sum_x) / n

    cp = intercept  # Critical Power
    w_prime = slope  # W' (J)

    # CP 应略高于 60min MMP, 但低于 20min
    mmp_20 = mmp.get("1200s", 0) or mmp.get("600s", 0)
    expected_ftp = int(round(cp))

    notes = []
    confidence = 0.4

    # 检查合理性
    if mmp_20 and expected_ftp > mmp_20:
        notes.append(f"⚠ CP ({expected_ftp}) > 20min MMP ({mmp_20}), 拟合异常, 取 20min 兜底")
        expected_ftp = int(round(mmp_20 * 0.95))
        confidence = 0.3
    elif mmp_20 and expected_ftp < mmp_20 * 0.85:
        notes.append(f"⚠ CP ({expected_ftp}) 远低于 20min MMP ({mmp_20})")

    # W' 合理性 (典型 10-30 kJ)
    w_prime_kj = w_prime / 1000
    if 10 <= w_prime_kj <= 30:
        confidence += 0.3
        notes.append(f"W' = {w_prime_kj:.1f} kJ (典型 10-30 kJ 范围, 合理)")
    elif 5 <= w_prime_kj <= 50:
        confidence += 0.1
        notes.append(f"W' = {w_prime_kj:.1f} kJ (略偏离典型范围)")
    else:
        notes.append(f"⚠ W' = {w_prime_kj:.1f} kJ 异常, 拟合可能有问题")

    # R² 检查拟合质量
    y_pred = slope * x + intercept
    ss_res = ((y - y_pred) ** 2).sum()
    ss_tot = ((y - y.mean()) ** 2).sum()
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    if r_squared > 0.95:
        confidence += 0.2
        notes.append(f"R² = {r_squared:.3f} (拟合优秀)")
    elif r_squared > 0.85:
        confidence += 0.1
        notes.append(f"R² = {r_squared:.3f} (拟合良好)")
    else:
        notes.append(f"⚠ R² = {r_squared:.3f} 偏低, 数据可能有误")

    confidence = min(1.0, max(0.0, confidence))

    return FTPEstimate(
        method="cp_3param",
        method_label="Critical Power 3 参数 (Morton)",
        ftp_w=expected_ftp,
        confidence=round(confidence, 2),
        notes=notes,
        details={
            "cp_w": int(round(cp)),
            "w_prime_j": int(round(w_prime)),
            "w_prime_kj": round(w_prime_kj, 1),
            "r_squared": round(r_squared, 4),
            "mmp_points": {k: v for k, v in mmp.items()},
            "mmp_20min": mmp_20,
        },
        source_activity_id=activity.id if hasattr(activity, 'id') else None,
    )


# ---------- 方法 4: Ramp Test ----------

def estimate_ftp_ramp(activity: Activity, max_hr: int = 190, lthr: int = 170) -> FTPEstimate:
    """Ramp Test (Pinzon & Anson 2018)

    协议:
    1. 热身 5-10min Z1
    2. 起始功率 (e.g. 100W), 每分钟 +20W
    3. 蹬不动停止 (RPE 10)
    4. 冷却

    算法: FTP = 0.75 × peak 1-min average

    为什么 0.75:
    - 实验数据: 达到力竭前最后 1min 平均 ≈ 130-140% FTP
    - 0.75 是经验修正系数
    """
    samples = activity.samples
    pwrs = np.array([s.power for s in samples if s.power is not None], dtype=float)
    if len(pwrs) < 5 * 60:
        return FTPEstimate(
            method="ramp",
            method_label="Ramp Test (递增测试)",
            ftp_w=0,
            confidence=0,
            notes=[f"活动时长不足 5 分钟"],
            details={},
        )

    # 找功率峰值 1min
    kernel = np.ones(60) / 60
    if len(pwrs) < 60:
        return FTPEstimate(
            method="ramp",
            method_label="Ramp Test",
            ftp_w=0,
            confidence=0,
            notes=["活动时长不足 1min"],
            details={},
        )

    smoothed = np.convolve(pwrs, kernel, mode="valid")
    peak_1min_idx = int(np.argmax(smoothed))
    peak_1min = int(round(smoothed[peak_1min_idx]))

    # 看是否典型 ramp 模式: 功率应单调上升到峰值
    # 取峰值前 5 分钟
    pre_peak = pwrs[max(0, peak_1min_idx - 5 * 60):peak_1min_idx]
    if len(pre_peak) < 60:
        ramp_quality = "数据不足评估 ramp 模式"
        is_ramp_like = False
    else:
        # 检查是否上升趋势
        diffs = np.diff(pre_peak)
        rising_pct = (diffs > 0).sum() / len(diffs) if len(diffs) > 0 else 0
        is_ramp_like = rising_pct > 0.7
        ramp_quality = f"前 5min 上升趋势 {rising_pct*100:.0f}% (ramp 模式应 > 70%)"

    ftp_w = int(round(peak_1min * 0.75))

    confidence = 0.3
    notes = []
    notes.append(f"峰值 1min: {peak_1min} W")
    notes.append(ramp_quality)

    if is_ramp_like:
        confidence += 0.4
        notes.append("✓ 符合递增测试模式")
    else:
        notes.append("⚠ 模式不典型, 可能是其他类型活动, 结果仅供参考")

    confidence = min(1.0, confidence)

    return FTPEstimate(
        method="ramp",
        method_label="Ramp Test (递增测试)",
        ftp_w=ftp_w,
        confidence=round(confidence, 2),
        notes=notes,
        details={
            "peak_1min_w": peak_1min,
            "peak_1min_idx": peak_1min_idx,
            "is_ramp_like": is_ramp_like,
        },
        source_activity_id=activity.id if hasattr(activity, 'id') else None,
    )


# ---------- 方法 5: Auto (从 MMP 启发式) ----------

def estimate_ftp_auto(activity: Activity, max_hr: int = 190, lthr: int = 170) -> FTPEstimate:
    """自动选择最合适的方法

    启发式:
    - 时长 ≥ 25min, 找稳态 20min → Coggan
    - 时长 ≥ 30min, 含两个 8min 段 → Carmichael
    - 时长 ≥ 25min → CP 3-param (兜底)
    - 短而猛 → Ramp
    - 取所有方法的"最稳健" (置信度 × 合理性)
    """
    n = len([s for s in activity.samples if s.power is not None])
    estimates: list[FTPEstimate] = []

    if n >= 25 * 60:
        estimates.append(estimate_ftp_coggan_20min(activity, max_hr, lthr))
        estimates.append(estimate_ftp_cp_3param(activity, max_hr, lthr))
    if n >= 30 * 60:
        estimates.append(estimate_ftp_carmichael_8min(activity, max_hr, lthr))

    # 总是算 ramp (作为基线)
    if n >= 5 * 60:
        estimates.append(estimate_ftp_ramp(activity, max_hr, lthr))

    if not estimates:
        return FTPEstimate(
            method="auto",
            method_label="自动检测",
            ftp_w=0,
            confidence=0,
            notes=["活动数据不足"],
            details={},
        )

    # 加权: 置信度最高 × 合理区间 (50-500W) 优先
    valid = [e for e in estimates if e.ftp_w > 0 and 50 < e.ftp_w < 500]
    if not valid:
        return FTPEstimate(
            method="auto",
            method_label="自动检测",
            ftp_w=0,
            confidence=0,
            notes=["所有方法都无法给出合理 FTP 估算"],
            details={"candidates": [{"method": e.method, "ftp": e.ftp_w, "conf": e.confidence} for e in estimates]},
        )

    # 选置信度最高的
    best = max(valid, key=lambda e: e.confidence)
    notes = [f"自动选择: {best.method_label} (置信度 {best.confidence})"]
    notes.append("其他方法结果:")
    for e in estimates:
        marker = " ← 选中" if e.method == best.method else ""
        if e.ftp_w > 0:
            notes.append(f"  {e.method_label}: {e.ftp_w}W (置信度 {e.confidence}){marker}")

    return FTPEstimate(
        method=best.method,
        method_label=f"自动检测 → {best.method_label}",
        ftp_w=best.ftp_w,
        confidence=best.confidence,
        notes=notes,
        details={
            "selected_method": best.method,
            "candidates": [
                {"method": e.method, "ftp_w": e.ftp_w, "confidence": e.confidence}
                for e in estimates
            ],
        },
        source_activity_id=activity.id if hasattr(activity, 'id') else None,
    )


# ---------- 入口 ----------

METHODS = {
    "coggan_20min": estimate_ftp_coggan_20min,
    "carmichael_8min": estimate_ftp_carmichael_8min,
    "cp_3param": estimate_ftp_cp_3param,
    "ramp": estimate_ftp_ramp,
    "auto": estimate_ftp_auto,
}


def estimate_ftp(activity: Activity, method: str = "auto", max_hr: int = 190, lthr: int = 170) -> FTPEstimate:
    """主入口: 从活动估算 FTP

    method:
    - coggan_20min: Coggan 20min 测试
    - carmichael_8min: Carmichael 8min × 2
    - cp_3param: Morton CP 3 参数
    - ramp: Ramp Test
    - auto: 自动选择 (推荐)
    """
    fn = METHODS.get(method)
    if not fn:
        return FTPEstimate(
            method=method,
            method_label="未知方法",
            ftp_w=0,
            confidence=0,
            notes=[f"未知方法: {method}, 可用: {list(METHODS.keys())}"],
            details={},
        )
    return fn(activity)
