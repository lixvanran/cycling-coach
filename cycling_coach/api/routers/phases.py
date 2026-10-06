"""训练周期 (Periodization) CRUD + 智能推荐

Joe Friel Periodization 框架:
- Base (基础期): Z1-Z2 为主, 大量耐力, 4-8 周
- Build (强化期): 引入 threshold / VO2max, 3-6 周
- Peak (巅峰期): 短间歇+长耐力, 模拟比赛, 2-3 周
- Taper (减量期): 降量 40-60%, 1-2 周
- Recovery (恢复期): 极轻量, 1-2 周
- Race (比赛日): 标注比赛
- Rest (休赛期): 不训练, 1-4 周
"""
from __future__ import annotations
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.data.sqlite.models import TrainingPhase, Activity, PhaseWorkout, PlannedWorkout
from cycling_coach.core.profile import store as profile_store
# V0.8.3.1 P1: 统一 UTC naive 时间戳
from cycling_coach.core.time_utils import utcnow_naive

router = APIRouter(prefix="/api/phases", tags=["phases"])


# ---------- Schemas ----------

class PhaseCreate(BaseModel):
    phase_type: str = Field(..., description="base/build/peak/taper/recovery/race/rest")
    name: str = Field(..., min_length=1, max_length=64)
    start_date: str = Field(..., description="YYYY-MM-DD")
    end_date: str = Field(..., description="YYYY-MM-DD")
    target_tss_week: int | None = None
    target_ftp_w: int | None = None
    notes: str | None = None
    is_race: bool = False
    race_type: str | None = Field(None, description="tt/road_race/stage_race/gran_fondo/crit/hill_climb/other")
    race_priority: str | None = Field(None, description="A/B/C")


class PhaseUpdate(BaseModel):
    phase_type: str | None = None
    name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    target_tss_week: int | None = None
    target_ftp_w: int | None = None
    notes: str | None = None
    is_race: bool | None = None
    race_type: str | None = None
    race_priority: str | None = None


class PhaseOut(BaseModel):
    id: int
    phase_type: str
    name: str
    start_date: str
    end_date: str
    target_tss_week: int | None
    target_ftp_w: int | None
    notes: str | None
    is_race: bool
    race_type: str | None = None
    race_priority: str | None = None
    duration_days: int
    actual_avg_tss_week: float | None = None  # 实际周均 TSS (只读)
    actual_count: int = 0
    class Config:
        from_attributes = True


# ---------- Phase metadata (前端用) ----------

PHASE_META = {
    "base": {"label": "基础期", "color": "blue", "description": "Z1-Z2 为主, 大量耐力", "icon": "🌱"},
    "build": {"label": "强化期", "color": "amber", "description": "引入 threshold / VO2max", "icon": "🔥"},
    "peak": {"label": "巅峰期", "color": "red", "description": "模拟比赛, 高强度短间歇", "icon": "⚡"},
    "taper": {"label": "减量期", "color": "green", "description": "降量 40-60%, 蓄能", "icon": "🪷"},
    "recovery": {"label": "恢复期", "color": "slate", "description": "极轻量, 主动恢复", "icon": "😌"},
    "race": {"label": "比赛", "color": "purple", "description": "比赛日 / 比赛周", "icon": "🏁"},
    "rest": {"label": "休赛期", "color": "slate", "description": "不训练 / 完全休息", "icon": "💤"},
}


@router.get("/meta")
def get_meta():
    return {"phases": PHASE_META}


# ---------- CRUD ----------

