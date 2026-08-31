"""模型注册表: 统一加载 joblib / onnx / torch 模型

进程内 LRU 8 缓存, 避免重复加载
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional

from cycling_coach.config.config import settings
from cycling_coach.data.sqlite.models import MLModelMeta
from cycling_coach.data.sqlite.database import SessionLocal

logger = logging.getLogger(__name__)


class ModelNotFoundError(Exception):
    """模型未注册或文件不存在"""


class ModelHandle:
    """统一包装不同格式的模型, 提供一致的 predict / predict_interval 接口"""

    def __init__(self, name: str, version: str, model: Any, model_format: str, metadata: dict):
        self.name = name
        self.version = version
        self.model = model
        self.model_format = model_format  # "joblib" / "onnx" / "pt" / "mock"
        self.metadata = metadata  # MLModelMeta 行 dict

    def predict(self, X) -> float:
        """点预测, 返回标量 float"""
        import numpy as np

        X_arr = np.asarray(X, dtype=np.float32)
        if self.model_format == "joblib":
            return float(self.model.predict(X_arr)[0])
        elif self.model_format == "onnx":
            return float(self.model.run(None, {"input": X_arr})[0][0])
        elif self.model_format == "pt":
            import torch
            with torch.no_grad():
                t = torch.tensor(X_arr.tolist(), dtype=torch.float32)
                return float(self.model(t).item())
        raise NotImplementedError(f"predict for {self.model_format} not implemented")

    def predict_interval(self, X, coverage: float = 0.8) -> tuple[float, float, float]:
        """区间预测, 返回 (point, lower, upper)

        V0.7.6 起步: 没有 conformal model 时, 简单用 ±10W 兜底
        V0.7.7+ 接入 Conformal 模型时, 这里改
        """
        point = self.predict(X)
        # 简化: ±10W (≈ 业内 MAE 6-8W 的 1.5x)
        half = 10.0
        return (point, point - half, point + half)


class ModelRegistry:
    """单例 registry, 进程内 LRU 8"""

    _lock = threading.Lock()
    _cache: dict[str, ModelHandle] = {}  # key: "{task_name}@{version or 'active'}"
    _max_cache = 8

    @classmethod
    def load(cls, task_name: str, version: Optional[str] = None) -> ModelHandle:
        """从 MLModelMeta 表查激活的模型, 加载进 cache"""
        with cls._lock:
            cache_key = f"{task_name}@{version or 'active'}"
            if cache_key in cls._cache:
                return cls._cache[cache_key]

            # 查 DB
            db = SessionLocal()
            try:
                q = db.query(MLModelMeta).filter(MLModelMeta.task_name == task_name)
                if version:
                    q = q.filter(MLModelMeta.version == version)
                else:
                    q = q.filter(MLModelMeta.is_active.is_(True))
                meta = q.first()
                if not meta:
                    raise ModelNotFoundError(
                        f"模型 {task_name}@{version or 'active'} 未在 MLModelMeta 注册"
                    )

                # 路径解析 (相对 workspace)
                workspace = Path(settings.workspace_dir).resolve()
                model_path = workspace / meta.model_path
                if not model_path.exists():
                    raise ModelNotFoundError(f"模型文件不存在: {model_path}")

                # 按格式加载
                model_obj = cls._load_format(model_path, meta.model_format)
                handle = ModelHandle(
                    name=meta.task_name,
                    version=meta.version,
                    model=model_obj,
                    model_format=meta.model_format,
                    metadata={
                        "training_metrics": meta.training_metrics or {},
                        "feature_schema": meta.feature_schema or {},
                        "feature_columns": meta.feature_columns or [],
                    },
                )

                # LRU: 满了就丢最早插入的
                if len(cls._cache) >= cls._max_cache:
                    oldest = next(iter(cls._cache))
                    del cls._cache[oldest]
                cls._cache[cache_key] = handle
                logger.info(
                    f"已加载模型 {cache_key} ({meta.model_format}, "
                    f"{model_path.stat().st_size} bytes)"
                )
                return handle
            finally:
                db.close()

    @staticmethod
    def _load_format(path: Path, fmt: str):
        if fmt == "joblib":
            import joblib
            return joblib.load(path)
        elif fmt == "onnx":
            import onnxruntime
            return onnxruntime.InferenceSession(str(path))
        elif fmt == "pt":
            import torch
            return torch.jit.load(str(path))
        else:
            raise ValueError(f"不支持的模型格式: {fmt}")


def get_active_model(task_name: str, version: Optional[str] = None) -> ModelHandle:
    """便捷入口: Registry.load(task_name, version)"""
    return ModelRegistry.load(task_name, version)
