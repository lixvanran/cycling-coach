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
    """datetime/date 统一为**本地日历日**

    ## 🔴 V0.9.0-07 (Verifier 复审指出, 实测确认)

    原来的写法: 先归一到 UTC, 再取 `.date()` —— 归档用 **UTC 日历日**。
    而 `get_pmc_today()` / 窗口 / 周报用的都是**本地** "今天"。

    写和读用了两个基准, 实测后果 (上海):

        FIT 存 UTC 10-08 17:00 (= 上海 10-09 01:00 的骑行)
        -> 入库剥掉 tzinfo, 存成 naive 17:00
        -> 旧实现归档到 **10-08**
        -> 而用户看的是 **10-09**, 今天那一行是空的

    UTC+8 每天有 **8 小时** (00:00-07:59) 落在这个缝里。
    骑行发生在当地, 用户认知也是当地, 所以归档要按**本地日历日**。

    ## 两个关键取舍

    **1. 为什么在这里转, 而不是把 UTC 转成本地再存**
    `start_time` 是**绝对时间戳**, 存 UTC 是对的 —— 出了差换了时区,
    它不该变。要变的只是"用哪个日历日归档"这一层, 所以只在归档时转换。
    改存储会让换时区的用户历史数据集体错位。

    **2. 为什么 naive 输入要补回 UTC**
    入库时 tzinfo 被剥掉了(`activity.py` 里 `replace(tzinfo=None)`),
    那个 naive 值承载的仍是 **UTC 墙钟**。补回 UTC 再转本地才不失真。
    直接 `.date()` 等于把 UTC 墙钟当本地墙钟, 正是原来那个错。
    """
    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            # naive = 被剥掉时区的 UTC 墙钟 (见上文第 2 点)
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().date()      # 本机时区的日历日
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
        anchor_date: **只重写这一天及之后的行**; 但计算所需的活动仍然全量加载
        backfill_days: 向前回溯天数(默认 365,够 PMC 看趋势)

    Returns: upsert 的行数

    ⚠️ V0.9.0 修掉的严重 bug —— anchor_date 不能用来裁剪输入数据
    ------------------------------------------------------------------
    原来这里写的是:

        if anchor_date:
            stmt = stmt.where(Activity.start_time >= anchor_date)
        ...
        start = min(earliest, latest - timedelta(days=backfill_days))

    后果: 增量导入新训练时, 只有 anchor 当天之后的活动参与聚合, 前面
    (up to 365 天) 全部被当作 TSS=0, EWMA 从"全是零"开始算, 然后
    **把之前算对的 daily_metrics 行全部覆盖掉**。

    实测: 导入 45 次训练后, 366 行 daily_metrics 里 365 行 TSS=0,
    CTL 变成 0.3 —— 一个认真训练了 8 周的人, 体能值被告知是 0.3。
    手动全量重算一次, CTL 立刻回到 56.1。

    这不是"新用户没数据"的小问题, 是**每个用户每天导入训练都会中招**:
    早上骑完导入, 应用就告诉你体能清零了。

    正确做法: anchor_date 只控制"写回哪些行", 不控制"读哪些活动"。
    EWMA 必须从真实历史起算, 否则 seed 值本身就是错的。
    """
    # 1. 找所有活动 —— 无论有没有 anchor_date, 都必须全量加载。
    #    EWMA 是递推的, seed 错了后面全错。
    stmt = select(Activity).where(Activity.athlete_id == athlete_id)
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

    # 4. 算 PMC (基于**全量**历史)
    daily_tss = [s[1] for s in series]
    ctl_list, atl_list = compute_ctl_atl(daily_tss)
    ramp_list = compute_ramp_rate(ctl_list)

    # 5. upsert
    #    anchor_date 只用于跳过"不需要重写"的早期行 —— 省 IO, 但不碰计算。
    skip_before = anchor_date if anchor_date and anchor_date > start else None
    upserted = 0
    for i, (d, tss, count, dur) in enumerate(series):
        if skip_before is not None and d < skip_before:
            continue
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
            # V0.9.0: 调用方以前靠 `status_label != "无数据"` 判断"有没有负荷数据"。
            # 那是**用中文字符串当契约** —— 只要有行、但 ctl/atl/tsb 全是 NULL,
            # tsb 就会被 `float(row.tsb or 0)` 变成 0.0, classify_status(0,0)
            # 返回"平衡", 哨兵放行, 于是**零训练负荷数据拿到满分 20/20**。
            # 改成结构化判据, 别再让显示文案承担数据可用性的职责。
            "has_load_data": False,
        }
    tsb = float(row.tsb or 0)
    ramp = float(row.ramp_rate or 0)
    code, label, color = classify_status(tsb, ramp)
    return {
        "date": today.isoformat(),
        # V0.9.0: 结构化地回答"这一行到底有没有真实负荷数据"。
        #
        # 注意是**有行**不等于**有负荷**: 休息日也会因为填了 RPE 而建行。
        # 而 models.py 里 ctl/atl/tsb 都是 `mapped_column(Float, default=0.0)`,
        # 所以 NULL 根本不会出现 —— **"没测"和"测出来是 0"在 schema 层就被
        # 抹平了**, 没法靠 IS NULL 区分。
        #
        # 因此这里用语义判据: CTL/ATL 是 TSS 的 EWMA, 只要有过任何训练史就必然 > 0;
        # 两者同时恰好为 0 只可能意味着"从来没有算过负荷"。TSB = CTL - ATL,
        # 所以单独查 tsb 没意义(它为 0 也可能是两者相等)。
        "has_load_data": bool(row.ctl) or bool(row.atl),
        "tss_today": float(row.tss or 0),
        "ctl": round(float(row.ctl or 0), 1),
        "atl": round(float(row.atl or 0), 1),
        "tsb": round(tsb, 1),
        "ramp_rate": round(ramp, 2),
        "status": code,
        "status_label": label,
        "status_color": color,
    }
