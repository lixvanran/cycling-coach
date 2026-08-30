"""比赛准备 + 5 维雷达 — V0.7 补遗漏

端点:
- GET /api/race-prep/types          所有比赛类型
- GET /api/race-prep/tsb-target     TSB 目标 + taper 倒推
- GET /api/race-prep/training-state 5 维训练状态 (雷达)
"""
from __future__ import annotations
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.metrics.race_prep import (
    RACE_TYPES, get_race_type, compute_tsb_target, compute_training_state,
)
from cycling_coach.core.pmc import get_pmc_today

router = APIRouter(prefix="/api/race-prep", tags=["race-prep"])


@router.get("/types")
def get_race_types():
    """所有比赛类型 + 训练学参数 (TSB 目标, taper 比例)"""
    out = {}
    for code, rt in RACE_TYPES.items():
        out[code] = {
            "code": rt.code,
            "label": rt.label,
            "label_en": rt.label_en,
            "duration_h": rt.duration_h,
            "tsb_target": [rt.tsb_target_min, rt.tsb_target_max],
            "taper": {
                "short": {"days": rt.taper_days_short, "reduction_pct": rt.taper_reduction_short},
                "long": {"days": rt.taper_days_long, "reduction_pct": rt.taper_reduction_long},
            },
            "description": rt.description,
            "notes": rt.notes,
        }
    return {"types": out}


@router.get("/tsb-target")
def get_tsb_target(
    race_date: str = Query(..., description="YYYY-MM-DD"),
    race_type: str = Query("road_race"),
    db: Session = Depends(get_db),
):
    """比赛日 TSB 目标 + 倒推 weekly TSS 计划

    借鉴: Friel + Le Meur + Bosquet 2007 meta-analysis
    """
    if race_type not in RACE_TYPES:
        raise HTTPException(400, f"race_type 必须是 {list(RACE_TYPES.keys())}")
    try:
        rd = datetime.fromisoformat(race_date)
    except ValueError:
        raise HTTPException(400, f"race_date 格式错误: {race_date}, 需 YYYY-MM-DD")

    athlete = profile_store.get_or_create_athlete(db)
    pcm = get_pmc_today(db, athlete.id)
    current_ctl = pcm.get("ctl", 60) or 60

    target = compute_tsb_target(rd, race_type, current_ctl=current_ctl)
    rt = get_race_type(race_type)
    return {
        "race_date": race_date,
        "race_type": rt.code,
        "race_type_label": rt.label,
        "tsb_target": [target.tsb_target_min, target.tsb_target_max],
        "taper_days": target.taper_days,
        "taper_reduction_pct": target.taper_reduction_pct,
        "description": target.description,
        "notes": target.notes,
        "weekly_plan": target.weekly_tss_plan,
        "current_ctl": round(current_ctl, 1),
    }


@router.get("/training-state")
def get_training_state(db: Session = Depends(get_db)):
    """5 维训练状态雷达 (借鉴 Friel Form Chart)

    5 维 (0-100):
    - Fitness: 体能 (CTL 归一化)
    - Fatigue: 恢复 (ATL 反向, 越高越 fresh)
    - Form: 状态 (TSB 归一化)
    - Rhythm: 节奏 (ramp_rate 归一化)
    - Recovery: 反馈 (RPE 7d 均值反向)
    """
    athlete = profile_store.get_or_create_athlete(db)
    state = compute_training_state(db, athlete.id)
    return {
        "dimensions": {
            "fitness": state.fitness,
            "fatigue": state.fatigue,
            "form": state.form,
            "rhythm": state.rhythm,
            "recovery": state.recovery,
        },
        "overall": state.overall,
        "interpretation": state.interpretation,
        "source": state.source,
    }
