"""/api/trends — 长期趋势分析 (V0.6 GoldenCheetah 对标)

端点:
- GET /api/trends/volume?days=90  → 训练量趋势 (周/月聚合)
- GET /api/trends/zones?days=90   → 7 区分布时间变化 (周聚合)
- GET /api/trends/metrics?days=90  → 关键指标趋势 (NP/IF/HR)
- GET /api/trends/overview?days=90 → 综合概览 (训练量 + 同比)
"""
from __future__ import annotations
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import Activity
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.pmc import get_pmc_series

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/trends", tags=["trends"])


# ============================================================
# 工具
# ============================================================

def _iso_week_key(d: datetime) -> str:
    """返回 ISO 周的 key, e.g. '2026-W34'"""
    iso = d.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _month_key(d: datetime) -> str:
    return f"{d.year}-{d.month:02d}"


def _filter_activities(db: Session, athlete_id: int, days: int) -> list[Activity]:
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    return (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff)
        .order_by(Activity.start_time.asc())
        .all()
    )


# ============================================================
# 1. 训练量趋势 (周/月聚合)
# ============================================================

@router.get("/volume")
def volume_trend(
    days: int = Query(90, ge=14, le=730, description="回溯天数"),
    bucket: str = Query("week", pattern="^(week|month)$", description="聚合粒度: week / month"),
    db: Session = Depends(get_db),
):
    """训练量趋势 (TSS / 距离 / 时长)

    返回:
    {
      "days": 90,
      "bucket": "week",
      "series": [
        { "key": "2026-W22", "tss": 280, "distance_km": 145.2, "duration_h": 6.5, "activities": 3 },
        ...
      ],
      "summary": {
        "total_tss": 2520,
        "avg_weekly_tss": 280,
        "total_distance_km": 1452.0,
        "total_duration_h": 65.0,
        "weeks_count": 12,
      },
      "yoy": {  # 同比 (跟前一周期比)
        "tss_change_pct": 12.5,
        "distance_change_pct": -3.2,
      }
    }
    """
    athlete = profile_store.get_or_create_athlete(db)
    activities = _filter_activities(db, athlete.id, days)

    bucket_key = _iso_week_key if bucket == "week" else _month_key
    grouped: dict[str, list[Activity]] = defaultdict(list)
    for a in activities:
        if a.start_time:
            grouped[bucket_key(a.start_time)].append(a)

    series = []
    for k in sorted(grouped.keys()):
        acts = grouped[k]
        tss = sum((a.metrics or {}).get("tss", 0) or 0 for a in acts)
        dist = sum((a.distance_m or 0) for a in acts) / 1000
        dur = sum(a.duration_s for a in acts) / 3600
        series.append({
            "key": k,
            "tss": int(tss),
            "distance_km": round(dist, 1),
            "duration_h": round(dur, 1),
            "activities": len(acts),
        })

    total_tss = sum(s["tss"] for s in series)
    total_dist = sum(s["distance_km"] for s in series)
    total_dur = sum(s["duration_h"] for s in series)

    # 平均每周 TSS
    weeks_count = max(1, len(series))
    avg_weekly_tss = round(total_tss / weeks_count, 1) if bucket == "week" else round(total_tss / max(1, days / 30), 1)

    # 同比: 跟前半周期比
    yoy = None
    if len(series) >= 2:
        half = len(series) // 2
        recent_tss = sum(s["tss"] for s in series[half:])
        recent_dist = sum(s["distance_km"] for s in series[half:])
        prior_tss = sum(s["tss"] for s in series[:half])
        prior_dist = sum(s["distance_km"] for s in series[:half])
        yoy = {
            "tss_change_pct": round((recent_tss - prior_tss) * 100.0 / prior_tss, 1) if prior_tss else 0,
            "distance_change_pct": round((recent_dist - prior_dist) * 100.0 / prior_dist, 1) if prior_dist else 0,
        }

    return {
        "days": days,
        "bucket": bucket,
        "series": series,
        "summary": {
            "total_tss": int(total_tss),
            "total_distance_km": round(total_dist, 1),
            "total_duration_h": round(total_dur, 1),
            "avg_weekly_tss": avg_weekly_tss,
            "weeks_count": weeks_count,
        },
        "yoy": yoy,
    }


