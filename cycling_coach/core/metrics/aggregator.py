"""指标聚合入口

对 Activity 算所有指标,返回结构化 dict,便于 DB 存 + API 返回
"""
from __future__ import annotations
import logging
from typing import Optional

from cycling_coach.data.parsers.schema import Activity
from . import power, hr, curve

logger = logging.getLogger(__name__)


def compute_metrics(
    activity: Activity,
    ftp: Optional[int] = None,
    max_hr: Optional[int] = None,
    lthr: Optional[int] = None,
) -> dict:
    """聚合计算所有指标

    V0.1.1 升级:
    - 加 power_zones (Coggan 7 区)
    - hr_zones 支持 LTHR 7 区(Karvonen),无 LTHR 兜底 max_hr 5 区
    - cadence_zones 改 4 区训练学标准
    """
    np_val = power.normalized_power(activity)

    # 🔴 V0.9.0-07: 原来直接用 `ftp` 算 IF/TSS, 而 `ftp` 在用户没测过的时候
    # 是 None(占位车手不再带假 250 之后)。于是:
    #     intensity_factor(np, None) -> None
    #     training_stress_score(...)  -> None
    # 结果: **用户导入训练成功, 但 TSS 是 None, PMC 判定"无负荷数据"**,
    # 界面上写"还没有带功率的训练记录" —— 而他明明刚导入了一条 200W 的训练。
    #
    # TSS 确实是 FTP 相对量(IF = NP/FTP), 没有基准就算不出来。
    # 但**我们本来就会估算 FTP**(`estimate_ftp`, 见下面), 只是一直没接上。
    #
    # 现在: 优先用真实 FTP, 没有就用估算值, 并在结果里标清楚用的是哪种 ——
    # 诚实但不把功能整个废掉。
    ftp_est = curve.estimate_ftp(activity) if not ftp else None
    ftp_for_calc = ftp or ftp_est
    tss_uses_estimated = bool(not ftp and ftp_est)

    if_val = power.intensity_factor(np_val, ftp_for_calc)
    tss_val = power.training_stress_score(np_val, if_val,
                                           activity.duration_s, ftp_for_calc)
    ef = power.efficiency_factor(np_val, activity.avg_hr)
    vi = power.variability_index(np_val, activity.avg_power)
    mmp = curve.mean_maximal_power(activity)
    pz = power.power_zones(activity, ftp_for_calc) if ftp_for_calc else {}
    hz = hr.hr_zones(activity, max_hr=max_hr, lthr=lthr)
    drift = hr.hr_drift(activity)
    cad_zones = curve.cadence_zones(activity)
    metrics = {
        "normalized_power": np_val,
        "intensity_factor": if_val,
        "tss": tss_val,
        "efficiency_factor": ef,
        "variability_index": vi,
        "power_curve": mmp,
        "power_zones": pz,
        "hr_zones": hz,
        "hr_drift": drift,
        "cadence_zones": cad_zones,
        "ftp_estimated": ftp_est,
        # 用了估算 FTP 时明确标记 —— 界面据此说明"基于估算值",
        # 而不是让用户以为这是基于实测 FTP 的结果
        "tss_uses_estimated_ftp": tss_uses_estimated,
        "ftp_used_for_tss": ftp_for_calc,
    }
    logger.info(
        f"指标聚合完成: NP={np_val}W IF={if_val} TSS={tss_val} VI={vi} "
        f"hr_zones_keys={list(hz.keys())} power_zones_keys={list(pz.keys())}"
    )
    return metrics
