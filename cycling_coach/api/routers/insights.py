"""自动训练洞察 API — V0.7

借鉴:
- Joe Friel Weekly Review (6 项检查)
- Tim Gabbett 训练负荷管理
- ACMS 过度训练综合征标准
- Seiler 80/20 极化分布

端点:
- GET /api/insights/today       今日所有洞察 (按严重度)
- GET /api/insights/weekly      周复盘 (Friel 6 项)
"""
from __future__ import annotations
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.metrics.insights import compute_today_insights, compute_weekly_review

router = APIRouter(prefix="/api/insights", tags=["insights"])


@router.get("/today")
def today_insights(db: Session = Depends(get_db)):
    """今日所有训练洞察 (按严重度排序)

    借鉴 Friel Weekly Review + Gabbett 训练负荷管理
    6 大维度:
    - 训练负荷 (ramp / 不足 / 过训)
    - 身体状态 (RPE)
    - 强度分布 (Seiler 80/20)
    - 比赛准备度
    - FTP 测试建议
    - 周期阶段一致性
    """
    athlete = profile_store.get_or_create_athlete(db)
    bundle = compute_today_insights(db, athlete.id)
    return {
        "generated_at": bundle.generated_at,
        "athlete_id": bundle.athlete_id,
        "summary": bundle.summary,
        "pcm": bundle.pcm,
        "insights": [i.to_dict() for i in bundle.insights],
    }


@router.get("/weekly")
def weekly_review(db: Session = Depends(get_db)):
    """周复盘 (Friel Weekly Review 6 项)

    1. 本周目标完成情况 (TSS / km / h)
    2. 强度分布 (Z1-Z7 占比)
    3. 关键训练完成情况
    4. 身体反馈 (RPE 趋势)
    5. 跟上周对比 (进步 / 退步)
    6. 下周计划建议
    """
    athlete = profile_store.get_or_create_athlete(db)
    return compute_weekly_review(db, athlete.id)
