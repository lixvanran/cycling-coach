"""/api/dashboard - 训练概览数据"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, Float

from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import Activity
from cycling_coach.core.profile import store as profile_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    """训练总览(用于 Dashboard)"""
    # V0.7.5.2 改: SQL 聚合, 不再 db.query().all() 拉全表 (DEV-5)
    athlete_id = profile_store.get_or_create_athlete(db).id
    base_q = db.query(Activity).filter(Activity.athlete_id == athlete_id)

    # 全部统计 (用 SQL 函数)
    agg_row = base_q.with_entities(
        func.count(Activity.id),
        func.coalesce(func.sum(Activity.distance_m), 0),
        func.coalesce(func.sum(Activity.duration_s), 0),
    ).first()
    total, total_distance_m, total_duration_s = agg_row or (0, 0, 0)
    total_distance_km = round((total_distance_m or 0) / 1000, 1)
    total_duration_h = round((total_duration_s or 0) / 3600, 1)
    # TSS 在 metrics JSON 里, 用 json_extract
    total_tss = base_q.with_entities(
        func.coalesce(
            func.sum(
                func.cast(func.json_extract(Activity.metrics, "$.tss"), Float)
            ),
            0,
        )
    ).scalar() or 0

    if total == 0:
        return {
            "total_activities": 0,
            "total_distance_km": 0,
            "total_duration_h": 0,
            "total_tss": 0,
            "this_week": {"activities": 0, "distance_km": 0, "duration_h": 0, "tss": 0},
            "last_7_days": [],
        }

    # 本周 (SQL 聚合)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    week_row = base_q.filter(Activity.start_time >= cutoff).with_entities(
        func.count(Activity.id),
        func.coalesce(func.sum(Activity.distance_m), 0),
        func.coalesce(func.sum(Activity.duration_s), 0),
        func.coalesce(
            func.sum(func.cast(func.json_extract(Activity.metrics, "$.tss"), Float)),
            0,
        ),
    ).first()
    week_count, week_dist, week_dur, week_tss = week_row or (0, 0, 0, 0)
    week_stats = {
        "activities": week_count or 0,
        "distance_km": round((week_dist or 0) / 1000, 1),
        "duration_h": round((week_dur or 0) / 3600, 1),
        "tss": int(week_tss or 0),
    }

    # 最近 7 天每日 (SQL 聚合 + GROUP BY)
    daily_start = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=6)).date()
    daily_rows = base_q.filter(Activity.start_time >= daily_start).with_entities(
        func.date(Activity.start_time).label("d"),
        func.coalesce(func.sum(Activity.distance_m), 0),
        func.coalesce(func.sum(Activity.duration_s), 0),
        func.coalesce(
            func.sum(func.cast(func.json_extract(Activity.metrics, "$.tss"), Float)),
            0,
        ),
    ).group_by(func.date(Activity.start_time)).all()
    by_day = {str(r[0]): r for r in daily_rows}
    daily = []
    for i in range(6, -1, -1):
        day = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=i)).date()
        r = by_day.get(day.isoformat())
        if r:
            _, dm, ds, tss = r
        else:
            dm, ds, tss = 0, 0, 0
        daily.append({
            "date": day.isoformat(),
            "tss": int(tss or 0),
            "distance_km": round((dm or 0) / 1000, 1),
            "duration_h": round((ds or 0) / 3600, 1),
        })

    return {
        "total_activities": total or 0,
        "total_distance_km": total_distance_km,
        "total_duration_h": total_duration_h,
        "total_tss": int(total_tss),
        "this_week": week_stats,
        "last_7_days": daily,
    }
