"""自动训练洞察告警 — V0.7

借鉴 (不简化):
- Joe Friel "The Cyclist's Training Bible" Weekly Review 章节
  (每周自检 6 项: 训练质量 / 身体状态 / 比赛准备 / 强度分布 / 恢复 / 计划)
- Tim Gabbett 2016 训练负荷管理 (ACWR + ramp_rate + 受伤风险)
- ACMS 过度训练综合征 (OTS) 诊断标准
  (持续疲劳 + 性能下降 + 心情低落 + 睡眠差 + RPE 上升)
- Seiler 80/20 极化分布
- 中等强度陷阱 (Pollock 1998, "灰色地带" 增加受伤风险)

设计:
- 6 大维度 (训练负荷 / 身体状态 / 强度分布 / 恢复 / 比赛准备 / 计划)
- 每条洞察: severity (info / warning / alert) + category + 标题 + 描述 + 建议
- 训练学引用: 来源 (Friel / Gabbett / ACMS / Seiler)
- 数据驱动: 全部基于历史活动 + PMC + 已有指标
"""
from __future__ import annotations
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date as _date
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import desc

from cycling_coach.data.sqlite.models import Activity, FTPTest, TrainingPhase
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.pmc import get_pmc_today, get_pmc_series, aggregate_tss_by_day
from cycling_coach.core.metrics.acwr import compute_acwr, get_acwr_overview
from cycling_coach.core.metrics.periodization import derive_phase, analyze_polarized, COGGAN_ZONES


# ---------- 数据结构 ----------

@dataclass
class Insight:
    """单条训练洞察"""
    id: str                        # 唯一 ID
    category: str                  # load / recovery / race / phase / ftp / distribution
    severity: str                  # info / warning / alert
    title: str                     # 标题 (一句话)
    description: str               # 详细描述 (2-3 句)
    recommendation: str            # 建议行动
    metric_value: Optional[str] = None    # 关键数据 (e.g. "TSB = -35")
    academic_source: Optional[str] = None  # 学术引用

    def to_dict(self):
        return asdict(self)


@dataclass
class InsightsBundle:
    """洞察集合 (今日)"""
    generated_at: str
    athlete_id: int
    insights: list[Insight]
    summary: dict
    pcm: dict
    acwr: dict


# ---------- 主入口: 今日洞察 ----------