@router.get("", response_model=list[PhaseOut])
def list_phases(db: Session = Depends(get_db)):
    """所有阶段 (按开始时间倒序)"""
    athlete = profile_store.get_or_create_athlete(db)
    phases = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete.id)
        .order_by(TrainingPhase.start_date.desc())
        .all()
    )
    out = []
    for p in phases:
        # 实际周均 TSS
        acts = (
            db.query(Activity)
            .filter(Activity.athlete_id == athlete.id)
            .filter(Activity.start_time >= p.start_date)
            .filter(Activity.start_time <= p.end_date)
            .all()
        )
        if acts:
            total_tss = sum((a.metrics or {}).get("tss", 0) or 0 for a in acts)
            weeks = max(1, (p.end_date - p.start_date).days / 7)
            actual_avg_tss_week = round(total_tss / weeks, 1)
            actual_count = len(acts)
        else:
            actual_avg_tss_week = None
            actual_count = 0

        out.append(PhaseOut(
            id=p.id,
            phase_type=p.phase_type,
            name=p.name,
            start_date=p.start_date.date().isoformat(),
            end_date=p.end_date.date().isoformat(),
            target_tss_week=p.target_tss_week,
            target_ftp_w=p.target_ftp_w,
            notes=p.notes,
            is_race=p.is_race,
            race_type=p.race_type,
            race_priority=p.race_priority,
            duration_days=(p.end_date - p.start_date).days + 1,
            actual_avg_tss_week=actual_avg_tss_week,
            actual_count=actual_count,
        ))
    return out


@router.post("", response_model=PhaseOut)
def create_phase(payload: PhaseCreate, db: Session = Depends(get_db)):
    if payload.phase_type not in PHASE_META:
        raise HTTPException(400, f"phase_type 必须是 {list(PHASE_META.keys())}")
    try:
        start = datetime.fromisoformat(payload.start_date)
        end = datetime.fromisoformat(payload.end_date + "T23:59:59")
    except ValueError as e:
        raise HTTPException(400, f"日期格式错误: {e}")
    if end < start:
        raise HTTPException(400, "end_date 必须在 start_date 之后")

    athlete = profile_store.get_or_create_athlete(db)
    p = TrainingPhase(
        athlete_id=athlete.id,
        phase_type=payload.phase_type,
        name=payload.name,
        start_date=start,
        end_date=end,
        target_tss_week=payload.target_tss_week,
        target_ftp_w=payload.target_ftp_w,
        notes=payload.notes,
        is_race=payload.is_race,
        race_type=payload.race_type,
        race_priority=payload.race_priority,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return _to_out(p, db)


@router.get("/current", response_model=PhaseOut | None)
def current_phase(db: Session = Depends(get_db)):
    """今天的阶段 (None = 无)"""
    athlete = profile_store.get_or_create_athlete(db)
    now = utcnow_naive()
    p = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete.id)
        .filter(TrainingPhase.start_date <= now)
        .filter(TrainingPhase.end_date >= now)
        .order_by(TrainingPhase.start_date.desc())
        .first()
    )
    if not p:
        return None
    return _to_out(p, db)


@router.get("/next-race")
def next_race(db: Session = Depends(get_db)):
    """下一个比赛日 (含倒计时)"""
    athlete = profile_store.get_or_create_athlete(db)
    now = utcnow_naive()
    p = (
        db.query(TrainingPhase)
        .filter(TrainingPhase.athlete_id == athlete.id)
        .filter(TrainingPhase.is_race == True)  # noqa: E712
        .filter(TrainingPhase.end_date >= now)
        .order_by(TrainingPhase.start_date.asc())
        .first()
    )
    if not p:
        return None
    days_to = (p.start_date.date() - now.date()).days
    return {
        "id": p.id,
        "name": p.name,
        "date": p.start_date.date().isoformat(),
        "days_to_race": days_to,
        "phase_type": p.phase_type,
    }


