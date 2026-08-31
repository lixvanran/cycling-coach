"""特征工程: 从 Activity / DailyMetric / Athlete 拼一行特征

V0.7.6 起步: 12 维
- 7 维 PMC: ctl / atl / tsb / ramp_rate / sleep_h / hrv_ms / rpe
- 5 维 当日活动: distance_m / duration_s / tss / normalized_power / intensity_factor

后续 V0.7.7+ 扩到 20 维 (HR Zones, Power Zones)
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Activity, DailyMetric


# V0.7.6: 12 维起步
FEATURE_SCHEMA: dict[str, str] = {
    # PMC (从 daily_metrics 拿)
    "ctl": "float",
    "atl": "float",
    "tsb": "float",
    "ramp_rate": "float",
    "sleep_h": "float|null",
    "hrv_ms": "float|null",
    "rpe": "float|null",
    # 当日活动 (从 activities 拿)
    "distance_m": "float",
    "duration_s": "float",
    "tss": "float",
    "normalized_power": "float|null",
    "intensity_factor": "float|null",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_feature_row(
    db: Session,
    athlete_id: int,
    activity_id: Optional[int] = None,
    ref_date: Optional[datetime] = None,
) -> tuple[list[float], list[str]]:
    """构造一行特征

    Args:
        db: SQLAlchemy Session
        athlete_id: 运动员 id
        activity_id: 基于哪个活动预测, None 用最近一个
        ref_date: 参考日期, None 用今天

    Returns:
        (values, columns) — values 顺序对齐 columns, 长度 = len(FEATURE_SCHEMA)

    Raises:
        ValueError: 数据不足 (< 7 天 daily_metrics)
    """
    ref = ref_date or _utcnow()
    columns = list(FEATURE_SCHEMA.keys())

    # 1) 拿今日 daily_metrics
    today_metric = (
        db.query(DailyMetric)
        .filter(DailyMetric.athlete_id == athlete_id)
        .filter(DailyMetric.date == ref.date())
        .first()
    )

    # 2) 今日没, 找最近 7 天内最新一条
    if not today_metric:
        cutoff = ref - timedelta(days=7)
        today_metric = (
            db.query(DailyMetric)
            .filter(DailyMetric.athlete_id == athlete_id)
            .filter(DailyMetric.date >= cutoff.date())
            .order_by(DailyMetric.date.desc())
            .first()
        )

    if not today_metric:
        raise ValueError("数据不足: 7 天内无 daily_metrics 记录, 请先上传活动")

    # 3) 拿指定活动 (或当日活动)
    if activity_id:
        activity = db.query(Activity).filter(Activity.id == activity_id).first()
    else:
        # 当日: ref 当天 0 点到现在
        day_start = ref.replace(hour=0, minute=0, second=0, microsecond=0)
        activity = (
            db.query(Activity)
            .filter(Activity.athlete_id == athlete_id)
            .filter(Activity.start_time >= day_start)
            .order_by(Activity.start_time.desc())
            .first()
        )

    # 4) 填特征 (None 落 0)
    values: list[float] = []
    for col in columns:
        if col in ("ctl", "atl", "tsb", "ramp_rate"):
            values.append(float(getattr(today_metric, col) or 0))
        elif col in ("sleep_h", "hrv_ms", "rpe"):
            v = getattr(today_metric, col)
            values.append(float(v) if v is not None else 0.0)
        elif col == "distance_m":
            values.append(float(activity.distance_m or 0) if activity else 0.0)
        elif col == "duration_s":
            values.append(float(activity.duration_s or 0) if activity else 0.0)
        elif col == "tss":
            values.append(float(activity.tss or 0) if activity else 0.0)
        elif col in ("normalized_power", "intensity_factor"):
            v = getattr(activity, col) if activity else None
            values.append(float(v) if v is not None else 0.0)
        else:
            values.append(0.0)

    return values, columns
