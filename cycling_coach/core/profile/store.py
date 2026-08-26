"""个体画像存储 / 读取

MVP:单用户,只维护一个 athlete;FTP / max_hr 是核心字段
"""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Athlete, Activity

logger = logging.getLogger(__name__)


def get_or_create_athlete(db: Session) -> Athlete:
    """MVP:始终返回第 1 个 athlete(没有就建)"""
    a = db.query(Athlete).first()
    if a is None:
        a = Athlete(name="Rider", ftp=250, max_hr=185)
        db.add(a)
        db.commit()
        db.refresh(a)
        logger.info(f"创建默认 athlete: id={a.id}, ftp={a.ftp}")
    return a


def update_athlete(
    db: Session, athlete_id: int, **fields
) -> Athlete:
    a = db.query(Athlete).get(athlete_id)
    if not a:
        raise ValueError(f"athlete {athlete_id} not found")
    for k, v in fields.items():
        if hasattr(a, k):
            setattr(a, k, v)
    db.commit()
    db.refresh(a)
    logger.info(f"更新 athlete {athlete_id}: {fields}")
    return a


def get_training_history(
    db: Session, athlete_id: int, limit: int = 30
) -> list[Activity]:
    """最近的训练(用于画像聚合)"""
    return (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .order_by(Activity.start_time.desc())
        .limit(limit)
        .all()
    )