@router.patch("/{phase_id}", response_model=PhaseOut)
def update_phase(phase_id: int, payload: PhaseUpdate, db: Session = Depends(get_db)):
    athlete = profile_store.get_or_create_athlete(db)
    p = db.get(TrainingPhase, phase_id)
    # V0.8.3.1 P0: IDOR 防护 — phase 必须属于当前 athlete
    if not p or p.athlete_id != athlete.id:
        raise HTTPException(404, f"阶段 {phase_id} 不存在")
    data = payload.model_dump(exclude_unset=True)
    if "phase_type" in data and data["phase_type"] not in PHASE_META:
        raise HTTPException(400, f"phase_type 必须是 {list(PHASE_META.keys())}")
    if "start_date" in data:
        data["start_date"] = datetime.fromisoformat(data["start_date"])
    if "end_date" in data:
        data["end_date"] = datetime.fromisoformat(data["end_date"] + "T23:59:59")
    for k, v in data.items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _to_out(p, db)


@router.delete("/{phase_id}")
def delete_phase(phase_id: int, db: Session = Depends(get_db)):
    athlete = profile_store.get_or_create_athlete(db)
    p = db.get(TrainingPhase, phase_id)
    # V0.8.3.1 P0: IDOR 防护
    if not p or p.athlete_id != athlete.id:
        raise HTTPException(404, f"阶段 {phase_id} 不存在")
    db.delete(p)
    db.commit()
    return {"ok": True, "id": phase_id}


# ---------- 阶段周模板 CRUD (B1-3) ----------

class PhaseWorkoutCreate(BaseModel):
    week_index: int = Field(..., ge=1, le=52)
    day_of_week: int = Field(..., ge=1, le=7)  # 1=Mon .. 7=Sun
    title: str = Field(..., min_length=1, max_length=128)
    intent: str = Field("endurance", max_length=32)
    duration_target_min: int | None = None
    tss_target: int | None = None
    notes: str | None = None
    workout_id: int | None = None


class PhaseWorkoutOut(BaseModel):
    id: int
    week_index: int
    day_of_week: int
    title: str
    intent: str
    duration_target_min: int | None
    tss_target: int | None
    notes: str | None
    workout_id: int | None
    class Config:
        from_attributes = True


@router.get("/{phase_id}/workouts", response_model=list[PhaseWorkoutOut])
def list_phase_workouts(phase_id: int, db: Session = Depends(get_db)):
    """列出阶段的所有周模板(按 week_index, day_of_week 排序)"""
    athlete = profile_store.get_or_create_athlete(db)
    phase = db.get(TrainingPhase, phase_id)
    # V0.8.3.1 P0: IDOR 防护 — phase 必须属于当前 athlete
    if not phase or phase.athlete_id != athlete.id:
        raise HTTPException(404, f"阶段 {phase_id} 不存在")
    rows = (
        db.query(PhaseWorkout)
        .filter(PhaseWorkout.phase_id == phase_id)
        .order_by(PhaseWorkout.week_index.asc(), PhaseWorkout.day_of_week.asc())
        .all()
    )
    return rows


@router.post("/{phase_id}/workouts", response_model=PhaseWorkoutOut, status_code=201)
def add_phase_workout(
    phase_id: int, payload: PhaseWorkoutCreate, db: Session = Depends(get_db)
):
    """新增阶段周模板的一个格子"""
    athlete = profile_store.get_or_create_athlete(db)
    phase = db.get(TrainingPhase, phase_id)
    # V0.8.3.1 P0: IDOR 防护
    if not phase or phase.athlete_id != athlete.id:
        raise HTTPException(404, f"阶段 {phase_id} 不存在")
    # 校验 workout 存在
    if payload.workout_id is not None:
        from cycling_coach.data.sqlite.models import Workout
        if not db.get(Workout, payload.workout_id):
            raise HTTPException(400, f"workout_id {payload.workout_id} 不存在")
    # 唯一性 (week_index, day_of_week) — 用 INSERT OR FAIL 行为
    existing = (
        db.query(PhaseWorkout)
        .filter(PhaseWorkout.phase_id == phase_id)
        .filter(PhaseWorkout.week_index == payload.week_index)
        .filter(PhaseWorkout.day_of_week == payload.day_of_week)
        .first()
    )
    if existing:
        raise HTTPException(
            409,
            f"phase #{phase_id} 已有 week {payload.week_index} / day {payload.day_of_week} 的模板",
        )
    pw = PhaseWorkout(
        phase_id=phase_id,
        week_index=payload.week_index,
        day_of_week=payload.day_of_week,
        title=payload.title,
        intent=payload.intent,
        duration_target_min=payload.duration_target_min,
        tss_target=payload.tss_target,
        notes=payload.notes,
        workout_id=payload.workout_id,
    )
    db.add(pw)
    db.commit()
    db.refresh(pw)
    return pw


