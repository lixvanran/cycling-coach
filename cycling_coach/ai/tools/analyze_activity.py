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

    # V0.7.5.1: 检索 KB — query 用训练学主题词, 不用数字/文件名
    # (V0.7.4.1 bug: query = 文件名 + 数字, 检索出无关文档)
    try:
        from cycling_coach.ai.orchestrator import _retrieve_kb
        # 1) 主题词: focus (用户给) + 活动类型 + 训练学关键词
        focus_kw = (focus or "").strip()
        # 从 metrics 推断活动类型
        type_kw = ""
        np = metrics_view.get("normalized_power") or 0
        avg_p = metrics_view.get("avg_power") or 0
        ife = metrics_view.get("intensity_factor") or 0
        if avg_p > 0 and ife > 0.95:
            type_kw = "阈值 间歇 VO2 强度"
        elif ife > 0.85:
            type_kw = "阈值 间歇 节奏"
        elif ife > 0.7:
            type_kw = "耐力 巡航 长时间"
        else:
            type_kw = "恢复 主动休息"
        # 加 athlete 关键参数
        athlete_kw = ""
        if athlete_view.get("ftp"):
            athlete_kw = f"FTP {athlete_view['ftp']}W"
        if athlete_view.get("max_hr"):
            athlete_kw += f" 最大心率 {athlete_view['max_hr']}"
        query = f"{focus_kw} {type_kw} {athlete_kw}".strip()
        retrieved = _retrieve_kb(query, top_k=3)
        # V0.7.5.1: 加相邻 chunks (前/后 1) 提升上下文
        if retrieved:
            from cycling_coach.data.sqlite.models import KbChunk, KbDocument
            from cycling_coach.data.sqlite.database import SessionLocal
            from sqlalchemy import or_ as _or2
            with SessionLocal() as s:
                for r in retrieved:
                    # 找该 chunk 的 doc + chunk_index
                    cm = s.query(KbChunk).filter(KbChunk.content == r["content"]).first()
                    if not cm:
                        continue
                    # 找 doc 全部 chunks
                    siblings = (
                        s.query(KbChunk)
                        .filter(KbChunk.document_id == cm.document_id)
                        .filter(_or2(KbChunk.chunk_index == cm.chunk_index - 1,
                                     KbChunk.chunk_index == cm.chunk_index + 1))
                        .all()
                    )
                    if siblings:
                        # 拼 sibling 内容
                        sib_text = " ".join(sb.content for sb in siblings)
                        r["content"] = f"{r['content']}\n\n[上下文] {sib_text}"
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
