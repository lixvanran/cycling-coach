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
    category: str  # "workout" | "warning" | "tip" | "lifestyle" | "info"
    priority: int  # 1-5, 5 = 最重要
    title: str
    detail: str
    action: Optional[str] = None  # 具体动作 (可选)
    icon: Optional[str] = None  # 前端 emoji / icon name


@dataclass
class DailyRecommendation:
    """今日综合建议"""
    date: str
    # V0.9.0: 无数据时 readiness_score 为 None (不是 0, 也不是高分)
    # 语义 = "算不出来"。前端据此显示"需要数据"而不是"危险"。
    readiness_score: Optional[int]  # 0-100, None = 数据不足算不出
    readiness_label: str  # "极佳" / "良好" / "中等" / "低迷" / "危险" / "数据不足"
    recommended_workout_type: str  # "rest" | "recovery" | "endurance" | "tempo" | "threshold" | "vo2" | "none"
    recommended_intensity: str  # 描述: "轻松骑 60-90min Z1-Z2" 等
    target_tss: int  # 今日目标 TSS
    recommendations: list[Recommendation] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    signals_summary: dict = field(default_factory=dict)


# V0.9.0: 判定"数据够不够算 readiness"的门槛
# 依据: ACWR 需要 28 天 chronic, PMC 需要至少几天训练才有意义。
# 少于这个量给分 = 猜, 而猜出来的"高分"会让新用户以为自己状态很好。
MIN_ACTIVITIES_FOR_READINESS = 7
MIN_DAYS_SPAN_FOR_READINESS = 7

# V0.9.0: readiness 五维的权重, 以及"敢不敢给分"的门槛
#
# 起因: 上面那个 MIN_ACTIVITIES 门槛只解决了"完全没有数据"的情况, 但**没有解决
# "有活动、可是某些维度算不出来"**。实测(8 次活动 / 7 天, 零 HRV 记录, 算不出
# ACWR)的用户拿到 67 分"良好" + 阈值间歇处方, 其中:
#     hrv  20/30  ← 纯编的 (status=insufficient_data 仍然给了 2/3 分)
#     acwr 25/25  ← 纯编的, 而且是**满分**, 等于宣称"负荷平衡完美";
#                    而 ACWR 结构上需要 28 天 chronic, 7 天根本算不出来
# 也就是说 **75% 的分数来自没有数据的维度**, 并且直接驱动了训练处方。
#
# 根因是每个维度在无数据时各自编了一个"看起来合理"的高分默认值, 方向跟
# "数据越少分越高"一样是反的。所以顶层门槛不够 —— 必须在**每个维度内部**
# 区分"真实测量"和"兜底猜测"。
#
# 现在的规则:
#   - 只有**真实有数据**的维度才进 breakdown
#   - 分数按**可用维度的满分**归一化 (全 5 维时与旧算法完全一致, 无回归)
#   - 可用维度 < 2, 或缺训练负荷维度(没有它就没法谈"今天该不该练") → 返回 None
READINESS_WEIGHTS = {"hrv": 30, "acwr": 25, "tsb": 20, "phase": 15, "rpe": 10}

# 训练负荷是 readiness 的地基: 不知道最近骑了多少, 就没资格说今天该上什么强度
REQUIRED_READINESS_DIMENSION = "tsb"

# 低于这个可用维度数就不给分 —— 单一维度归一化出来的 0-100 看着和五维的一样权威
MIN_DIMENSIONS_FOR_READINESS = 2


def readiness_coverage(breakdown: dict) -> dict:
    """把 breakdown 变成一句人能读懂的"这个分是怎么来的"

    V0.9.0: readiness 分数即使是真的, 也只代表**部分**维度。必须把依据说清楚,
    否则一个 67 分和另一个数据齐全用户的 67 分看起来毫无区别 —— 但前者可能是
    拿两个维度归一化出来的。
    """
    have = [k for k in READINESS_WEIGHTS if k in breakdown]
    missing = [k for k in READINESS_WEIGHTS if k not in breakdown]
    _names = {"hrv": "HRV", "acwr": "ACWR", "tsb": "训练负荷", "phase": "周期阶段", "rpe": "主观疲劳"}
    return {
        "available": have,
        "missing": missing,
        "available_labels": [_names[k] for k in have],
        "missing_labels": [_names[k] for k in missing],
        "n_available": len(have),
        "n_total": len(READINESS_WEIGHTS),
        "complete": not missing,
    }


