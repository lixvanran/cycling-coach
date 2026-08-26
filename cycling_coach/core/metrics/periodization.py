"""Periodization 真正的算法推导 — V0.6.1 深度版

学术依据 (Joe Friel 训练学 + 现代周期化):
- Base 期 (4-12 周): Z1-Z2 为主, 大量耐力, 建立有氧基础
- Build 期 (3-6 周): 引入 threshold + VO2max, 强化
- Peak 期 (2-3 周): 模拟比赛, 高强度短间歇
- Taper 期 (1-2 周): 降量 40-60%, 蓄能
- Race: 比赛日
- Recovery (1-2 周): 极轻量, 主动恢复
- Rest (1-4 周): 不训练, 休赛期

关键算法:
1. 当前阶段判定 (基于 CTL 趋势 + TSB 状态)
2. 比赛日倒推 (Race - 16w Base → - 12w Build → - 6w Peak → - 2w Taper)
3. 周目标 TSS 自动推导 (基于当前 CTL + 阶段)
4. Polarized 80/20 检测 (Seiler)
5. 周计划自动生成 (Z1/Z2/Z3/Z4/Z5 时间分配)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta, date as _date
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Activity, TrainingPhase, FTPTest
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.pmc import get_pmc_today, get_pmc_series


# ---------- 数据结构 ----------

@dataclass
class PhaseDerivation:
    """阶段自动推导结果"""
    suggested_type: str           # base/build/peak/taper/recovery/race
    suggested_label: str
    confidence: float             # 0-1
    reasons: list[str]            # 推导依据
    target_weekly_tss: int        # 建议周目标 TSS
    target_weekly_tss_range: tuple[int, int]  # 范围
    weeks_recommended: int        # 建议持续周数
    weeks_to_race: Optional[int]  # 距比赛几周
    current_ctl: float
    current_atl: float
    current_tsb: float
    ramp_rate: float              # TSS/wk


@dataclass
class PolarizedAnalysis:
    """极化训练分布 (Seiler 80/20)"""
    total_seconds: int
    z1_seconds: int  # Active Recovery
    z2_seconds: int  # Endurance
    z3_seconds: int  # Tempo
    z4_seconds: int  # Threshold
    z5_seconds: int  # VO2max
    z6_seconds: int  # Anaerobic
    z7_seconds: int  # Neuromuscular

    easy_pct: float  # Z1+Z2 占比
    hard_pct: float  # Z5+Z6+Z7 占比
    threshold_pct: float  # Z4 占比
    polarized_score: float  # 0-1, 越高越极化 (80/20 目标)
    interpretation: str
    days_analyzed: int
    target_easy_pct: float = 0.80
    target_hard_pct: float = 0.20


@dataclass
class RacePlan:
    """比赛日倒推计划"""
    race_date: _date
    race_name: str
    weeks_total: int
    plan: list[dict]  # [{phase, weeks, weekly_tss, ftp_target, notes}]


# ---------- 工具: 7 区 (Coggan) ----------

COGGAN_ZONES = [
    ("Z1", "Active Recovery", 0.0, 0.55),
    ("Z2", "Endurance", 0.55, 0.75),
    ("Z3", "Tempo", 0.75, 0.90),
    ("Z4", "Threshold", 0.90, 1.05),
    ("Z5", "VO2max", 1.05, 1.20),
    ("Z6", "Anaerobic", 1.20, 1.50),
    ("Z7", "Neuromuscular", 1.50, 999),
]


# ---------- 阶段自动推导 ----------

def derive_phase(db: Session, athlete_id: int) -> PhaseDerivation:
    """基于 PMC + 比赛日 + 历史, 自动推导当前应处阶段

    决策树:
    1. 距比赛 0-7 天 → Race
    2. 距比赛 8-14 天 → Taper (赛前减量)
    3. 距比赛 15-28 天 → Peak (巅峰期)
    4. 距比赛 29-84 天 (4-12 周) → Build
    5. 距比赛 > 84 天 → Base
    6. 无比赛:
       - TSB < -30 持续 → Recovery
       - ramp_rate > 8 TSS/wk + ATL 极高 → Taper 自发
       - CTL 稳定 + IF 0.7-0.85 → Build
       - CTL 低 (< 50) → Base
       - 长期高负荷 (>4 周) → Build
       - 长期休训 → Rest
    """
    today_pmc = get_pmc_today(db, athlete_id)
    ctl = today_pmc.get("ctl", 0)
    atl = today_pmc.get("atl", 0)
    tsb = today_pmc.get("tsb", 0)
    ramp_rate = today_pmc.get("ramp_rate", 0)

    # 找下一个比赛
    next_race = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete_id)
        .filter(TrainingPhase.is_race == True)  # noqa: E712
        .filter(TrainingPhase.end_date >= datetime.utcnow())
        .order_by(TrainingPhase.start_date.asc())
        .first()
    )

    weeks_to_race = None
    if next_race:
        days_to = (next_race.start_date.date() - datetime.utcnow().date()).days
        weeks_to_race = max(0, days_to // 7)

    # 找当前是否在 phase 内
    now = datetime.utcnow()
    current_phase = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete_id)
        .filter(TrainingPhase.start_date <= now)
        .filter(TrainingPhase.end_date >= now)
        .order_by(TrainingPhase.start_date.desc())
        .first()
    )

    reasons: list[str] = []
    confidence = 0.5
    suggested = "base"
    label = "基础期"
    weeks_rec = 8
    target_weekly = int(ctl * 1.1) if ctl > 0 else 300
    target_range = (int(ctl * 0.95), int(ctl * 1.2)) if ctl > 0 else (250, 350)

    # 决策 1: 比赛倒推
    if weeks_to_race is not None:
        if weeks_to_race == 0:
            suggested = "race"
            label = "比赛日"
            target_weekly = int(ctl * 0.3)
            target_range = (0, int(ctl * 0.4))
            weeks_rec = 1
            confidence = 0.95
            reasons.append(f"距比赛 {weeks_to_race} 周 → 比赛日")
            if next_race:
                reasons.append(f"比赛: {next_race.name} ({next_race.start_date.date()})")
        elif weeks_to_race == 1:
            suggested = "taper"
            label = "减量期 (赛前 1 周)"
            target_weekly = int(ctl * 0.5)
            target_range = (int(ctl * 0.4), int(ctl * 0.6))
            weeks_rec = 1
            confidence = 0.9
            reasons.append(f"距比赛 1 周 → 最后减量, 降量 50%")
        elif weeks_to_race <= 2:
            suggested = "taper"
            label = "减量期 (赛前 2 周)"
            target_weekly = int(ctl * 0.6)
            target_range = (int(ctl * 0.5), int(ctl * 0.7))
            weeks_rec = 2
            confidence = 0.85
            reasons.append(f"距比赛 2 周 → 减量 40%")
        elif weeks_to_race <= 4:
            suggested = "peak"
            label = "巅峰期 (赛前 4 周)"
            target_weekly = int(ctl * 1.0)
            target_range = (int(ctl * 0.9), int(ctl * 1.1))
            weeks_rec = 2
            confidence = 0.8
            reasons.append(f"距比赛 4 周 → 巅峰期, 保持 CTL, 强化质")
        elif weeks_to_race <= 12:
            suggested = "build"
            label = "强化期"
            target_weekly = int(ctl * 1.3)
            target_range = (int(ctl * 1.2), int(ctl * 1.4))
            weeks_rec = 6
            confidence = 0.75
            reasons.append(f"距比赛 {weeks_to_race} 周 → 强化期, CTL × 1.3")
        else:
            suggested = "base"
            label = "基础期"
            target_weekly = int(ctl * 1.15)
            target_range = (int(ctl * 1.0), int(ctl * 1.3))
            weeks_rec = 8
            confidence = 0.7
            reasons.append(f"距比赛 {weeks_to_race} 周 (> 12) → 基础期")

        if next_race:
            reasons.insert(0, f"目标比赛: {next_race.name} ({next_race.start_date.date()})")
    else:
        # 决策 2: 无比赛, 看 PMC 状态
        reasons.append("无目标比赛, 基于 PMC 状态推导")
        if ctl < 30:
            suggested = "base"
            label = "基础期 (低 CTL)"
            weeks_rec = 6
            target_weekly = 250
            target_range = (200, 300)
            reasons.append(f"CTL {ctl:.0f} 偏低 (< 30), 基础期建立有氧")
        elif tsb < -30:
            suggested = "recovery"
            label = "恢复期 (TSB 极低)"
            weeks_rec = 1
            target_weekly = int(ctl * 0.5)
            target_range = (0, int(ctl * 0.6))
            reasons.append(f"TSB {tsb:.0f} < -30, 深度疲劳, 需恢复")
        elif ramp_rate > 8 and atl > ctl:
            suggested = "taper"
            label = "减量期 (ATL 风险)"
            weeks_rec = 1
            target_weekly = int(ctl * 0.7)
            target_range = (int(ctl * 0.5), int(ctl * 0.8))
            reasons.append(f"ramp_rate {ramp_rate:.1f} TSS/wk + ATL > CTL, 急性疲劳过载")
        elif ctl < 70 and ramp_rate > 0:
            suggested = "build"
            label = "强化期 (CTL 提升中)"
            weeks_rec = 6
            target_weekly = int(ctl * 1.25)
            target_range = (int(ctl * 1.15), int(ctl * 1.35))
            reasons.append(f"CTL {ctl:.0f} 中低, ramp_rate {ramp_rate:.1f}, 强化中")
        elif ctl >= 70 and abs(ramp_rate) < 2:
            suggested = "peak"
            label = "巅峰期 (CTL 稳定)"
            weeks_rec = 3
            target_weekly = int(ctl)
            target_range = (int(ctl * 0.9), int(ctl * 1.1))
            reasons.append(f"CTL {ctl:.0f} 高位稳定, 可进入巅峰/比赛准备")
        elif ramp_rate < -3:
            suggested = "recovery"
            label = "恢复期 (ramp 下降)"
            weeks_rec = 1
            target_weekly = int(ctl * 0.6)
            target_range = (int(ctl * 0.4), int(ctl * 0.7))
            reasons.append(f"ramp_rate {ramp_rate:.1f} 下降, 已在减量")
        else:
            suggested = "build"
            label = "强化期 (常规)"
            weeks_rec = 4
            target_weekly = int(ctl * 1.2)
            target_range = (int(ctl * 1.1), int(ctl * 1.3))
            reasons.append(f"默认: CTL {ctl:.0f}, ramp {ramp_rate:.1f}, 常规强化")

    # 加修正因素
    if current_phase:
        reasons.append(f"当前阶段: {current_phase.name} ({current_phase.phase_type})")

    return PhaseDerivation(
        suggested_type=suggested,
        suggested_label=label,
        confidence=round(confidence, 2),
        reasons=reasons,
        target_weekly_tss=target_weekly,
        target_weekly_tss_range=target_range,
        weeks_recommended=weeks_rec,
        weeks_to_race=weeks_to_race,
        current_ctl=ctl,
        current_atl=atl,
        current_tsb=tsb,
        ramp_rate=ramp_rate,
    )


# ---------- 比赛日倒推计划生成 ----------

def generate_race_plan(
    race_date: _date,
    race_name: str,
    current_ctl: float = 50,
    current_ftp: int = 250,
) -> RacePlan:
    """比赛日倒推, 生成完整周期计划

    训练学标准 (Joe Friel "The Cyclist's Training Bible"):
    - Base: 12-16 周 (有氧基础 + 力量)
    - Build: 6-8 周 (强化 threshold + VO2)
    - Peak: 2-3 周 (模拟比赛)
    - Taper: 1-2 周 (减量 50-60%)
    - Race: 1 天
    - Recovery: 1-2 周 (主动恢复)
    """
    today = datetime.utcnow().date()
    days_to_race = (race_date - today).days
    weeks_total = max(1, days_to_race // 7)

    if weeks_total < 2:
        # 比赛临近, 简单 Taper
        return RacePlan(
            race_date=race_date,
            race_name=race_name,
            weeks_total=weeks_total,
            plan=[{
                "phase": "taper",
                "label": "减量期",
                "weeks": weeks_total,
                "weekly_tss_target": int(current_ctl * 0.6),
                "weekly_tss_range": (int(current_ctl * 0.4), int(current_ctl * 0.7)),
                "ftp_target": current_ftp,
                "zone_distribution": {"Z1": 0.30, "Z2": 0.50, "Z3": 0.15, "Z4": 0.05, "Z5+": 0.0},
                "intensity_focus": "短间歇 + 长恢复骑, 蓄能",
                "key_workouts": ["4×30s 全力 sprint", "60min Z2 轻松", "2×8min threshold"],
                "notes": "降量 50%, 保持高强度短间歇维持神经肌肉",
            }],
        )

    # 标准 16 周: 12 base + 4 build (然后建议加更长)
    plan = []

    # 分配周数
    if weeks_total >= 16:
        base_w = 8
        build1_w = 4
        build2_w = 3  # 第二个 build 周期
        peak_w = 2
        taper_w = 2
        recovery_w = 0  # 比赛后
    elif weeks_total >= 10:
        base_w = max(2, weeks_total - 9)
        build1_w = 4
        build2_w = 2
        peak_w = 2
        taper_w = 1
    else:
        # 短: build 为主
        base_w = max(0, weeks_total - 7)
        build1_w = min(3, weeks_total - 4)
        build2_w = 2
        peak_w = 1
        taper_w = 1

    # Base 阶段
    if base_w > 0:
        plan.append({
            "phase": "base",
            "label": f"基础期 (第 1 - {base_w} 周)",
            "weeks": base_w,
            "weekly_tss_target": int(current_ctl * (1.0 + 0.05 * base_w / 4)),
            "weekly_tss_range": (int(current_ctl * 0.9), int(current_ctl * 1.1)),
            "ftp_target": current_ftp,
            "zone_distribution": {"Z1": 0.25, "Z2": 0.65, "Z3": 0.08, "Z4": 0.02, "Z5+": 0.0},
            "intensity_focus": "Z2 大量耐力 + 1-2 次 Z3 tempo",
            "key_workouts": [
                "2-3h Z2 长骑",
                "1× 90min Z3 tempo",
                "4×10min Z3 (intervals)",
                "腿/核心力量训练 2×/周",
            ],
            "notes": "重点: 大量 Z2, 每周递增 5-10% TSS",
        })

    # Build 1
    if build1_w > 0:
        plan.append({
            "phase": "build",
            "label": f"强化期 I (Build 1)",
            "weeks": build1_w,
            "weekly_tss_target": int(current_ctl * 1.25),
            "weekly_tss_range": (int(current_ctl * 1.15), int(current_ctl * 1.35)),
            "ftp_target": current_ftp,
            "zone_distribution": {"Z1": 0.18, "Z2": 0.55, "Z3": 0.12, "Z4": 0.10, "Z5+": 0.05},
            "intensity_focus": "引入 threshold + 少量 VO2max",
            "key_workouts": [
                "2×20min threshold (88-94% FTP)",
                "4×8min threshold",
                "3×12min sweet spot",
                "5×4min VO2max",
                "Z2 长骑 1×",
            ],
            "notes": "保持 1-2 次 Z2 长骑, 加 threshold / VO2 间歇",
        })

    # Build 2
    if build2_w > 0:
        plan.append({
            "phase": "build",
            "label": f"强化期 II (Build 2)",
            "weeks": build2_w,
            "weekly_tss_target": int(current_ctl * 1.15),
            "weekly_tss_range": (int(current_ctl * 1.05), int(current_ctl * 1.25)),
            "ftp_target": current_ftp,
            "zone_distribution": {"Z1": 0.15, "Z2": 0.50, "Z3": 0.15, "Z4": 0.12, "Z5+": 0.08},
            "intensity_focus": "增加 VO2max + race-pace 模拟",
            "key_workouts": [
                "5×5min VO2max (110-120% FTP)",
                "4×6min race-pace",
                "2×30min sweet spot",
                "Crit 模拟 (短而猛)",
            ],
            "notes": "Build 2 强度更高, 量略降, 重点提升功率峰值",
        })

    # Peak
    if peak_w > 0:
        plan.append({
            "phase": "peak",
            "label": "巅峰期",
            "weeks": peak_w,
            "weekly_tss_target": int(current_ctl * 1.0),
            "weekly_tss_range": (int(current_ctl * 0.9), int(current_ctl * 1.1)),
            "ftp_target": current_ftp,
            "zone_distribution": {"Z1": 0.20, "Z2": 0.45, "Z3": 0.15, "Z4": 0.10, "Z5+": 0.10},
            "intensity_focus": "模拟比赛强度 (race-pace)",
            "key_workouts": [
                "完整 race-pace 模拟 (跟比赛同样长)",
                "2× 比赛后半段距离 race-pace",
                "sprint 训练 (比赛会用到的话)",
            ],
            "notes": "短而高质量, 重点比赛配速感觉",
        })

    # Taper
    if taper_w > 0:
        plan.append({
            "phase": "taper",
            "label": f"减量期 (Taper, {taper_w} 周)",
            "weeks": taper_w,
            "weekly_tss_target": int(current_ctl * 0.5),
            "weekly_tss_range": (int(current_ctl * 0.4), int(current_ctl * 0.6)),
            "ftp_target": current_ftp,
            "zone_distribution": {"Z1": 0.30, "Z2": 0.50, "Z3": 0.15, "Z4": 0.05, "Z5+": 0.0},
            "intensity_focus": "短而猛, 蓄能",
            "key_workouts": [
                "4×30s 全 sprint (维持神经肌肉)",
                "60min Z2 轻松",
                "2×8min threshold (短促)",
            ],
            "notes": "降量 50%, 不降强度 (Friel 原则), 保持锐度",
        })

    # Race
    plan.append({
        "phase": "race",
        "label": "比赛日",
        "weeks": 1,
        "weekly_tss_target": 0,
        "weekly_tss_range": (0, 0),
        "ftp_target": current_ftp,
        "zone_distribution": {"Z1": 0.0, "Z2": 0.0, "Z3": 0.0, "Z4": 0.0, "Z5+": 1.0},
        "intensity_focus": "全力!",
        "key_workouts": [f"🏁 {race_name}"],
        "notes": "比赛! 相信训练, 不要前段过猛",
    })

    return RacePlan(
        race_date=race_date,
        race_name=race_name,
        weeks_total=weeks_total,
        plan=plan,
    )


# ---------- Seiler 80/20 极化分布 ----------

def analyze_polarized(db: Session, athlete_id: int, days: int = 30, ftp_w: int = 250) -> PolarizedAnalysis:
    """Seiler 极化训练分布分析 (80/20 原则)

    Stephen Seiler 2010 经典研究:
    - Z1+Z2 (低强度) ≈ 80% 时间
    - Z5+Z6+Z7 (高强度) ≈ 20% 时间
    - Z3+Z4 (中强度 / threshold) ≈ 0% (避免 "灰色地带")
    - 精英运动员比例可达 90/10

    实际 FTP: 优先用最新 FTPTest
    """
    from cycling_coach.core.metrics.ftp import METHODS as _  # avoid unused

    # 找最新 FTP
    latest_ftp = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == athlete_id)
        .order_by(FTPTest.test_date.desc())
        .first()
    )
    if latest_ftp:
        ftp_w = latest_ftp.ftp_w

    cutoff = datetime.utcnow() - timedelta(days=days)
    activities = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff)
        .filter(Activity.start_time <= datetime.utcnow())
        .all()
    )

    total_seconds = 0
    zone_seconds = {f"Z{i+1}": 0 for i in range(7)}

    for a in activities:
        samples = a.samples_json or []
        if not samples:
            continue
        for s in samples:
            p = s.get("power")
            if p is None or p <= 0:
                continue
            ratio = p / ftp_w
            for i, (code, name, lo, hi) in enumerate(COGGAN_ZONES):
                if lo <= ratio < hi:
                    zone_seconds[code] += 1
                    total_seconds += 1
                    break

    if total_seconds == 0:
        return PolarizedAnalysis(
            total_seconds=0,
            z1_seconds=0, z2_seconds=0, z3_seconds=0, z4_seconds=0,
            z5_seconds=0, z6_seconds=0, z7_seconds=0,
            easy_pct=0, hard_pct=0, threshold_pct=0,
            polarized_score=0, interpretation="无训练数据",
            days_analyzed=days,
        )

    easy_pct = (zone_seconds["Z1"] + zone_seconds["Z2"]) / total_seconds
    threshold_pct = (zone_seconds["Z3"] + zone_seconds["Z4"]) / total_seconds
    hard_pct = (zone_seconds["Z5"] + zone_seconds["Z6"] + zone_seconds["Z7"]) / total_seconds

    # 极化分数: easy 越接近 80%, threshold 越接近 0% → 越高
    # 简单公式: 100 - |easy - 80| - |threshold| - |hard - 20|
    polarized = 100 - abs(easy_pct * 100 - 80) - threshold_pct * 100 - abs(hard_pct * 100 - 20)
    polarized = max(0, min(100, polarized)) / 100

    # 解读
    if easy_pct >= 0.78 and hard_pct <= 0.22 and threshold_pct < 0.10:
        interp = "✓ 优秀极化训练 (接近 Seiler 80/20 目标)"
    elif easy_pct >= 0.70 and hard_pct <= 0.30:
        interp = "接近极化, 但可微调"
    elif threshold_pct > 0.30:
        interp = "⚠ 太多 threshold 训练 (灰色地带), 容易积累疲劳"
    elif easy_pct < 0.65:
        interp = "⚠ 低强度太少, 恢复不足, 长期易过训"
    elif hard_pct > 0.30:
        interp = "⚠ 高强度太多 (> 20%), 需减强度训练"
    else:
        interp = "分布不平衡, 需调整"

    return PolarizedAnalysis(
        total_seconds=total_seconds,
        z1_seconds=zone_seconds["Z1"],
        z2_seconds=zone_seconds["Z2"],
        z3_seconds=zone_seconds["Z3"],
        z4_seconds=zone_seconds["Z4"],
        z5_seconds=zone_seconds["Z5"],
        z6_seconds=zone_seconds["Z6"],
        z7_seconds=zone_seconds["Z7"],
        easy_pct=round(easy_pct, 3),
        hard_pct=round(hard_pct, 3),
        threshold_pct=round(threshold_pct, 3),
        polarized_score=round(polarized, 2),
        interpretation=interp,
        days_analyzed=days,
    )
