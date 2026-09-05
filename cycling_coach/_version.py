"""版本号 — V0.7.1 单一真相源 (SSOT)

通过 importlib.metadata 在运行时从已安装包元数据读版本,
避免 pyproject.toml / package.json / FastAPI / 前端四处分散维护。
"""
from __future__ import annotations
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# 1) 优先 importlib.metadata (包安装后)
try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("cycling-coach")
except Exception as e:
    logger.debug(f"importlib.metadata 失败, 尝试 pyproject 兜底: {e}")
    # 2) 兜底: 直接解析 pyproject.toml
    try:
        import tomllib
        pp = Path(__file__).parent.parent / "pyproject.toml"
        with open(pp, "rb") as f:
            data = tomllib.load(f)
        __version__ = data.get("project", {}).get("version", "0.0.0")
    except Exception as e2:
        logger.warning(f"读 pyproject.toml 也失败, 用 hardcoded: {e2}")
        __version__ = "0.7.8"  # hardcoded 兜底
