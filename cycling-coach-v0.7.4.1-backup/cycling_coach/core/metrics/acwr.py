"""ACWR (Acute:Chronic Workload Ratio) — 受伤风险预警

学术背景: Tim Gabbett (2016) 训练负荷管理研究
- Acute load (ATL): 7 天滚动平均 TSS
- Chronic load (CTL): 28 天滚动平均 TSS
- ACWR = ATL / CTL
- Sweet spot: 0.8-1.3 (训练效果最好)
- 高风险: > 1.5 (受伤风险飙升 ~2-4x)
- 低负荷: < 0.8 (去训练, 体能下降)
- 突然上升: 周环比 +0.2 以上也属风险

注意: 这里 CTL 用 28 天 (Tim Gabbett 2016 原始论文).
PMC 里的 CTL 用 42 天 exponential decay (Coggan), 是不同概念.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Activity
from cycling_coach.core.profile import store as profile_store


def compute_daily_tss(db: Session, athlete_id: int, days: int = 90) -> list[dict]:
    """计算每天 TSS 总和"""
    cutoff = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days)
    activities = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff)
        .all()
    )

    by_day: dict[str, float] = {}
    for a in activities:
        tss = (a.metrics or {}).get("tss", 0) or 0
        if tss <= 0 or not a.start_time:
            continue
        day_key = a.start_time.date().isoformat()
        by_day[day_key] = by_day.get(day_key, 0) + tss

    # 补全缺失日期 (TSS = 0)
    series = []
    for i in range(days + 1):
        d = (datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=days - i)).date()
        series.append({
            "date": d.isoformat(),
            "tss": by_day.get(d.isoformat(), 0),
        })
    return series


def compute_acwr(daily_tss: list[dict], acute_window: int = 7, chronic_window: int = 28) -> list[dict]:
    """ACWR 时间序列

    返回:
    [
      { "date": "2026-05-20", "acute": 95.5, "chronic": 78.2, "acwr": 1.22, "zone": "sweet_spot" },
      ...
    ]
    """
    if len(daily_tss) < chronic_window:
        return []

    series = []
    for i in range(chronic_window - 1, len(daily_tss)):
        # 急性窗口: i-acute+1 到 i
        acute_slice = daily_tss[i - acute_window + 1: i + 1]
        # 慢性窗口: i-chronic+1 到 i
        chronic_slice = daily_tss[i - chronic_window + 1: i + 1]

        acute = sum(d["tss"] for d in acute_slice) / acute_window
        chronic = sum(d["tss"] for d in chronic_slice) / chronic_window
        acwr = round(acute / chronic, 2) if chronic > 0 else 0

        # 分区
        if acwr < 0.8:
            zone = "low"
        elif acwr <= 1.3:
            zone = "sweet_spot"
        elif acwr <= 1.5:
            zone = "caution"
        else:
            zone = "danger"

        series.append({
            "date": daily_tss[i]["date"],
            "acute": round(acute, 1),
            "chronic": round(chronic, 1),
            "acwr": acwr,
            "zone": zone,
        })
    return series


def get_acwr_overview(db: Session, days: int = 90) -> dict:
    """ACWR 当前状态 + 时间序列"""
    athlete = profile_store.get_or_create_athlete(db)
    daily = compute_daily_tss(db, athlete.id, days=days)
    series = compute_acwr(daily)

    today = series[-1] if series else None

    # 周环比
    weekly_change = None
    if len(series) >= 7:
        now = series[-1]["acwr"]
        week_ago = series[-7]["acwr"]
        weekly_change = round(now - week_ago, 2)

    # 受伤风险评估
    risk = "low"
    risk_label = "低"
    recommendation = "保持当前训练节奏"
    if today:
        z = today["zone"]
        if z == "low":
            risk = "low"
            risk_label = "训练不足"
            recommendation = "考虑增加训练量 (ACWR < 0.8 体能会下降)"
        elif z == "sweet_spot":
            risk = "low"
            risk_label = "最佳区间"
            recommendation = "保持训练节奏, 受伤风险最低"
        elif z == "caution":
            risk = "medium"
            risk_label = "注意"
            recommendation = "训练量较高, 安排 1-2 天轻松日"
        else:
            risk = "high"
            risk_label = "高风险"
            recommendation = "建议立即降低训练量, 受伤风险显著上升"

        if weekly_change and weekly_change > 0.2:
            recommendation += " · 周环比 +" + str(weekly_change) + ", 上升过快"

    return {
        "today": today,
        "weekly_change": weekly_change,
        "risk": risk,
        "risk_label": risk_label,
        "recommendation": recommendation,
        "series": series,
        "windows": {"acute_days": 7, "chronic_days": 28},
    }
