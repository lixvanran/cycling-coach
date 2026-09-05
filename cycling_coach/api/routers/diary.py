"""训练日记 API — V0.7.4.2

V0.8.0: 业务逻辑抽到 cycling_coach.core.services.DiaryService
        本文件只剩 router 端点 (薄)

端点:
- GET    /api/diary             最近 N 天日记 (默认 30)
- GET    /api/diary/{date}      某天日记
- POST   /api/diary             创建/更新 (upsert by date)
- DELETE /api/diary/{date}      删除
- GET    /api/diary/template    KB 训练日记模板 (从 KB 检索)
"""
from __future__ import annotations
import logging

from fastapi import APIRouter, Depends, Query

from cycling_coach.api.dependencies import Services, get_services
from cycling_coach.core.services.diary import DiaryIn

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/diary", tags=["diary"])


@router.get("")
def list_diary(
    days: int = Query(30, ge=1, le=365),
    svc: Services = Depends(get_services),
):
    """最近 N 天日记 (默认 30 天)"""
    return svc.diary.list_recent(days=days)


@router.get("/template")
def get_diary_template(svc: Services = Depends(get_services)):
    """KB 训练日记模板 (从训练百科 - 训练日记 文档)"""
    return svc.diary.get_template()


@router.get("/{date_str}")
def get_diary_by_date(
    date_str: str,
    svc: Services = Depends(get_services),
):
    """某天的日记 (YYYY-MM-DD)"""
    return svc.diary.get_by_date(date_str)


@router.post("")
def upsert_diary(
    req: DiaryIn,
    svc: Services = Depends(get_services),
):
    """创建或更新某天的日记 (upsert)"""
    return svc.diary.upsert(req)


@router.delete("/{date_str}")
def delete_diary(
    date_str: str,
    svc: Services = Depends(get_services),
):
    """删除某天的日记"""
    return svc.diary.delete_by_date(date_str)
