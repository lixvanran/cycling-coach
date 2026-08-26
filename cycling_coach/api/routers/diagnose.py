"""/api/diagnose - 健康检查 + 配置诊断"""
from __future__ import annotations
import logging
import platform
import sys

from fastapi import APIRouter

from cycling_coach.config.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["diagnose"])


@router.get("/diagnose")
def diagnose():
    """诊断信息(给前端 / 健康检查用)"""
    from ..main import app
    return {
        "ok": True,
        "version": app.version,
        "m3_mock_mode": settings.is_mock,
        "m3_model": settings.m3_model,
        "python": sys.version.split()[0],
        "system": platform.system(),
    }


@router.get("/health")
def health():
    return {"status": "ok"}