def _data_sufficiency(db: Session, athlete_id: int) -> dict:
    """查数据够不够算 readiness — 并如实报告缺什么

    V0.9.0 新增。原来没有这个判断, 导致零数据用户拿到 82 分"极佳"。
    """
    acts = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .order_by(Activity.start_time.asc())
        .limit(MIN_ACTIVITIES_FOR_READINESS + 1)
        .all()
    )
    n = len(acts)
    span_days = 0
    if n >= 2:
        from datetime import date as _d
        try:
            first = acts[0].start_time
            last = acts[-1].start_time
            if isinstance(first, str):
                first = datetime.fromisoformat(first)
            if isinstance(last, str):
                last = datetime.fromisoformat(last)
            span_days = (last.date() - first.date()).days
        except Exception:
            span_days = 0

    enough = n >= MIN_ACTIVITIES_FOR_READINESS and span_days >= MIN_DAYS_SPAN_FOR_READINESS
    reasons = []
    if n < MIN_ACTIVITIES_FOR_READINESS:
        reasons.append(f"只有 {n} 次训练记录 (需要至少 {MIN_ACTIVITIES_FOR_READINESS} 次)")
    if span_days < MIN_DAYS_SPAN_FOR_READINESS:
        reasons.append(f"训练跨度仅 {span_days} 天 (需要至少 {MIN_DAYS_SPAN_FOR_READINESS} 天)")
    return {
        "sufficient": enough,
        "n_activities": n,
        "span_days": span_days,
        "reasons": reasons,
    }


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

    V0.9.0: **只把真实有数据的维度算进分数**, 返回的 breakdown 里也只有这些维度。
    原来无数据时每个维度各自编一个高分默认值 (ACWR 缺数据默认 1.0 拿满分 25/25,
    HRV 无数据拿 20/30), 于是一个算不出 ACWR 的用户拿到满分负荷平衡分, 还会
    因为这个假分被派去骑阈值间歇。分数按可用维度的满分归一化; 维度太少或缺
    训练负荷维度时返回 None —— 宁可说算不出来, 也不要自信地给错建议。

    返回: (score, breakdown)。score 是 Optional[int], 调用方**必须**处理 None。
    """
    breakdown = {}

    # 1. HRV (30 分) — 只有真测到 HRV 才算
    hrv = compute_hrv_state(db, athlete_id)
    if hrv["status"] == "ok":
        hrv_score = 30
        breakdown["hrv"] = hrv_score
    elif hrv["status"] == "caution":
        breakdown["hrv"] = 15
    elif hrv["status"] == "warning":
        breakdown["hrv"] = 0
    # status == "insufficient_data" → 整维不计入。
    # 原来这里给 20/30 (2/3 分), 意思���"没测心率但我按三分之二算上了"。

    # 2. ACWR (25 分) — 算不出来就不算。ACWR 需要 28 天 chronic, 短期用户必然算不出。
    acwr = get_acwr(db, days=7)  # get_acwr_overview 内部用 athlete_id
    today = acwr.get("today", {}) if isinstance(acwr, dict) else {}
    acwr_val = today.get("acwr") if today else None
    if acwr_val is not None:
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
    # 原来: acwr_val = today.get("acwr", 1.0) if today else 1.0
    # 无数据 → 默认 1.0 → 落在甜区 → **满分 25/25**。

    # 3. TSB (20 分) — 训练负荷, readiness 的地基
    pmc = get_pmc_today(db, athlete_id)
    if pmc.get("status_label") != "无数据":
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
    # 原来: tsb = pmc.get("tsb", 0) —— 无数据时 0 落在 -10~20, **满分 20/20**。

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

    # 5. RPE 7d (10 分) — 主观疲劳。没有记录就是没有, 不给中性分
    today_d = datetime.utcnow().date()
    rpe_7d = (
        db.query(DailyMetric)
        .filter(DailyMetric.athlete_id == athlete_id)
        .filter(DailyMetric.date >= today_d - timedelta(days=7))
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
        breakdown["rpe"] = rpe_score
    # 原来: 无 RPE 记录时给 5/10 中性分。

    # 数据够不够给一个分?
    if REQUIRED_READINESS_DIMENSION not in breakdown:
        return None, breakdown
    if len(breakdown) < MIN_DIMENSIONS_FOR_READINESS:
        return None, breakdown

    # 按**可用维度**的满分归一化。
    # 五个维度齐全时 max_total == 100, 与旧算法逐位一致 —— 不会给老用户改分。
    total = sum(breakdown.values())
    max_total = sum(READINESS_WEIGHTS[k] for k in breakdown)
    return round(total / max_total * 100), breakdown


def _insufficient_data_recommendation(suff: dict) -> DailyRecommendation:
    """数据不足时的返回 — 如实说"算不出来", 不猜

    V0.9.0 新增。这里刻意**不**返回 readiness_score(而不是返回 0 或高分):
    0 会被前端渲染成"危险", 高分会渲染成"极佳", 两者都是骗人。
    None 的语义是"还没法算"。
    """
    why = "; ".join(suff["reasons"]) or "训练数据不足"
    recs = [
        Recommendation(
            category="info", priority=1,
            title="还不能算今日状态",
            detail=why,
            action=(
                f"先导入至少 {MIN_ACTIVITIES_FOR_READINESS} 次训练记录"
                f"（跨 {MIN_DAYS_SPAN_FOR_READINESS} 天以上），"
                "之后这里会给出 readiness 分数和训练建议"
            ),
            icon="📊",
        )
    ]
    if suff["n_activities"] == 0:
        recs.insert(0, Recommendation(
            category="info", priority=1,
            title="还没有任何训练数据",
            detail="App 不会凭空猜你的状态",
            action="在「数据 → 导入」上传 FIT 文件，或把码表导出的 .fit 丢进 inbox 文件夹",
            icon="📥",
        ))

    return DailyRecommendation(
        date=_date.today().isoformat(),
        readiness_score=None,
        readiness_label="数据不足",
        recommended_workout_type="none",
        recommended_intensity="数据不足，暂不给出训练强度建议",
        target_tss=0,
        recommendations=recs,
        warnings=[],
        signals_summary={
            "data_sufficiency": suff,
            "readiness_breakdown": {},
        },
    )


def _missing_dimension_guidance(missing: list[str]) -> str:
    """缺某个维度时, 告诉用户**具体怎么做**才能补上

    V0.9.0: 光说"缺 ACWR"没用 —— 用户要的是"我该干什么"。
    这些都是用户能自己做的动作, 不是"请升级设备"这种无解的建议。
    """
    parts = []
    if "hrv" in missing:
        parts.append("心率带能提供每日晨起 HRV（约需 2 周建立基线）")
    if "acwr" in missing:
        parts.append("ACWR 需要 28 天训练史, 继续记录就会自动出现")
    if "tsb" in missing:
        parts.append("导入带功率的训练记录, 才有训练负荷可算")
    if "rpe" in missing:
        parts.append("每次训练后填一次主观疲劳度 (RPE 1-10)")
    if "phase" in missing:
        parts.append("完成一次周期设定, 才有训练阶段可判")
    return "；".join(parts) or "继续积累数据"


def generate_recommendations(
    db: Session, athlete_id: int
) -> DailyRecommendation:
    """V0.7.3: 生成今日综合建议

    V0.9.0: 数据不足时**不给 readiness 分数, 也不给训练强度建议**。
    原来零数据用户拿到 82 分"极佳" + VO2max 高强度间歇 ——
    因为每个维度在无数据时都默认给中高分 (ACWR 缺数据默认 1.0 拿满分 25/25,
    TSB=0 拿满分 20/20)。数据越少分越高, 方向完全反了。
    宁可说"算不出来", 也不要自信地给错建议。
    """
    suff = _data_sufficiency(db, athlete_id)
    if not suff["sufficient"]:
        return _insufficient_data_recommendation(suff)

    readiness, breakdown = compute_readiness(db, athlete_id)
    coverage = readiness_coverage(breakdown)

    # 5 维数据
    pmc = get_pmc_today(db, athlete_id)
    ctl, atl, tsb = pmc.get("ctl", 0), pmc.get("atl", 0), pmc.get("tsb", 0)
    hrv = compute_hrv_state(db, athlete_id)
    phase = derive_phase(db, athlete_id)
    signals = detect_phase_signals(db, athlete_id)

    # readiness 标签
    # V0.9.0: readiness 可能是 None (数据够门槛但关键维度算不出来)。
    # 原来这里是 score >= 80 直接开跑 —— Python 3 里 None >= 80 是 TypeError,
    # 会让整个 /api/recommendations/readiness 500。
    if readiness is None:
        readiness_label = "数据不足"
        rec_type = "none"
        intensity = f"数据不足，暂不给出训练强度建议（缺: {('、'.join(coverage['missing_labels']) or '未知')}）"
        target = 0
    elif readiness >= 80:
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

    # V0.9.0: 分数即使是真的, 也只代表部分维度。必须让用户知道这个分怎么来的,
    # 否则"67 分"看起来和另一个数据齐全用户的 67 分毫无区别。
    if readiness is not None and not coverage["complete"]:
        recs.append(Recommendation(
            category="info", priority=2,
            title=f"今日状态基于 {coverage['n_available']}/{coverage['n_total']} 个维度",
            detail=(
                f"可用: {'、'.join(coverage['available_labels'])}；"
                f"缺: {'、'.join(coverage['missing_labels'])}"
            ),
            action=_missing_dimension_guidance(coverage["missing"]),
            icon="📐",
        ))
    
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
            # V0.9.0: 前端要能告诉用户"这个分基于哪几个维度"。
            # 没有它, breakdown 里的键变少时用户只会觉得"数据丢了", 不会知道是诚实。
            "readiness_coverage": coverage,
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
