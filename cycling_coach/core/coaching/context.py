"""V0.7.5.2: 训练上下文构建 (统一 6 块, 消除 orchestrator + recommendations 重复)

借鉴 TrainingPeaks Dashboard / WKO5 Home / GoldenCheetah Athlete Home:
- athlete 基础信息 (FTP / Max HR / LTHR)
- 今日 PMC (CTL / ATL / TSB)
- ACWR (急性慢性负荷比)
- RPE 7d 主观疲劳
- 当前周期阶段
- 最新 FTP 测试
"""
from __future__ import annotations
import logging
from datetime import datetime, timedelta
from typing import Optional, Any

from sqlalchemy import desc
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Activity, TrainingPhase, FTPTest
from cycling_coach.core.profile import store as profile_store

logger = logging.getLogger(__name__)


def _safe(label: str, fn) -> Any:
    """V0.7.5.2: 统一 try/except + warning 替代 debug (DEV-7)"""
    try:
        return fn()
    except Exception as e:
        logger.warning(f"[context] {label} 读取失败: {e}", exc_info=False)
        return None


def build_athlete_context(db: Session) -> dict:
    """基础 athlete 信息 (不依赖 query)"""
    return _safe("athlete", lambda: _build_athlete_context(db)) or {}


def _build_athlete_context(db: Session) -> dict:
    athlete = profile_store.get_or_create_athlete(db)
    return {
        "id": athlete.id,
        "name": athlete.name,
        "experience": getattr(athlete, "experience", None) or "未填",
        "ftp": athlete.ftp,
        "ftp_estimated": athlete.ftp_estimated,
        "max_hr": athlete.max_hr,
        "lthr": athlete.lthr,
        "weight_kg": athlete.weight_kg,
    }


def build_pmc_context(db: Session, athlete_id: int) -> Optional[dict]:
    return _safe("pmc", lambda: _build_pmc_context(db, athlete_id))


def _build_pmc_context(db: Session, athlete_id: int) -> Optional[dict]:
    from cycling_coach.core.pmc import get_pmc_today
    pmc = get_pmc_today(db, athlete_id)
    if not pmc:
        return None
    return {
        "ctl": getattr(pmc, "ctl", None),
        "atl": getattr(pmc, "atl", None),
        "tsb": getattr(pmc, "tsb", None),
    }


def build_acwr_context(db: Session, athlete_id: int, days: int = 90) -> Optional[dict]:
    return _safe("acwr", lambda: _build_acwr_context(db, athlete_id, days))


def _build_acwr_context(db: Session, athlete_id: int, days: int) -> Optional[dict]:
    from cycling_coach.core.metrics.acwr import get_acwr_overview
    overview = get_acwr_overview(db, days=days)
    if not overview:
        return None
    # get_acwr_overview 返回 dict (acwr / acute / chronic / risk_zone)
    return {
        "acwr": overview.get("acwr") if isinstance(overview, dict) else None,
        "acute": overview.get("acute") if isinstance(overview, dict) else None,
        "chronic": overview.get("chronic") if isinstance(overview, dict) else None,
        "risk_zone": overview.get("risk_zone") if isinstance(overview, dict) else None,
    }


def build_rpe_7d_context(db: Session, athlete_id: int) -> Optional[dict]:
    return _safe("rpe_7d", lambda: _build_rpe_7d_context(db, athlete_id))


def _build_rpe_7d_context(db: Session, athlete_id: int) -> Optional[dict]:
    cutoff_7d = datetime.utcnow() - timedelta(days=7)
    acts = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff_7d)
        .filter(Activity.rpe.isnot(None))
        .all()
    )
    if not acts:
        return None
    return {
        "avg": round(sum(a.rpe for a in acts) / len(acts), 1),
        "count": len(acts),
        "high_count": sum(1 for a in acts if a.rpe >= 7),
        "days": sorted({a.start_time.date().isoformat() for a in acts})[-7:],
    }


def build_phase_context(db: Session, athlete_id: int) -> Optional[dict]:
    return _safe("phase", lambda: _build_phase_context(db, athlete_id))


def _build_phase_context(db: Session, athlete_id: int) -> Optional[dict]:
    from cycling_coach.core.metrics.periodization import derive_phase
    info = derive_phase(db, athlete_id)
    if not info:
        return None
    return {
        "phase_type": getattr(info, "phase_type", None) or (info.get("phase_type") if isinstance(info, dict) else None),
        "label": getattr(info, "label", None) or (info.get("label") if isinstance(info, dict) else None),
    }


def build_ftp_context(db: Session, athlete_id: int) -> Optional[dict]:
    return _safe("ftp", lambda: _build_ftp_context(db, athlete_id))


def _build_ftp_context(db: Session, athlete_id: int) -> Optional[dict]:
    from cycling_coach.core.profile import store as profile_store
    athlete = profile_store.get_or_create_athlete(db)
    latest = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == athlete_id)
        .order_by(desc(FTPTest.test_date))
        .first()
    )
    if not latest and not athlete.ftp:
        return None
    return {
        "ftp_w": latest.ftp_w if latest else athlete.ftp,
        "test_date": latest.test_date.date().isoformat() if latest else None,
        "method": latest.method if latest else "默认",
    }


def build_chat_context(db: Session, athlete_id: int) -> dict:
    """V0.7.5.2 抽: 6 块统一入口 (DEV-10)
    
    返回 6 块上下文, 每块独立 try/except, 失败不连累其他块 (DEV-7).
    orchestrator + recommendations 都用这个.
    """
    return {
        "athlete": build_athlete_context(db),
        "pmc": build_pmc_context(db, athlete_id),
        "acwr": build_acwr_context(db, athlete_id),
        "rpe_7d": build_rpe_7d_context(db, athlete_id),
        "phase": build_phase_context(db, athlete_id),
        "ftp": build_ftp_context(db, athlete_id),
    }
