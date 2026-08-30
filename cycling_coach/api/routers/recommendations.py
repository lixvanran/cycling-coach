"""V0.7.3: AI 训练建议 API

端点:
- GET /api/recommendations/today    今日建议
- GET /api/recommendations/readiness    只看 readiness 分数
"""
from __future__ import annotations
import logging
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.coaching.recommendations import (
    generate_recommendations,
    compute_readiness,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


@router.get("/today")
def get_today_recommendations(db: Session = Depends(get_db)):
    """V0.7.3: 今日综合训练建议
    
    综合 5 维数据 (HRV 30 + ACWR 25 + TSB 20 + Phase 15 + RPE 7d 10) = 100 分
    返回 readiness + 今日推荐类型 + 触发建议列表
    """
    athlete = profile_store.get_or_create_athlete(db)
    rec = generate_recommendations(db, athlete.id)
    return {
        "date": rec.date,
        "readiness_score": rec.readiness_score,
        "readiness_label": rec.readiness_label,
        "recommended_workout_type": rec.recommended_workout_type,
        "recommended_intensity": rec.recommended_intensity,
        "target_tss": rec.target_tss,
        "recommendations": [
            {
                "category": r.category,
                "priority": r.priority,
                "title": r.title,
                "detail": r.detail,
                "action": r.action,
                "icon": r.icon,
            }
            for r in rec.recommendations
        ],
        "warnings": rec.warnings,
        "signals_summary": rec.signals_summary,
    }


@router.get("/readiness")
def get_readiness_only(db: Session = Depends(get_db)):
    """V0.7.3: 只看 readiness 分数 + 5 维拆分"""
    athlete = profile_store.get_or_create_athlete(db)
    score, breakdown = compute_readiness(db, athlete.id)
    return {
        "readiness_score": score,
        "breakdown": breakdown,
        "weights": {
            "hrv": 30,
            "acwr": 25,
            "tsb": 20,
            "phase": 15,
            "rpe": 10,
        },
    }