@router.delete("/{phase_id}/workouts/{pw_id}")
def delete_phase_workout(phase_id: int, pw_id: int, db: Session = Depends(get_db)):
    """删除阶段周模板"""
    athlete = profile_store.get_or_create_athlete(db)
    pw = db.get(PhaseWorkout, pw_id)
    # V0.8.3.1 P0: IDOR 防护 — 同时校验 pw 属于该 phase 且 phase 属于该 athlete
    if not pw or pw.phase_id != phase_id:
        raise HTTPException(404, f"模板 {pw_id} 不属于阶段 {phase_id}")
    phase = db.get(TrainingPhase, pw.phase_id)
    if not phase or phase.athlete_id != athlete.id:
        raise HTTPException(404, f"阶段 {phase_id} 不存在")
    db.delete(pw)
    db.commit()
    return {"ok": True, "id": pw_id}


# ---------- 一键应用到日历 (B1-3) ----------

@router.post("/{phase_id}/apply")
def apply_phase_to_calendar(
    phase_id: int,
    start_date: str = Query(..., description="YYYY-MM-DD, 起始周一"),
    weeks: int = Query(..., ge=1, le=52),
    db: Session = Depends(get_db),
):
    """把阶段的周模板批量生成 PlannedWorkout 到日历

    算法:
      a. 拉 phase 关联的 PhaseWorkout(按 week_index + day_of_week 排序)
      b. 每周 7 天, 按 day_of_week 计算实际日期:
           cycle_week = ((target_week - 1) % max_week_index) + 1
           scheduled_date = start_date + (target_week-1)*7 + (day_of_week-1)
      c. 调 internal PlannedCreate 批量创建 (直接 ORM 写入 + 自动关联)
      d. 返回所有 planned_id

    返回: { ok, applied_count, planned_ids: [int] }
    """
    athlete = profile_store.get_or_create_athlete(db)
    phase = db.get(TrainingPhase, phase_id)
    # V0.8.3.1 P0: IDOR 防护 — phase 必须属于当前 athlete
    if not phase or phase.athlete_id != athlete.id:
        raise HTTPException(404, f"阶段 {phase_id} 不存在")

    # 1. 校验 start_date
    try:
        sd = datetime.fromisoformat(start_date)
    except ValueError:
        raise HTTPException(400, f"start_date 格式错误: {start_date}, 需 YYYY-MM-DD")

    # 2. 拉模板
    templates = (
        db.query(PhaseWorkout)
        .filter(PhaseWorkout.phase_id == phase_id)
        .order_by(PhaseWorkout.week_index.asc(), PhaseWorkout.day_of_week.asc())
        .all()
    )
    if not templates:
        raise HTTPException(
            400,
            f"阶段 {phase_id} 没有周模板, 先在阶段里定义 (week_index, day_of_week, title) 再应用",
        )

    # 3. 计算 max_week_index 用于 cycle
    max_week_index = max(t.week_index for t in templates)

    # 4. 对 weeks 范围内的每周, 取出 cycle_week + day_of_week 对应的模板, 写入 PlannedWorkout
    planned_ids: list[int] = []
    from cycling_coach.api.routers.calendar import _try_auto_link

    for target_week in range(1, weeks + 1):
        cycle_week = ((target_week - 1) % max_week_index) + 1
        for tpl in templates:
            if tpl.week_index != cycle_week:
                continue
            offset_days = (target_week - 1) * 7 + (tpl.day_of_week - 1)
            scheduled = sd + timedelta(days=offset_days)
            pw = PlannedWorkout(
                athlete_id=athlete.id,  # V0.8.3.1 P0: 显式归属
                scheduled_date=scheduled,
                title=tpl.title,
                intent=tpl.intent,
                duration_target_min=tpl.duration_target_min,
                tss_target=tpl.tss_target,
                notes=tpl.notes,
                # 不挂 plan_period(phase 与 plan_period 是两个层级),不挂 workout_id(由 calendar 解析)
                period_id=None,
                workout_id=tpl.workout_id,
            )
            db.add(pw)
            db.flush()  # 拿到 id 再 auto-link
            _try_auto_link(db, pw)
            planned_ids.append(pw.id)

    db.commit()
    return {
        "ok": True,
        "applied_count": len(planned_ids),
        "planned_ids": planned_ids,
    }


