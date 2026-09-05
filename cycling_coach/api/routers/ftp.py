"""FTP 测试管理 API — V0.6.1

V0.8.0: 业务逻辑抽到 cycling_coach.core.services.FTPService
        本文件只剩 router 端点 (薄)

端点:
- POST /api/ftp/test            从活动估算 + 录入
- GET  /api/ftp/history         历史记录
- GET  /api/ftp/recommend       推荐下次测试时间
- GET  /api/ftp/methods         方法说明
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from cycling_coach.api.dependencies import Services, get_services
from cycling_coach.core.services.ftp import (
    EstimateRequest, RecordFTPTest, FTPTestOut,
)

router = APIRouter(prefix="/api/ftp", tags=["ftp"])


# ---------- 端点 ----------

@router.get("/methods")
def get_methods(svc: Services = Depends(get_services)):
    return svc.ftp.get_methods()


@router.post("/estimate")
def estimate_from_activity(
    req: EstimateRequest,
    svc: Services = Depends(get_services),
):
    """从已上传的活动估算 FTP (不录入, 试用)"""
    return svc.ftp.estimate_from_activity(req)


@router.post("/test", response_model=FTPTestOut)
def record_ftp_test(
    payload: RecordFTPTest,
    svc: Services = Depends(get_services),
):
    """录入一次 FTP 测试结果"""
    return svc.ftp.record_test(payload)


@router.get("/history", response_model=list[FTPTestOut])
def list_history(
    days: int = 365,
    svc: Services = Depends(get_services),
):
    """FTP 测试历史"""
    return svc.ftp.list_history(days=days)


@router.get("/recommend")
def recommend_next_test(
    svc: Services = Depends(get_services),
):
    """推荐下次测试时间"""
    return svc.ftp.recommend_next_test()


@router.delete("/test/{test_id}")
def delete_test(
    test_id: int,
    svc: Services = Depends(get_services),
):
    return svc.ftp.delete_test(test_id)