# ============================================================
# 2. 7 区分布时间变化 (周聚合)
# ============================================================

@router.get("/zones")
def zones_trend(
    days: int = Query(90, ge=14, le=730),
    bucket: str = Query("week", pattern="^(week|month)$"),
    db: Session = Depends(get_db),
):
    """7 区分布时间变化

    每桶: 各区累计秒数, 用于堆叠柱状图 / 面积图
    """
    athlete = profile_store.get_or_create_athlete(db)
    activities = _filter_activities(db, athlete.id, days)

    bucket_key = _iso_week_key if bucket == "week" else _month_key
    grouped: dict[str, list[Activity]] = defaultdict(list)
    for a in activities:
        if a.start_time:
            grouped[bucket_key(a.start_time)].append(a)

    zone_codes = ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    series = []
    for k in sorted(grouped.keys()):
        acts = grouped[k]
        zone_secs: dict[str, int] = {z: 0 for z in zone_codes}
        total_secs = 0
        for a in acts:
            pz = (a.metrics or {}).get("power_zones", {})
            if pz:
                for z in zone_codes:
                    zone_secs[z] += int(pz.get(z, 0) or 0)
                total_secs += sum(int(pz.get(z, 0) or 0) for z in zone_codes)
        row = {"key": k, "total_seconds": total_secs}
        row.update(zone_secs)
        # %time
        for z in zone_codes:
            row[f"{z}_pct"] = round(zone_secs[z] * 100.0 / total_secs, 1) if total_secs else 0
        series.append(row)

    return {
        "days": days,
        "bucket": bucket,
        "series": series,
    }


# ============================================================
# 3. 关键指标趋势 (NP/IF/HR)
# ============================================================

@router.get("/metrics")
def metrics_trend(
    days: int = Query(90, ge=14, le=730),
    bucket: str = Query("week", pattern="^(week|month)$"),
    db: Session = Depends(get_db),
):
    """关键指标趋势 (NP / IF / 平均心率 / 平均功率)

    每桶: 平均值 (活动级别平均, 不按时间加权)
    """
    athlete = profile_store.get_or_create_athlete(db)
    activities = _filter_activities(db, athlete.id, days)

    bucket_key = _iso_week_key if bucket == "week" else _month_key
    grouped: dict[str, list[Activity]] = defaultdict(list)
    for a in activities:
        if a.start_time:
            grouped[bucket_key(a.start_time)].append(a)

    series = []
    for k in sorted(grouped.keys()):
        acts = grouped[k]
        if not acts:
            continue
        nps = [(a.metrics or {}).get("normalized_power") for a in acts if (a.metrics or {}).get("normalized_power")]
        ifs = [(a.metrics or {}).get("intensity_factor") for a in acts if (a.metrics or {}).get("intensity_factor")]
        avgs = [a.avg_power for a in acts if a.avg_power]
        hrs = [a.avg_hr for a in acts if a.avg_hr]
        cads = [a.avg_cadence for a in acts if a.avg_cadence]
        series.append({
            "key": k,
            "avg_normalized_power": int(sum(nps) / len(nps)) if nps else None,
            "avg_intensity_factor": round(sum(ifs) / len(ifs), 3) if ifs else None,
            "avg_power": int(sum(avgs) / len(avgs)) if avgs else None,
            "avg_hr": int(sum(hrs) / len(hrs)) if hrs else None,
            "avg_cadence": int(sum(cads) / len(cads)) if cads else None,
            "activities": len(acts),
        })

    return {
        "days": days,
        "bucket": bucket,
        "series": series,
    }


# ============================================================
# 4. 综合概览 (训练量 + PMC + 同期对比)
# ============================================================