# ---------- 智能推荐 (基于过去 30 天 TSS) ----------

@router.get("/suggest")
def suggest_phase(db: Session = Depends(get_db)):
    """根据 PMC + 比赛日 + 训练学推导下个阶段 (Joe Friel 框架)

    V0.6.1 深度版: 基于 CTL/ATL/TSB + 比赛日倒推
    """
    from cycling_coach.core.metrics.periodization import derive_phase
    athlete = profile_store.get_or_create_athlete(db)
    d = derive_phase(db, athlete.id)
    # V0.9.0 P0-3: 数据不足时那三个字段现在是 None (之前是 0)。
    # 0 是个**看起来合法的训练学数值**: 前端会渲染成"目标 TSS 0 / 建议 0 周",
    # 还会拿 0 去调"一键创建" → HTTP 400。
    # 而且 `list(None)` 直接 TypeError → 整个接口 500。
    #
    # 所以显式告诉前端"这次算不出来", 别让它自己猜 0 是什么意思。
    sufficient = d.suggested_type != "unknown"
    return {
        "data_sufficient": sufficient,
        "suggestion": d.suggested_type,
        "label": d.suggested_label,
        "confidence": d.confidence,
        "reasons": d.reasons,
        "target_weekly_tss": d.target_weekly_tss,
        "target_weekly_tss_range": (
            list(d.target_weekly_tss_range) if d.target_weekly_tss_range else None
        ),
        "weeks_recommended": d.weeks_recommended,
        "weeks_to_race": d.weeks_to_race,
        "current_ctl": round(d.current_ctl, 1),
        "current_atl": round(d.current_atl, 1),
        "current_tsb": round(d.current_tsb, 1),
        "ramp_rate": round(d.ramp_rate, 2),
    }


@router.get("/polarized")
def polarized_analysis(days: int = 30, db: Session = Depends(get_db)):
    """Seiler 80/20 极化训练分布分析

    学术: Stephen Seiler 2010
    - Z1+Z2 ≈ 80%
    - Z5+Z6+Z7 ≈ 20%
    - Z3+Z4 ≈ 0% (避免 "灰色地带")
    """
    from cycling_coach.core.metrics.periodization import analyze_polarized
    athlete = profile_store.get_or_create_athlete(db)
    p = analyze_polarized(db, athlete.id, days=days)
    return {
        "total_seconds": p.total_seconds,
        "total_hours": round(p.total_seconds / 3600, 1),
        "zones": {
            "Z1": p.z1_seconds,
            "Z2": p.z2_seconds,
            "Z3": p.z3_seconds,
            "Z4": p.z4_seconds,
            "Z5": p.z5_seconds,
            "Z6": p.z6_seconds,
            "Z7": p.z7_seconds,
        },
        "pct": {
            "easy": round(p.easy_pct * 100, 1),
            "threshold": round(p.threshold_pct * 100, 1),
            "hard": round(p.hard_pct * 100, 1),
        },
        "polarized_score": p.polarized_score,
        "interpretation": p.interpretation,
        "target": {
            "easy_pct": 80,
            "hard_pct": 20,
            "threshold_pct_max": 10,
        },
        "days_analyzed": p.days_analyzed,
    }


