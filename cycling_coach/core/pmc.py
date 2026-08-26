"""PMC (Performance Management Chart) — CTL/ATL/TSB 计算

经典算法 (TrainingPeaks 公式):
  CTL_t = CTL_{t-1} + (TSS_t - CTL_{t-1}) * (1 - exp(-1/42))
  ATL_t = ATL_{t-1} + (TSS_t - ATL_{t-1}) * (1 - exp(-1/7))
  TSB_t = CTL_t - ATL_t

或展开形式(等价,便于批处理):
  CTL_t = sum_{i=0..N-1} TSS_{t-i} * exp(-i/42) / sum exp(-i/42)
  简化为非归一化: CTL = sum TSS_i * exp(-(N-1-i) / 42)
  (差一个常数不影响曲线形状,TrainerRoad / Xert 都用这种非归一化)

ramp_rate: 7 天 CTL 斜率 (TSS/week),衡量训练强度趋势
  - > +7 TSS/wk: 快速提升(可能过训)
  - 0 ~ +7: 健康提升
  - -3 ~ 0: 维持
  - < -3: 减量
"""
from __future__ import annotations
import math
from datetime import date as _date, datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..data.sqlite.models import Activity, DailyMetric

# EWMA 时间常数(天)
CTL_TC = 42  # 慢性负荷
ATL_TC = 7   # 急性负荷
RAMP_WINDOW = 7  # ramp_rate 计算窗口


def _day_key(dt: datetime | _date) -> _date:
    """datetime/date 统一为 date"""
    if isinstance(dt, datetime):
        # 用 UTC 日期(避免时区漂移)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt.date()
    return dt


def aggregate_tss_by_day(activities: Iterable[Activity]) -> dict[_date, dict]:
    """把活动按日期聚合 → {date: {tss, count, duration_s}}"""
    out: dict[_date, dict] = {}
    for a in activities:
        d = _day_key(a.start_time)
        bucket = out.setdefault(d, {"tss": 0.0, "count": 0, "duration_s": 0})
        tss = (a.metrics or {}).get("tss") or 0
        bucket["tss"] += float(tss)
        bucket["count"] += 1
        bucket["duration_s"] += int(a.duration_s or 0)
    return out


def compute_ctl_atl(
    daily_tss: list[float],
    ctl_today: float = 0.0,
    atl_today: float = 0.0,
) -> tuple[list[float], list[float]]:
    """对一段历史每日 TSS,算出每日 CTL/ATL

    输入 daily_tss 长度 N,输出 (ctl_list, atl_list),长度 N。
    ctl_today / atl_today 是序列**前**一天的 CTL/ATL(默认 0,首次计算)。
    """
    ctl_list: list[float] = []
    atl_list: list[float] = []
    ctl_prev = ctl_today
    atl_prev = atl_today
    # 注意: 经典 EWMA 公式是 CTL_t = CTL_{t-1} + (TSS_t - CTL_{t-1}) * (1 - exp(-1/TC))
    # 等价于: CTL_t = CTL_{t-1} * exp(-1/TC) + TSS_t * (1 - exp(-1/TC))
    k_ctl = 1 - math.exp(-1 / CTL_TC)
    k_atl = 1 - math.exp(-1 / ATL_TC)
    for tss in daily_tss:
        ctl_prev = ctl_prev * (1 - k_ctl) + tss * k_ctl
        atl_prev = atl_prev * (1 - k_atl) + tss * k_atl
        ctl_list.append(ctl_prev)
        atl_list.append(atl_prev)
    return ctl_list, atl_list


def compute_ramp_rate(ctl_series: list[float], window: int = RAMP_WINDOW) -> list[float]:
    """7 天 CTL 斜率(TSS/week)= (CTL_today - CTL_{t-window}) / window * 7"""
    ramp: list[float] = []
    for i in range(len(ctl_series)):
        if i < window:
            ramp.append(0.0)
        else:
            delta = ctl_series[i] - ctl_series[i - window]
            ramp.append(delta / window * 7)
    return ramp


def classify_status(tsb: float, ramp_rate: float) -> tuple[str, str, str]:
    """根据 TSB + ramp_rate 返回 (status_code, label_zh, color)

    color: green / yellow / red / blue
    """
    # 优先级:过训 > 减量 > 良好 > 状态巅峰
    if tsb < -30:
        return "overtraining", "过度训练", "red"
    if ramp_rate < -5:
        return "taper", "主动减量", "blue"
    if tsb < -10:
        return "tired", "在累积疲劳", "yellow"
    if tsb > 20:
        return "fresh", "状态巅峰", "green"
    if tsb > 5:
        return "good", "状态良好", "green"
    return "neutral", "平衡", "yellow"