@router.get("/rpe-trend")
def rpe_trend(
    days: int = Query(60, ge=7, le=365),
    db: Session = Depends(get_db),
):
    """RPE 主观疲劳趋势 (V0.6.1)

    返回:
    - series: [{date, avg_rpe, count, tss, ratio}, ...]
    - overall_avg: 总平均 RPE
    - high_rpe_days: RPE >= 8 的天数 (硬训练日)
    - by_phase: 按训练阶段分组的 RPE (待 Phase 标签上线)

    训练学用途:
    - 单日 RPE / TSS ≈ 0.018 (TSS 100 ~ RPE 5-6)
    - RPE 突然升高但 TSS 稳定 → 提示: 生理疲劳/睡眠不足
    - RPE 突然降低但 TSS 升高 → 提示: 状态太好/取样误差
    - 7 天滑动平均 RPE 持续 > 7 → 建议降量
    """
    from datetime import datetime, timedelta, timezone
    from cycling_coach.data.sqlite.models import Activity
    from cycling_coach.core.profile import store as profile_store

    athlete = profile_store.get_or_create_athlete(db)
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    activities = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete.id)
        .filter(Activity.start_time >= cutoff)
        .filter(Activity.rpe.isnot(None))
        .all()
    )

    # 按日聚合
    by_day: dict[str, dict] = {}
    for a in activities:
        if not a.start_time or a.rpe is None:
            continue
        day_key = a.start_time.date().isoformat()
        if day_key not in by_day:
            by_day[day_key] = {"rpe_sum": 0, "count": 0, "tss_sum": 0}
        by_day[day_key]["rpe_sum"] += a.rpe
        by_day[day_key]["count"] += 1
        tss = (a.metrics or {}).get("tss", 0) or 0
        by_day[day_key]["tss_sum"] += tss

    series = []
    for day_key in sorted(by_day.keys()):
        d = by_day[day_key]
        avg_rpe = d["rpe_sum"] / d["count"]
        ratio = d["rpe_sum"] / d["tss_sum"] if d["tss_sum"] > 0 else None
        series.append({
            "date": day_key,
            "avg_rpe": round(avg_rpe, 1),
            "count": d["count"],
            "tss": d["tss_sum"],
            "rpe_tss_ratio": round(ratio, 4) if ratio is not None else None,
        })

    # 整体统计
    if series:
        overall_avg = round(sum(s["avg_rpe"] * s["count"] for s in series) / sum(s["count"] for s in series), 1)
        high_rpe_days = sum(1 for s in series if s["avg_rpe"] >= 8)
        low_rpe_days = sum(1 for s in series if s["avg_rpe"] <= 3)
    else:
        overall_avg = None
        high_rpe_days = 0
        low_rpe_days = 0

    return {
        "series": series,
        "overall_avg": overall_avg,
        "high_rpe_days": high_rpe_days,
        "low_rpe_days": low_rpe_days,
        "days": days,
    }


@router.get("/acwr")
def acwr_trend(
    days: int = Query(90, ge=14, le=730),
    db: Session = Depends(get_db),
):
    """ACWR 急慢性负荷比 (V0.6.1 受伤风险预警)

    学术: Tim Gabbett 2016
    - Acute (7d) / Chronic (28d) = ACWR
    - Sweet spot 0.8-1.3, danger > 1.5
    """
    from cycling_coach.core.metrics.acwr import get_acwr_overview
    return get_acwr_overview(db, days=days)


@router.get("/overview")
def overview(
    days: int = Query(90, ge=14, le=730),
    db: Session = Depends(get_db),
):
    """长期趋势综合概览

    一次返回所有: volume + zones + metrics + PMC + 同期对比
    """
    athlete = profile_store.get_or_create_athlete(db)

    # 复用其它端点
    vol = volume_trend(days=days, bucket="week", db=db)
    zones = zones_trend(days=days, bucket="week", db=db)
    mtr = metrics_trend(days=days, bucket="week", db=db)
    pmc = get_pmc_series(db, athlete.id, days=days)

    # 周数
    weeks = vol["summary"]["weeks_count"]

    return {
        "days": days,
        "weeks": weeks,
        "volume": vol,
        "zones": zones,
        "metrics": mtr,
        "pmc": pmc,
        "yoy": vol.get("yoy"),
    }
