"""比赛准备度 / 训练状态雷达 — V0.7 补遗漏

借鉴 (不简化):
- Joe Friel "The Cyclist's Training Bible" Performance Management Chart
  (Form Chart: CTL 趋势 + TSB 当日 + ATL 趋势)
- ACMS (American College of Sports Medicine) Periodization 框架
- Seiler 80/20 强度分布
- 比赛类型专项 taper 研究:
  * Bosquet 2007 meta-analysis (TT taper 持续 7-14 天)
  * Le Meur 2011 (TT vs endurance taper 区别)
  * Banister 1999 (Taper model)
"""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Activity, TrainingPhase, FTPTest
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.pmc import get_pmc_today, get_pmc_series


# ---------- 比赛类型元信息 ----------

@dataclass
class RaceTypeMeta:
    code: str              # 'tt', 'road_race', etc.
    label: str             # '个人计时赛 (TT)'
    label_en: str          # 'Time Trial'
    duration_h: float      # 典型时长 (h)
    tsb_target_min: float  # 比赛日 TSB 目标下限
    tsb_target_max: float  # 比赛日 TSB 目标上限
    taper_days_short: int  # 短 taper 天数
    taper_reduction_short: float  # 短 taper 降量 (%)
    taper_days_long: int   # 长 taper 天数
    taper_reduction_long: float
    description: str
    notes: str

RACE_TYPES: dict[str, RaceTypeMeta] = {
    "tt": RaceTypeMeta(
        code="tt", label="个人计时赛 (TT)", label_en="Time Trial",
        duration_h=1.0,
        tsb_target_min=5, tsb_target_max=15,
        taper_days_short=7, taper_reduction_short=0.5,
        taper_days_long=14, taper_reduction_long=0.6,
        description="纯功率输出, 短而猛",
        notes="TT 最需要 fresh, TSB 越高越好 (但避免 > 25 反而掉状态)",
    ),
    "road_race": RaceTypeMeta(
        code="road_race", label="单日赛 (Road Race)", label_en="Road Race",
        duration_h=4.0,
        tsb_target_min=10, tsb_target_max=20,
        taper_days_short=7, taper_reduction_short=0.5,
        taper_days_long=14, taper_reduction_long=0.6,
        description="中等时长, 战术 + 体能",
        notes="经典比赛, 1 周减量 50% 足够",
    ),
    "stage_race": RaceTypeMeta(
        code="stage_race", label="多日赛 (Stage Race)", label_en="Stage Race",
        duration_h=20.0,
        tsb_target_min=0, tsb_target_max=5,
        taper_days_short=7, taper_reduction_short=0.4,
        taper_days_long=14, taper_reduction_long=0.5,
        description="持续 3-7 天, 每天一赛",
        notes="多日赛要保留体能给后续赛段, TSB 不能太高, taper 减量略少 (避免掉状态)",
    ),
    "gran_fondo": RaceTypeMeta(
        code="gran_fondo", label="长距离 (Gran Fondo)", label_en="Gran Fondo",
        duration_h=8.0,
        tsb_target_min=5, tsb_target_max=15,
        taper_days_short=10, taper_reduction_short=0.55,
        taper_days_long=14, taper_reduction_long=0.65,
        description="120-250km 业余挑战赛, 长时长 + 后半段掉力管理",
        notes="比单日赛更长的 taper, 后半段能量补给是关键",
    ),
    "crit": RaceTypeMeta(
        code="crit", label="绕圈赛 (Crit)", label_en="Criterium",
        duration_h=1.0,
        tsb_target_min=5, tsb_target_max=15,
        taper_days_short=7, taper_reduction_short=0.5,
        taper_days_long=10, taper_reduction_long=0.55,
        description="短时高强度绕圈, 反复冲刺",
        notes="神经肌肉是关键, 短 taper 足够",
    ),
    "hill_climb": RaceTypeMeta(
        code="hill_climb", label="爬坡赛 (Hill Climb)", label_en="Hill Climb",
        duration_h=0.75,
        tsb_target_min=10, tsb_target_max=20,
        taper_days_short=7, taper_reduction_short=0.5,
        taper_days_long=14, taper_reduction_long=0.6,
        description="短而猛的爬坡",
        notes="跟 TT 类似, 但更看重 W/kg, 减重期能 +5-8% W/kg",
    ),
    "other": RaceTypeMeta(
        code="other", label="其他", label_en="Other",
        duration_h=2.0,
        tsb_target_min=5, tsb_target_max=15,
        taper_days_short=7, taper_reduction_short=0.5,
        taper_days_long=14, taper_reduction_long=0.6,
        description="自定义比赛类型",
        notes="默认参数",
    ),
}


