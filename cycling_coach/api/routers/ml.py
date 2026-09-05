"""/api/ml/* V0.7.6+: ML 推理端点

端点:
- POST /api/ml/predict/ftp    预测当前 FTP (20 维特征, 接 ftp-predictor 真模型 + Conformal)
- GET  /api/ml/models         列出已注册模型
- POST /api/ml/models/register 注册新模型
- POST /api/ml/models/activate 切换激活模型
- GET  /api/ml/predictions    列出最近预测

V0.8.0 升级:
- 12 维 → 20 维特征 (对齐 lixvanran/ftp-predictor)
- 接 Conformal 校准区间 (q_models[0.1, 0.5, 0.9] + conformal_quantile)
- 模型加载失败的 graceful fallback: 没注册 → mock, 特征不匹配 → 400
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import (
    Activity,
    DailyMetric,
    MLPrediction,
    MLModelMeta,
)
from cycling_coach.core.ml import (
    build_feature_row,
    get_active_model,
    ModelNotFoundError,
    FeatureSchemaMismatchError,
    MockFTPModel,
    FEATURE_SCHEMA,
    FEATURE_COLUMNS,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ml", tags=["ml"])


# ============================================================
# Pydantic schemas
# ============================================================

class FTPPredictRequest(BaseModel):
    activity_id: Optional[int] = Field(None, description="基于哪个活动预测, 留空用 14d 窗口聚合")
    model_version: Optional[str] = Field(None, description="指定模型版本, 留空用 active")
    window_days: Optional[int] = Field(None, description="特征聚合窗口天数, 默认 14")


class FTPPredictResponse(BaseModel):
    ok: bool
    predicted_ftp: float
    lower_80: float
    upper_80: float
    confidence: str  # "high" / "medium" / "low"
    current_ftp: Optional[int] = None
    delta: Optional[int] = None
    data_window: str = "14d 窗口聚合"
    model_name: str
    model_version: str
    model_format: str
    model_has_conformal: bool = False
    feature_count: int = 20
    prediction_id: int
    inference_ms: int


class RegisterModelRequest(BaseModel):
    task_name: str
    version: str
    model_path: str
    model_format: str
    training_date: Optional[str] = None
    training_samples_count: Optional[int] = None
    training_metrics: Optional[dict] = None
    feature_schema: Optional[dict] = None
    feature_columns: Optional[list] = None
    is_active: bool = False
    notes: Optional[str] = None


class ActivateModelRequest(BaseModel):
    task_name: str
    version: str


# ============================================================
# 端点
# ============================================================

@router.post("/predict/ftp", response_model=FTPPredictResponse)
def predict_ftp(req: FTPPredictRequest, db: Session = Depends(get_db)):
    """基于近期训练数据预测当前 FTP

    V0.8.0 流程:
    1. 从 build_feature_row 拿 20 维特征 (14d 窗口聚合 或 单活动)
    2. 加载激活的 ftp_predictor 模型 (joblib + 可选 Conformal)
    3. 推理 → 80% 区间 (真模型用 Conformal, mock 降级 ±10W)
    4. 落库到 ml_predictions
    """
    start = time.time()
    athlete = profile_store.get_or_create_athlete(db)

    # 1) 特征 (20 维, 对齐 ftp-predictor)
    try:
        if req.activity_id is not None:
            values, columns = build_feature_row(db, athlete.id, activity_id=req.activity_id)
            data_window = f"单活动 #{req.activity_id}"
        else:
            kwargs = {}
            if req.window_days:
                kwargs["window_days"] = req.window_days
            values, columns = build_feature_row(db, athlete.id, **kwargs)
            data_window = f"{req.window_days or 14}d 窗口聚合"
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"数据不足: {e}")

    # 验证特征维度跟 schema 一致
    if len(values) != len(FEATURE_COLUMNS):
        raise HTTPException(
            status_code=500,
            detail=f"特征维度异常: 拿到 {len(values)}, 期望 {len(FEATURE_COLUMNS)}",
        )

    # 2) 加载模型 (失败时降级 mock)
    model_has_conformal = False
    try:
        handle = get_active_model("ftp_predictor", version=req.model_version)
        X = np.array([values], dtype=np.float32)
        point, lower, upper = handle.predict_interval(X, coverage=0.8)
        model_name = handle.name
        model_version = handle.version
        model_format = handle.model_format
        model_has_conformal = handle.has_conformal()
    except ModelNotFoundError as e:
        # 没注册模型 → mock 降级 (开发体验)
        logger.warning(f"ML 模型未注册, 降级 MockFTPModel: {e}")
        mock = MockFTPModel(base_ftp=athlete.ftp or 250)
        X = np.array([values], dtype=np.float32)
        point = float(mock.predict(X)[0])
        half = 10.0
        lower, upper = point - half, point + half
        model_name = "ftp_predictor"
        model_version = "mock-v0"
        model_format = "mock"
    except FeatureSchemaMismatchError as e:
        # 模型跟特征不匹配, 报 400 (拒预测, 不假装)
        logger.error(f"特征 schema 不匹配: {e}")
        raise HTTPException(status_code=400, detail=f"特征 schema 不匹配: {e}")

    # 3) 置信度 (基于活动历史数量)
    n_activities = (
        db.query(Activity).filter(Activity.athlete_id == athlete.id).count()
    )
    if n_activities >= 60:
        confidence = "high"
    elif n_activities >= 14:
        confidence = "medium"
    else:
        confidence = "low"

    # 4) delta
    current_ftp = athlete.ftp
    delta = int(round(point - current_ftp)) if current_ftp else None

    # 5) 落库
    elapsed_ms = int((time.time() - start) * 1000)
    pred = MLPrediction(
        athlete_id=athlete.id,
        model_name=model_name,
        model_version=model_version,
        model_format=model_format,
        target="ftp_w",
        predicted_value=point,
        lower_80=lower,
        upper_80=upper,
        confidence_label=confidence,
        feature_snapshot={"columns": columns, "values": values},
        activity_id=req.activity_id,
        inference_ms=elapsed_ms,
    )
    db.add(pred)
    db.commit()
    db.refresh(pred)

    return FTPPredictResponse(
        ok=True,
        predicted_ftp=round(point, 1),
        lower_80=round(lower, 1),
        upper_80=round(upper, 1),
        confidence=confidence,
        current_ftp=current_ftp,
        delta=delta,
        data_window=data_window,
        model_name=model_name,
        model_version=model_version,
        model_format=model_format,
        model_has_conformal=model_has_conformal,
        feature_count=len(values),
        prediction_id=pred.id,
        inference_ms=elapsed_ms,
    )


@router.get("/models")
def list_models(db: Session = Depends(get_db)):
    """列出已注册的 ML 模型"""
    rows = (
        db.query(MLModelMeta)
        .order_by(MLModelMeta.task_name, MLModelMeta.version)
        .all()
    )
    return {
        "ok": True,
        "models": [
            {
                "id": r.id,
                "task_name": r.task_name,
                "version": r.version,
                "format": r.model_format,
                "model_path": r.model_path,
                "training_date": r.training_date.isoformat() if r.training_date else None,
                "training_samples_count": r.training_samples_count,
                "training_metrics": r.training_metrics,
                "is_active": r.is_active,
                "notes": r.notes,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }


@router.post("/models/register")
def register_model(req: RegisterModelRequest, db: Session = Depends(get_db)):
    """注册一个新模型到 MLModelMeta

    V0.8.0 升级:
    - 默认 feature_columns / feature_schema 用 20 维 FEATURE_COLUMNS
    - 可传 feature_columns 自定义 (必须跟模型对齐)
    """
    # 如果 is_active=True, 把同 task 的其他置 False (单激活)
    if req.is_active:
        db.query(MLModelMeta).filter(
            MLModelMeta.task_name == req.task_name
        ).update({"is_active": False})
        db.commit()
    feature_cols = req.feature_columns or FEATURE_COLUMNS
    feature_schema = req.feature_schema or FEATURE_SCHEMA
    m = MLModelMeta(
        task_name=req.task_name,
        version=req.version,
        model_path=req.model_path,
        model_format=req.model_format,
        training_date=datetime.now(timezone.utc).replace(tzinfo=None),
        training_samples_count=req.training_samples_count,
        training_metrics=req.training_metrics,
        feature_schema=feature_schema,
        feature_columns=feature_cols,
        is_active=req.is_active,
        notes=req.notes,
    )
    db.add(m)
    db.commit()
    db.refresh(m)
    return {"ok": True, "id": m.id, "is_active": m.is_active, "feature_count": len(feature_cols)}


@router.post("/models/activate")
def activate_model(req: ActivateModelRequest, db: Session = Depends(get_db)):
    """切换指定版本的模型为激活"""
    target = (
        db.query(MLModelMeta)
        .filter(
            MLModelMeta.task_name == req.task_name,
            MLModelMeta.version == req.version,
        )
        .first()
    )
    if not target:
        raise HTTPException(404, f"模型 {req.task_name}@{req.version} 未注册")
    # 旧的置 False
    db.query(MLModelMeta).filter(
        MLModelMeta.task_name == req.task_name
    ).update({"is_active": False})
    target.is_active = True
    db.commit()
    # 清掉 registry 缓存
    from cycling_coach.core.ml.registry import ModelRegistry
    ModelRegistry._cache.clear()
    return {"ok": True, "activated": f"{req.task_name}@{req.version}"}


@router.get("/predictions")
def list_predictions(
    limit: int = 20,
    model_name: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """列出最近 ML 预测结果"""
    q = db.query(MLPrediction)
    if model_name:
        q = q.filter(MLPrediction.model_name == model_name)
    rows = q.order_by(MLPrediction.created_at.desc()).limit(limit).all()
    return {
        "ok": True,
        "predictions": [
            {
                "id": r.id,
                "model_name": r.model_name,
                "model_version": r.model_version,
                "target": r.target,
                "predicted_value": r.predicted_value,
                "lower_80": r.lower_80,
                "upper_80": r.upper_80,
                "confidence_label": r.confidence_label,
                "activity_id": r.activity_id,
                "inference_ms": r.inference_ms,
                "created_at": r.created_at.isoformat(),
            }
            for r in rows
        ],
    }
