"""V0.8.0: 训练计划/课程/阶段业务层 (P1 — 简版)

覆盖域:
- plans: 训练周期 (PlanPeriod)
- workouts: 训练课程库 (Workout) + 排课 (PlannedWorkout)
- phases: 阶段 (Phase)

V0.8.0 范围: 把 P1 router 的关键 CRUD 抽到 service, 包含异常替换
P2 深入的复杂操作后续版本再做
"""
from __future__ import annotations
import logging
from datetime import date as _date
from typing import Optional, List

from pydantic import BaseModel, Field
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session

from cycling_coach.core.exceptions import NotFoundError, ValidationError
from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite.models import PlanPeriod, PlannedWorkout, Workout, TrainingPhase

logger = logging.getLogger(__name__)


# ============== DTO ==============

class StepIn(BaseModel):
    kind: str = "main"
    duration_s: int = Field(..., ge=10, le=36000)
    power_pct_ftp: Optional[int] = Field(None, ge=0, le=300)
    hr_pct_lthr: Optional[int] = Field(None, ge=0, le=200)
    cadence_rpm: Optional[int] = Field(None, ge=0, le=200)
    label: Optional[str] = None
    repeat: int = 1


class PlanCreate(BaseModel):
    name: str = Field(..., max_length=128)
    period_type: str = Field("base", max_length=32)
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


class WorkoutCreate(BaseModel):
    title: str = Field(..., max_length=128)
    goal: str = "endurance"
    intensity: Optional[str] = None
    duration_min: int = Field(..., ge=5, le=600)
    structure: list[StepIn] = []
    tags: list[str] = []
    description: Optional[str] = None
    is_template: bool = True


class WorkoutUpdate(BaseModel):
    title: Optional[str] = None
    goal: Optional[str] = None
    intensity: Optional[str] = None
    duration_min: Optional[int] = Field(None, ge=5, le=600)
    structure: Optional[list[StepIn]] = None
    tags: Optional[list[str]] = None
    description: Optional[str] = None
    is_template: Optional[bool] = None


# ============== Service ==============