def recompute_pmc(
    db: Session,
    athlete_id: int,
    anchor_date: _date | None = None,
    backfill_days: int = 365,
) -> int:
    """重算并 upsert daily_metrics

    策略:
    1. 取 athlete 所有活动
    2. 按天聚合 TSS
    3. 序列填充空日(TSS=0)
    4. 算 CTL/ATL/TSB/ramp_rate
    5. upsert 到 daily_metrics(覆盖已有)

    Args:
        athlete_id: 运动员 id
        anchor_date: 重算起点(默认最早活动日;新增活动时传 activity.start_time.date())
        backfill_days: 向前回溯天数(默认 365,够 PMC 看趋势)

    Returns: upsert 的行数
    """
    # 1. 找所有活动
    stmt = select(Activity).where(Activity.athlete_id == athlete_id)
    if anchor_date:
        stmt = stmt.where(Activity.start_time >= datetime.combine(anchor_date, datetime.min.time()))
    activities = list(db.execute(stmt).scalars())

    if not activities:
        return 0

    # 2. 按天聚合
    tss_by_day = aggregate_tss_by_day(activities)
    if not tss_by_day:
        return 0

    # 3. 序列填充
    earliest = min(tss_by_day.keys())
    latest = max(max(tss_by_day.keys()), _date.today())
    # 从 backfill_days 前到 today
    start = min(earliest, latest - timedelta(days=backfill_days))
    series: list[tuple[_date, float, int, int]] = []
    cur = start
    while cur <= latest:
        bucket = tss_by_day.get(cur, {"tss": 0.0, "count": 0, "duration_s": 0})
        series.append((cur, bucket["tss"], bucket["count"], bucket["duration_s"]))
        cur += timedelta(days=1)

    # 4. 算 PMC
    daily_tss = [s[1] for s in series]
    ctl_list, atl_list = compute_ctl_atl(daily_tss)
    ramp_list = compute_ramp_rate(ctl_list)

    # 5. upsert
    upserted = 0
    for i, (d, tss, count, dur) in enumerate(series):
        ctl = ctl_list[i]
        atl = atl_list[i]
        tsb = ctl - atl
        ramp = ramp_list[i]
        existing = db.execute(
            select(DailyMetric).where(
                DailyMetric.athlete_id == athlete_id,
                DailyMetric.date == d,
            )
        ).scalar_one_or_none()
        if existing:
            existing.tss = tss
            existing.activity_count = count
            existing.duration_s = dur
            existing.ctl = ctl
            existing.atl = atl
            existing.tsb = tsb
            existing.ramp_rate = ramp
        else:
            db.add(DailyMetric(
                athlete_id=athlete_id,
                date=d,
                tss=tss,
                activity_count=count,
                duration_s=dur,
                ctl=ctl,
                atl=atl,
                tsb=tsb,
                ramp_rate=ramp,
            ))
        upserted += 1
    db.commit()
    return upserted


def get_pmc_series(db: Session, athlete_id: int, days: int = 90) -> list[dict]:
    """取最近 N 天的 PMC 时间序列"""
    cutoff = _date.today() - timedelta(days=days)
    rows = db.execute(
        select(DailyMetric)
        .where(DailyMetric.athlete_id == athlete_id, DailyMetric.date >= cutoff)
        .order_by(DailyMetric.date.asc())
    ).scalars().all()
    return [
        {
            "date": r.date.isoformat(),
            "tss": round(r.tss or 0, 1),
            "activity_count": r.activity_count or 0,
            "duration_s": r.duration_s or 0,
            "ctl": round(r.ctl or 0, 1),
            "atl": round(r.atl or 0, 1),
            "tsb": round(r.tsb or 0, 1),
            "ramp_rate": round(r.ramp_rate or 0, 2),
        }
        for r in rows
    ]


def get_pmc_today(db: Session, athlete_id: int) -> dict:
    """取今日 PMC 状态卡"""
    today = _date.today()
    row = db.execute(
        select(DailyMetric)
        .where(DailyMetric.athlete_id == athlete_id, DailyMetric.date == today)
    ).scalar_one_or_none()
    if not row:
        return {
            "date": today.isoformat(),
            "tss_today": 0,
            "ctl": 0,
            "atl": 0,
            "tsb": 0,
            "ramp_rate": 0,
            "status": "neutral",
            "status_label": "无数据",
            "status_color": "yellow",
        }
    tsb = float(row.tsb or 0)
    ramp = float(row.ramp_rate or 0)
    code, label, color = classify_status(tsb, ramp)
    return {
        "date": today.isoformat(),
        "tss_today": float(row.tss or 0),
        "ctl": round(float(row.ctl or 0), 1),
        "atl": round(float(row.atl or 0), 1),
        "tsb": round(tsb, 1),
        "ramp_rate": round(ramp, 2),
        "status": code,
        "status_label": label,
        "status_color": color,
    }
