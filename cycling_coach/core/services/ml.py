"""V0.8.0: ML 推理业务层 (V0.7.6)

覆盖端点:
- POST /api/ml/predict/ftp         predict_ftp
- GET  /api/ml/models              list_models
- POST /api/ml/models/register     register_model
- POST /api/ml/models/activate     activate_model
- GET  /api/ml/predictions         list_predictions
"""
from __future__ import annotations
import logging
import time
from datetime import datetime, timezone
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from cycling_coach.core.exceptions import NotFoundError, ValidationError
from cycling_coach.core.ml import (
    build_feature_row,
    get_active_model,
    ModelNotFoundError,
    MockFTPModel,
    FEATURE_SCHEMA,
)
from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite.models import (
    Activity,
    DailyMetric,
    MLPrediction,
    MLModelMeta,
)

logger = logging.getLogger(__name__)


# ============== DTO ==============

class FTPPredictRequest(BaseModel):
    activity_id: Optional[int] = Field(None, description="基于哪个活动预测, 留空用今日最新")
    model_version: Optional[str] = Field(None, description="指定模型版本, 留空用 active")


class FTPPredictResponse(BaseModel):
    ok: bool
    predicted_ftp: float
    lower_80: float
    upper_80: float
    confidence: str  # "high" / "medium" / "low"
    current_ftp: Optional[int] = None
    delta: Optional[int] = None
    data_window: str = "今日 + 7d PMC"
    model_name: str
    model_version: str
    model_format: str
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


# ============== Service ==============

class MLService:
    """ML 推理 + 模型注册"""
    def __init__(self, db: Session):
        self.db = db

    def predict_ftp(self, req: FTPPredictRequest) -> dict:
        """基于近期训练数据预测当前 FTP"""
        start = time.time()
        athlete = profile_store.get_or_create_athlete(self.db)

        # 1) 特征
        try:
            values, columns = build_feature_row(
                self.db, athlete.id, activity_id=req.activity_id,
            )
        except ValueError as e:
            raise ValidationError(f"数据不足: {e}")

        # 2) 加载模型 (失败时降级 mock)
        try:
            handle = get_active_model("ftp_predictor", version=req.model_version)
            X = np.array([values], dtype=np.float32)
            point, lower, upper = handle.predict_interval(X, coverage=0.8)
            model_name = handle.name
            model_version = handle.version
            model_format = handle.model_format
        except ModelNotFoundError as e:
            logger.warning(f"ML 模型未注册, 降级 MockFTPModel: {e}")
            mock = MockFTPModel(base_ftp=athlete.ftp or 250)
            X = np.array([values], dtype=np.float32)
            point = float(mock.predict(X)[0])
            half = 10.0
            lower, upper = point - half, point + half
            model_name = "ftp_predictor"
            model_version = "mock-v0"
            model_format = "mock"

        # 3) 置信度 (基于 daily_metrics 历史数量)
        n_history = (
            self.db.query(DailyMetric).filter(DailyMetric.athlete_id == athlete.id).count()
        )
        if n_history >= 90:
            confidence = "high"
        elif n_history >= 28:
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
        self.db.add(pred)
        self.db.commit()
        self.db.refresh(pred)

        return {
            "ok": True,
            "predicted_ftp": round(point, 1),
            "lower_80": round(lower, 1),
            "upper_80": round(upper, 1),
            "confidence": confidence,
            "current_ftp": current_ftp,
            "delta": delta,
            "model_name": model_name,
            "model_version": model_version,
            "model_format": model_format,
            "prediction_id": pred.id,
            "inference_ms": elapsed_ms,
        }

    def list_models(self) -> dict:
        """列出已注册的 ML 模型"""
        rows = (
            self.db.query(MLModelMeta)
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

    def register_model(self, req: RegisterModelRequest) -> dict:
        """注册一个新模型到 MLModelMeta"""
        if req.is_active:
            self.db.query(MLModelMeta).filter(
                MLModelMeta.task_name == req.task_name
            ).update({"is_active": False})
            self.db.commit()
        m = MLModelMeta(
            task_name=req.task_name,
            version=req.version,
            model_path=req.model_path,
            model_format=req.model_format,
            training_date=datetime.now(timezone.utc).replace(tzinfo=None),
            training_samples_count=req.training_samples_count,
            training_metrics=req.training_metrics,
            feature_schema=req.feature_schema or FEATURE_SCHEMA,
            feature_columns=req.feature_columns or list(FEATURE_SCHEMA.keys()),
            is_active=req.is_active,
            notes=req.notes,
        )
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        return {"ok": True, "id": m.id, "is_active": m.is_active}

    def activate_model(self, req: ActivateModelRequest) -> dict:
        """切换指定版本的模型为激活"""
        target = (
            self.db.query(MLModelMeta)
            .filter(
                MLModelMeta.task_name == req.task_name,
                MLModelMeta.version == req.version,
            )
            .first()
        )
        if not target:
            raise NotFoundError(f"模型 {req.task_name}@{req.version} 未注册")
        self.db.query(MLModelMeta).filter(
            MLModelMeta.task_name == req.task_name
        ).update({"is_active": False})
        target.is_active = True
        self.db.commit()
        # 清掉 registry 缓存
        from cycling_coach.core.ml.registry import ModelRegistry
        ModelRegistry._cache.clear()
        return {"ok": True, "activated": f"{req.task_name}@{req.version}"}

    def list_predictions(
        self, limit: int = 20, model_name: Optional[str] = None,
    ) -> dict:
        """列出最近 ML 预测结果"""
        q = self.db.query(MLPrediction)
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
