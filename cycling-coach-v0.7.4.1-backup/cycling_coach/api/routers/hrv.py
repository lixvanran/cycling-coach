"""HRV 趋势 API — V0.7.2 新加

端点:
- GET  /api/hrv/state         HRV 状态评估
- GET  /api/hrv/series       最近 30d HRV 序列
- POST /api/hrv/today         录入今日 HRV
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.metrics.hrv import (
    compute_hrv_state,
    get_hrv_series,
    record_hrv_today,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/hrv", tags=["hrv"])


class HRVRecord(BaseModel):
    hrv_ms: float = Field(..., ge=10, le=200, description="RMSSD 毫秒 (10-200 范围)")
    sleep_h: float | None = Field(None, ge=0, le=24, description="睡眠时长 (小时)")


@router.get("/state")
def get_hrv_state(db: Session = Depends(get_db)):
    """HRV 状态评估 (借鉴 Plews 2013, Bellenger 2016)

    状态:
    - ok: HRV 接近 baseline
    - caution: HRV < baseline - 10ms (注意)
    - warning: 连续 3d+ 低于 baseline - 10ms (警告, 需降量)
    - insufficient_data: 数据不足 (< 3d)
    """
    athlete = profile_store.get_or_create_athlete(db)
    return compute_hrv_state(db, athlete.id)


@router.get("/series")
def get_hrv_series_endpoint(days: int = 30, db: Session = Depends(get_db)):
    """最近 N 天 HRV 数据序列"""
    athlete = profile_store.get_or_create_athlete(db)
    return {"series": get_hrv_series(db, athlete.id, days=days)}


@router.post("/today")
def post_hrv_today(req: HRVRecord, db: Session = Depends(get_db)):
    """录入今日晨起 HRV (RMSSD 毫秒)

    训练学: 晨起静息测量最准 (躺着, 起床前)
    """
    athlete = profile_store.get_or_create_athlete(db)
    result = record_hrv_today(db, athlete.id, req.hrv_ms, req.sleep_h)
    # 录入后返回新状态
    state = compute_hrv_state(db, athlete.id)
    return {
        "ok": True,
        "recorded": result,
        "state": state,
    }
