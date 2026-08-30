"""/api/pmc — Performance Management Chart 路由

- GET /api/pmc?days=90  → 时间序列
- GET /api/pmc/today    → 今日状态卡
- POST /api/pmc/rebuild → 强制全量重算
"""
from __future__ import annotations
import logging
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.pmc import get_pmc_series, get_pmc_today, recompute_pmc
from cycling_coach.data.sqlite import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/pmc", tags=["pmc"])


@router.get("")
def get_pmc(
    days: int = Query(90, ge=7, le=730, description="回溯天数"),
    db: Session = Depends(get_db),
):
    """取最近 N 天 PMC 时间序列(默认 90)"""
    athlete = profile_store.get_or_create_athlete(db)
    series = get_pmc_series(db, athlete.id, days=days)
    return {
        "athlete_id": athlete.id,
        "days": days,
        "series": series,
    }


@router.get("/today")
def get_today(db: Session = Depends(get_db)):
    """今日状态卡:CTL/ATL/TSB + ramp_rate + 自动分类的状态码"""
    athlete = profile_store.get_or_create_athlete(db)
    return get_pmc_today(db, athlete.id)


@router.post("/rebuild")
def rebuild(db: Session = Depends(get_db)):
    """强制全量重算(首次/数据异常时用)"""
    athlete = profile_store.get_or_create_athlete(db)
    updated = recompute_pmc(db, athlete.id)
    return {
        "ok": True,
        "athlete_id": athlete.id,
        "updated_rows": updated,
    }
