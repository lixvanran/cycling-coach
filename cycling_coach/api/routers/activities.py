"""/api/activities - 训练管理

V0.8.0: 业务逻辑抽到 cycling_coach.core.services.ActivityService
        本文件只剩 router 端点 (薄, 共 ~150 行)
        异常统一走 AppError → main.py handler → JSON 响应
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, BackgroundTasks, Query
from fastapi.responses import Response
from pydantic import BaseModel

from cycling_coach.api.dependencies import Services, get_services
from cycling_coach.core.services.activity import (
    ActivityFilters, AnalyzeRequest, AnalyzeResponse, ActivityDetail,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/activities", tags=["activities"])


# ---------- API ----------


@router.post("/upload")
async def upload_activity(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    svc: Services = Depends(get_services),
):
    """上传 FIT/TCX/CSV 文件 → 解析 + 入库 + 异步生成 AI 报告"""
    if not file.filename:
        from cycling_coach.core.exceptions import ValidationError
        raise ValidationError("未提供文件名")
    # 读字节 (file.file 是 SpooledTemporaryFile, 读后 service 写盘)
    content = await file.read()
    return await svc.activity.upload(
        filename=file.filename,
        file_bytes=content,
        background_tasks=background_tasks,
    )


@router.get("")
def list_activities(
    date_from: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    min_distance_km: Optional[float] = Query(None, ge=0),
    max_distance_km: Optional[float] = Query(None, ge=0),
    min_tss: Optional[int] = Query(None, ge=0),
    max_tss: Optional[int] = Query(None, ge=0),
    min_normalized_power: Optional[int] = Query(None, ge=0),
    max_normalized_power: Optional[int] = Query(None, ge=0),
    min_avg_power: Optional[int] = Query(None, ge=0),
    max_avg_power: Optional[int] = Query(None, ge=0),
    min_duration_min: Optional[int] = Query(None, ge=0),
    max_duration_min: Optional[int] = Query(None, ge=0),
    min_avg_hr: Optional[int] = Query(None, ge=0),
    max_avg_hr: Optional[int] = Query(None, ge=0),
    source: Optional[str] = Query(None, description="fit/tcx/csv/mock"),
    has_report: Optional[bool] = Query(None, description="是否已生成 AI 报告"),
    sort: str = Query("start_time", description="排序字段"),
    order: str = Query("desc", description="asc/desc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    svc: Services = Depends(get_services),
):
    """活动列表(多维过滤 + 排序 + 分页 + 聚合)"""
    filters = ActivityFilters(
        date_from=date_from, date_to=date_to,
        min_distance_km=min_distance_km, max_distance_km=max_distance_km,
        min_tss=min_tss, max_tss=max_tss,
        min_normalized_power=min_normalized_power, max_normalized_power=max_normalized_power,
        min_avg_power=min_avg_power, max_avg_power=max_avg_power,
        min_duration_min=min_duration_min, max_duration_min=max_duration_min,
        min_avg_hr=min_avg_hr, max_avg_hr=max_avg_hr,
        source=source, has_report=has_report,
        sort=sort, order=order, limit=limit, offset=offset,
    )
    return svc.activity.list_activities(filters)


@router.get("/compare")
def compare_activities(
    ids: str = Query(..., description="活动 ID 列表, 逗号分隔, 如 1,2,3"),
    svc: Services = Depends(get_services),
):
    """多活动对比 (V0.6 GoldenCheetah 对标)"""
    return svc.activity.compare(ids)


@router.get("/{activity_id}", response_model=ActivityDetail)
def get_activity(
    activity_id: int,
    svc: Services = Depends(get_services),
):
    """活动详情(含 1Hz 样本 + AI 报告)"""
    return svc.activity.get_activity(activity_id)


@router.delete("/{activity_id}")
def delete_activity(
    activity_id: int,
    svc: Services = Depends(get_services),
):
    return svc.activity.delete_activity(activity_id)


@router.patch("/{activity_id}/rpe")
def update_rpe(
    activity_id: int,
    payload: dict,
    svc: Services = Depends(get_services),
):
    """更新 RPE 主观疲劳 (Borg CR-10, 1-10)"""
    return svc.activity.update_rpe(activity_id, payload)


@router.post("/{activity_id}/analyze", response_model=AnalyzeResponse)
def trigger_analyze(
    activity_id: int,
    req: AnalyzeRequest = AnalyzeRequest(),
    background_tasks: BackgroundTasks = None,
    svc: Services = Depends(get_services),
):
    """重新生成 AI 报告"""
    return svc.activity.trigger_analyze(activity_id, req, background_tasks)


# ---------- 分析端点 (分析活动详情, power / HR / CP) ----------

@router.get("/{activity_id}/power-curve")
def get_power_curve(
    activity_id: int,
    svc: Services = Depends(get_services),
):
    """功率曲线 (Mean Maximal Power / MMP)"""
    return svc.activity.get_power_curve(activity_id)


@router.get("/{activity_id}/power-zones-detailed")
def get_power_zones_detailed(
    activity_id: int,
    ftp: Optional[int] = Query(None, description="FTP (W), 不传则用 athlete profile"),
    svc: Services = Depends(get_services),
):
    """Coggan 7 区分布详细分析 (V0.6 GoldenCheetah 对标)"""
    return svc.activity.get_power_zones_detailed(activity_id, ftp=ftp)


@router.get("/{activity_id}/wbal")
def get_wbal(
    activity_id: int,
    cp: Optional[int] = Query(None, description="Critical Power (W), 不传则估算"),
    w_prime: Optional[int] = Query(20000, description="W' (J), 默认 20 kJ"),
    svc: Services = Depends(get_services),
):
    """W'bal 详细分析 (V0.6 GoldenCheetah 对标, Skiba 模型)"""
    return svc.activity.get_wbal(activity_id, cp=cp, w_prime=w_prime or 20000)


@router.get("/{activity_id}/decoupling")
def get_decoupling(
    activity_id: int,
    svc: Services = Depends(get_services),
):
    """Pa:HR Decoupling (V0.6.1 — GC 杀手锏)"""
    return svc.activity.get_decoupling(activity_id)


@router.get("/{activity_id}/cp-estimate")
def get_cp_estimate(
    activity_id: int,
    svc: Services = Depends(get_services),
):
    """CP 3 参数自动估算 (V0.6 GoldenCheetah 对标)"""
    return svc.activity.get_cp_estimate(activity_id)
