"""V0.7.5.4 DEV-13: activities router 共享代码

activities.py 872 行拆分:
- 抽 Pydantic schema (AnalyzeResponse)
- 抽 helper: _downsample_samples, _run_analyze, _serialize_activity
- 抽 _ALLOWED_EXTS, _run_analyze

router 端点保留在 activities.py (FastAPI prefix 已固定)
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cycling_coach.ai.tools import analyze_activity_tool
from cycling_coach.data.sqlite.models import Activity

logger = logging.getLogger(__name__)


# ============== 常量 ==============

ALLOWED_EXTS = {".fit", ".tcx", ".csv"}  # V0.7.5.4 简化: 大小写在 router 内 normalize


# ============== Pydantic ==============

class AnalyzeResponse(BaseModel):
    ok: bool
    activity_id: int
    report: str | None = None
    report_status: str | None = None
    reason: str | None = None


# ============== Helpers ==============

def downsample_samples(samples: list, max_samples: int = 14400) -> list:
    """V0.7.1: 短课 (<4h) 全存, 长课 (>4h) 降采样到 5s 间隔
    
    14400 样本 = 4h × 3600s, 5s 间隔意味着每个 5s 取 1 个
    """
    if not samples or len(samples) <= max_samples:
        return samples
    step = (len(samples) + max_samples - 1) // max_samples
    return samples[::step]


def serialize_activity(a: Activity) -> dict:
    """统一序列化"""
    return {
        "id": a.id,
        "start_time": a.start_time.isoformat() if a.start_time else None,
        "duration_s": a.duration_s,
        "distance_m": a.distance_m,
        "avg_power": a.avg_power,
        "avg_hr": a.avg_hr,
        "avg_cadence": a.avg_cadence,
        "file_name": a.file_name,
        "device": a.device,
        "report_status": a.report_status,
    }


def run_analyze_task(activity_id: int, focus: str | None) -> None:
    """后台任务: 生成 AI 报告 (V0.7.5.2 修: 外层 try/except, 失败强制写 failed 状态)"""
    from cycling_coach.data.sqlite.database import SessionLocal
    db = SessionLocal()
    try:
        try:
            result = analyze_activity_tool(db, activity_id, focus=focus)
        except Exception as e:
            logger.exception(f"活动 {activity_id} AI 报告任务异常: {e}")
            try:
                a = db.get(Activity, activity_id)
                if a:
                    a.report_status = "failed"
                    a.report = f"⚠️ AI 报告生成失败: {e}\n\n请尝试手动重试, 或查看后端日志."
                    db.commit()
            except Exception as e2:
                logger.error(f"活动 {activity_id} 写失败状态也错: {e2}")
            return
        a = db.get(Activity, activity_id)
        if a:
            if result.get("ok"):
                report = result.get("report") or ""
                a.report = report
                a.report_status = "done" if report.strip() else "failed"
                logger.info(
                    f"活动 {activity_id} 报告生成: status={a.report_status}, len={len(report)}"
                )
            else:
                a.report_status = "failed"
                a.report = f"⚠️ AI 报告生成失败: {result.get('reason', '未知原因')}"
                logger.warning(f"活动 {activity_id} 报告生成失败: {result.get('reason')}")
            db.commit()
            logger.info(f"活动 {activity_id} 报告状态: {a.report_status}")
        else:
            logger.warning(f"活动 {activity_id} 不存在, 跳过报告状态更新")
    finally:
        db.close()
