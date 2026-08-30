"""V0.7.3: AI 训练建议生成 (模板化, 不依赖 LLM)

借鉴:
- TrainingPeaks "Daily Workout Suggestion"
- WKO5 Readiness Score
- WHOOP Strain Coach
- Plews 2013 (HRV-guided training)
- Gabbett 2016 (ACWR)

设计: 综合 5 维数据 → readiness 0-100 → 行动建议
- 高 readiness (80-100): 高强度日
- 中 readiness (60-79): 阈值间歇
- 低 readiness (40-59): 轻松
- 极低 (< 40): 恢复 / 休息
"""
from __future__ import annotations
import logging
from dataclasses import dataclass, field
from datetime import date as _date, datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.core.pmc import get_pmc_today
from cycling_coach.core.metrics.acwr import get_acwr_overview as get_acwr
from cycling_coach.core.metrics.hrv import compute_hrv_state
from cycling_coach.core.metrics.periodization import (
    detect_phase_signals,
    derive_phase,
)
from cycling_coach.data.sqlite.models import Activity, DailyMetric, Athlete

logger = logging.getLogger(__name__)


@dataclass
class Recommendation:
    """一条训练建议"""
    category: str  # "workout" | "warning" | "tip" | "lifestyle"
    priority: int  # 1-5, 5 = 最重要
    title: str
    detail: str
    action: Optional[str] = None  # 具体动作 (可选)
    icon: Optional[str] = None  # 前端 emoji / icon name


