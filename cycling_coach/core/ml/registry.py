"""模型注册表: 统一加载 joblib / onnx / torch 模型

进程内 LRU 8 缓存, 避免重复加载

V0.8.0 升级:
- 加载 ftp-predictor 风格 joblib (含 model / feature_cols / q_models / conformal_quantile)
- predict_interval 接 Conformal 校准区间
- 模型文件缺失 / 特征数不匹配时 graceful fallback / 400 错误
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Optional

import numpy as np

from cycling_coach.config.config import settings
from cycling_coach.data.sqlite.models import MLModelMeta
from cycling_coach.data.sqlite.database import SessionLocal

logger = logging.getLogger(__name__)


class ModelNotFoundError(Exception):
    """模型未注册或文件不存在"""


class FeatureSchemaMismatchError(Exception):
    """特征维度/名称不匹配模型期望"""


class ModelHandle:
    """统一包装不同格式的模型, 提供一致的 predict / predict_interval 接口

    V0.8.0: 新增 conformal 字段, predict_interval 用 Conformal 区间
    """

    def __init__(
        self,
        name: str,
        version: str,
        model: Any,
        model_format: str,
        metadata: dict,
        conformal: Optional[dict] = None,
    ):
        self.name = name
        self.version = version
        self.model = model
        self.model_format = model_format  # "joblib" / "onnx" / "pt" / "mock"
        self.metadata = metadata
        # conformal: {"q_models": {0.1: model, 0.5: model, 0.9: model},
        #             "conformal_quantile": float}
        self.conformal = conformal

    def predict(self, X) -> float:
        """点预测, 返回标量 float"""
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

    def predict_interval(
        self, X, coverage: float = 0.8
    ) -> tuple[float, float, float]:
        """区间预测, 返回 (point, lower, upper)

        V0.8.0 流程:
        1. 优先用 Conformal (q_models[0.1, 0.5, 0.9] + conformal_quantile)
        2. 没有 Conformal 时, 退到 ±10W (兜底)

        Conformal 校准公式:
            lower = q_models[0.1].predict(X) - conformal_quantile
            upper = q_models[0.9].predict(X) + conformal_quantile
            point = q_models[0.5].predict(X)  # 中位数
        """
        X_arr = np.asarray(X, dtype=np.float32)

        if self.conformal and self.conformal.get("q_models"):
            return self._conformal_interval(X_arr, coverage)

        # 兜底: ±10W
        point = self.predict(X_arr)
        half = 10.0
        return (point, point - half, point + half)

    def _conformal_interval(
        self, X_arr: np.ndarray, coverage: float
    ) -> tuple[float, float, float]:
        """用 Conformal 校准算 80% 区间"""
        q_models = self.conformal["q_models"]
        q = float(self.conformal.get("conformal_quantile", 0.0))

        # q_models 是 dict[float, model], e.g. {0.1: ..., 0.5: ..., 0.9: ...}
        # 容错: 如果键不是 float, 试 str
        def _q(key: float):
            if key in q_models:
                return q_models[key]
            if str(key) in q_models:
                return q_models[str(key)]
            raise KeyError(f"q_models 缺 {key}: keys={list(q_models.keys())}")

        p10 = float(_q(0.1).predict(X_arr)[0]) - q
        p50 = float(_q(0.5).predict(X_arr)[0])
        p90 = float(_q(0.9).predict(X_arr)[0]) + q
        return (p50, p10, p90)

    def has_conformal(self) -> bool:
        return self.conformal is not None and bool(self.conformal.get("q_models"))


class ModelRegistry:
    """单例 registry, 进程内 LRU 8"""

    _lock = threading.Lock()
    _cache: dict[str, ModelHandle] = {}  # key: "{task_name}@{version or 'active'}"
    _max_cache = 8

    @classmethod
    def load(cls, task_name: str, version: Optional[str] = None) -> ModelHandle:
        """从 MLModelMeta 表查激活的模型, 加载进 cache

        失败处理:
        - ModelNotFoundError: 模型未注册
        - ModelNotFoundError: joblib 文件不存在
        - 加载异常: log error, 抛 ModelNotFoundError (让上层 fallback 到 mock)
        """
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
                try:
                    handle = cls._build_handle(meta, model_path)
                except FeatureSchemaMismatchError:
                    raise  # 让上层抛 400, 不 fallback
                except Exception as e:
                    logger.error(f"加载模型失败 {cache_key}: {e}", exc_info=True)
                    raise ModelNotFoundError(
                        f"模型加载失败: {e} ({model_path})"
                    ) from e

                # LRU: 满了就丢最早插入的
                if len(cls._cache) >= cls._max_cache:
                    oldest = next(iter(cls._cache))
                    del cls._cache[oldest]
                cls._cache[cache_key] = handle
                logger.info(
                    f"已加载模型 {cache_key} ({meta.model_format}, "
                    f"{model_path.stat().st_size} bytes, "
                    f"conformal={'yes' if handle.has_conformal() else 'no'})"
                )
                return handle
            finally:
                db.close()

    @staticmethod
    def _build_handle(meta: MLModelMeta, model_path: Path) -> ModelHandle:
        """按 meta 构造 ModelHandle, 包含 conformal 加载

        ftp-predictor 约定:
        - best_model.joblib  dict: {model, feature_cols, target_col, ...}
        - 同目录下 conformal_models.joblib  dict: {q_models, conformal_quantile, ...}
        - ml_model_meta.feature_columns 记录 feature_cols (跟模型对齐)
        """
        model_obj = ModelRegistry._load_format(model_path, meta.model_format)
        feature_cols_expected = meta.feature_columns or []

        # ftp-predictor 风格: dict 包装
        if meta.model_format == "joblib" and isinstance(model_obj, dict):
            inner_model = model_obj.get("model")
            if inner_model is None:
                raise ModelNotFoundError(
                    f"joblib 格式应为 dict 含 'model' 字段, 但拿到 {type(model_obj)}"
                )

            # 验证特征维度
            if feature_cols_expected and hasattr(inner_model, "n_features_in_"):
                n_expected = len(feature_cols_expected)
                n_actual = inner_model.n_features_in_
                if n_expected != n_actual:
                    raise FeatureSchemaMismatchError(
                        f"特征维度不匹配: meta.feature_columns={n_expected}, "
                        f"model.n_features_in_={n_actual}"
                    )

            # 加载 Conformal (跟 best_model 同目录)
            conformal = None
            if meta.model_format == "joblib":
                # 默认命名: conformal_models.joblib
                # 兼容 v1.0.0 旧版 ftp-predictor
                conformal_path = model_path.parent / "conformal_models.joblib"
                if conformal_path.exists():
                    try:
                        import joblib
                        conf_data = joblib.load(conformal_path)
                        if isinstance(conf_data, dict) and "q_models" in conf_data:
                            conformal = {
                                "q_models": conf_data["q_models"],
                                "conformal_quantile": float(
                                    conf_data.get("conformal_quantile", 0.0)
                                ),
                                "alpha": conf_data.get("alpha", 0.2),
                                "test_coverage": conf_data.get("test_coverage"),
                                "cv_coverage_mean": conf_data.get("cv_coverage_mean"),
                            }
                            logger.info(
                                f"Conformal 已加载: q={list(conformal['q_models'].keys())}, "
                                f"quantile={conformal['conformal_quantile']:.2f}W"
                            )
                    except Exception as e:
                        logger.warning(f"Conformal 加载失败, 降级 ±10W: {e}")

            handle = ModelHandle(
                name=meta.task_name,
                version=meta.version,
                model=inner_model,
                model_format=meta.model_format,
                metadata={
                    "training_metrics": meta.training_metrics or {},
                    "feature_schema": meta.feature_schema or {},
                    "feature_columns": meta.feature_columns or [],
                    "model_name_inner": model_obj.get("model_name", "unknown"),
                    "cv_mae_mean": model_obj.get("cv_mae_mean"),
                    "cv_r2_mean": model_obj.get("cv_r2_mean"),
                    "target_col": model_obj.get("target_col", "ftp"),
                },
                conformal=conformal,
            )
            return handle

        # 其他格式 (onnx, pt, 裸 sklearn) 走老路
        return ModelHandle(
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