class TrainingService:
    """训练计划 + 课程库 + 阶段服务

    V0.8.0 P1: 核心 CRUD 抽到 service, P2 深入在后续版本
    """
    def __init__(self, db: Session):
        self.db = db

    # ---------- Plans ----------

    def list_plans(self) -> list:
        athlete = profile_store.get_or_create_athlete(self.db)
        rows = (
            self.db.query(PlanPeriod)
            .filter(PlanPeriod.athlete_id == athlete.id)
            .order_by(PlanPeriod.start_date.desc())
            .all()
        )
        return [_serialize_plan(p) for p in rows]

    def create_plan(self, req: PlanCreate) -> dict:
        athlete = profile_store.get_or_create_athlete(self.db)
        if req.end_date < req.start_date:
            raise ValidationError("end_date 不能早于 start_date")
        p = PlanPeriod(
            athlete_id=athlete.id,
            name=req.name,
            period_type=req.period_type,
            start_date=req.start_date,
            end_date=req.end_date,
            target_event=req.target_event,
            weekly_hours_target=req.weekly_hours_target,
            notes=req.notes,
        )
        self.db.add(p)
        self.db.commit()
        self.db.refresh(p)
        return _serialize_plan(p)

    def get_plan(self, plan_id: int) -> dict:
        p = self.db.get(PlanPeriod, plan_id)
        if not p:
            raise NotFoundError(f"训练计划 {plan_id} 不存在")
        return _serialize_plan(p)

    def update_plan(self, plan_id: int, req: PlanUpdate) -> dict:
        p = self.db.get(PlanPeriod, plan_id)
        if not p:
            raise NotFoundError(f"训练计划 {plan_id} 不存在")
        payload = req.model_dump(exclude_unset=True)
        for k, v in payload.items():
            if hasattr(p, k):
                setattr(p, k, v)
        self.db.commit()
        self.db.refresh(p)
        return _serialize_plan(p)

    def delete_plan(self, plan_id: int) -> dict:
        p = self.db.get(PlanPeriod, plan_id)
        if not p:
            raise NotFoundError(f"训练计划 {plan_id} 不存在")
        self.db.delete(p)
        self.db.commit()
        return {"ok": True, "id": plan_id}

    # ---------- Workouts (Library) ----------

    def list_workouts(
        self,
        scope: str = "all",
        goal: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        """列出课程

        scope: all / system / user
        """
        athlete = profile_store.get_or_create_athlete(self.db)
        q = self.db.query(Workout)
        if scope == "system":
            q = q.filter(Workout.athlete_id.is_(None))
        elif scope == "user":
            q = q.filter(Workout.athlete_id == athlete.id)
        else:
            q = q.filter(or_(Workout.athlete_id.is_(None), Workout.athlete_id == athlete.id))
        if goal:
            q = q.filter(Workout.goal == goal)
        total = q.count()
        rows = q.order_by(Workout.created_at.desc()).offset(offset).limit(limit).all()
        return {
            "items": [_serialize_workout(w) for w in rows],
            "total": total,
            "offset": offset,
            "limit": limit,
        }

    def get_workout(self, workout_id: int) -> dict:
        w = self.db.get(Workout, workout_id)
        if not w:
            raise NotFoundError(f"课程 {workout_id} 不存在")
        return _serialize_workout(w)

    def create_workout(self, req: WorkoutCreate) -> dict:
        athlete = profile_store.get_or_create_athlete(self.db)
        w = Workout(
            athlete_id=athlete.id,
            title=req.title,
            goal=req.goal,
            intensity=req.intensity,
            duration_min=req.duration_min,
            structure=[s.model_dump() for s in req.structure],
            tags=req.tags,
            description=req.description,
            is_template=req.is_template,
            source="user",
        )
        self.db.add(w)
        self.db.commit()
        self.db.refresh(w)
        return _serialize_workout(w)

    def update_workout(self, workout_id: int, req: WorkoutUpdate) -> dict:
        w = self.db.get(Workout, workout_id)
        if not w:
            raise NotFoundError(f"课程 {workout_id} 不存在")
        payload = req.model_dump(exclude_unset=True)
        if "structure" in payload and payload["structure"] is not None:
            payload["structure"] = [
                s.model_dump() if hasattr(s, "model_dump") else s
                for s in payload["structure"]
            ]
        for k, v in payload.items():
            if hasattr(w, k):
                setattr(w, k, v)
        self.db.commit()
        self.db.refresh(w)
        return _serialize_workout(w)

    def delete_workout(self, workout_id: int) -> dict:
        w = self.db.get(Workout, workout_id)
        if not w:
            raise NotFoundError(f"课程 {workout_id} 不存在")
        if w.source == "system":
            raise ValidationError("系统课程不能删除, 可复制为自定义课程")
        self.db.delete(w)
        self.db.commit()
        return {"ok": True, "id": workout_id}

    # ---------- Phases (基础 CRUD, 完整逻辑后续版本) ----------

    def list_phases(self, limit: int = 50) -> list:
        athlete = profile_store.get_or_create_athlete(self.db)
        rows = (
            self.db.query(TrainingPhase)
            .filter(TrainingPhase.athlete_id == athlete.id)
            .order_by(TrainingPhase.start_date.desc())
            .limit(limit)
            .all()
        )
        return [_serialize_phase(p) for p in rows]


# ============== helpers ==============

def _serialize_plan(p: PlanPeriod) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "period_type": p.period_type,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "target_event": p.target_event,
        "weekly_hours_target": p.weekly_hours_target,
        "notes": p.notes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serialize_workout(w: Workout) -> dict:
    return {
        "id": w.id,
        "title": w.title,
        "goal": w.goal,
        "intensity": w.intensity,
        "duration_min": w.duration_min,
        "structure": w.structure or [],
        "tags": w.tags or [],
        "description": w.description,
        "is_template": w.is_template,
        "source": w.source,
        "athlete_id": w.athlete_id,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


def _serialize_phase(p: TrainingPhase) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "phase_type": p.phase_type,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "notes": getattr(p, "notes", None),
    }
