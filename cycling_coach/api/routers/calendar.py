"""/api/calendar — 月历视图 + 单次计划课 CRUD + 自动关联"""
from __future__ import annotations
import logging
from datetime import date as _date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import (
    Activity, PlanPeriod, PlannedWorkout, Workout
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/calendar", tags=["calendar"])


# ---------- Schemas ----------

class PlannedCreate(BaseModel):
    scheduled_date: _date
    title: str = Field(..., max_length=128)
    intent: str = Field("endurance", max_length=32)  # recovery/endurance/tempo/threshold/vo2max/race
    duration_target_min: Optional[int] = None
    tss_target: Optional[int] = None
    notes: Optional[str] = None
    period_id: Optional[int] = None
    workout_id: Optional[int] = None


class PlannedUpdate(BaseModel):
    scheduled_date: Optional[_date] = None
    title: Optional[str] = None
    intent: Optional[str] = None
    duration_target_min: Optional[int] = None
    tss_target: Optional[int] = None
    notes: Optional[str] = None
    period_id: Optional[int] = None
    status: Optional[str] = None  # planned/done/skipped/moved


# ---------- Helpers ----------

def _serialize_planned(w: PlannedWorkout) -> dict:
    return {
        "id": w.id,
        "period_id": w.period_id,
        "workout_id": w.workout_id,
        "actual_activity_id": w.actual_activity_id,
        "scheduled_date": w.scheduled_date.isoformat(),
        "title": w.title,
        "intent": w.intent,
        "duration_target_min": w.duration_target_min,
        "tss_target": w.tss_target,
        "notes": w.notes,
        "status": w.status,
        "completed_at": w.completed_at.isoformat() if w.completed_at else None,
    }


def _try_auto_link(db: Session, planned: PlannedWorkout) -> bool:
    """尝试把 planned 关联到 scheduled_date 当天的 activity

    匹配规则:同一天、有 planned.workout_id 时按 duration 接近度匹配;
    否则按当天第一/最近的活动匹配。
    关联成功返回 True。
    """
    target_date = planned.scheduled_date
    start = datetime.combine(target_date, datetime.min.time())
    end = start + timedelta(days=1)
    candidates = db.execute(
        select(Activity)
        .where(and_(
            Activity.start_time >= start,
            Activity.start_time < end,
        ))
        .order_by(Activity.start_time.asc())
    ).scalars().all()

    if not candidates:
        return False

    # 优先按 duration_target_min 接近度匹配
    best = None
    if planned.duration_target_min:
        target_s = planned.duration_target_min * 60
        best = min(candidates, key=lambda a: abs((a.duration_s or 0) - target_s))
    else:
        best = candidates[0]

    planned.actual_activity_id = best.id
    planned.status = "done"
    planned.completed_at = datetime.utcnow()
    logger.info(
        f"自动关联: planned#{planned.id} ({planned.scheduled_date}) → activity#{best.id}"
    )
    return True


def _build_calendar_month(
    db: Session, athlete_id: int, year: int, month: int
) -> dict:
    """构造月历视图:每天一组 planned + actual"""
    from calendar import monthrange
    import calendar as cal

    first = _date(year, month, 1)
    last_day = monthrange(year, month)[1]
    last = _date(year, month, last_day)

    # 取整月所有 planned
    planned_rows = db.execute(
        select(PlannedWorkout)
        .where(
            PlannedWorkout.scheduled_date >= first,
            PlannedWorkout.scheduled_date <= last,
        )
        .order_by(PlannedWorkout.scheduled_date.asc())
    ).scalars().all()

    # 过滤:本 athlete 的(通过 period 间接确认)
    athlete_periods = set(
        db.execute(
            select(PlanPeriod.id).where(PlanPeriod.athlete_id == athlete_id)
        ).scalars()
    )
    planned_rows = [p for p in planned_rows
                    if p.period_id is None or p.period_id in athlete_periods]

    # 取整月所有 activity
    act_start = datetime.combine(first, datetime.min.time())
    act_end = datetime.combine(last + timedelta(days=1), datetime.min.time())
    acts = db.execute(
        select(Activity)
        .where(
            Activity.athlete_id == athlete_id,
            Activity.start_time >= act_start,
            Activity.start_time < act_end,
        )
    ).scalars().all()

    # 按天分组
    planned_by_day: dict[_date, list] = {}
    for p in planned_rows:
        planned_by_day.setdefault(p.scheduled_date, []).append(_serialize_planned(p))

    actual_by_day: dict[_date, list] = {}
    for a in acts:
        d = a.start_time.date() if isinstance(a.start_time, datetime) else a.start_time
        actual_by_day.setdefault(d, []).append({
            "id": a.id,
            "title": a.file_name or f"Activity #{a.id}",
            "duration_s": a.duration_s,
            "distance_m": a.distance_m,
            "avg_power": a.avg_power,
            "avg_hr": a.avg_hr,
            "tss": (a.metrics or {}).get("tss"),
            "start_time": a.start_time.isoformat() if a.start_time else None,
        })

    # 构造 grid(包含 padding 让周一开始)
    cal_matrix = cal.Calendar(firstweekday=0)  # 周一第一天
    weeks = cal_matrix.monthdayscalendar(year, month)

    # 计算月度统计
    total_planned = sum(len(v) for v in planned_by_day.values())
    done_count = sum(1 for p in planned_rows if p.status == "done")
    skipped_count = sum(1 for p in planned_rows if p.status == "skipped")
    completion_rate = (done_count / total_planned * 100) if total_planned else 0.0
    total_actual_tss = sum((a.metrics or {}).get("tss") or 0 for a in acts)
    total_actual_minutes = sum((a.duration_s or 0) for a in acts) / 60.0

    return {
        "year": year,
        "month": month,
        "month_label": f"{year}-{month:02d}",
        "weeks": weeks,  # 6 行 × 7 列
        "planned_by_day": {d.isoformat(): v for d, v in planned_by_day.items()},
        "actual_by_day": {d.isoformat(): v for d, v in actual_by_day.items()},
        "stats": {
            "planned_count": total_planned,
            "done_count": done_count,
            "skipped_count": skipped_count,
            "completion_rate": round(completion_rate, 1),
            "actual_activities": len(acts),
            "actual_tss_total": round(total_actual_tss, 0),
            "actual_hours_total": round(total_actual_minutes / 60, 1),
        },
    }


# ---------- Routes ----------

@router.get("")
def get_calendar(
    year: int = Query(..., ge=2000, le=2100),
    month: int = Query(..., ge=1, le=12),
    db: Session = Depends(get_db),
):
    """取月历视图(每月一次调用)"""
    athlete = profile_store.get_or_create_athlete(db)
    return _build_calendar_month(db, athlete.id, year, month)


@router.get("/planned")
def list_planned(
    start: Optional[_date] = None,
    end: Optional[_date] = None,
    db: Session = Depends(get_db),
):
    """列出日期范围内的所有计划课(列表视图)"""
    stmt = select(PlannedWorkout).order_by(PlannedWorkout.scheduled_date.asc())
    if start:
        stmt = stmt.where(PlannedWorkout.scheduled_date >= start)
    if end:
        stmt = stmt.where(PlannedWorkout.scheduled_date <= end)
    rows = db.execute(stmt).scalars().all()
    return {"planned": [_serialize_planned(w) for w in rows]}


@router.post("/planned")
def create_planned(payload: PlannedCreate, db: Session = Depends(get_db)):
    """创建单次计划课"""
    athlete = profile_store.get_or_create_athlete(db)
    # 校验 period
    if payload.period_id:
        period = db.get(PlanPeriod, payload.period_id)
        if not period or period.athlete_id != athlete.id:
            raise HTTPException(400, "plan_period 不存在或不属于本 athlete")
    planned = PlannedWorkout(
        scheduled_date=payload.scheduled_date,
        title=payload.title,
        intent=payload.intent,
        duration_target_min=payload.duration_target_min,
        tss_target=payload.tss_target,
        notes=payload.notes,
        period_id=payload.period_id,
        workout_id=payload.workout_id,
    )
    db.add(planned)
    db.commit()
    db.refresh(planned)
    # 尝试自动关联
    _try_auto_link(db, planned)
    db.commit()
    return _serialize_planned(planned)


@router.patch("/planned/{planned_id}")
def update_planned(
    planned_id: int, payload: PlannedUpdate, db: Session = Depends(get_db)
):
    """更新单次计划课"""
    p = db.get(PlannedWorkout, planned_id)
    if not p:
        raise HTTPException(404, "计划课不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(p, k, v)
    db.commit()
    db.refresh(p)
    return _serialize_planned(p)


@router.delete("/planned/{planned_id}")
def delete_planned(planned_id: int, db: Session = Depends(get_db)):
    """删除单次计划课"""
    p = db.get(PlannedWorkout, planned_id)
    if not p:
        raise HTTPException(404, "计划课不存在")
    db.delete(p)
    db.commit()
    return {"ok": True, "id": planned_id}


@router.post("/planned/{planned_id}/link/{activity_id}")
def link_planned_to_activity(
    planned_id: int, activity_id: int, db: Session = Depends(get_db)
):
    """手动把计划课关联到真实活动"""
    p = db.get(PlannedWorkout, planned_id)
    if not p:
        raise HTTPException(404, "计划课不存在")
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(404, "活动不存在")
    p.actual_activity_id = a.id
    p.status = "done"
    p.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(p)
    return _serialize_planned(p)


@router.post("/planned/{planned_id}/unlink")
def unlink_planned(planned_id: int, db: Session = Depends(get_db)):
    """解除关联(回到 planned 状态)"""
    p = db.get(PlannedWorkout, planned_id)
    if not p:
        raise HTTPException(404, "计划课不存在")
    p.actual_activity_id = None
    p.status = "planned"
    p.completed_at = None
    db.commit()
    db.refresh(p)
    return _serialize_planned(p)


@router.post("/auto-link")
def auto_link_all(
    year: int = Query(...), month: int = Query(...),
    db: Session = Depends(get_db),
):
    """把本月所有未关联的 planned 自动关联到当天活动(批量)"""
    from calendar import monthrange
    first = _date(year, month, 1)
    last = _date(year, month, monthrange(year, month)[1])
    rows = db.execute(
        select(PlannedWorkout)
        .where(
            PlannedWorkout.scheduled_date >= first,
            PlannedWorkout.scheduled_date <= last,
            PlannedWorkout.actual_activity_id.is_(None),
        )
    ).scalars().all()
    linked = 0
    for p in rows:
        if _try_auto_link(db, p):
            linked += 1
    db.commit()
    return {"ok": True, "linked": linked, "total": len(rows)}
