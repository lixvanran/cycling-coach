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

from cycling_coach.data.sqlite.models import Activity, TrainingPhase, FTPTest, Athlete, DailyMetric
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
    # 🔴 V0.9.0: 这三个字段原来是非空 int, 于是数据不足时只能填 0。
    # 而 0 是个**看起来合法的训练学数值** —— 前端会老老实实渲染成
    # "目标 TSS 0 / 建议 0 周", 还会拿 0 去调"一键创建"。
    #
    # 改成 Optional: 算不出来就是 None, 让类型系统帮我们说真话。
    # 有了数据时永远是 int, 消费方用 `is not None` 守卫即可。
    target_weekly_tss: Optional[int]        # 建议周目标 TSS (无数据时 None)
    target_weekly_tss_range: Optional[tuple[int, int]]  # 范围 (无数据时 None)
    weeks_recommended: Optional[int]       # 建议持续周数 (无数据时 None)
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


def _polarized_score(hard_pct: float) -> float:
    """Seiler 极化评分 (0-1)

    抽成独立函数是为了能直接测边界 —— 之前这个式子内联在
    detect_phase_signals 里, 算出负数时只有界面能发现。
    """
    return round(min(1.0, max(0.0, 1.0 - abs(0.20 - hard_pct) * 2)), 2)


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
# 🔴 V0.9.0-07: 这里原来用 `datetime.utcnow().date()` (UTC) 算"今天",
# 而 pmc 的读取侧和这个模块的其他部分用本地日期 —— 同一个产品里两个"今天"。
# 中国骑行者 (UTC+8) 每天 00:00-07:59 有 8 小时落在这个缝里:
# 数据归属错一天, 周报/周期化/HRV 窗口全部对不上。
#
# 真时间戳 (completed_at / updated_at) 走 `utcnow_naive()`, 那个是对的,
# 不要一起改 —— 改的是**日历日**语义, 不是时间戳语义。
        days_to = (next_race.start_date.date() - _date.today()).days
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

    # V0.9.0: 没有真实负荷数据时, 下面那些 `ctl < 50` / `tsb < -30` 的
    # 判断全部是在拿 0 当真实读数 —— 零 CTL 会被判成"基础期(低 CTL)",
    # 零 TSB 会被判成"恢复期(TSB 极低)"。方向是反的:
    # 用户需要的不是"你现在处于某个阶段", 而是"先去导入训练记录"。
    #
    # 这跟 race_prep 57.5 分、insights 95 分是同一株病。
    # 之前只在 compute_readiness 里加了一层守卫挡它, 但 derive_phase
    # **还有另外两个调用方** —— 其中一个是 AI 上下文(context.py),
    # 也就是说零数据用户问 AI"我该练什么", 模型会拿到"低 CTL 基础期"
    # 当真实信息。必须在源头修。
    if not today_pmc.get("has_load_data"):
        return PhaseDerivation(
            suggested_type="unknown",
            suggested_label="数据不足，无法判断阶段",
            confidence=0.0,
            reasons=[
                "没有真实训练负荷数据(CTL/ATL 都是 0, 但那是因为没有记录, "
                "不是真的低)"
            ],
            # 不是 0 —— 0 是"建议一周都不练", 那是个**具体的训练处方**。
            # 数据不足时我们**没有处方**, 所以是 None。
            target_weekly_tss=None,
            target_weekly_tss_range=None,
            weeks_recommended=None,
            weeks_to_race=weeks_to_race,
            current_ctl=ctl,
            current_atl=atl,
            current_tsb=tsb,
            ramp_rate=ramp_rate,
        )

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
    today = _date.today()
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


# ---------- V0.7.2 新加: 周期化阶段信号检测 ----------

