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


def _pick(obj: Any, key: str, default: Any = None) -> Any:
    """从 dict 或对象上取值, 两种都支持

    V0.9.0 修 P0: 之前 `_build_pmc_context` 对 `get_pmc_today()` 的返回值
    (dict!) 用 `getattr(pmc, "ctl", None)` —— dict 上 getattr 永远返回 None,
    于是 AI 教练拿到的 PMC 永远是 0/0/0。

    实测: 真实 API 返回 ctl 34.9 / atl 80.2 / tsb -45.3, AI 看到的是 None。
    AI 因此还会反问用户"你的面板是不是显示 CTL=0? 跟我说的对不上",
    把我们自己的 bug 甩给用户去检查同步 —— 典型的"自信地给错建议"。

    同文件的 phase 上下文 (line ~120) 本来就写对了
    (`getattr(...) or (info.get(...) if isinstance(info, dict) else None)`),
    只是 PMC/ACWR 这两块没照做。
    """
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _build_pmc_context(db: Session, athlete_id: int) -> Optional[dict]:
    from cycling_coach.core.pmc import get_pmc_today
    pmc = get_pmc_today(db, athlete_id)
    if not pmc:
        return None
    return {
        "ctl": _pick(pmc, "ctl"),
        "atl": _pick(pmc, "atl"),
        "tsb": _pick(pmc, "tsb"),
        "tss_today": _pick(pmc, "tss_today"),
        "status": _pick(pmc, "status"),
    }


def build_acwr_context(db: Session, athlete_id: int, days: int = 90) -> Optional[dict]:
    return _safe("acwr", lambda: _build_acwr_context(db, athlete_id, days))


def _build_acwr_context(db: Session, athlete_id: int, days: int) -> Optional[dict]:
    from cycling_coach.core.metrics.acwr import get_acwr_overview
    overview = get_acwr_overview(db, days=days)
    if not overview:
        return None
    # V0.9.0 修 P0: get_acwr_overview 的返回结构是
    #   {"today": {"date":..., "acute":..., "chronic":..., "acwr":..., "zone":...},
    #    "weekly_change":..., "risk":..., "risk_label":..., "series":[...]}
    # 旧代码在**顶层**找 acwr / acute / chronic / risk_zone → 全 None。
    # (顶层根本没有这些 key, 真正数值在 today 里; 顶层叫 "risk" 不是 "risk_zone")
    today = (overview.get("today") or {}) if isinstance(overview, dict) else {}
    return {
        "acwr": _pick(today, "acwr"),
        "acute": _pick(today, "acute"),
        "chronic": _pick(today, "chronic"),
        "zone": _pick(today, "zone"),
        "risk": _pick(overview, "risk"),
        "risk_label": _pick(overview, "risk_label"),
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
        "phase_type": _pick(info, "phase_type"),
        "label": _pick(info, "label"),
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