@dataclass
class DailyRecommendation:
    """今日综合建议"""
    date: str
    readiness_score: int  # 0-100
    readiness_label: str  # "极佳" / "良好" / "中等" / "低迷" / "危险"
    recommended_workout_type: str  # "rest" | "recovery" | "endurance" | "tempo" | "threshold" | "vo2"
    recommended_intensity: str  # 描述: "轻松骑 60-90min Z1-Z2" 等
    target_tss: int  # 今日目标 TSS
    recommendations: list[Recommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    signals_summary: dict = field(default_factory=dict)


def compute_readiness(
    db: Session, athlete_id: int
) -> tuple[int, dict]:
    """V0.7.3: 计算 readiness 0-100 (综合 5 维)
    
    借鉴:
    - Plews 2013 (HRV readiness 30 分)
    - Gabbett 2016 (ACWR 25 分)
    - Banister TRIMP (TSB 20 分)
    - Friel CTB (Phase 15 分)
    - 训练学常识 (RPE 7d 10 分)
    
    总分 100, 每维加权:
    - HRV: 30 (心率变异性, 最重要)
    - ACWR: 25 (急慢性负荷比)
    - TSB: 20 (训练平衡)
    - Phase: 15 (周期阶段适配)
    - RPE 7d: 10 (主观疲劳)
    """
    breakdown = {}
    
    # 1. HRV (30 分)
    hrv = compute_hrv_state(db, athlete_id)
    if hrv["status"] == "ok":
        hrv_score = 30
    elif hrv["status"] == "caution":
        hrv_score = 15
    elif hrv["status"] == "warning":
        hrv_score = 0
    else:
        hrv_score = 20  # insufficient_data
    breakdown["hrv"] = hrv_score
    
    # 2. ACWR (25 分)
    acwr = get_acwr(db, days=7)  # get_acwr_overview 内部用 athlete_id
    today = acwr.get("today", {}) if isinstance(acwr, dict) else {}
    acwr_val = today.get("acwr", 1.0) if today else 1.0
    # 0.8-1.3 sweet spot
    if 0.8 <= acwr_val <= 1.3:
        acwr_score = 25
    elif 0.6 <= acwr_val < 0.8 or 1.3 < acwr_val <= 1.5:
        acwr_score = 15
    elif 1.5 < acwr_val <= 1.8:
        acwr_score = 5  # 危险区
    else:
        acwr_score = 0  # 过低/过高
    breakdown["acwr"] = acwr_score
    
    # 3. TSB (20 分)
    pmc = get_pmc_today(db, athlete_id)
    tsb = pmc.get("tsb", 0)
    if -10 <= tsb <= 20:
        tsb_score = 20  # 状态良好
    elif -20 <= tsb < -10 or 20 < tsb <= 30:
        tsb_score = 15
    elif -30 <= tsb < -20:
        tsb_score = 5  # 累积疲劳
    elif tsb > 30:
        tsb_score = 10  # 减量中
    else:
        tsb_score = 0  # 极疲劳
    breakdown["tsb"] = tsb_score
    
    # 4. Phase (15 分) — 周期化阶段适配
    phase = derive_phase(db, athlete_id)
    if phase.suggested_type in ("build", "peak"):
        phase_score = 15  # 强化期 / 巅峰期
    elif phase.suggested_type == "base":
        phase_score = 12  # 基础期
    elif phase.suggested_type == "taper":
        phase_score = 10  # 减量
    elif phase.suggested_type == "recovery":
        phase_score = 5
    elif phase.suggested_type == "race":
        phase_score = 8
    else:
        phase_score = 10
    breakdown["phase"] = phase_score
    
    # 5. RPE 7d (10 分) — 主观疲劳
    today = datetime.utcnow().date()
    rpe_7d = (
        db.query(DailyMetric)
        .filter(DailyMetric.athlete_id == athlete_id)
        .filter(DailyMetric.date >= today - timedelta(days=7))
        .filter(DailyMetric.rpe.isnot(None))
        .all()
    )
    if rpe_7d:
        avg_rpe = sum(r.rpe for r in rpe_7d) / len(rpe_7d)
        if avg_rpe <= 4:
            rpe_score = 10  # 轻松
        elif avg_rpe <= 6:
            rpe_score = 7
        elif avg_rpe <= 8:
            rpe_score = 3  # 高
        else:
            rpe_score = 0  # 极高
    else:
        rpe_score = 5  # 无数据
    breakdown["rpe"] = rpe_score
    
    total = sum(breakdown.values())
    return total, breakdown


def generate_recommendations(
    db: Session, athlete_id: int
) -> DailyRecommendation:
    """V0.7.3: 生成今日综合建议"""
    
    readiness, breakdown = compute_readiness(db, athlete_id)
    
    # 5 维数据
    pmc = get_pmc_today(db, athlete_id)
    ctl, atl, tsb = pmc.get("ctl", 0), pmc.get("atl", 0), pmc.get("tsb", 0)
    hrv = compute_hrv_state(db, athlete_id)
    phase = derive_phase(db, athlete_id)
    signals = detect_phase_signals(db, athlete_id)
    
    # readiness 标签
    if readiness >= 80:
        readiness_label = "极佳"
        rec_type = "vo2"
        intensity = "高强度日: VO2max 间歇 (4-6×3min @ 110-120% FTP, 间歇 3min Z1)"
        target = 120
    elif readiness >= 60:
        readiness_label = "良好"
        rec_type = "threshold"
        intensity = "阈值日: Threshold 间歇 (2×20min @ 88-92% FTP, 间歇 5min Z1)"
        target = 90
    elif readiness >= 40:
        readiness_label = "中等"
        rec_type = "endurance"
        intensity = "轻松骑: Z2 长骑 60-90min @ 65-75% FTP"
        target = 60
    elif readiness >= 20:
        readiness_label = "低迷"
        rec_type = "recovery"
        intensity = "恢复骑: Z1-Z2 30-45min @ < 65% FTP, 主动恢复"
        target = 30
    else:
        readiness_label = "危险"
        rec_type = "rest"
        intensity = "完全休息: 建议今天不骑车, 优先睡眠/营养"
        target = 0
    
    # 生成建议列表
    recs = []
    warnings = []
    
    # HRV 触发
    if hrv["status"] == "warning":
        recs.append(Recommendation(
            category="warning", priority=5,
            title="HRV 持续低",
            detail=hrv["recommendation"],
            action="考虑今天完全休息或 30min Z1 主动恢复",
            icon="⚠️"
        ))
        warnings.append(f"HRV 连续 {hrv['consecutive_low_days']} 天低")
    elif hrv["status"] == "caution":
        recs.append(Recommendation(
            category="warning", priority=4,
            title="HRV 偏低",
            detail=hrv["recommendation"],
            action="避免高强度, Z1-Z2 轻松骑",
            icon="💛"
        ))
    elif hrv["status"] == "ok" and hrv.get("today_hrv", 0) > hrv.get("baseline_30d", 0) + 10:
        recs.append(Recommendation(
            category="tip", priority=3,
            title="HRV 优秀",
            detail=f"今日 HRV {hrv['today_hrv']:.0f}ms 高于 baseline {hrv['baseline_30d']:.0f}ms, 状态好",
            action="可按计划进行高强度训练",
            icon="💚"
        ))
    
    # ACWR 触发
    acwr = get_acwr(db, days=7)  # get_acwr_overview 内部用 athlete_id
    today = acwr.get("today", {}) if isinstance(acwr, dict) else {}
    acwr_val = today.get("acwr", 1.0) if today else 1.0
    if acwr_val > 1.5:
        recs.append(Recommendation(
            category="warning", priority=5,
            title="ACWR 危险区",
            detail=f"急慢性负荷比 {acwr_val:.2f} > 1.5 (Gabbett 2016 危险区), 伤病风险高",
            action="立即减量 30-50%, 优先恢复",
            icon="🚨"
        ))
        warnings.append(f"ACWR {acwr_val:.2f} > 1.5")
    elif acwr_val > 1.3:
        recs.append(Recommendation(
            category="warning", priority=3,
            title="ACWR 偏高",
            detail=f"急慢性负荷比 {acwr_val:.2f} > 1.3, 注意过训风险",
            action="今天避免高强度, 监控身体反应",
            icon="⚠️"
        ))
    
    # TSB 触发
    if tsb < -30:
        recs.append(Recommendation(
            category="warning", priority=4,
            title="TSB 极低, 深度疲劳",
            detail=f"训练平衡 {tsb:.0f} < -30, 累积疲劳严重, 表现下降风险",
            action="建议 1-2 天完全恢复, 优先睡眠/营养",
            icon="😴"
        ))
    elif tsb > 30:
        recs.append(Recommendation(
            category="tip", priority=2,
            title="TSB 高, 减量中",
            detail=f"训练平衡 {tsb:.0f} > 30, 可能在减量/恢复期",
            action="维持轻松强度, 不要勉强加量",
            icon="📉"
        ))
    
    # 周期阶段
    if phase.suggested_type == "taper":
        recs.append(Recommendation(
            category="tip", priority=3,
            title=f"减量期 (距比赛 {phase.weeks_to_race} 周)",
            detail="比赛临近, 减量保持神经肌肉刺激",
            action="短间歇 + 长恢复, 蓄能比赛日",
            icon="🎯"
        ))
    elif phase.suggested_type == "peak":
        recs.append(Recommendation(
            category="tip", priority=2,
            title=f"巅峰期 (距比赛 {phase.weeks_to_race} 周)",
            detail="保持 CTL, 强化质",
            action="中等强度 + 短间歇, 模拟比赛",
            icon="🏔️"
        ))
    
    # 训练连续天数
    if signals.streak_days >= 6:
        recs.append(Recommendation(
            category="warning", priority=4,
            title=f"连续训练 {signals.streak_days} 天",
            detail="长时间连续训练无休, 容易过训",
            action="建议 1-2 天完全休息或主动恢复",
            icon="📅"
        ))
    
    # 距上次减量
    if signals.weeks_since_taper >= 8:
        recs.append(Recommendation(
            category="tip", priority=3,
            title=f"距上次减量 {signals.weeks_since_taper}+ 周",
            detail="长期未减量, 训练学建议每 8-12 周减量",
            action="建议未来 1-2 周安排减量周",
            icon="🗓️"
        ))
    
    # 极化评分低
    if signals.polarized_score_28d < 0.5:
        recs.append(Recommendation(
            category="tip", priority=2,
            title="极化评分偏低",
            detail=f"28d 极化评分 {signals.polarized_score_28d:.2f}, 偏离 Seiler 80/20",
            action="增加 Z1-Z2 比例, 减少 '灰色地带' Z3-Z4",
            icon="⚖️"
        ))
    
    # IF 过高
    if signals.avg_if_28d > 1.0:
        recs.append(Recommendation(
            category="warning", priority=3,
            title=f"28d 平均 IF 偏高 ({signals.avg_if_28d:.2f})",
            detail="长期高强度, 过训风险累积",
            action="未来 1-2 周增加 Z1-Z2 比例",
            icon="🔥"
        ))
    
    # 按 priority 排序
    recs.sort(key=lambda r: -r.priority)
    
    return DailyRecommendation(
        date=datetime.utcnow().date().isoformat(),
        readiness_score=readiness,
        readiness_label=readiness_label,
        recommended_workout_type=rec_type,
        recommended_intensity=intensity,
        target_tss=target,
        recommendations=recs,
        warnings=warnings,
        signals_summary={
            "readiness_breakdown": breakdown,
            "tsb": tsb,
            "ctl": ctl,
            "atl": atl,
            "hrv_status": hrv["status"],
            "hrv_today": hrv.get("today_hrv"),
            "phase": phase.suggested_type,
            "phase_label": phase.suggested_label,
            "weeks_to_race": phase.weeks_to_race,
        },
    )