@dataclass
class PhaseSignals:
    """周期化阶段信号 (用于增强 derive_phase 决策)
    
    借鉴 (V0.7.2 加):
    - Seiler 2010 (极化训练 80/20)
    - Friel "Cyclist's Training Bible" (基础期/强化期/巅峰/减量)
    - Jeukendrup 2018 (周期化营养)
    - Banister TRIMP 累计训练负荷
    """
    # 🔴 V0.9.0-06: 这六个原来都是 float = 0.0, 于是**算不出来和真实的 0
    # 完全分不开**。
    #
    # 实测零数据用户的输出:
    #     avg_if_28d = 0.00        理想区间是 0.70-0.85 → 界面判"不好"
    #     polarized_score_28d = 0.0
    #     freq_7d = 0.0            → "0.0 天/周"
    #
    # 而 PhaseSignalsCard 会拿 0.00 去对照"理想 0.70-0.85"给出红色警告,
    # 甚至生成"增加 Z1-Z2 比例, 减少灰色地带"这种**凭空来的训练处方**。
    #
    # 0.00 看起来像一个真实的测量结果(而不是缺失), 这是 V0.9.0 一直在
    # 消灭的东西。改成 Optional: 算不出来就是 None。
    #
    # streak_days / weeks_since_taper 保持 int —— "0 天连续训练"对零数据
    # 用户是**真的**(他确实一天都没练), 那个 0 是诚实的。
    avg_if_28d: Optional[float] = None
    # 7 天训练频率 (0-1)
    freq_7d: Optional[float] = None
    # 当前训练连续天数 (streak) —— 0 是诚实的
    streak_days: int = 0
    # 距上次减量周数 (≥ 8 → 衰减风险) —— 0 是诚实的
    weeks_since_taper: int = 0
    # 28d 极化评分 (0-1, 1 = 完全极化)
    polarized_score_28d: Optional[float] = None
    # 7d 实际 TSS / 7d 目标 TSS (负荷达成率)
    load_achievement_7d: Optional[float] = None
    # 信号建议
    warnings: list = None  # type: ignore
    hints: list = None  # type: ignore

    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []
        if self.hints is None:
            self.hints = []


