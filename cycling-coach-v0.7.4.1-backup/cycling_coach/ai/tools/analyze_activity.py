"""analyze_activity 工具 — 核心解读"""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Activity
from cycling_coach.core.profile import store as profile_store
from ..prompts.analyze import build_analyze_prompt
from ..m3_client import get_m3, M3Error, M3AuthError, M3QuotaError, M3NetworkError

logger = logging.getLogger(__name__)


def _format_laps(activity: Activity) -> str:
    if not activity.laps_json:
        return ""
    lines = []
    for i, lap in enumerate(activity.laps_json[:10], 1):
        lines.append(
            f"- Lap {i}: {lap.get('duration_s', '?')}s, "
            f"avg_pwr={lap.get('avg_power', '?')}W, "
            f"avg_hr={lap.get('avg_hr', '?')}bpm, "
            f"trigger={lap.get('trigger', 'manual')}"
        )
    return "\n".join(lines)


def _compute_weekly_tss(db: Session, athlete_id: int) -> int:
    """本周已累计 TSS(简化:最近 7 天)"""
    from datetime import datetime, timedelta, timezone
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=7)
    activities = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff)
        .all()
    )
    total = 0
    for a in activities:
        m = a.metrics or {}
        tss = m.get("tss") if isinstance(m, dict) else None
        if tss:
            total += int(tss)
    return total


def analyze_activity_tool(
    db: Session, activity_id: int, focus: Optional[str] = None
) -> dict:
    """解读单次训练,生成 AI 报告

    返回:
      {
        'ok': bool,
        'report': str,        # AI 报告 (markdown)
        'reason': str | None, # 失败原因
      }
    """
    activity = db.query(Activity).get(activity_id)
    if not activity:
        return {"ok": False, "report": "", "reason": f"活动 {activity_id} 不存在"}

    athlete = profile_store.get_or_create_athlete(db)
    weekly_tss = _compute_weekly_tss(db, athlete.id)

    metrics = activity.metrics or {}
    metrics_view = {
        "duration_min": round(activity.duration_s / 60, 1),
        "distance_km": round((activity.distance_m or 0) / 1000, 2),
        "avg_power": activity.avg_power,
        "normalized_power": metrics.get("normalized_power"),
        "intensity_factor": metrics.get("intensity_factor"),
        "tss": metrics.get("tss"),
        "efficiency_factor": metrics.get("efficiency_factor"),
        "variability_index": metrics.get("variability_index"),
        "avg_hr": activity.avg_hr,
        "hr_drift": metrics.get("hr_drift"),
        "avg_cadence": activity.avg_cadence,
        "elevation_gain": activity.total_elevation_gain,
    }
    athlete_view = {
        "name": athlete.name,
        "ftp": athlete.ftp,
        "ftp_estimated": athlete.ftp_estimated,
        "max_hr": athlete.max_hr,
    }
    system, user = build_analyze_prompt(
        metrics_view, athlete_view, weekly_tss, _format_laps(activity)
    )

    if focus:
        user += f"\n\n用户特别关注: {focus}"

    # V0.7.4.1: 检索 KB (mock 模式下用 KB 拼报告, 真 LLM 也用 KB 增强)
    try:
        from cycling_coach.ai.orchestrator import _retrieve_kb
        # 检索关键词: 活动标题 + 训练学关键词
        query = f"{activity.file_name or ''} {' '.join(str(v) for v in metrics_view.values() if v)}"
        retrieved = _retrieve_kb(query, top_k=3)
    except Exception as e:
        logger.debug(f"KB 检索失败: {e}")
        retrieved = []

    m3 = get_m3()
    try:
        report = m3.chat(system, user, temperature=0.6, max_tokens=1200, retrieved=retrieved)
        return {"ok": True, "report": report, "reason": None}
    except (M3AuthError, M3QuotaError, M3NetworkError) as e:
        # 致命错 — 任务级中断
        logger.error(f"analyze_activity 致命错: {e}")
        return {"ok": False, "report": "", "reason": str(e)}
    except M3Error as e:
        logger.error(f"analyze_activity 错误: {e}")
        return {"ok": False, "report": "", "reason": str(e)}
    except Exception as e:
        logger.exception(f"analyze_activity 异常: {e}")
        return {"ok": False, "report": "", "reason": f"未知错误: {e}"}
