"""V0.8.0: Activity 业务层

V0.7.x: activities.py 863 行, 业务全在 router
V0.8.0: 抽到 ActivityService, router 只剩 ~30 行的端点定义

覆盖端点:
- POST /api/activities/upload            upload_activity
- GET  /api/activities                    list_activities
- GET  /api/activities/compare            compare_activities
- GET  /api/activities/{id}               get_activity
- POST /api/activities/{id}/analyze       trigger_analyze
- DELETE /api/activities/{id}             delete_activity
- PATCH /api/activities/{id}/rpe          update_rpe
- GET  /api/activities/{id}/power-curve           get_power_curve
- GET  /api/activities/{id}/power-zones-detailed  get_power_zones_detailed
- GET  /api/activities/{id}/wbal                   get_wbal
- GET  /api/activities/{id}/decoupling             get_decoupling
- GET  /api/activities/{id}/cp-estimate            get_cp_estimate
"""
from __future__ import annotations
import asyncio
import json
import logging
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any

from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session, defer

from cycling_coach.config.config import settings
from cycling_coach.core.exceptions import NotFoundError, ValidationError
from cycling_coach.core.metrics import compute_metrics
from cycling_coach.core.metrics.curve import mean_maximal_power, estimate_ftp
from cycling_coach.core.metrics.power import (
    power_zones_detailed, wbal_analysis, detect_cp_3param,
)
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.pmc import recompute_pmc
from cycling_coach.data.parsers import FitParser, TcxParser, WkoCsvParser
from cycling_coach.data.parsers.schema import Activity as PydanticActivity, Sample
from cycling_coach.data.sqlite.models import Activity as DBActivity

logger = logging.getLogger(__name__)


# ============== DTO ==============

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
    rpe: int | None = None
    rpe_note: str | None = None

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


class AnalyzeResponse(BaseModel):
    ok: bool
    activity_id: int
    report: str | None = None
    report_status: str | None = None
    reason: str | None = None


class ActivityFilters(BaseModel):
    """活动列表过滤器 (Pydantic, 直接当 router Depends)"""
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    min_distance_km: Optional[float] = None
    max_distance_km: Optional[float] = None
    min_tss: Optional[int] = None
    max_tss: Optional[int] = None
    min_normalized_power: Optional[int] = None
    max_normalized_power: Optional[int] = None
    min_avg_power: Optional[int] = None
    max_avg_power: Optional[int] = None
    min_duration_min: Optional[int] = None
    max_duration_min: Optional[int] = None
    min_avg_hr: Optional[int] = None
    max_avg_hr: Optional[int] = None
    source: Optional[str] = None
    has_report: Optional[bool] = None
    sort: str = "start_time"
    order: str = "desc"
    limit: int = 50
    offset: int = 0


# ============== Service ==============

ALLOWED_EXTS = {".fit", ".tcx", ".csv"}


