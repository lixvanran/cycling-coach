"""V0.7.6: ML 推理基础设施

不包含训练代码 — 训练走独立 CLI (V0.7.7+)
本包只负责: 加载模型 + 特征工程 + 推理 + 落库

支持的模型格式:
- joblib (sklearn / xgboost / lightgbm)
- onnx (onnxruntime)
- pt (torchscript)
- mock (无真实模型, 规则 fallback)
"""
from .registry import ModelRegistry, get_active_model, ModelNotFoundError
from .feature_pipe import build_feature_row, FEATURE_SCHEMA
from ._mock import MockFTPModel

__all__ = [
    "ModelRegistry",
    "get_active_model",
    "ModelNotFoundError",
    "build_feature_row",
    "FEATURE_SCHEMA",
    "MockFTPModel",
]