def detect_phase_signals(
    db: Session, athlete_id: int, days: int = 28
) -> PhaseSignals:
    """V0.7.2: 检测 7 个周期化阶段信号
    
    1. avg_if_28d: 28 天平均 IF (0.7 = endurance, 0.85 = tempo, 0.95+ = race)
    2. freq_7d: 7 天训练频率 (0.71 = 5/7 天, 目标 4-5 天/周)
    3. streak_days: 连续训练天数 (> 6 = 风险, 建议 1-2 天休)
    4. weeks_since_taper: 距上次减量 (> 8 周 = 衰减风险)
    5. polarized_score_28d: 极化评分 (Seiler 80/20)
    6. load_achievement_7d: 7d 负荷达成率
    """
    from datetime import date as _date
    
    today = _date.today()
    start = today - timedelta(days=days)
    
    signals = PhaseSignals()
    
    # 拉 28d 每日指标
    daily_rows = (
        db.query(DailyMetric)
        .filter(DailyMetric.athlete_id == athlete_id)
        .filter(DailyMetric.date >= start)
        .order_by(DailyMetric.date.asc())
        .all()
    )
    
    if not daily_rows:
        return signals
    
    # 1. 28d 平均 IF (从 avg_power + FTP 推, 简化: TSS/总时长)
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    ftp = (athlete.ftp if athlete and athlete.ftp else None) or (athlete.ftp_estimated if athlete else None) or 200
    
    # 28d 总 TSS / 总时长 (秒) / 3600 = 平均小时
    # IF ≈ NP/FTP, 但我们没有 NP, 用 TSS 估算
    # TSS/时长(小时) ≈ NP^2/FTP^2, 简化: IF = sqrt(TSS/h)
    total_tss = sum(r.tss for r in daily_rows)
    total_hours = sum(r.duration_s for r in daily_rows) / 3600
    if total_hours > 0:
        # 经验公式: IF ≈ sqrt(avg_daily_tss / 1.0) (avg_tss ~ 80 = endurance)
        avg_tss = total_tss / len(daily_rows)
        # 标准化: 100 TSS = roughly IF 1.0, 50 TSS = IF 0.7
        signals.avg_if_28d = round(min(1.5, (avg_tss / 100) ** 0.5), 2)
    
    # 2. 7d 训练频率
    last_7d = [r for r in daily_rows if r.date >= today - timedelta(days=7)]
    active_days = sum(1 for r in last_7d if r.tss > 0)
    signals.freq_7d = round(active_days / 7, 2)
    
    # 3. 训练连续天数
    streak = 0
    for r in reversed(daily_rows):
        if r.tss > 0:
            streak += 1
        else:
            break
    # 只看 last 14d
    signals.streak_days = min(streak, 14)
    
    # 4. 距上次减量周数
    # 简化: 查训练阶段, 找 phase_type=taper/end_date <= today
    # 兜底: 用 ramp_rate 推 (连续 4 周 ramp < 0 → 上次减量)
    # 简单做法: 检查 28d 内 ramp_rate 历史 (pmc 模型已有, 但聚合行没存)
    # 用 last 4 周 ramp_rate 推: 如果最近 4 周 TSS 持续递增 → 上次减量 > 4 周前
    weeks_recent = [r for r in daily_rows if r.date >= today - timedelta(days=28)]
    if len(weeks_recent) >= 21:
        # 4 周 rolling 算平均 weekly TSS
        wk1_avg = sum(r.tss for r in weeks_recent[0:7]) / 7
        wk4_avg = sum(r.tss for r in weeks_recent[21:28]) / 7
        if wk4_avg > 0 and wk1_avg / wk4_avg > 1.2:
            # 4 周前低, 现在高 → 4+ 周没减量
            signals.weeks_since_taper = 4
        else:
            # 看最近 14d 是否有 ramp < 0
            last_14 = [r for r in daily_rows if r.date >= today - timedelta(days=14)]
            if len(last_14) >= 7:
                wk1 = sum(r.tss for r in last_14[0:7]) / 7
                wk2 = sum(r.tss for r in last_14[7:14]) / 7
                if wk2 < wk1 * 0.7:
                    signals.weeks_since_taper = 1  # 14d 内减过
                else:
                    signals.weeks_since_taper = 2
            else:
                signals.weeks_since_taper = 2
    
    # 5. 极化评分 (28d)
    # 简化: 高强度日 (TSS > 100) / 总量
    hard_days = sum(1 for r in daily_rows if r.tss > 100)
    active_total_days = sum(1 for r in daily_rows if r.tss > 0)
    if active_total_days > 0:
        hard_pct = hard_days / active_total_days
        # Seiler 80/20: hard ≈ 20%
        # score: 1.0 = 完美 (hard=20%), 偏离越多越低
        #
        # 🔴 必须 clamp 到 [0, 1]。原式子 1 - |0.2 - hard_pct|*2 在
        # hard_pct > 0.7 时**会算出负数**:
        #     hard_pct=0.8 → -0.20
        #     hard_pct=1.0 → -0.60
        # 于是界面上出现"28d 极化评分 -0.60, 偏离 Seiler 80/20"。
        # 负数评分一眼就是 bug, 用户会怀疑整个 App 的可信度 ——
        # 而这正是我们"诚实"要积累的信任。
        #
        # 0 分的语义是"完全没极化", 而不是"比完全没极化更糟"。
        signals.polarized_score_28d = _polarized_score(hard_pct)
    
    # 6. 7d 负荷达成率
    # 用最近 7d 平均 daily_tss / 7d 目标 (目标 = 近期 CTL × 0.7 经验值)
    if last_7d:
        avg_7d_tss = sum(r.tss for r in last_7d) / 7
        recent_ctl = daily_rows[-1].ctl if daily_rows else 0
        target_7d_tss = max(50, recent_ctl)  # 简化
        if target_7d_tss > 0:
            signals.load_achievement_7d = round(avg_7d_tss / target_7d_tss, 2)
    
    # 信号建议
    if signals.streak_days >= 6:
        signals.warnings.append(
            f"⚠ 连续训练 {signals.streak_days} 天, 建议 1-2 天完全休息"
        )
    if signals.weeks_since_taper >= 8:
        signals.warnings.append(
            f"⚠ 距上次减量 {signals.weeks_since_taper}+ 周, 训练学建议每 8-12 周减量一次"
        )
    # ⚠️ V0.9.0-06: 下面三个字段现在是 Optional —— 算不出来是 None。
    # `None < 0.4` / `None < 0.5` 在 Python 3 里是 TypeError。
    #
    # 这条是我自己写的反向测试抓到的: 12 次训练的用户跑 detect_phase_signals
    # 直接崩了。因为 `if not daily_rows: return signals` 那条早退路径上
    # 它们还是 None, 而下面这堆比较没跟上。
    #
    # **改字段类型 = 所有比较点都要跟着改**, 这跟改函数契约是同一类活。
    if signals.freq_7d is not None and signals.freq_7d < 0.4:
        signals.hints.append(
            f"训练频率偏低 ({signals.freq_7d:.0%}, < 4 天/周), 建议增加 1-2 次轻松骑"
        )
    if signals.polarized_score_28d is not None and signals.polarized_score_28d < 0.5:
        signals.hints.append(
            f"极化评分 {signals.polarized_score_28d:.2f} 偏低, 目标 Seiler 80/20"
        )
    if signals.avg_if_28d is not None and signals.avg_if_28d > 1.0:
        signals.warnings.append(
            f"⚠ 28d 平均 IF {signals.avg_if_28d:.2f} 偏高, 长期高强度风险"
        )
    
    return signals


def derive_phase_enhanced(
    db: Session, athlete_id: int
) -> PhaseDerivation:
    """V0.7.2: 增强版 derive_phase
    
    跟原 derive_phase 一样, 但额外加 phase_signals 警告/提示
    """
    base = derive_phase(db, athlete_id)
    signals = detect_phase_signals(db, athlete_id)
    
    # 合并 warnings/hints 到 reasons
    base.reasons.extend(signals.warnings)
    base.reasons.extend(signals.hints)
    
    # 信号会影响 confidence
    if signals.warnings:
        # 警告 → 降 confidence (说明当前阶段有风险)
        base.confidence = round(max(0.4, base.confidence - 0.1 * len(signals.warnings)), 2)
    
    return base
