"""V0.9.0: 数据可信度自检端点

## 为什么做这个

核心竞争点是「性能齐平 + 开源免费」。**"免费"本身就是最大的不信任理由** ——
用户会想"免费的能靠谱吗"。

而我们这一周在 readiness / insights / race_prep / periodization 里
清掉了 10 处"编造看起来合理的数据"的 bug, **但用户一个都看不见**。
诚实如果不可见, 就等于不存在。

这个端点把那些内部约定**摊开给用户看**:

- 每个指标依据哪篇公开文献(Coggan 2003 / Banister / Gabbett 2016 /
  Plews 2013 / Friel), 可点进去核对
- 当前用户每个维度的真实状态: 有数据 / 缺数据 / 为什么缺
- 本 App 在数据不足时**会做什么、不会做什么**

## 和 /api/diagnose 的区别

`/api/diagnose` 是环境自检(Python 版本、系统、LLM 是否 mock)——
给开发者和排障用。这个是**给用户看的信任证明**。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends

from cycling_coach.api.dependencies import Services, get_services
from cycling_coach.config.config import settings
from cycling_coach.core.metrics.hrv import compute_hrv_state
from cycling_coach.core.metrics.periodization import derive_phase
from cycling_coach.core.pmc import get_pmc_today

router = APIRouter(prefix="/api/trust", tags=["trust"])


# 每个指标的公开文献出处。开源的意义之一就是: 这些数字可以被任何人核对。
METRIC_SOURCES = [
    {
        "key": "hrv",
        "name": "HRV 心率变异性",
        "weight": 30,
        "source": "Plews et al. 2013, 'Training adaptation and heart rate variability in elite endurance athletes'",
        "note": "反映自主神经系统的恢复状态。无数据时本维度不计入评分。",
    },
    {
        "key": "acwr",
        "name": "ACWR 急慢性负荷比",
        "weight": 25,
        "source": "Gabbett 2016, 'The training-injury prevention paradox'",
        "note": "急性负荷 / 慢性负荷。需要 28 天真实训练史才会计算。",
    },
    {
        "key": "tsb",
        "name": "TSB 训练平衡",
        "weight": 20,
        "source": "Banister impulse-response model (Foster 1998)",
        "note": "CTL − ATL。判断累积疲劳与恢复。",
    },
    {
        "key": "phase",
        "name": "周期阶段",
        "weight": 15,
        "source": "Joe Friel, 'The Cycling Training Bible'",
        "note": "基于训练负荷与赛程推导。需要真实负荷数据或已设比赛。",
    },
    {
        "key": "rpe",
        "name": "主观疲劳 RPE",
        "weight": 10,
        "source": "Borg CR-10 scale",
        "note": "训练后填写的疲劳感受。需要你手动记录。",
    },
]


def _has_rpe(db, athlete_id: int) -> bool:
    """最近 7 天有没有记录过 RPE"""
    from datetime import date as _date, datetime, timedelta
    from cycling_coach.data.sqlite.models import DailyMetric
# 🔴 V0.9.0-07: 这里原来用 `datetime.utcnow().date()` (UTC) 算"今天",
# 而 pmc 的读取侧和这个模块的其他部分用本地日期 —— 同一个产品里两个"今天"。
# 中国骑行者 (UTC+8) 每天 00:00-07:59 有 8 小时落在这个缝里:
# 数据归属错一天, 周报/周期化/HRV 窗口全部对不上。
#
# 真时间戳 (completed_at / updated_at) 走 `utcnow_naive()`, 那个是对的,
# 不要一起改 —— 改的是**日历日**语义, 不是时间戳语义。
    cutoff = _date.today() - timedelta(days=7)
    return db.query(DailyMetric).filter(
        DailyMetric.athlete_id == athlete_id,
        DailyMetric.date >= cutoff,
        DailyMetric.rpe.isnot(None),
    ).count() > 0


@router.get("/metrics")
def metric_sources():
    """每个指标依据哪篇公开文献 —— 可核对, 这才是开源的意义"""
    return {"metrics": METRIC_SOURCES}


@router.get("/self-check")
def self_check(_svc: Services = Depends(get_services)):
    """当前用户的真实数据状态 —— 缺什么、为什么缺, 全部如实列出

    这个页面存在的意义: 让用户**自己看到**这个 App 在数据不足时
    选择说"算不出来", 而不是给一个看起来不错的分数。
    """
    from cycling_coach.core.profile import store as profile_store
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.coaching.recommendations import acwr_history_is_real

    db = SessionLocal()
    athlete = profile_store.get_or_create_athlete(db)
    aid = athlete.id

    pmc = get_pmc_today(db, aid)
    has_load = bool(pmc.get("has_load_data"))
    hrv = compute_hrv_state(db, aid)
    phase = derive_phase(db, aid)
    acwr_ok = acwr_history_is_real(db, aid)

    dims = [
        {
            "key": "tsb", "name": "训练平衡", "weight": 20,
            "available": has_load,
            "why": "有训练负荷数据" if has_load else "还没有带功率的训练记录",
        },
        {
            "key": "hrv", "name": "HRV", "weight": 30,
            "available": hrv["status"] in ("ok", "caution", "warning"),
            "why": {"ok": "今日 HRV 正常", "caution": "HRV 偏低",
                    "warning": "HRV 持续低"}.get(hrv["status"], "还没有心率带记录"),
        },
        {
            "key": "acwr", "name": "ACWR", "weight": 25,
            "available": acwr_ok,
            "why": "训练史已满 28 天" if acwr_ok else "需要 28 天真实训练史才会计算",
        },
        {
            "key": "phase", "name": "周期阶段", "weight": 15,
            "available": phase.suggested_type != "unknown",
            "why": phase.suggested_label,
        },
        {
            "key": "rpe", "name": "主观疲劳", "weight": 10,
            # V0.9.0: 原来这里是写死的 available: False —— 于是用户**明明
            # 填了 RPE**, 自检页还是告诉他"缺 RPE"。自检页如果自己都不准,
            # 那它证明不了任何东西。
            "available": _has_rpe(db, aid),
            "why": "已记录主观疲劳" if _has_rpe(db, aid)
                   else "训练后填一次 RPE (1-10) 即可计入",
        },
    ]
    n_avail = sum(1 for d in dims if d["available"])

    return {
        "version": settings.app_version if hasattr(settings, "app_version") else "0.9.0",
        # V0.9.0-07: 这里是 None 就显示 None(前端渲染"未设置"),
        # 不要退回任何默认值 —— 250 看起来像测出来的。
        "athlete": {"name": athlete.name, "ftp": athlete.ftp},
        "dimensions": dims,
        "n_available": n_avail,
        "n_total": len(dims),
        "policies": [
            "数据不足时不评分, 而不是猜一个看起来不错的分数。",
            "缺失的维度会明确标成「无数据」, 不会渲染成 0 分。",
            "评分会按实际可用的维度归一化, 并在界面上标出「基于 N/5 维」。",
            "覆盖度不完整时, 训练强度会被自动封顶 —— 缺 HRV 不会给你派 VO2max 间歇。",
            "所有指标算法都基于公开文献, 源码可查可改。",
        ],
    }
