"""/api/athlete - 运动员画像"""
from __future__ import annotations
import logging
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import Activity
from cycling_coach.core.profile import store as profile_store, builder as profile_builder

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/athlete", tags=["athlete"])


class AthleteView(BaseModel):
    id: int
    name: str
    ftp: int | None
    ftp_estimated: int | None
    max_hr: int | None
    lthr: int | None
    weight_kg: float | None
    height_cm: float | None
    total_activities: int
    weekly_tss: int

    class Config:
        from_attributes = True


class AthleteUpdate(BaseModel):
    name: str | None = None
    ftp: int | None = None
    max_hr: int | None = None
    lthr: int | None = None
    weight_kg: float | None = None
    height_cm: float | None = None


@router.get("", response_model=AthleteView)
def get_athlete(db: Session = Depends(get_db)):
    a = profile_store.get_or_create_athlete(db)
    total = db.query(Activity).filter(Activity.athlete_id == a.id).count()
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    acts = db.query(Activity).filter(
        Activity.athlete_id == a.id, Activity.start_time >= cutoff
    ).all()
    weekly = sum((act.metrics or {}).get("tss", 0) or 0 for act in acts)
    return AthleteView(
        id=a.id, name=a.name, ftp=a.ftp, ftp_estimated=a.ftp_estimated,
        max_hr=a.max_hr, lthr=a.lthr, weight_kg=a.weight_kg, height_cm=a.height_cm,
        total_activities=total, weekly_tss=int(weekly),
    )


@router.patch("", response_model=AthleteView)
def update_athlete(req: AthleteUpdate, db: Session = Depends(get_db)):
    a = profile_store.get_or_create_athlete(db)
    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if fields:
        a = profile_store.update_athlete(db, a.id, **fields)
    # 重算估算
    a = profile_builder.refresh_athlete_profile(db, a.id)
    return get_athlete(db)


@router.post("/refresh-ftp")
def refresh_ftp(db: Session = Depends(get_db)):
    """根据历史活动重算 FTP 估算"""
    a = profile_store.get_or_create_athlete(db)
    a = profile_builder.refresh_athlete_profile(db, a.id)
    return {"ok": True, "ftp_estimated": a.ftp_estimated}