def get_race_type(code: str | None) -> RaceTypeMeta:
    """获取比赛类型元信息 (默认 road_race)"""
    if not code:
        return RACE_TYPES["road_race"]
    return RACE_TYPES.get(code, RACE_TYPES["other"])


# ---------- TSB 目标建议 ----------

@dataclass
class TSBTarget:
    race_type: str
    tsb_target_min: float
    tsb_target_max: float
    taper_days: int
    taper_reduction_pct: float
    description: str
    notes: str
    weekly_tss_plan: list[dict]  # 倒推每周 TSS 计划


def compute_tsb_target(
    race_date: datetime,
    race_type: str = "road_race",
    current_ctl: float = 60,
) -> TSBTarget:
    """计算比赛日 TSB 目标 + taper 倒推计划

    借鉴 Friel + Le Meur + Bosquet 2007 meta-analysis
    """
    rt = get_race_type(race_type)
    today = datetime.utcnow().date()
    race_d = race_date.date() if isinstance(race_date, datetime) else race_date
    days_to_race = (race_d - today).days
    weeks_to_race = max(0, days_to_race // 7)

    # 选 taper 时长
    if days_to_race >= 14:
        taper_days = rt.taper_days_long
        reduction = rt.taper_reduction_long
    else:
        taper_days = rt.taper_days_short
        reduction = rt.taper_reduction_short

    # 倒推 weekly TSS 计划
    # 基础: 当前 CTL × 1.0 (Build 期维持), 之后 taper
    # taper 期: CTL × (1 - reduction × (1 - week/taper_weeks))
    plan = []
    base_tss_week = int(current_ctl * 1.2)  # 假设 Build 期目标
    
    taper_weeks = max(1, (taper_days + 6) // 7)
    for w in range(weeks_to_race, 0, -1):
        if w > taper_weeks:
            # Build 期
            tss = int(base_tss_week)
            label = f"Build (W-{w})"
        else:
            # Taper 期
            # 越接近比赛, 越减量
            taper_progress = (taper_weeks - w + 1) / taper_weeks
            tss = int(base_tss_week * (1 - reduction * taper_progress))
            label = f"Taper (W-{w})"
        plan.append({
            "week": weeks_to_race - w + 1,
            "weeks_to_race": w,
            "label": label,
            "weekly_tss_target": tss,
        })

    return TSBTarget(
        race_type=rt.code,
        tsb_target_min=rt.tsb_target_min,
        tsb_target_max=rt.tsb_target_max,
        taper_days=taper_days,
        taper_reduction_pct=reduction,
        description=rt.description,
        notes=rt.notes,
        weekly_tss_plan=plan,
    )


# ---------- 5 维训练状态雷达 ----------

@dataclass
class TrainingState:
    """5 维训练状态 (0-100 标准化)"""
    fitness: float         # 体能 - CTL 归一化 (高 = 好)
    fatigue: float         # 疲劳 - ATL 归一化 (高 = 累)
    form: float            # 状态 - TSB 归一化 (高 = fresh)
    rhythm: float          # 节奏 - ramp_rate 归一化 (高 = 稳)
    recovery: float        # 恢复 - RPE 7d 均值归一化 (高 = 恢复好)

    overall: float         # 综合分 (0-100)
    interpretation: dict[str, str]  # 5 维解读
    source: str            # 数据来源说明


def compute_training_state(db: Session, athlete_id: int) -> TrainingState:
    """计算 5 维训练状态 (借鉴 Friel Form Chart + Seiler + Banister)

    维度说明 (借鉴 Joe Friel Form):
    1. Fitness (体能) = CTL 趋势, 过去 42 天积累
    2. Fatigue (疲劳) = ATL, 过去 7 天积累
    3. Form (状态) = TSB = CTL - ATL
    4. Rhythm (节奏) = ramp_rate 7 天, 训练量变化趋势
    5. Recovery (恢复) = RPE 7 天均值 (反向) + IF 趋势

    归一化: 0-100, 越高越"好" (对 fitness/form/rhythm/recovery 是高好,
                       对 fatigue 是高累, 显示时反向)
    """
    pcm = get_pmc_today(db, athlete_id)
    ctl = pcm.get("ctl", 0) or 0
    atl = pcm.get("atl", 0) or 0
    tsb = pcm.get("tsb", 0) or 0
    ramp_rate = pcm.get("ramp_rate", 0) or 0

    now = datetime.utcnow()
    cutoff_7d = now - timedelta(days=7)
    cutoff_14d = now - timedelta(days=14)

    acts_7d = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff_7d)
        .all()
    )
    acts_14d = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff_14d)
        .all()
    )

    # 1. Fitness: CTL 归一化 (50 = 中等训练者, 100 = 精英)
    # 训练学: 业余 30-50, 半专业 50-80, 精英 80-120+
    fitness = min(100, ctl * 0.9 + 20)
    if ctl < 20:
        fitness = max(0, ctl * 1.5)  # 起步阶段线性

    # 2. Fatigue: ATL 归一化 (返回"低好"分数)
    # ATL 80+ 算高疲劳, 40-60 中等, < 30 fresh
    fatigue_raw = atl
    if atl < 30:
        fatigue_score = 100
    elif atl < 60:
        fatigue_score = 100 - (atl - 30) * 1.0  # 30→100, 60→70
    elif atl < 100:
        fatigue_score = 70 - (atl - 60) * 0.8   # 60→70, 100→38
    else:
        fatigue_score = max(0, 38 - (atl - 100) * 0.5)
    fatigue = round(fatigue_score, 1)

    # 3. Form: TSB 归一化 (-30 累 → +20 比赛状态)
    # TSB 0 = 中性, +10 ideal, +20 race
    if tsb < -30:
        form = max(0, 30 - abs(tsb) * 0.5)
    elif tsb < 0:
        form = 60 + (tsb + 30) * 1.0  # -30→60, 0→90
    elif tsb < 20:
        form = 90 + tsb * 0.5  # 0→90, 20→100
    else:
        form = 100
    form = round(min(100, form), 1)

    # 4. Rhythm: ramp_rate 7d (理想 -3 ~ +7)
    # 太低 (< -5) = 减量期 / 掉状态, 中等 (-3~+7) = 健康, 太高 (> 10) = 突增风险
    if ramp_rate < -5:
        rhythm = max(30, 50 + ramp_rate)
    elif ramp_rate < 0:
        rhythm = 50 + (ramp_rate + 5) * 4  # -5→50, 0→70
    elif ramp_rate < 7:
        rhythm = 70 + ramp_rate * 3  # 0→70, 7→91
    elif ramp_rate < 10:
        rhythm = 91 - (ramp_rate - 7) * 5  # 7→91, 10→76
    else:
        rhythm = max(0, 76 - (ramp_rate - 10) * 5)  # 10→76, 14→46
    rhythm = round(min(100, rhythm), 1)

    # 5. Recovery: RPE 7d 均值 (反向) + 训练频率
    rpe_acts = [a for a in acts_7d if a.rpe is not None]
    if rpe_acts:
        avg_rpe = sum(a.rpe for a in rpe_acts) / len(rpe_acts)
        if avg_rpe < 4:
            recovery = 100
        elif avg_rpe < 6:
            recovery = 100 - (avg_rpe - 4) * 10  # 4→100, 6→80
        elif avg_rpe < 7.5:
            recovery = 80 - (avg_rpe - 6) * 13  # 6→80, 7.5→60
        else:
            recovery = max(0, 60 - (avg_rpe - 7.5) * 20)  # 7.5→60, 9→20
    else:
        # 没 RPE 数据, 用训练频率 + 距离
        days_active = len({a.start_time.date() for a in acts_7d if a.start_time})
        if days_active >= 4:
            recovery = 80
        elif days_active >= 2:
            recovery = 70
        else:
            recovery = 60
    recovery = round(min(100, recovery), 1)

    # 综合分: 5 维加权 (疲劳反向, 因为高疲劳是低分)
    # fitness 0.3, fatigue 0.2 (反向), form 0.2, rhythm 0.15, recovery 0.15
    overall = round(fitness * 0.30 + fatigue * 0.20 + form * 0.20 + rhythm * 0.15 + recovery * 0.15, 1)

    # 解读
    def interpret(score: float, name: str) -> str:
        if score >= 85:
            return f"{name}优秀"
        elif score >= 70:
            return f"{name}良好"
        elif score >= 55:
            return f"{name}中等"
        elif score >= 40:
            return f"{name}需注意"
        else:
            return f"{name}警告"

    return TrainingState(
        fitness=round(fitness, 1),
        fatigue=fatigue,
        form=form,
        rhythm=rhythm,
        recovery=recovery,
        overall=overall,
        interpretation={
            "fitness": interpret(fitness, "体能"),
            "fatigue": interpret(fatigue, "恢复"),
            "form": interpret(form, "状态"),
            "rhythm": interpret(rhythm, "节奏"),
            "recovery": interpret(recovery, "反馈"),
        },
        source=f"PMC 实时: CTL {ctl:.0f} / ATL {atl:.0f} / TSB {tsb:.0f} / ramp {ramp_rate:.1f}",
    )