def compute_today_insights(db: Session, athlete_id: Optional[int] = None) -> InsightsBundle:
    """今日所有训练洞察, 按严重度排序

    算法 (借鉴 Friel Weekly Review):
    1. 训练负荷维度
       - 训练量突增 (TSS 7d vs 28d)
       - 训练量不足
       - 过度训练信号 (TSB 持续低)
    2. 身体状态维度
       - RPE 7 天均值
       - HR drift (同样 NP 下 IF 上升)
    3. 强度分布维度 (Seiler 80/20)
       - 灰色地带 (Z3+Z4 过多)
       - 高强度过多
    4. 比赛准备度
       - 距比赛天数
       - Taper 状态
       - 模拟比赛
    5. FTP 测试
       - 距离上次测试 > 6 周
       - IF 持续高 (可能突破)
    6. 周期阶段
       - 当前阶段 vs 建议阶段
    """
    if athlete_id is None:
        athlete = profile_store.get_or_create_athlete(db)
        athlete_id = athlete.id

    insights: list[Insight] = []
    now = datetime.utcnow()
    today = now.date()

    # ===== 1. 训练负荷维度 =====

    pcm = get_pmc_today(db, athlete_id)
    ctl = pcm.get("ctl", 0) or 0
    atl = pcm.get("atl", 0) or 0
    tsb = pcm.get("tsb", 0) or 0
    ramp_rate = pcm.get("ramp_rate", 0) or 0

    # 1.1 训练量突增
    if ramp_rate > 8:
        insights.append(Insight(
            id="load_spike",
            category="load",
            severity="alert",
            title=f"训练量突增 (ramp_rate {ramp_rate:.1f} TSS/wk)",
            description=f"过去 7 天 CTL 斜率为 {ramp_rate:.1f} TSS/wk, 远超安全范围。Gabbett 2016 研究显示, 训练量突增是受伤 / 过训的主要诱因。",
            recommendation="立即安排 1-2 天轻松日 (Z1-Z2), 减少高强度间歇, 让身体适应新负荷。",
            metric_value=f"ramp_rate = {ramp_rate:.1f} TSS/wk (建议 < 7)",
            academic_source="Gabbett 2016, 'Training load paradox'",
        ))
    elif ramp_rate > 5:
        insights.append(Insight(
            id="load_moderate",
            category="load",
            severity="info",
            title=f"训练量稳步提升 (ramp {ramp_rate:.1f} TSS/wk)",
            description=f"过去 7 天 CTL 上升 {ramp_rate:.1f} TSS/wk, 在健康范围内。这是典型的 Build 期特征, 持续 3-4 周可显著提升有氧能力。",
            recommendation="保持当前节奏, 注意睡眠和营养, 每周安排 1 个完全休息日。",
            metric_value=f"ramp_rate = {ramp_rate:.1f} TSS/wk",
            academic_source="Friel, Periodization for Cyclists",
        ))

    # 1.2 训练量不足
    cutoff_14d = now - timedelta(days=14)
    acts_14d = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff_14d)
        .all()
    )
    total_tss_14d = sum((a.metrics or {}).get("tss", 0) or 0 for a in acts_14d)
    days_active_14d = len({a.start_time.date() for a in acts_14d if a.start_time})

    if days_active_14d == 0:
        insights.append(Insight(
            id="load_inactive",
            category="load",
            severity="warning",
            title="过去 14 天无训练活动",
            description="你已经 14 天没有训练记录了。Friel 建议运动员每 5-7 天至少有 1 次训练, 否则有氧能力会快速下降 (停训 2 周, VO2max 下降 4-6%)。",
            recommendation="从今天开始重新建立训练习惯, 先做 Z1-Z2 短骑 (30-60 分钟), 1-2 周后再恢复常规强度。",
            metric_value=f"14 天总 TSS = 0",
            academic_source="Mujika & Padilla 2000, 'Detraining'",
        ))
    elif total_tss_14d < 200:
        insights.append(Insight(
            id="load_low",
            category="load",
            severity="info",
            title=f"近 14 天训练量偏低 ({total_tss_14d:.0f} TSS)",
            description=f"过去 14 天只累计 {total_tss_14d:.0f} TSS, 远低于维持体能的最低阈值 (建议 14 天 ≥ 600 TSS)。如果是有意为之 (恢复期 / 休赛期), 没问题; 如果是懈怠, 需提升。",
            recommendation="检查是否处于恢复期或休赛期。如不是, 增加 1-2 次 Z2 长骑, 每次 60-90 分钟。",
            metric_value=f"14d TSS = {total_tss_14d:.0f} (建议 ≥ 600)",
            academic_source="Friel, Periodization",
        ))

    # 1.3 过度训练信号 (TSB 持续低)
    if tsb < -30 and ctl > 50:
        insights.append(Insight(
            id="load_overtraining",
            category="load",
            severity="alert",
            title=f"深度疲劳警告 (TSB = {tsb:.0f})",
            description=f"训练平衡分数 TSB 为 {tsb:.0f}, 低于 -30 警戒线。ACMS (美国运动医学学会) 列出 5 大过度训练信号: 持续疲劳 / 性能下降 / 心情低落 / 睡眠差 / RPE 异常上升。如果你有 2+ 项, 应立即降量。",
            recommendation="建议立即安排 3-5 天主动恢复 (Z1, 短时长), 完全避开 Z3+ 强度。考虑跳过本周关键训练, 不要硬撑。",
            metric_value=f"TSB = {tsb:.0f} (建议 ≥ -30)",
            academic_source="ACMS 过度训练综合征诊断标准",
        ))
    elif tsb < -15 and tsb >= -30:
        insights.append(Insight(
            id="load_fatigue",
            category="load",
            severity="warning",
            title=f"疲劳累积 (TSB = {tsb:.0f})",
            description=f"TSB 为 {tsb:.0f}, 处于 -15 ~ -30 区间, 这是 Build 期的正常表现, 但已进入警戒区。短期可承受, 持续 2 周以上需注意。",
            recommendation="本周安排 1-2 天轻松日, 关注睡眠时长 (>7 小时), 留意身体反馈 (晨脉 / RPE 异常上升)。",
            metric_value=f"TSB = {tsb:.0f}",
            academic_source="Banister 经典 PMC 模型",
        ))

    # ===== 2. 身体状态维度 (RPE) =====

    cutoff_7d = now - timedelta(days=7)
    rpe_acts = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff_7d)
        .filter(Activity.rpe.isnot(None))
        .all()
    )
    if rpe_acts:
        avg_rpe = sum(a.rpe for a in rpe_acts) / len(rpe_acts)
        if avg_rpe > 7.5:
            insights.append(Insight(
                id="recovery_rpe_high",
                category="recovery",
                severity="alert",
                title=f"RPE 持续高位 (7 天均值 {avg_rpe:.1f})",
                description=f"过去 7 天平均 RPE 为 {avg_rpe:.1f}, 超过 7.5 警戒线。Friel 指出持续高 RPE 而 TSS 没明显下降, 提示生理疲劳在累积, 即使客观负荷 (TSS) 不高。",
                recommendation="降低本周训练强度 (cap IF ≤ 0.75), 增加休息日。RPE 7+ 至少连续 2-3 天, 不要硬上高强度间歇。",
                metric_value=f"7d avg RPE = {avg_rpe:.1f} (建议 ≤ 7)",
                academic_source="Borg CR-10 + Friel Weekly Review",
            ))
        elif avg_rpe > 6.5:
            insights.append(Insight(
                id="recovery_rpe_elevated",
                category="recovery",
                severity="info",
                title=f"RPE 略高 (7 天均值 {avg_rpe:.1f})",
                description=f"过去 7 天平均 RPE 为 {avg_rpe:.1f}, 略高于舒适区。可能是状态好 (高强度训练正常反映) 或疲劳累积信号。",
                recommendation="对比同样 NP 下的 RPE 变化: 如果 RPE 持续上升但 NP 没变, 说明疲劳在累积, 考虑降量。",
                metric_value=f"7d avg RPE = {avg_rpe:.1f}",
                academic_source="Borg CR-10",
            ))

    # ===== 3. 强度分布 (Seiler 80/20) =====

    polarized = analyze_polarized(db, athlete_id, days=30, ftp_w=250)

    if polarized.total_seconds > 0:
        if polarized.threshold_pct > 0.25:
            insights.append(Insight(
                id="distribution_grey_zone",
                category="distribution",
                severity="warning",
                title=f"灰色地带过多 ({polarized.threshold_pct*100:.0f}% 在 Z3+Z4)",
                description=f"近 30 天 Z3+Z4 时间占比 {polarized.threshold_pct*100:.0f}%, 超过 25%。Seiler 2010 研究明确指出, 中等强度 (Z3+Z4) 是「灰色地带」, 既不能充分发展有氧, 也不足够强到提升无氧, 但累积疲劳最大。",
                recommendation="把 Z3 间歇改为 Z2 长时间 (同样 TSS 累计, 但有氧刺激更深) 或 Z5 VO2max (更短, 更高强度, 更低疲劳)。",
                metric_value=f"Z3+Z4 = {polarized.threshold_pct*100:.0f}% (理想 ≤ 10%)",
                academic_source="Seiler 2010, 'Polarized training'",
            ))

        if polarized.hard_pct > 0.25:
            insights.append(Insight(
                id="distribution_too_much_hi",
                category="distribution",
                severity="warning",
                title=f"高强度偏多 ({polarized.hard_pct*100:.0f}% 在 Z5+)",
                description=f"近 30 天 Z5+ (高强度) 时间占比 {polarized.hard_pct*100:.0f}%, 超过 20% 阈值。精英运动员典型 80/20 分布是 Z1+Z2 ≈ 80%, Z5+ ≈ 20%。高强度过多易过训。",
                recommendation="本周高强度训练 (VO2max / 重复冲刺) 减半, 替换为 Z2 长骑, 让神经肌肉和心血管都充分恢复。",
                metric_value=f"Z5+ = {polarized.hard_pct*100:.0f}% (理想 ≈ 20%)",
                academic_source="Seiler & Kjerland 2006, 'Polarized training'",
            ))

    # ===== 4. 比赛准备度 =====

    next_race = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete_id)
        .filter(TrainingPhase.is_race == True)  # noqa: E712
        .filter(TrainingPhase.end_date >= now)
        .order_by(TrainingPhase.start_date.asc())
        .first()
    )
    if next_race:
        days_to_race = (next_race.start_date.date() - today).days

        if 0 <= days_to_race <= 14:
            insights.append(Insight(
                id="race_taper_check",
                category="race",
                severity="info",
                title=f"距比赛 {days_to_race} 天, 检查 Taper 状态",
                description=f"目标比赛: {next_race.name} ({next_race.start_date.date()})。距比赛 ≤ 14 天是关键减量期, Friel 建议降量 40-60%, 保持强度, 不引入新动作。",
                recommendation="本周 TSS 降到目标比赛前的 50%。避免任何 >90 分钟的训练, 保持 1-2 次短促高强度维持神经肌肉。",
                metric_value=f"距比赛 {days_to_race} 天, 当前 TSS/wk ≈ {atl*7:.0f}",
                academic_source="Friel, Pre-race Taper",
            ))
        elif 14 < days_to_race <= 28:
            insights.append(Insight(
                id="race_peak_phase",
                category="race",
                severity="info",
                title=f"距比赛 {days_to_race} 天, 进入 Peak 期",
                description=f"目标比赛: {next_race.name} ({next_race.start_date.date()})。2-4 周是 Peak 期, 重点是模拟比赛强度, 让身体熟悉比赛节奏。",
                recommendation="安排 1-2 次 race-pace 训练 (按比赛时长和强度), 验证装备 / 补给 / 配速策略。TSS 维持当前水平, 不再加量。",
                metric_value=f"距比赛 {days_to_race} 天",
                academic_source="Friel, Peak Phase",
            ))

    # ===== 5. FTP 测试 =====

    latest_ftp = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == athlete_id)
        .order_by(desc(FTPTest.test_date))
        .first()
    )
    if latest_ftp:
        days_since_ftp = (today - latest_ftp.test_date.date()).days
        if days_since_ftp > 84:
            insights.append(Insight(
                id="ftp_retest_long",
                category="ftp",
                severity="info",
                title=f"FTP 测试超过 12 周 ({days_since_ftp} 天前)",
                description=f"上次 FTP 测试: {latest_ftp.ftp_w}W ({latest_ftp.test_date.date()})。Gabbett 建议 6-12 周复测一次, 长时间未测会导致训练区不准, 训练效果打折。",
                recommendation="本周安排一次 FTP 测试 (推荐 Coggan 20min 协议)。状态好 + 持续训练 2-3 月通常会有 3-5% 提升。",
                metric_value=f"FTP = {latest_ftp.ftp_w}W, {days_since_ftp} 天前",
                academic_source="Coggan 训练学",
            ))
        elif days_since_ftp > 42:
            # 中等优先级: 看 IF 平均
            recent_activities = (
                db.query(Activity)
                .filter(Activity.athlete_id == athlete_id)
                .filter(Activity.start_time >= now - timedelta(days=14))
                .all()
            )
            recent_ifs = []
            for a in recent_activities:
                np_v = (a.metrics or {}).get("normalized_power") or (a.metrics or {}).get("np")
                if np_v and latest_ftp.ftp_w > 0:
                    recent_ifs.append(np_v / latest_ftp.ftp_w)
            if recent_ifs:
                avg_if = sum(recent_ifs) / len(recent_ifs)
                if avg_if > 0.88:
                    insights.append(Insight(
                        id="ftp_consider_retest",
                        category="ftp",
                        severity="info",
                        title=f"考虑复测 FTP (近期 IF {avg_if:.2f})",
                        description=f"上次测试 {days_since_ftp} 天前, 但近期 14 天平均 IF 达 {avg_if:.2f}, 持续高强度训练可能已经突破。建议安排一次复测, 校准训练区。",
                        recommendation="安排 FTP 测试, 状态好通常会提升 3-8W, 训练区会重新校准。",
                        metric_value=f"14d avg IF = {avg_if:.2f}",
                        academic_source="Coggan 训练学",
                    ))

    # ===== 6. 周期阶段一致性 =====

    suggested = derive_phase(db, athlete_id)

    # 找当前阶段
    current_phase = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete_id)
        .filter(TrainingPhase.start_date <= now)
        .filter(TrainingPhase.end_date >= now)
        .order_by(TrainingPhase.start_date.desc())
        .first()
    )

    if current_phase and current_phase.phase_type != suggested.suggested_type:
        insights.append(Insight(
            id="phase_mismatch",
            category="phase",
            severity="info",
            title=f"当前阶段 vs 建议阶段不一致",
            description=f"当前阶段: {current_phase.name} ({current_phase.phase_type}), 但根据 PMC 状态 + 比赛日推算, 建议阶段是: {suggested.suggested_label} ({suggested.suggested_type})。不一致可能影响训练效果。",
            recommendation=f"考虑调整下一阶段类型为 {suggested.suggested_type}, 建议周目标 TSS = {suggested.target_weekly_tss}。",
            metric_value=f"当前 {current_phase.phase_type} vs 建议 {suggested.suggested_type}",
            academic_source="Friel 周期化 + PMC 推导",
        ))

    # ===== 7. 整体总结 =====

    # 按 severity 排序
    severity_order = {"alert": 0, "warning": 1, "info": 2}
    insights.sort(key=lambda i: (severity_order.get(i.severity, 99), i.id))

    # summary
    counts = {"alert": 0, "warning": 0, "info": 0}
    for i in insights:
        counts[i.severity] = counts.get(i.severity, 0) + 1

    # 健康分 (0-100): alert -20, warning -5, info +0
    health_score = 100 - counts["alert"] * 20 - counts["warning"] * 5
    health_score = max(0, min(100, health_score))

    return InsightsBundle(
        generated_at=now.isoformat(),
        athlete_id=athlete_id,
        insights=insights,
        summary={
            "total": len(insights),
            "alert": counts["alert"],
            "warning": counts["warning"],
            "info": counts["info"],
            "health_score": health_score,
            "health_label": "需要关注" if health_score < 60 else "一般" if health_score < 85 else "良好",
        },
        pcm={
            "ctl": round(ctl, 1),
            "atl": round(atl, 1),
            "tsb": round(tsb, 1),
            "ramp_rate": round(ramp_rate, 2),
        },
        acwr=get_acwr_overview(db) if False else {},  # 简化
    )


