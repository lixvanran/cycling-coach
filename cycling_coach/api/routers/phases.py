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

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.data.sqlite.models import TrainingPhase, Activity
from cycling_coach.core.profile import store as profile_store

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


class PhaseUpdate(BaseModel):
    phase_type: str | None = None
    name: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    target_tss_week: int | None = None
    target_ftp_w: int | None = None
    notes: str | None = None
    is_race: bool | None = None


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
        target_ftp_w=p.payload_target_ftp_w if False else payload.target_ftp_w,
        notes=payload.notes,
        is_race=payload.is_race,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return list_phases.__wrapped__(db) if False else _to_out(p, db)


@router.get("/current", response_model=PhaseOut | None)
def current_phase(db: Session = Depends(get_db)):
    """今天的阶段 (None = 无)"""
    athlete = profile_store.get_or_create_athlete(db)
    now = datetime.utcnow()
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
    now = datetime.utcnow()
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
    p = db.get(TrainingPhase, phase_id)
    if not p:
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
    p = db.get(TrainingPhase, phase_id)
    if not p:
        raise HTTPException(404, f"阶段 {phase_id} 不存在")
    db.delete(p)
    db.commit()
    return {"ok": True, "id": phase_id}


# ---------- 智能推荐 (基于过去 30 天 TSS) ----------

@router.get("/suggest")
def suggest_phase(db: Session = Depends(get_db)):
    """根据 PMC + 比赛日 + 训练学推导下个阶段 (Joe Friel 框架)

    V0.6.1 深度版: 基于 CTL/ATL/TSB + 比赛日倒推
    """
    from cycling_coach.core.metrics.periodization import derive_phase
    athlete = profile_store.get_or_create_athlete(db)
    d = derive_phase(db, athlete.id)
    return {
        "suggestion": d.suggested_type,
        "label": d.suggested_label,
        "confidence": d.confidence,
        "reasons": d.reasons,
        "target_weekly_tss": d.target_weekly_tss,
        "target_weekly_tss_range": list(d.target_weekly_tss_range),
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
        duration_days=(p.end_date - p.start_date).days + 1,
        actual_avg_tss_week=actual_avg,
        actual_count=actual_count,
    )
