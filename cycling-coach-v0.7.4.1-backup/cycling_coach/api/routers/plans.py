"""/api/plans — 训练周期 CRUD"""
from __future__ import annotations
import logging
from datetime import date as _date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import PlanPeriod, PlannedWorkout

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/plans", tags=["plans"])


# ---------- Schemas ----------

class PlanCreate(BaseModel):
    name: str = Field(..., max_length=128)
    period_type: str = Field("base", max_length=32)  # base/build/peak/taper/recovery/race
    start_date: _date
    end_date: _date
    target_event: Optional[str] = None
    weekly_hours_target: Optional[float] = None
    notes: Optional[str] = None


class PlanUpdate(BaseModel):
    name: Optional[str] = None
    period_type: Optional[str] = None
    start_date: Optional[_date] = None
    end_date: Optional[_date] = None
    target_event: Optional[str] = None
    weekly_hours_target: Optional[float] = None
    notes: Optional[str] = None


def _serialize_plan(p: PlanPeriod) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "period_type": p.period_type,
        "start_date": p.start_date.isoformat(),
        "end_date": p.end_date.isoformat(),
        "target_event": p.target_event,
        "weekly_hours_target": p.weekly_hours_target,
        "notes": p.notes,
        "workout_count": len(p.workouts) if p.workouts else 0,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


# ---------- Routes ----------

@router.get("")
def list_plans(db: Session = Depends(get_db)):
    """列出所有训练周期"""
    athlete = profile_store.get_or_create_athlete(db)
    plans = db.execute(
        select(PlanPeriod)
        .where(PlanPeriod.athlete_id == athlete.id)
        .order_by(PlanPeriod.start_date.desc())
    ).scalars().all()
    return {"plans": [_serialize_plan(p) for p in plans]}


@router.post("")
def create_plan(payload: PlanCreate, db: Session = Depends(get_db)):
    """新建训练周期"""
    if payload.end_date < payload.start_date:
        raise HTTPException(400, "end_date 必须 >= start_date")
    athlete = profile_store.get_or_create_athlete(db)
    plan = PlanPeriod(
        athlete_id=athlete.id,
        name=payload.name,
        period_type=payload.period_type,
        start_date=payload.start_date,
        end_date=payload.end_date,
        target_event=payload.target_event,
        weekly_hours_target=payload.weekly_hours_target,
        notes=payload.notes,
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    logger.info(f"计划创建: {plan.name} ({plan.start_date} ~ {plan.end_date})")
    return _serialize_plan(plan)


@router.get("/{plan_id}")
def get_plan(plan_id: int, db: Session = Depends(get_db)):
    """取单个计划详情(含计划课列表)"""
    plan = db.get(PlanPeriod, plan_id)
    if not plan:
        raise HTTPException(404, "计划不存在")
    result = _serialize_plan(plan)
    result["workouts"] = [_serialize_planned(w) for w in (plan.workouts or [])]
    return result


@router.patch("/{plan_id}")
def update_plan(plan_id: int, payload: PlanUpdate, db: Session = Depends(get_db)):
    """更新计划元信息"""
    plan = db.get(PlanPeriod, plan_id)
    if not plan:
        raise HTTPException(404, "计划不存在")
    for k, v in payload.model_dump(exclude_unset=True).items():
        setattr(plan, k, v)
    db.commit()
    db.refresh(plan)
    return _serialize_plan(plan)


@router.delete("/{plan_id}")
def delete_plan(plan_id: int, db: Session = Depends(get_db)):
    """删除计划

    行为:其下的 PlannedWorkout 不删除,只把 period_id 置 NULL
    (用户能保留历史计划课记录)。
    """
    plan = db.get(PlanPeriod, plan_id)
    if not plan:
        raise HTTPException(404, "计划不存在")
    # 先把关联的 planned 解绑
    from cycling_coach.data.sqlite.models import PlannedWorkout
    from sqlalchemy import update
    db.execute(
        update(PlannedWorkout)
        .where(PlannedWorkout.period_id == plan_id)
        .values(period_id=None)
    )
    db.delete(plan)
    db.commit()
    return {"ok": True, "id": plan_id, "kept_planned": True}


# ---------- Helpers (for calendar router) ----------

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
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }
