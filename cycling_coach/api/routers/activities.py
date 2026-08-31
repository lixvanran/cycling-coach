"""/api/activities - 训练管理"""
from __future__ import annotations
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, BackgroundTasks, Query
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, defer

from cycling_coach.config.config import settings
from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import Activity
from cycling_coach.data.parsers import FitParser, TcxParser, WkoCsvParser
from cycling_coach.data.parsers.schema import Activity as PydanticActivity, Sample
from cycling_coach.core.metrics import compute_metrics
from cycling_coach.core.metrics.curve import mean_maximal_power, estimate_ftp
from cycling_coach.core.metrics.power import power_zones_detailed, wbal_analysis, detect_cp_3param
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.pmc import recompute_pmc
from ._activities_shared import (
    ALLOWED_EXTS, AnalyzeResponse, downsample_samples, run_analyze_task,
)
from cycling_coach.ai.tools import analyze_activity_tool

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/activities", tags=["activities"])

# 上传白名单
# ALLOWED_EXTS 在 _activities_shared.py


# ---------- Schema ----------

class ActivitySummary(BaseModel):
    id: int
    start_time: datetime
    duration_s: int
    distance_m: float | None
    avg_power: int | None
    normalized_power: int | None
    tss: int | None
    avg_hr: int | None
    avg_cadence: int | None
    total_elevation_gain: float | None
    device: str | None
    source: str
    has_report: bool
    rpe: int | None = None  # V0.6.1 主观疲劳 (Borg CR-10, 1-10)
    rpe_note: str | None = None  # V0.6.1 RPE 标签

    class Config:
        from_attributes = True


class ActivityDetail(ActivitySummary):
    max_power: int | None
    max_hr: int | None
    max_speed: float | None
    calories: int | None
    metrics: dict | None
    samples: list | None
    laps: list | None
    report: str | None
    report_status: str


class AnalyzeRequest(BaseModel):
    focus: str | None = None



# ---------- API ----------

@router.post("/upload")
async def upload_activity(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """上传 FIT 文件 → 解析 + 入库 + 异步生成 AI 报告"""
    if not file.filename:
        raise HTTPException(400, "未提供文件名")
    ext = Path(file.filename).suffix
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"不支持的文件类型: {ext}(仅 .fit/.tcx/.csv)")

    # 落盘 (V0.7.5.2 修: 路径遍历 — basename + 解析后断言)
    workspace = Path(settings.workspace_dir).resolve()
    input_dir = workspace / "input" / datetime.now().strftime("%Y%m%d-%H%M%S")
    input_dir.mkdir(parents=True, exist_ok=True)
    # basename 去路径前缀 (../foo.fit → foo.fit, C:\evil\foo.fit → foo.fit)
    safe_basename = Path(file.filename).name
    if not safe_basename or safe_basename.startswith("."):
        raise HTTPException(400, f"非法文件名: {file.filename!r}")
    file_path = (input_dir / safe_basename).resolve()
    # 断言仍在 input_dir 内 (defense-in-depth)
    try:
        file_path.relative_to(input_dir.resolve())
    except ValueError:
        raise HTTPException(400, f"文件路径不安全: {safe_basename!r}")
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    logger.info(f"文件已保存: {file_path} ({file_path.stat().st_size} bytes)")

    # V0.7.5.3 DEV-4: 解析跑在 worker thread (asyncio.to_thread), EventLoop 不阻塞
    # 仍同步等结果 (用户看到 loading), 但 server 能继续处理其他请求
    import asyncio
    try:
        ext_lower = ext.lower()
        if ext_lower == ".fit":
            activity = await asyncio.to_thread(FitParser().parse_file, file_path)
        elif ext_lower == ".tcx":
            activity = await asyncio.to_thread(TcxParser().parse_file, file_path)
        elif ext_lower == ".csv":
            activity = await asyncio.to_thread(WkoCsvParser().parse_file, file_path)
        else:
            raise HTTPException(400, f"不支持的文件类型: {ext}")
    except HTTPException:
        raise
    except ValueError as e:
        logger.warning(f"解析失败(内容): {e}")
        raise HTTPException(
            415,
            f"文件无法解析 (可能损坏或码表固件不兼容): {e}"
        )
    except Exception as e:
        logger.exception(f"解析失败: {e}")
        raise HTTPException(400, f"解析失败: {e}")

    # 指标计算 (也用 to_thread, NP/W'bal/CP 都是 CPU 密集)
    athlete = profile_store.get_or_create_athlete(db)
    metrics = await asyncio.to_thread(
        compute_metrics,
        activity,
        ftp=athlete.ftp,
        max_hr=athlete.max_hr,
        lthr=athlete.lthr,
    )

    # 入库
    db_activity = Activity(
        athlete_id=athlete.id,
        source="fit",
        file_name=file.filename,
        file_path=str(file_path),
        start_time=activity.start_time.replace(tzinfo=None) if activity.start_time.tzinfo else activity.start_time,
        duration_s=activity.duration_s,
        distance_m=activity.distance_m,
        total_elevation_gain=activity.total_elevation_gain,
        avg_power=activity.avg_power,
        max_power=activity.max_power,
        avg_hr=activity.avg_hr,
        max_hr=activity.max_hr,
        avg_cadence=activity.avg_cadence,
        avg_speed=activity.avg_speed,
        max_speed=activity.max_speed,
        calories=activity.calories,
        device=activity.device,
        metrics=metrics,
        # V0.7.5.3 DEV-6: 关键指标单独列 (tss/np/if 已有索引)
        tss=metrics.get("tss"),
        normalized_power=metrics.get("normalized_power"),
        intensity_factor=metrics.get("intensity_factor"),
        # V0.7.1: samples 智能截断 — 短课 (<4h) 全存, 长课 (>4h) 降采样到 5s 间隔
        # 7200 = 2h 上限太短, Gran Fondo 8h 会被截掉后半
        samples_json=downsample_samples(activity.samples, max_samples=14400),
        laps_json=[lap.model_dump() for lap in activity.laps],
        report_status="pending",
    )
    db.add(db_activity)
    db.commit()
    db.refresh(db_activity)
    logger.info(f"活动入库: id={db_activity.id}, NP={metrics.get('normalized_power')}")

    # 增量更新 PMC(从活动日期向前回溯 365 天重算)
    try:
        anchor = db_activity.start_time.date() if hasattr(db_activity.start_time, 'date') else db_activity.start_time
        updated = recompute_pmc(db, athlete.id, anchor_date=anchor)
        logger.info(f"PMC 更新: {updated} 天")
    except Exception as e:
        # PMC 更新失败不影响主流程
        logger.warning(f"PMC 更新失败(非致命): {e}")

    # 异步生成报告
    if background_tasks is not None:
        background_tasks.add_task(run_analyze_task, db_activity.id, None)

    return {
        "ok": True,
        "id": db_activity.id,
        "metrics": metrics,
        "report_status": "pending",
    }