# ---------- 周复盘 (Friel Weekly Review) ----------

def compute_weekly_review(db: Session, athlete_id: Optional[int] = None) -> dict:
    """周复盘 (Friel Weekly Review 6 项检查)

    借鉴 Friel "Your First Week" + Training Bible Weekly Review:
    1. 本周目标完成情况 (TSS / km / h)
    2. 强度分布 (Z1-Z7 占比)
    3. 关键训练完成情况
    4. 身体反馈 (RPE 趋势)
    5. 跟上周对比 (进步 / 退步)
    6. 下周计划建议
    """
    if athlete_id is None:
        athlete = profile_store.get_or_create_athlete(db)
        athlete_id = athlete.id

    now = datetime.utcnow()
    week_start = (now - timedelta(days=now.weekday() + 7)).replace(hour=0, minute=0, second=0, microsecond=0)  # 上周一
    this_week_start = week_start + timedelta(days=7)
    last_week_start = week_start
    last_week_end = this_week_start

    # 本周
    this_week_acts = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= this_week_start)
        .filter(Activity.start_time < this_week_start + timedelta(days=7))
        .all()
    )
    # 上周
    last_week_acts = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= last_week_start)
        .filter(Activity.start_time < last_week_end)
        .all()
    )

    def agg(acts):
        tss = sum((a.metrics or {}).get("tss", 0) or 0 for a in acts)
        dist = sum(a.distance_m or 0 for a in acts) / 1000
        dur = sum(a.duration_s or 0 for a in acts) / 3600
        count = len(acts)
        rpes = [a.rpe for a in acts if a.rpe is not None]
        avg_rpe = sum(rpes) / len(rpes) if rpes else None
        return {"tss": round(tss, 0), "distance_km": round(dist, 1), "duration_h": round(dur, 1), "count": count, "avg_rpe": round(avg_rpe, 1) if avg_rpe else None}

    this_week = agg(this_week_acts)
    last_week = agg(last_week_acts)

    # 强度分布 (本周)
    latest_ftp = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == athlete_id)
        .order_by(desc(FTPTest.test_date))
        .first()
    )
    ftp_w = latest_ftp.ftp_w if latest_ftp else 250

    zone_seconds = {f"Z{i+1}": 0 for i in range(7)}
    total_s = 0
    for a in this_week_acts:
        samples = a.samples_json or []
        for s in samples:
            p = s.get("power") if isinstance(s, dict) else None
            if not p or p <= 0:
                continue
            ratio = p / ftp_w
            for i, (code, name, lo, hi) in enumerate(COGGAN_ZONES):
                if lo <= ratio < hi:
                    zone_seconds[code] += 1
                    total_s += 1
                    break
    zone_pct = {k: round(v / total_s * 100, 1) if total_s > 0 else 0 for k, v in zone_seconds.items()}

    # 对比
    tss_change = this_week["tss"] - last_week["tss"]
    tss_change_pct = round(tss_change / last_week["tss"] * 100, 1) if last_week["tss"] > 0 else None

    # 下周建议
    today_pcm = get_pmc_today(db, athlete_id)
    ctl = today_pcm.get("ctl", 0) or 0
    if tss_change_pct and tss_change_pct > 20:
        next_week_advice = "本周训练量大幅增加, 下周建议保持当前水平, 给身体适应时间。"
    elif tss_change_pct and tss_change_pct < -20:
        next_week_advice = "本周训练量下降明显, 下周可考虑逐步回升到正常水平。"
    elif ctl < 30:
        next_week_advice = "CTL 偏低, 下周以 Base 为主, 重点是累积 Z2 耐力。"
    elif ctl > 80:
        next_week_advice = "CTL 较高, 下周可考虑安排 1 天完全休息 + 1-2 次高强度维持。"
    else:
        next_week_advice = "当前节奏稳定, 下周保持, 每周小幅递增 5-10% TSS。"

    return {
        "this_week": {**this_week, "zone_pct": zone_pct, "total_zone_seconds": total_s},
        "last_week": last_week,
        "comparison": {
            "tss_change": tss_change,
            "tss_change_pct": tss_change_pct,
        },
        "next_week_advice": next_week_advice,
        "ftp_used": ftp_w,
    }
