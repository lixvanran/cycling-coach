"""从历史活动构建画像(MVP:估算 FTP)"""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Athlete, Activity
from . import store
from cycling_coach.core.metrics.aggregator import compute_metrics

logger = logging.getLogger(__name__)


def refresh_athlete_profile(db: Session, athlete_id: int) -> Athlete:
    """根据最近的活动重新估算 FTP / max_hr

    MVP 策略:
    - FTP:用 90 天内最长活动的 20-min power × 0.95(若有)
    - 兜底:用户手动设的 FTP
    """
    athlete = db.query(Athlete).get(athlete_id)
    if not athlete:
        raise ValueError(f"athlete {athlete_id} not found")

    # 简单:用最近 30 个活动找最高 NP
    activities = store.get_training_history(db, athlete_id, limit=30)
    if not activities:
        return athlete

    # 这里简化:MVP 不重跑 metrics(已存),直接用 activity.avg_power 找
    # 实际更稳的是重算 NP,但 1Hz 样本不一定存了
    best = max(
        (a for a in activities if a.avg_power),
        key=lambda a: a.avg_power or 0,
        default=None,
    )
    if best and best.avg_power:
        # 简单启发式:NP ≈ avg × 1.05(粗略),然后 × 0.95
        est = int(best.avg_power * 1.05 * 0.95)
        if not athlete.ftp or est > athlete.ftp:
            athlete.ftp_estimated = est
            logger.info(f"估算 FTP 更新: {est}W (来自活动 #{best.id})")

    return athlete
