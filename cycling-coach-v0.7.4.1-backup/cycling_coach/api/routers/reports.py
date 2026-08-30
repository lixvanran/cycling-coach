"""V0.7.3: 周报 PDF API

端点:
- GET /api/reports/weekly?days=7  下载 PDF
"""
from __future__ import annotations
import logging
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.reports.weekly import generate_weekly_report

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/weekly")
def get_weekly_report(
    days: int = Query(7, ge=1, le=90, description="回看天数 (1-90)"),
    db: Session = Depends(get_db),
):
    """V0.7.3: 生成周报 PDF (训练学综合报告)
    
    借鉴 TrainingPeaks Weekly Summary + WKO5 Weekly Review
    
    包含:
    - Readiness 大数字 + 5 维拆解
    - PMC 状态 (CTL/ATL/TSB)
    - HRV 状态
    - 周期化阶段
    - 触发建议
    - 活动明细表
    - 学术引用
    """
    athlete = profile_store.get_or_create_athlete(db)
    pdf_bytes = generate_weekly_report(db, athlete.id, days=days)
    
    today = datetime.utcnow().date().isoformat()
    filename = f"cycling-coach-weekly-{today}-d{days}.pdf"
    
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