class ActivityService:
    """活动业务服务

    所有方法接收基本参数, 返回 dict / 模型, 不抛 HTTPException
    业务异常用 NotFoundError / ValidationError
    """
    def __init__(self, db: Session):
        self.db = db

    # ---------- 解析 + 入库 ----------

    async def upload(
        self,
        filename: str,
        file_bytes: bytes,
        background_tasks: Optional[Any] = None,
    ) -> dict:
        """上传 + 解析 + 入库 + 异步生成报告

        Args:
            filename: 原始文件名 (带扩展名)
            file_bytes: 文件字节内容
            background_tasks: FastAPI BackgroundTasks, 用于异步跑 AI 报告
        """
        if not filename:
            raise ValidationError("未提供文件名")
        ext = Path(filename).suffix
        if ext.lower() not in ALLOWED_EXTS:
            raise ValidationError(f"不支持的文件类型: {ext}(仅 .fit/.tcx/.csv)")

        # 落盘
        workspace = Path(settings.workspace_dir).resolve()
        input_dir = workspace / "input" / datetime.now().strftime("%Y%m%d-%H%M%S")
        input_dir.mkdir(parents=True, exist_ok=True)
        safe_basename = Path(filename).name
        if not safe_basename or safe_basename.startswith("."):
            raise ValidationError(f"非法文件名: {filename!r}")
        file_path = (input_dir / safe_basename).resolve()
        try:
            file_path.relative_to(input_dir.resolve())
        except ValueError:
            raise ValidationError(f"文件路径不安全: {safe_basename!r}")
        with open(file_path, "wb") as f:
            f.write(file_bytes)
        logger.info(f"文件已保存: {file_path} ({file_path.stat().st_size} bytes)")

        # 解析
        ext_lower = ext.lower()
        try:
            if ext_lower == ".fit":
                activity = await asyncio.to_thread(FitParser().parse_file, file_path)
            elif ext_lower == ".tcx":
                activity = await asyncio.to_thread(TcxParser().parse_file, file_path)
            elif ext_lower == ".csv":
                activity = await asyncio.to_thread(WkoCsvParser().parse_file, file_path)
            else:
                raise ValidationError(f"不支持的文件类型: {ext}")
        except ValueError as e:
            logger.warning(f"解析失败(内容): {e}")
            raise ValidationError(f"文件无法解析 (可能损坏或码表固件不兼容): {e}")
        except Exception as e:
            logger.exception(f"解析失败: {e}")
            raise ValidationError(f"解析失败: {e}")

        # 指标计算
        athlete = profile_store.get_or_create_athlete(self.db)
        metrics = await asyncio.to_thread(
            compute_metrics,
            activity,
            ftp=athlete.ftp,
            max_hr=athlete.max_hr,
            lthr=athlete.lthr,
        )

        # 入库
        db_activity = DBActivity(
            athlete_id=athlete.id,
            source="fit",
            file_name=filename,
            file_path=str(file_path),
            start_time=activity.start_time.replace(tzinfo=None)
                if activity.start_time.tzinfo else activity.start_time,
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
            tss=metrics.get("tss"),
            normalized_power=metrics.get("normalized_power"),
            intensity_factor=metrics.get("intensity_factor"),
            samples_json=downsample_samples(activity.samples, max_samples=14400),
            laps_json=[lap.model_dump() for lap in activity.laps],
            report_status="pending",
        )
        self.db.add(db_activity)
        self.db.commit()
        self.db.refresh(db_activity)
        logger.info(f"活动入库: id={db_activity.id}, NP={metrics.get('normalized_power')}")

        # 增量更新 PMC
        try:
            anchor = db_activity.start_time.date() if hasattr(db_activity.start_time, "date") else db_activity.start_time
            updated = recompute_pmc(self.db, athlete.id, anchor_date=anchor)
            logger.info(f"PMC 更新: {updated} 天")
        except Exception as e:
            logger.warning(f"PMC 更新失败(非致命): {e}")

        # 异步生成报告
        if background_tasks is not None:
            from cycling_coach.api.routers._activities_shared import run_analyze_task
            background_tasks.add_task(run_analyze_task, db_activity.id, None)

        return {
            "ok": True,
            "id": db_activity.id,
            "metrics": metrics,
            "report_status": "pending",
        }

    # ---------- 列表 / 详情 ----------

    def list_activities(self, f: ActivityFilters) -> dict:
        """活动列表(多维过滤 + 排序 + 分页 + 聚合)"""
        q = (
            self.db.query(DBActivity)
            .options(
                defer(DBActivity.samples_json),
                defer(DBActivity.laps_json),
                defer(DBActivity.metrics),
                defer(DBActivity.report),
            )
        )
        if f.date_from:
            try:
                q = q.filter(DBActivity.start_time >= datetime.fromisoformat(f.date_from))
            except ValueError:
                raise ValidationError(f"date_from 格式错误: {f.date_from}")
        if f.date_to:
            try:
                q = q.filter(DBActivity.start_time <= datetime.fromisoformat(f.date_to + "T23:59:59"))
            except ValueError:
                raise ValidationError(f"date_to 格式错误: {f.date_to}")
        if f.min_distance_km is not None:
            q = q.filter(DBActivity.distance_m >= f.min_distance_km * 1000)
        if f.max_distance_km is not None:
            q = q.filter(DBActivity.distance_m <= f.max_distance_km * 1000)
        if f.min_duration_min is not None:
            q = q.filter(DBActivity.duration_s >= f.min_duration_min * 60)
        if f.max_duration_min is not None:
            q = q.filter(DBActivity.duration_s <= f.max_duration_min * 60)
        if f.min_avg_power is not None:
            q = q.filter(DBActivity.avg_power >= f.min_avg_power)
        if f.max_avg_power is not None:
            q = q.filter(DBActivity.avg_power <= f.max_avg_power)
        if f.min_avg_hr is not None:
            q = q.filter(DBActivity.avg_hr >= f.min_avg_hr)
        if f.max_avg_hr is not None:
            q = q.filter(DBActivity.avg_hr <= f.max_avg_hr)
        if f.source:
            q = q.filter(DBActivity.source == f.source)
        if f.has_report is not None:
            if f.has_report:
                q = q.filter(DBActivity.report.isnot(None))
            else:
                q = q.filter(DBActivity.report.is_(None))
        if f.min_tss is not None:
            q = q.filter(DBActivity.tss >= f.min_tss)
        if f.max_tss is not None:
            q = q.filter(DBActivity.tss <= f.max_tss)
        if f.min_normalized_power is not None:
            q = q.filter(DBActivity.normalized_power >= f.min_normalized_power)
        if f.max_normalized_power is not None:
            q = q.filter(DBActivity.normalized_power <= f.max_normalized_power)

        # 排序
        if f.sort == "tss":
            q = q.order_by(DBActivity.tss.desc() if f.order == "desc" else DBActivity.tss.asc())
        elif f.sort == "normalized_power":
            q = q.order_by(DBActivity.normalized_power.desc() if f.order == "desc" else DBActivity.normalized_power.asc())

        total = q.with_entities(func.count(DBActivity.id)).scalar() or 0
        activities_all = q.limit(f.limit).offset(f.offset).all()

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
            "offset": f.offset,
            "limit": f.limit,
            "aggregate": aggregate,
        }

    def get_activity(self, activity_id: int) -> dict:
        """活动详情 (含 1Hz 样本 + AI 报告)"""
        a = self.db.get(DBActivity, activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
        return _to_detail(a)

    def delete_activity(self, activity_id: int) -> dict:
        a = self.db.get(DBActivity, activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
        self.db.delete(a)
        self.db.commit()
        return {"ok": True}

    def update_rpe(self, activity_id: int, payload: dict) -> dict:
        """更新 RPE 主观疲劳"""
        a = self.db.get(DBActivity, activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
        rpe = payload.get("rpe")
        if rpe is not None:
            try:
                rpe = int(rpe)
            except (TypeError, ValueError):
                raise ValidationError("rpe 必须是整数")
            if rpe < 0 or rpe > 10:
                raise ValidationError("rpe 必须在 0-10 之间 (Borg CR-10)")
        a.rpe = rpe
        a.rpe_note = (payload.get("rpe_note") or None) if rpe is not None else None
        self.db.commit()
        return {"ok": True, "activity_id": activity_id, "rpe": a.rpe, "rpe_note": a.rpe_note}

    def trigger_analyze(
        self, activity_id: int, req: AnalyzeRequest,
        background_tasks: Optional[Any] = None,
    ) -> dict:
        """重新生成 AI 报告"""
        a = self.db.query(DBActivity).get(activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
        a.report_status = "analyzing"
        self.db.commit()
        if background_tasks is not None:
            from cycling_coach.api.routers._activities_shared import run_analyze_task
            background_tasks.add_task(run_analyze_task, activity_id, req.focus)
        return {"ok": True, "report": None, "reason": "已加入后台队列"}

    # ---------- 分析端点 (power-curve / zones / wbal / decoupling / cp) ----------

    def get_power_curve(self, activity_id: int) -> dict:
        """功率曲线 (Mean Maximal Power)"""
        a = self.db.get(DBActivity, activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
        samples = a.samples_json or []
        if not samples:
            return {
                "activity_id": activity_id,
                "points": [],
                "ftp_estimate": None,
                "key_durations": {},
            }
        pyd = _to_pyd(a)
        mmp = mean_maximal_power(pyd)
        ftp_est = estimate_ftp(pyd)
        durations_s = [5, 10, 30, 60, 120, 300, 600, 1200, 3600]
        points = [{"duration_s": d, "watts": mmp.get(f"{d}s")} for d in durations_s if f"{d}s" in mmp]
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

    def get_power_zones_detailed(
        self, activity_id: int, ftp: Optional[int] = None,
    ) -> dict:
        """Coggan 7 区分布"""
        a = self.db.get(DBActivity, activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
        if ftp is None:
            prof = profile_store.get_profile()
            ftp = prof.ftp_w if prof and prof.ftp_w else None
        if not ftp:
            raise ValidationError("FTP 未设置, 请在个人资料里配置或传 ?ftp=N")
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
        pyd = _to_pyd(a)
        result = power_zones_detailed(pyd, ftp=ftp)
        result["activity_id"] = activity_id
        return result

    def get_wbal(
        self, activity_id: int,
        cp: Optional[int] = None, w_prime: int = 20000,
    ) -> dict:
        """W'bal 详细分析"""
        a = self.db.get(DBActivity, activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
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
        if cp is None:
            prof = profile_store.get_profile()
            if prof and prof.ftp_w:
                cp = prof.ftp_w
            else:
                cp3 = detect_cp_3param(sample_objs)
                if "cp_estimated" in cp3:
                    cp = cp3["cp_estimated"]
        if not cp or cp <= 0:
            raise ValidationError("CP 无法确定, 请传 ?cp=N 或先在个人资料配置 FTP")
        result = wbal_analysis(sample_objs, cp=cp, w_prime=w_prime)
        result["activity_id"] = activity_id
        return result

    def get_decoupling(self, activity_id: int) -> dict:
        """Pa:HR Decoupling (有氧效率衰减)"""
        from cycling_coach.core.metrics.hr import pa_hr_decoupling, aerobic_decoupling_trend
        a = self.db.get(DBActivity, activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
        samples_json = a.samples_json or []
        if not samples_json:
            return {"activity_id": activity_id, "applicable": False, "error": "no_samples"}
        pyd = _to_pyd(a)
        result = pa_hr_decoupling(pyd)
        result["activity_id"] = activity_id
        if result.get("applicable"):
            result["trend"] = aerobic_decoupling_trend(pyd.samples)
        return result

    def get_cp_estimate(self, activity_id: int) -> dict:
        """CP 3 参数自动估算"""
        a = self.db.get(DBActivity, activity_id)
        if not a:
            raise NotFoundError(f"活动 {activity_id} 不存在")
        samples_json = a.samples_json or []
        if not samples_json:
            return {"activity_id": activity_id, "error": "no_power_data"}
        sample_objs = [Sample(**s) if isinstance(s, dict) else s for s in samples_json]
        result = detect_cp_3param(sample_objs)
        result["activity_id"] = activity_id
        return result

    # ---------- 对比 ----------

    def compare(self, ids: str) -> dict:
        """多活动对比"""
        try:
            activity_ids = [int(x) for x in ids.split(",") if x.strip()]
        except ValueError:
            raise ValidationError("ids 格式错误, 应为逗号分隔的整数")
        if not activity_ids:
            raise ValidationError("ids 不能为空")
        if len(activity_ids) > 10:
            raise ValidationError("最多对比 10 个活动")

        activities_data = []
        for aid in activity_ids:
            a = self.db.get(DBActivity, aid)
            if not a:
                continue
            samples_json = a.samples_json or []
            mmp: dict[str, int] = {}
            pyd = None
            if samples_json:
                pyd = _to_pyd(a)
                mmp = mean_maximal_power(pyd)
            pz = a.metrics.get("power_zones", {}) if a.metrics else {}
            h = a.duration_s // 3600
            m = (a.duration_s % 3600) // 60
            duration_str = f"{h}h{m:02d}m" if h > 0 else f"{m}m"
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
            raise NotFoundError("所有活动 ID 都不存在")

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
        best_by_metric: dict[str, int] = {}
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


# ============== helpers ==============

def downsample_samples(samples: list, max_samples: int = 14400) -> list:
    """短课 (<4h) 全存, 长课 (>4h) 降采样到 5s 间隔

    14400 样本 = 4h × 3600s, 5s 间隔意味着每个 5s 取 1 个
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


def _to_pyd(a: DBActivity) -> PydanticActivity:
    """ORM Activity → Pydantic Activity (供 metrics 用)"""
    samples = a.samples_json or []
    return PydanticActivity(
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


def _to_summary(a: DBActivity) -> dict:
    return {
        "id": a.id,
        "start_time": a.start_time,
        "duration_s": a.duration_s,
        "distance_m": a.distance_m,
        "avg_power": a.avg_power,
        "normalized_power": a.normalized_power,
        "tss": int(a.tss) if a.tss is not None else None,
        "avg_hr": a.avg_hr,
        "avg_cadence": a.avg_cadence,
        "total_elevation_gain": a.total_elevation_gain,
        "device": a.device,
        "source": a.source,
        "has_report": bool(a.report),
        "rpe": a.rpe,
        "rpe_note": a.rpe_note,
    }


def _to_detail(a: DBActivity) -> dict:
    s = _to_summary(a)
    return {
        **s,
        "max_power": a.max_power,
        "max_hr": a.max_hr,
        "max_speed": a.max_speed,
        "calories": a.calories,
        "metrics": a.metrics,
        "samples": a.samples_json or [],
        "laps": a.laps_json or [],
        "report": a.report,
        "report_status": a.report_status,
    }
