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
        # V0.9.0: 补 ramp_rate 和状态中文标签。
        # 之前这两个没给, 模型就自己编了一个:
        #   "ramp_rate+0.00: 维持期, 没有在加量也没有掉量"
        # 而接口返回的是 -3.46 (负荷在下降, 减量周)。
        # **上下文缺一个字段, 模型就会用听起来合理的话补上。**
        "ramp_rate": _pick(pmc, "ramp_rate"),
        "status_label": _pick(pmc, "status_label"),
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
    # V0.9.0: 字段名原来是 `phase_type` / `label`, 而 PhaseDerivation 上
    # 实际叫 `suggested_type` / `suggested_label` —— **两个都取不到**。
    # 后果: AI 拿到的 phase 上下文恒为 {'phase_type': None, 'label': None},
    # 而这是**静默**的 —— 没有任何异常, 只是模型永远不知道用户在哪个阶段。
    # (V0.9.0 修 AI 上下文时我只加了 _pick() 兼容 dict/object, 没核对字段名。)
    if _pick(info, "suggested_type") == "unknown":
        # V0.9.0: derive_phase 在无数据时返回 unknown, 不要把它当成
        # 一个真实阶段喂给模型。
        return {
            "phase_type": None,
            "label": None,
            "data_insufficient": True,
            "note": "没有真实训练负荷数据, 无法判断训练阶段",
        }
    return {
        "phase_type": _pick(info, "suggested_type"),
        "label": _pick(info, "suggested_label"),
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
    ftp_w = latest.ftp_w if latest else athlete.ftp
    out = {
        "ftp_w": ftp_w,
        "test_date": latest.test_date.date().isoformat() if latest else None,
        "method": latest.method if latest else "默认",
    }
    # V0.9.0: 把功率区间表直接算好给模型。
    #
    # 实测: 上下文里只有 ftp_w=280 时, 模型自己算区间, 把
    # Z2 说成 "196-224W" (实际是 70%-80% FTP, 那是 Z3 节奏区;
    # 正确的 Z2 是 154-210W)。用户照着这个数骑, 以为是轻松恢复骑,
    # 实际一直在踩节奏区 —— **自信地给错训练强度, 比不给更伤**。
    #
    # 区间不该让模型心算: 应用这边本来就有权威实现
    # (core/metrics/power.py 的 Coggan 7 区), 直接喂进去。
    if ftp_w:
        out["zones_w"] = power_zone_ranges_w(ftp_w)
    return out


# Coggan 7 区的中文名。边界**不在这里定义** —— 从 core/metrics/power.py
# 的 COGGAN_7_ZONES 取, 保证 AI 上下文和用户界面永远同一套。
#
# V0.9.0 教训: 我第一版在这里自己写了一份 _COGGAN_BOUNDS,
# 而 core/metrics/power.py 里已经有一份。两份常量一定会漂移 ——
# 哪天有人调了 power.py 的边界, AI 还在按旧的给建议, 而且两边都"看着对"。
# 界面显示 Z2 154-210W 而 AI 说 196-224W, 用户会以为软件有 bug。
_COGGAN_ZH = {
    "Z1": "主动恢复", "Z2": "耐力", "Z3": "节奏", "Z4": "阈值",
    "Z5": "无氧氧", "Z6": "无氧", "Z7": "神经肌肉",
}


def power_zone_ranges_w(ftp: int) -> list[dict]:
    """把 Coggan 7 区换算成瓦数, 供 AI 上下文直接使用。

    边界来自 core/metrics/power.py 的 COGGAN_7_ZONES —— **不另立一份**。
    这里的任务只做"比例 -> 瓦数"的换算和中文命名。
    """
    from cycling_coach.core.metrics.power import COGGAN_7_ZONES

    out: list[dict] = []
    for z in COGGAN_7_ZONES:
        code = z["code"]
        lo = int(round(ftp * z["lo"]))
        # 无上限判定**跟着数据走**, 不硬编码区号。
        # COGGAN_7_ZONES 里 Z7 的 hi 是 9.99 这个哨兵值; 之前写 code=="Z7",
        # 一旦加 Z8 或改了哨兵, 那行会静默翻出 2797W 的假上限 ——
        # 正是这里要避免的事。
        unbounded = z["hi"] >= 9.99
        hi = None if unbounded else int(round(ftp * z["hi"]))
        out.append({
            "zone": code,
            "name_en": z["name"],
            "name_cn": _COGGAN_ZH.get(code, z["name"]),
            "pct": (f">{int(z['lo']*100)}%" if unbounded
                    else f"{int(z['lo']*100)}-{int(z['hi']*100)}%"),
            "watts_from": lo,
            "watts_to": hi,
            "watts": f">{lo}W" if hi is None else f"{lo}-{hi}W",
        })
    return out


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
