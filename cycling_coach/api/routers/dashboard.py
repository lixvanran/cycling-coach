"""/api/dashboard - 训练概览数据"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func

from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import Activity

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """训练总览(用于 Dashboard)"""
    total = db.query(Activity).count()
    if total == 0:
        return {
            "total_activities": 0,
            "total_distance_km": 0,
            "total_duration_h": 0,
            "total_tss": 0,
            "this_week": {"activities": 0, "distance_km": 0, "duration_h": 0, "tss": 0},
            "last_7_days": [],
        }

    # 全部统计
    activities = db.query(Activity).all()
    total_distance = sum((a.distance_m or 0) for a in activities) / 1000
    total_duration = sum(a.duration_s for a in activities) / 3600
    total_tss = sum((a.metrics or {}).get("tss", 0) or 0 for a in activities)

    # 本周
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    week_acts = [a for a in activities if a.start_time >= cutoff]
    week_stats = {
        "activities": len(week_acts),
        "distance_km": round(sum((a.distance_m or 0) for a in week_acts) / 1000, 1),
        "duration_h": round(sum(a.duration_s for a in week_acts) / 3600, 1),
        "tss": int(sum((a.metrics or {}).get("tss", 0) or 0 for a in week_acts)),
    }

    # 最近 7 天每日数据
    daily = []
    for i in range(6, -1, -1):
        day = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=i)).date()
        day_acts = [a for a in activities if a.start_time.date() == day]
        daily.append({
            "date": day.isoformat(),
            "tss": int(sum((a.metrics or {}).get("tss", 0) or 0 for a in day_acts)),
            "distance_km": round(sum((a.distance_m or 0) for a in day_acts) / 1000, 1),
            "duration_h": round(sum(a.duration_s for a in day_acts) / 3600, 1),
        })

    return {
        "total_activities": total,
        "total_distance_km": round(total_distance, 1),
        "total_duration_h": round(total_duration, 1),
        "total_tss": int(total_tss),
        "this_week": week_stats,
        "last_7_days": daily,
    }
