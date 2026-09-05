"""V0.7.6+: ML 推理基础设施

不包含训练代码 — 训练走独立 CLI / ftp-predictor 仓库
本包只负责: 加载模型 + 特征工程 + 推理 + 落库

支持的模型格式:
- joblib (sklearn / xgboost / lightgbm)
- onnx (onnxruntime)
- pt (torchscript)
- mock (无真实模型, 规则 fallback)

V0.8.0 升级:
- 特征从 12 维 → 20 维, 对齐 lixvanran/ftp-predictor
- ModelHandle.predict_interval 接 Conformal 校准 (q_models + conformal_quantile)
"""
from .registry import (
    ModelRegistry,
    get_active_model,
    ModelHandle,
    ModelNotFoundError,
    FeatureSchemaMismatchError,
)
from .feature_pipe import (
    build_feature_row,
    FEATURE_SCHEMA,
    FEATURE_COLUMNS,
    DEFAULT_WINDOW_DAYS,
)
from ._mock import MockFTPModel

__all__ = [
    "ModelRegistry",
    "get_active_model",
    "ModelHandle",
    "ModelNotFoundError",
    "FeatureSchemaMismatchError",
    "build_feature_row",
    "FEATURE_SCHEMA",
    "FEATURE_COLUMNS",
    "DEFAULT_WINDOW_DAYS",
    "MockFTPModel",
]