@router.get("")
def list_activities(
    date_from: Optional[str] = Query(None, description="起始日期 YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="结束日期 YYYY-MM-DD"),
    min_distance_km: Optional[float] = Query(None, ge=0),
    max_distance_km: Optional[float] = Query(None, ge=0),
    min_tss: Optional[int] = Query(None, ge=0),
    max_tss: Optional[int] = Query(None, ge=0),
    min_normalized_power: Optional[int] = Query(None, ge=0),
    max_normalized_power: Optional[int] = Query(None, ge=0),
    min_avg_power: Optional[int] = Query(None, ge=0),
    max_avg_power: Optional[int] = Query(None, ge=0),
    min_duration_min: Optional[int] = Query(None, ge=0),
    max_duration_min: Optional[int] = Query(None, ge=0),
    min_avg_hr: Optional[int] = Query(None, ge=0),
    max_avg_hr: Optional[int] = Query(None, ge=0),
    source: Optional[str] = Query(None, description="fit/tcx/csv/mock"),
    has_report: Optional[bool] = Query(None, description="是否已生成 AI 报告"),
    sort: str = Query("start_time", description="排序字段"),
    order: str = Query("desc", description="asc/desc"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """活动列表(多维过滤 + 排序 + 分页)

    V0.3.4:对标 TP Activity Search
    - 日期范围 / 距离 / TSS / 平均功率 / 时长 / 心率 多维过滤
    - 按 start_time / duration_s / tss / distance_m / avg_power 排序
    - 分页 offset+limit
    - 返回 total + 聚合统计,前端可一次画完顶部统计卡
    """
    # V0.7.6: defer 大字段 (samples_json 800KB+, laps_json, metrics)
    # 列表端不需要这些,只在详情端用 → 显著降低 I/O (18 行 ≈ 11MB → 几百 KB)
    q = (
        db.query(Activity)
        .options(
            defer(Activity.samples_json),
            defer(Activity.laps_json),
            defer(Activity.metrics),
            defer(Activity.report),
        )
    )
    if date_from:
        try:
            q = q.filter(Activity.start_time >= datetime.fromisoformat(date_from))
        except ValueError:
            raise HTTPException(400, f"date_from 格式错误: {date_from}")
    if date_to:
        try:
            q = q.filter(Activity.start_time <= datetime.fromisoformat(date_to + "T23:59:59"))
        except ValueError:
            raise HTTPException(400, f"date_to 格式错误: {date_to}")
    if min_distance_km is not None:
        q = q.filter(Activity.distance_m >= min_distance_km * 1000)
    if max_distance_km is not None:
        q = q.filter(Activity.distance_m <= max_distance_km * 1000)
    if min_duration_min is not None:
        q = q.filter(Activity.duration_s >= min_duration_min * 60)
    if max_duration_min is not None:
        q = q.filter(Activity.duration_s <= max_duration_min * 60)
    if min_avg_power is not None:
        q = q.filter(Activity.avg_power >= min_avg_power)
    if max_avg_power is not None:
        q = q.filter(Activity.avg_power <= max_avg_power)
    if min_avg_hr is not None:
        q = q.filter(Activity.avg_hr >= min_avg_hr)
    if max_avg_hr is not None:
        q = q.filter(Activity.avg_hr <= max_avg_hr)
    if source:
        q = q.filter(Activity.source == source)
    if has_report is not None:
        if has_report:
            q = q.filter(Activity.report.isnot(None))
        else:
            q = q.filter(Activity.report.is_(None))

    # V0.7.6: tss / normalized_power 走独立列 + 索引 (不再 Python 端 filter metrics JSON)
    if min_tss is not None:
        q = q.filter(Activity.tss >= min_tss)
    if max_tss is not None:
        q = q.filter(Activity.tss <= max_tss)
    if min_normalized_power is not None:
        q = q.filter(Activity.normalized_power >= min_normalized_power)
    if max_normalized_power is not None:
        q = q.filter(Activity.normalized_power <= max_normalized_power)

    # V0.7.6: tss / np 排序也走独立列 (ix_activities_tss / ix_activities_normalized_power)
    if sort == "tss":
        q = q.order_by(Activity.tss.desc() if order == "desc" else Activity.tss.asc())
    elif sort == "normalized_power":
        q = q.order_by(Activity.normalized_power.desc() if order == "desc" else Activity.normalized_power.asc())

    # V0.7.6: 一次性 count() + 拉列表,SQL 端 limit/offset (defer 仍生效)
    # 用一个分开的 count query 以便返回 total
    total = q.with_entities(func.count(Activity.id)).scalar() or 0
    activities_all = q.limit(limit).offset(offset).all()

    # V0.7.6: 聚合统计改读独立列 (metrics 已 defer, 避免触发 lazy load)
    total_dur = sum(a.duration_s for a in activities_all)
    total_tss_agg = sum((a.tss or 0) for a in activities_all)
    total_dist = sum(a.distance_m or 0 for a in activities_all)
    aggregate = {
        "count": total,
        "total_duration_s": int(total_dur),
        "total_tss": int(total_tss_agg),
        "total_distance_m": float(total_dist),
    }

    return {
        "activities": [_to_summary(a) for a in activities_all],
        "total": total,
        "offset": offset,
        "limit": limit,
        "aggregate": aggregate,
    }


@router.get("/{activity_id}/power-curve")
def get_power_curve(
    activity_id: int,
    db: Session = Depends(get_db),
):
    """功率曲线 (Mean Maximal Power / MMP)

    V0.3.4:对标 TP Power Curve
    返回各时长的最大平均功率:
    - 5s / 10s / 30s / 60s: 冲刺 + 重复冲刺
    - 2min / 5min: 神经肌肉 + 5 分钟能力
    - 10min / 20min: 阈值
    - 60min: ≈ FTP
    """
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")
    samples = a.samples_json or []
    if not samples:
        return {
            "activity_id": activity_id,
            "points": [],
            "ftp_estimate": None,
            "key_durations": {},
        }
    # 转 Pydantic Activity 给 metrics 用
    pyd = PydanticActivity(
        source=a.source or "fit",
        start_time=a.start_time,
        duration_s=a.duration_s,
        distance_m=a.distance_m,
        total_elevation_gain=a.total_elevation_gain,
        avg_power=a.avg_power,
        max_power=a.max_power,
        avg_hr=a.avg_hr,
        max_hr=a.max_hr,
        avg_cadence=a.avg_cadence,
        avg_speed=a.avg_speed,
        max_speed=a.max_speed,
        calories=a.calories,
        device=a.device,
        samples=[Sample(**s) if isinstance(s, dict) else s for s in samples],
    )
    mmp = mean_maximal_power(pyd)
    ftp_est = estimate_ftp(pyd)
    # 转成 [{duration_s, watts}, ...] + key_durations 友好格式
    durations_s = [5, 10, 30, 60, 120, 300, 600, 1200, 3600]
    points = [{"duration_s": d, "watts": mmp.get(f"{d}s")} for d in durations_s if f"{d}s" in mmp]
    # 关键时长(可读性)
    key = {
        "5s": mmp.get("5s"),
        "1min": mmp.get("60s"),
        "5min": mmp.get("300s"),
        "20min": mmp.get("1200s"),
        "60min": mmp.get("3600s"),
    }
    return {
        "activity_id": activity_id,
        "points": points,
        "ftp_estimate": ftp_est,
        "key_durations": key,
        "weight_kg": a.metrics.get("weight_kg") if a.metrics else None,
    }


@router.get("/{activity_id}/power-zones-detailed")
def get_power_zones_detailed(
    activity_id: int,
    ftp: Optional[int] = Query(None, description="FTP (W), 不传则用 athlete profile"),
    db: Session = Depends(get_db),
):
    """Coggan 7 区分布详细分析 (V0.6 GoldenCheetah 对标)

    返回:
    - 7 区每区: seconds, %time, %distance, avg_power, max_power, kJ
    - summary: polarization_index, sweet_spot_seconds, above_ftp_seconds
    """
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")

    # FTP 解析: query > athlete profile > None
    if ftp is None:
        prof = profile_store.get_profile()
        ftp = prof.ftp_w if prof and prof.ftp_w else None
    if not ftp:
        raise HTTPException(400, "FTP 未设置, 请在个人资料里配置或传 ?ftp=N")

    samples_json = a.samples_json or []
    if not samples_json:
        return {
            "activity_id": activity_id,
            "ftp": ftp,
            "total_seconds": 0,
            "total_distance_km": 0.0,
            "total_kj": 0.0,
            "zones": [],
            "summary": {
                "polarization_index": 0.0,
                "sweet_spot_seconds": 0,
                "above_ftp_seconds": 0,
                "easy_seconds": 0,
                "hard_seconds": 0,
            },
        }
    pyd = PydanticActivity(
        source=a.source or "fit",
        start_time=a.start_time,
        duration_s=a.duration_s,
        distance_m=a.distance_m,
        total_elevation_gain=a.total_elevation_gain,
        avg_power=a.avg_power,
        max_power=a.max_power,
        avg_hr=a.avg_hr,
        max_hr=a.max_hr,
        avg_cadence=a.avg_cadence,
        avg_speed=a.avg_speed,
        max_speed=a.max_speed,
        calories=a.calories,
        device=a.device,
        samples=[Sample(**s) if isinstance(s, dict) else s for s in samples_json],
    )
    result = power_zones_detailed(pyd, ftp=ftp)
    result["activity_id"] = activity_id
    return result


@router.get("/{activity_id}/wbal")
def get_wbal(
    activity_id: int,
    cp: Optional[int] = Query(None, description="Critical Power (W), 不传则估算"),
    w_prime: Optional[int] = Query(20000, description="W\' (J), 默认 20 kJ"),
    db: Session = Depends(get_db),
):
    """W\'bal 详细分析 (V0.6 GoldenCheetah 对标, Skiba 模型)

    返回:
    - wbal_curve: 每秒 W\'bal 数组
    - min_wbal + min_wbal_at_s
    - depleted / depletion_at_s
    - critical_events: W\'bal < 30% W\' 的段
    - match_potential: 0-1
    """
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")

    samples_json = a.samples_json or []
    if not samples_json:
        return {
            "activity_id": activity_id,
            "cp": cp or 0,
            "w_prime": w_prime,
            "wbal_curve": [],
            "min_wbal": 0,
            "min_wbal_at_s": 0,
            "min_wbal_pct": 0.0,
            "depleted": False,
            "depletion_at_s": None,
            "critical_events": [],
            "match_potential": 0.0,
        }
    sample_objs = [Sample(**s) if isinstance(s, dict) else s for s in samples_json]

    # CP 解析: query > profile FTP > 估算
    if cp is None:
        prof = profile_store.get_profile()
        if prof and prof.ftp_w:
            cp = prof.ftp_w
        else:
            # 尝试从样本估算 CP
            cp3 = detect_cp_3param(sample_objs)
            if "cp_estimated" in cp3:
                cp = cp3["cp_estimated"]
    if not cp or cp <= 0:
        raise HTTPException(400, "CP 无法确定, 请传 ?cp=N 或先在个人资料配置 FTP")

    result = wbal_analysis(sample_objs, cp=cp, w_prime=w_prime)
    result["activity_id"] = activity_id
    return result


@router.get("/{activity_id}/decoupling")
def get_decoupling(
    activity_id: int,
    db: Session = Depends(get_db),
):
    """Pa:HR Decoupling (V0.6.1 — GC 杀手锏)

    心率-功率解耦: 衡量有氧效率衰减
    """
    from cycling_coach.core.metrics.hr import pa_hr_decoupling, aerobic_decoupling_trend

    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")
    samples_json = a.samples_json or []
    if not samples_json:
        return {
            "activity_id": activity_id,
            "applicable": False,
            "error": "no_samples",
        }
    pyd = PydanticActivity(
        source=a.source or "fit",
        start_time=a.start_time,
        duration_s=a.duration_s,
        distance_m=a.distance_m,
        total_elevation_gain=a.total_elevation_gain,
        avg_power=a.avg_power,
        max_power=a.max_power,
        avg_hr=a.avg_hr,
        max_hr=a.max_hr,
        avg_cadence=a.avg_cadence,
        avg_speed=a.avg_speed,
        max_speed=a.max_speed,
        calories=a.calories,
        device=a.device,
        samples=[Sample(**s) if isinstance(s, dict) else s for s in samples_json],
    )
    result = pa_hr_decoupling(pyd)
    result["activity_id"] = activity_id
    if result.get("applicable"):
        result["trend"] = aerobic_decoupling_trend(pyd.samples)
    return result


@router.get("/{activity_id}/cp-estimate")
def get_cp_estimate(
    activity_id: int,
    db: Session = Depends(get_db),
):
    """CP 3 参数自动估算 (V0.6 GoldenCheetah 对标)

    返回: cp_estimated, w_prime_estimated, confidence, p60/p180 watts
    """
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")

    samples_json = a.samples_json or []
    if not samples_json:
        return {
            "activity_id": activity_id,
            "error": "no_power_data",
        }
    sample_objs = [Sample(**s) if isinstance(s, dict) else s for s in samples_json]
    result = detect_cp_3param(sample_objs)
    result["activity_id"] = activity_id
    return result


@router.patch("/{activity_id}/rpe")
def update_rpe(
    activity_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    """更新 RPE 主观疲劳 (Borg CR-10, 1-10)

    请求体: { "rpe": 7, "rpe_note": "腿有点沉" }
    训练学: Borg CR-10 (Category-Ratio scale 0-10)
      1-2  几乎无感 (rest day / active recovery)
      3-4  轻松 (Z1-Z2 endurance)
      5-6  中等 (Z3 tempo / sweet spot)
      7-8  困难 (Z4 threshold)
      9-10 极限 (Z5+ VO2max / neuromuscular)
    """
    a = db.get(Activity, activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")
    rpe = payload.get("rpe")
    if rpe is not None:
        try:
            rpe = int(rpe)
        except (TypeError, ValueError):
            raise HTTPException(400, "rpe 必须是整数")
        if rpe < 0 or rpe > 10:
            raise HTTPException(400, "rpe 必须在 0-10 之间 (Borg CR-10)")
    a.rpe = rpe
    a.rpe_note = (payload.get("rpe_note") or None) if rpe is not None else None
    db.commit()
    return {"ok": True, "activity_id": activity_id, "rpe": a.rpe, "rpe_note": a.rpe_note}


@router.get("/compare")
def compare_activities(
    ids: str = Query(..., description="活动 ID 列表, 逗号分隔, 如 1,2,3"),
    db: Session = Depends(get_db),
):
    """多活动对比 (V0.6 GoldenCheetah 对标)

    返回:
    {
      "activities": [
        {
          "id": 1,
          "name": "...",
          "start_time": "...",
          "duration_s": 3600,
          "distance_km": 42.5,
          "metrics": { NP, IF, TSS, VI, EF, ... },
          "mmp": { "5s": 480, "60s": 280, "300s": 250, "1200s": 220 },
          "zones": { "Z1": ..., "Z7": ... },
        }
      ],
      "comparison": {
        "metrics_table": [
          { "label": "时长", "values": ["1h 30m", "1h 45m", ...] },
          { "label": "NP", "values": [245, 250, ...] },
          ...
        ],
        "best_by_metric": {
          "normalized_power": 2,         # 第 3 个活动 NP 最高
          "tss_per_hour": 0,
          ...
        }
      }
    }
    """
    try:
        activity_ids = [int(x) for x in ids.split(",") if x.strip()]
    except ValueError:
        raise HTTPException(400, "ids 格式错误, 应为逗号分隔的整数")

    if not activity_ids:
        raise HTTPException(400, "ids 不能为空")
    if len(activity_ids) > 10:
        raise HTTPException(400, "最多对比 10 个活动")

    activities_data = []
    for aid in activity_ids:
        a = db.get(Activity, aid)
        if not a:
            continue  # 跳过不存在的 ID

        samples_json = a.samples_json or []
        mmp: dict[str, int] = {}
        pyd = None
        if samples_json:
            pyd = PydanticActivity(
                source=a.source or "fit",
                start_time=a.start_time,
                duration_s=a.duration_s,
                distance_m=a.distance_m,
                total_elevation_gain=a.total_elevation_gain,
                avg_power=a.avg_power,
                max_power=a.max_power,
                avg_hr=a.avg_hr,
                max_hr=a.max_hr,
                avg_cadence=a.avg_cadence,
                avg_speed=a.avg_speed,
                max_speed=a.max_speed,
                calories=a.calories,
                device=a.device,
                samples=[Sample(**s) if isinstance(s, dict) else s for s in samples_json],
            )
            mmp = mean_maximal_power(pyd)

        # Power zones
        pz = a.metrics.get("power_zones", {}) if a.metrics else {}
        # 时长
        h = a.duration_s // 3600
        m = (a.duration_s % 3600) // 60
        duration_str = f"{h}h{m:02d}m" if h > 0 else f"{m}m"

        # TSS per hour
        tss_per_hour = 0.0
        if a.metrics and a.metrics.get("tss") and a.duration_s > 0:
            tss_per_hour = round(a.metrics.get("tss") * 3600.0 / a.duration_s, 1)

        activities_data.append({
            "id": a.id,
            "name": a.file_name or f"Activity {a.id}",
            "start_time": a.start_time.isoformat() if a.start_time else None,
            "duration_s": a.duration_s,
            "duration_str": duration_str,
            "distance_km": round((a.distance_m or 0) / 1000.0, 2),
            "avg_power": a.avg_power,
            "avg_hr": a.avg_hr,
            "avg_cadence": a.avg_cadence,
            "tss": a.metrics.get("tss") if a.metrics else None,
            "tss_per_hour": tss_per_hour,
            "metrics": {
                "normalized_power": a.metrics.get("normalized_power") if a.metrics else None,
                "intensity_factor": a.metrics.get("intensity_factor") if a.metrics else None,
                "variability_index": a.metrics.get("variability_index") if a.metrics else None,
                "efficiency_factor": a.metrics.get("efficiency_factor") if a.metrics else None,
                "ftp_estimated": a.metrics.get("ftp_estimated") if a.metrics else None,
            },
            "mmp": {k: mmp.get(k) for k in ["5s", "30s", "60s", "120s", "300s", "600s", "1200s", "3600s"] if mmp.get(k) is not None},
            "zones": pz,
        })

    if not activities_data:
        raise HTTPException(404, "所有活动 ID 都不存在")

    # 构造对比表
    metrics_table = [
        {"label": "日期", "values": [a["start_time"][:10] if a["start_time"] else "—" for a in activities_data]},
        {"label": "时长", "values": [a["duration_str"] for a in activities_data]},
        {"label": "距离 (km)", "values": [a["distance_km"] for a in activities_data]},
        {"label": "平均功率 (W)", "values": [a["avg_power"] for a in activities_data]},
        {"label": "NP (W)", "values": [a["metrics"]["normalized_power"] for a in activities_data]},
        {"label": "IF", "values": [a["metrics"]["intensity_factor"] for a in activities_data]},
        {"label": "TSS", "values": [a["tss"] for a in activities_data]},
        {"label": "TSS/h", "values": [a["tss_per_hour"] for a in activities_data]},
        {"label": "VI", "values": [a["metrics"]["variability_index"] for a in activities_data]},
        {"label": "EF", "values": [a["metrics"]["efficiency_factor"] for a in activities_data]},
        {"label": "平均心率 (bpm)", "values": [a["avg_hr"] for a in activities_data]},
        {"label": "平均踏频 (rpm)", "values": [a["avg_cadence"] for a in activities_data]},
        {"label": "5s 峰值 (W)", "values": [a["mmp"].get("5s") for a in activities_data]},
        {"label": "1min 峰值 (W)", "values": [a["mmp"].get("60s") for a in activities_data]},
        {"label": "5min 峰值 (W)", "values": [a["mmp"].get("300s") for a in activities_data]},
        {"label": "20min 峰值 (W)", "values": [a["mmp"].get("1200s") for a in activities_data]},
    ]

    # Best by metric (找最大值/最小值的 index)
    best_by_metric: dict[str, int] = {}
    # 越大越好 (功率类)
    for label, key in [
        ("normalized_power", "NP (W)"),
        ("tss", "TSS"),
        ("tss_per_hour", "TSS/h"),
        ("5s", "5s 峰值 (W)"),
        ("60s", "1min 峰值 (W)"),
        ("300s", "5min 峰值 (W)"),
        ("1200s", "20min 峰值 (W)"),
    ]:
        row = next((r for r in metrics_table if r["label"] == key), None)
        if row and any(v is not None for v in row["values"]):
            valid_idx = [i for i, v in enumerate(row["values"]) if v is not None]
            if valid_idx:
                best_idx = max(valid_idx, key=lambda i: row["values"][i] or 0)
                best_by_metric[label] = best_idx

    return {
        "activities": activities_data,
        "comparison": {
            "metrics_table": metrics_table,
            "best_by_metric": best_by_metric,
            "count": len(activities_data),
        },
    }


@router.get("/{activity_id}", response_model=ActivityDetail)
def get_activity(activity_id: int, db: Session = Depends(get_db)):
    """活动详情(含 1Hz 样本 + AI 报告)"""
    a = db.query(Activity).get(activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")
    return _to_detail(a)


@router.post("/{activity_id}/analyze", response_model=AnalyzeResponse)
def trigger_analyze(
    activity_id: int,
    req: AnalyzeRequest = AnalyzeRequest(),
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
):
    """重新生成 AI 报告"""
    a = db.query(Activity).get(activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")
    a.report_status = "analyzing"
    db.commit()
    if background_tasks is not None:
        background_tasks.add_task(run_analyze_task, activity_id, req.focus)
    return {"ok": True, "report": None, "reason": "已加入后台队列"}


@router.delete("/{activity_id}")
def delete_activity(activity_id: int, db: Session = Depends(get_db)):
    a = db.query(Activity).get(activity_id)
    if not a:
        raise HTTPException(404, f"活动 {activity_id} 不存在")
    db.delete(a)
    db.commit()
    return {"ok": True}


# ---------- helpers ----------

def downsample_samples(samples: list, max_samples: int = 14400) -> list:
    """V0.7.1: 智能降采样, 避免长活动 (Gran Fondo 8h) DB 膨胀

    策略:
    - len <= max_samples: 全存
    - len > max_samples: 均匀降采样到 max_samples (step = ceil(n/max))

    max_samples=14400 = 4h @ 1Hz
    8h 活动会被降采样到 5s 间隔 (14400/28800=0.5 → step 2)
    训练学计算 (NP/W'bal/7区) 仍可用, 但 GPS/海拔会丢细节
    """
    if not samples:
        return []
    if len(samples) <= max_samples:
        return [s.model_dump() if hasattr(s, "model_dump") else s for s in samples]
    step = max(1, len(samples) // max_samples)
    out = []
    for i in range(0, len(samples), step):
        s = samples[i]
        out.append(s.model_dump() if hasattr(s, "model_dump") else s)
    return out


def _to_summary(a: Activity) -> ActivitySummary:
    # V0.7.6: 列表端 metrics 已 defer,改读独立列 (tss / normalized_power)
    return ActivitySummary(
        id=a.id,
        start_time=a.start_time,
        duration_s=a.duration_s,
        distance_m=a.distance_m,
        avg_power=a.avg_power,
        normalized_power=a.normalized_power,
        tss=int(a.tss) if a.tss is not None else None,
        avg_hr=a.avg_hr,
        avg_cadence=a.avg_cadence,
        total_elevation_gain=a.total_elevation_gain,
        device=a.device,
        source=a.source,
        has_report=bool(a.report),
        rpe=a.rpe,
        rpe_note=a.rpe_note,
    )


def _to_detail(a: Activity) -> ActivityDetail:
    s = _to_summary(a)
    return ActivityDetail(
        **s.model_dump(),
        max_power=a.max_power,
        max_hr=a.max_hr,
        max_speed=a.max_speed,
        calories=a.calories,
        metrics=a.metrics,
        samples=a.samples_json or [],
        laps=a.laps_json or [],
        report=a.report,
        report_status=a.report_status,
    )