@router.get("/race-plan")
def race_plan(
    race_date: str,
    race_name: str = "目标比赛",
    db: Session = Depends(get_db),
):
    """比赛日倒推自动生成周期计划

    输入: race_date (YYYY-MM-DD), race_name
    输出: Base / Build I / Build II / Peak / Taper / Race 完整计划
    """
    from datetime import date as _date
    from cycling_coach.core.metrics.periodization import generate_race_plan
    athlete = profile_store.get_or_create_athlete(db)

    # 找最新 FTP
    from cycling_coach.data.sqlite.models import FTPTest
    latest_ftp = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == athlete.id)
        .order_by(FTPTest.test_date.desc())
        .first()
    )
    current_ftp = latest_ftp.ftp_w if latest_ftp else 250

    # 找当前 CTL
    from cycling_coach.core.pmc import get_pmc_today
    today_pmc = get_pmc_today(db, athlete.id)
    current_ctl = today_pmc.get("ctl", 50)

    try:
        rd = _date.fromisoformat(race_date)
    except ValueError:
        raise HTTPException(400, f"race_date 格式错误: {race_date}, 需 YYYY-MM-DD")

    plan = generate_race_plan(rd, race_name, current_ctl=current_ctl, current_ftp=current_ftp)
    return {
        "race_date": plan.race_date.isoformat(),
        "race_name": plan.race_name,
        "weeks_total": plan.weeks_total,
        "current_ftp": current_ftp,
        "current_ctl": round(current_ctl, 1),
        "plan": plan.plan,
    }


# ---------- helpers ----------

def _to_out(p: TrainingPhase, db: Session) -> PhaseOut:
    """转 PhaseOut (含实际统计)"""
    acts = (
        db.query(Activity)
        .filter(Activity.athlete_id == p.athlete_id)
        .filter(Activity.start_time >= p.start_date)
        .filter(Activity.start_time <= p.end_date)
        .all()
    )
    if acts:
        total_tss = sum((a.metrics or {}).get("tss", 0) or 0 for a in acts)
        weeks = max(1, (p.end_date - p.start_date).days / 7)
        actual_avg = round(total_tss / weeks, 1)
        actual_count = len(acts)
    else:
        actual_avg = None
        actual_count = 0

    return PhaseOut(
        id=p.id,
        phase_type=p.phase_type,
        name=p.name,
        start_date=p.start_date.date().isoformat(),
        end_date=p.end_date.date().isoformat(),
        target_tss_week=p.target_tss_week,
        target_ftp_w=p.target_ftp_w,
        notes=p.notes,
        is_race=p.is_race,
        race_type=p.race_type,
        race_priority=p.race_priority,
        duration_days=(p.end_date - p.start_date).days + 1,
        actual_avg_tss_week=actual_avg,
        actual_count=actual_count,
    )


@router.get("/signals")
def phase_signals(db: Session = Depends(get_db)):
    """V0.7.2: 周期化阶段信号检测
    
    7 个信号:
    - avg_if_28d: 28d 平均强度
    - freq_7d: 7d 训练频率
    - streak_days: 连续训练天数
    - weeks_since_taper: 距上次减量
    - polarized_score_28d: 极化评分
    - load_achievement_7d: 负荷达成率
    - warnings / hints: 训练学建议
    """
    from cycling_coach.core.metrics.periodization import detect_phase_signals
    athlete = profile_store.get_or_create_athlete(db)
    s = detect_phase_signals(db, athlete.id)
    return {
        "avg_if_28d": s.avg_if_28d,
        "freq_7d": s.freq_7d,
        "streak_days": s.streak_days,
        "weeks_since_taper": s.weeks_since_taper,
        "polarized_score_28d": s.polarized_score_28d,
        "load_achievement_7d": s.load_achievement_7d,
        "warnings": s.warnings,
        "hints": s.hints,
    }
