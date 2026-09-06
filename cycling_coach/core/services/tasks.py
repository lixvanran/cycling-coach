"""
V0.8.1 批 1: 修循环依赖 - 共享后台任务

把 run_analyze_task 从 api/routers/_activities_shared.py 搬到 core/services/tasks.py,
消除 core/services/activity.py:242 → api/routers 的反向依赖。
"""
from __future__ import annotations
import logging
from typing import Optional

from cycling_coach.ai.tools import analyze_activity_tool
from cycling_coach.data.sqlite.models import Activity

logger = logging.getLogger(__name__)


def run_analyze_task(activity_id: int, focus: Optional[str] = None) -> None:
    """后台任务: 生成 AI 报告 (V0.7.5.2 修: 外层 try/except, 失败强制写 failed 状态)
    
    V0.8.1 批 1: 从 api 层迁出, 消除 core → api 的循环依赖。
    """
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
