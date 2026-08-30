"""HRV (心率变异性) 趋势分析 — V0.7.2 新加

借鉴 (V0.7.2 加):
- Plews & Laursen 2013 (HRV in athletes: training adaptation)
- Bellenger et al. 2016 (HRV monitoring in endurance athletes)
- Buchheit 2014 (HRV derived indices in training monitoring)

HRV 阈值 (RMSSD, ms):
- > 80: 良好, 恢复充分
- 50-80: 正常
- 30-50: 中等疲劳, 注意
- < 30: 高疲劳 / 过度训练风险

训练学用法:
- 晨起静息 HRV 连续 7d 滑动 < 30d baseline - 10ms → 建议降量
- 1d 异常可不作判断 (受睡眠/酒精影响)
- 3d 持续下降 → 减量 30%
"""
from __future__ import annotations
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from sqlalchemy import desc
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import DailyMetric

logger = logging.getLogger(__name__)


def get_hrv_series(
    db: Session, athlete_id: int, days: int = 60
) -> list[dict]:
    """取最近 N 天 HRV 数据

    Returns:
        [
            {"date": "2026-08-01", "hrv_ms": 65.0, "sleep_h": 7.5},
            ...
        ]
    """
    rows = (
        db.query(DailyMetric)
        .filter(DailyMetric.athlete_id == athlete_id)
        .filter(DailyMetric.hrv_ms.isnot(None))
        .order_by(desc(DailyMetric.date))
        .limit(days)
        .all()
    )
    return [
        {
            "date": r.date.isoformat(),
            "hrv_ms": r.hrv_ms,
            "sleep_h": r.sleep_h,
        }
        for r in reversed(rows)
    ]


def compute_hrv_state(
    db: Session, athlete_id: int
) -> dict:
    """V0.7.2: HRV 训练状态评估

    Returns:
        {
            "today_hrv": 52.3,                  # 今日 HRV
            "rolling_7d_avg": 58.1,            # 7d 滑动
            "baseline_30d": 65.0,              # 30d baseline
            "delta_from_baseline": -6.9,       # 负值 = 低于 baseline
            "delta_pct": -10.6,                # 百分比
            "consecutive_low_days": 2,         # 连续低 HRV 天数
            "status": "ok" | "caution" | "warning",
            "status_label": "正常" | "注意" | "警告: 需降量",
            "recommendation": "...",
            "series": [...],                   # 最近 30d 数据
        }

    借鉴: Plews 2013, Bellenger 2016, Buchheit 2014
    """
    series = get_hrv_series(db, athlete_id, days=30)
    if len(series) < 3:
        return {
            "today_hrv": None,
            "status": "insufficient_data",
            "status_label": "数据不足",
            "recommendation": "至少需要 3 天 HRV 数据 (建议连续 7 天晨起静息测量)",
            "series": series,
            "consecutive_low_days": 0,
        }

    today_hrv = series[-1]["hrv_ms"]

    # 7d 滑动平均 (排除今天, 看前 7 天趋势)
    last_7 = [d["hrv_ms"] for d in series[-8:-1]] if len(series) >= 8 else [d["hrv_ms"] for d in series[:-1]]
    rolling_7d_avg = round(sum(last_7) / len(last_7), 1) if last_7 else today_hrv

    # 30d baseline
    baseline_30d = round(sum(d["hrv_ms"] for d in series) / len(series), 1)

    delta_from_baseline = round(today_hrv - baseline_30d, 1)
    delta_pct = round((delta_from_baseline / baseline_30d) * 100, 1) if baseline_30d > 0 else 0

    # 连续低于 baseline - 10ms 的天数
    consecutive_low = 0
    for d in reversed(series):
        if d["hrv_ms"] < baseline_30d - 10:
            consecutive_low += 1
        else:
            break

    # 状态判断
    if consecutive_low >= 3:
        status = "warning"
        status_label = "警告: 需降量"
        recommendation = (
            f"连续 {consecutive_low} 天 HRV 低于 baseline {baseline_30d:.0f}ms 以下 10ms+, "
            "提示累积疲劳 / 过度训练风险 (Bellenger 2016). "
            "建议: 减量 30-50% 或安排 1-2 天完全恢复, 优先睡眠与营养."
        )
    elif delta_from_baseline < -10 or today_hrv < 30:
        status = "caution"
        status_label = "注意"
        recommendation = (
            f"HRV ({today_hrv:.0f}ms) 显著低于 baseline ({baseline_30d:.0f}ms, {delta_pct:+.1f}%). "
            "提示疲劳累积, 建议今天安排轻松骑 (Z1-Z2) 或休息, 避免高强度."
        )
    else:
        status = "ok"
        status_label = "正常"
        if today_hrv > baseline_30d + 10:
            recommendation = (
                f"HRV ({today_hrv:.0f}ms) 高于 baseline ({baseline_30d:.0f}ms, {delta_pct:+.1f}%), "
                "状态好, 可以按计划进行高强度训练 (Plews 2013)."
            )
        else:
            recommendation = (
                f"HRV ({today_hrv:.0f}ms) 接近 baseline ({baseline_30d:.0f}ms, {delta_pct:+.1f}%), "
                "状态稳定, 按计划训练."
            )

    return {
        "today_hrv": today_hrv,
        "rolling_7d_avg": rolling_7d_avg,
        "baseline_30d": baseline_30d,
        "delta_from_baseline": delta_from_baseline,
        "delta_pct": delta_pct,
        "consecutive_low_days": consecutive_low,
        "status": status,
        "status_label": status_label,
        "recommendation": recommendation,
        "series": series[-30:],  # 最近 30d 给前端
    }


def record_hrv_today(
    db: Session, athlete_id: int, hrv_ms: float, sleep_h: float | None = None
) -> dict:
    """V0.7.2: 用户手动录入今日 HRV (前端 /api/hrv 端点调用)

    更新今日 DailyMetric 的 hrv_ms / sleep_h 字段
    """
    today = datetime.utcnow().date()
    row = (
        db.query(DailyMetric)
        .filter(DailyMetric.athlete_id == athlete_id)
        .filter(DailyMetric.date == today)
        .first()
    )
    if not row:
        row = DailyMetric(athlete_id=athlete_id, date=today)
        db.add(row)
    row.hrv_ms = hrv_ms
    if sleep_h is not None:
        row.sleep_h = sleep_h
    db.commit()
    db.refresh(row)
    return {"date": today.isoformat(), "hrv_ms": row.hrv_ms, "sleep_h": row.sleep_h}
