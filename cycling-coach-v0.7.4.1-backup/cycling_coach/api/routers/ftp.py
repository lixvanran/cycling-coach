"""FTP 测试管理 API — V0.6.1

4 种协议:
- coggan_20min: Coggan 20min 测试
- carmichael_8min: Carmichael 8min × 2
- cp_3param: Morton 3 参数临界功率
- ramp: Ramp Test 递增测试

端点:
- POST /api/ftp/test            从活动估算 + 录入
- GET  /api/ftp/history         历史记录
- GET  /api/ftp/recommend       推荐下次测试时间
- GET  /api/ftp/methods         方法说明
"""
from __future__ import annotations
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.data.sqlite.models import FTPTest, Activity
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.metrics.ftp import estimate_ftp, METHODS

router = APIRouter(prefix="/api/ftp", tags=["ftp"])


# ---------- Schemas ----------

class EstimateRequest(BaseModel):
    activity_id: int
    method: str = "auto"


class RecordFTPTest(BaseModel):
    test_date: str  # YYYY-MM-DD
    method: str
    ftp_w: int
    confidence: float = 0.5
    hr_bpm: int | None = None
    weight_kg: float | None = None
    notes: str | None = None
    source_activity_id: int | None = None
    cp_w: int | None = None
    w_prime_kj: float | None = None


class FTPTestOut(BaseModel):
    id: int
    test_date: str
    method: str
    method_label: str
    ftp_w: int
    confidence: float
    hr_bpm: int | None
    weight_kg: float | None
    w_per_kg: float | None
    notes: str | None
    source_activity_id: int | None
    cp_w: int | None
    w_prime_kj: float | None
    days_since: int
    ftp_change_w: int | None
    ftp_change_pct: float | None
    class Config:
        from_attributes = True


# ---------- 方法元信息 ----------

METHOD_INFO = {
    "coggan_20min": {
        "label": "Coggan 20 分钟测试",
        "short": "20 分钟",
        "duration_min": 65,
        "protocol": "15min Z1-Z2 热身 → 5min Z3 → 20min 全力 → 10min 冷却",
        "formula": "FTP = 0.95 × 20min NP",
        "academic": "Allen & Coggan 2010, Training and Racing with a Power Meter",
        "best_for": "最经典, 大多数教练推荐",
        "icon": "📏",
    },
    "carmichael_8min": {
        "label": "Carmichael 8min × 2",
        "short": "8min × 2",
        "duration_min": 50,
        "protocol": "15min 热身 → 8min 全 → 10min 恢复 → 8min 全 → 5min 冷却",
        "formula": "FTP = ((8min#1 + 8min#2) / 2) × 0.9",
        "academic": "Chris Carmichael / Carmichael Training Systems 2009",
        "best_for": "时间紧, 想 8min 估准",
        "icon": "⏱️",
    },
    "cp_3param": {
        "label": "Critical Power 3 参数 (Morton)",
        "short": "CP 3-param",
        "duration_min": None,
        "protocol": "不需要专门测试, 用任何 ≥ 30min 骑行的 MMP 曲线拟合",
        "formula": "P(t) = W'/t + CP, 最小二乘拟合",
        "academic": "Morton 1996, Journal of Applied Physiology",
        "best_for": "已有训练数据, 不想专门测试",
        "icon": "📊",
    },
    "ramp": {
        "label": "Ramp Test (递增测试)",
        "short": "Ramp",
        "duration_min": 25,
        "protocol": "10min 热身 → 起始 100W 起, 每分钟 +20W → 力竭 → 5min 冷却",
        "formula": "FTP = 0.75 × 峰值 1min 平均",
        "academic": "Pinzon & Anson 2018, Cycling Science",
        "best_for": "没时间测 20min, 想快速估",
        "icon": "📈",
    },
    "auto": {
        "label": "自动选择 (推荐)",
        "short": "Auto",
        "duration_min": None,
        "protocol": "根据活动时长和数据特征, 自动选最合适方法",
        "formula": "综合 4 种方法, 选置信度最高",
        "academic": "本项目综合",
        "best_for": "不确定选哪个时, 用这个",
        "icon": "🤖",
    },
}


# ---------- 端点 ----------

@router.get("/methods")
def get_methods():
    return {"methods": METHOD_INFO}


@router.post("/estimate")
def estimate_from_activity(req: EstimateRequest, db: Session = Depends(get_db)):
    """从已上传的活动估算 FTP (不录入, 试用)"""
    a = db.get(Activity, req.activity_id)
    if not a:
        raise HTTPException(404, f"活动 {req.activity_id} 不存在")
    if req.method not in METHODS:
        raise HTTPException(400, f"未知方法: {req.method}, 可用: {list(METHODS.keys())}")

    # 转 Pydantic Activity
    from cycling_coach.data.parsers.schema import Activity as PydanticActivity, Sample
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
        samples=[Sample(**s) if isinstance(s, dict) else s for s in (a.samples_json or [])],
    )

    # V0.7.1: 从 athlete 档案读 max_hr / lthr, 替代硬编码 190/175
    athlete = profile_store.get_or_create_athlete(db)
    max_hr = athlete.max_hr or 190
    lthr = athlete.lthr or 170

    est = estimate_ftp(pyd, req.method, max_hr=max_hr, lthr=lthr)
    return {
        "method": est.method,
        "method_label": est.method_label,
        "ftp_w": est.ftp_w,
        "confidence": est.confidence,
        "notes": est.notes,
        "details": est.details,
        "source_activity_id": req.activity_id,
        "athlete_profile": {"max_hr": max_hr, "lthr": lthr},
        "activity_summary": {
            "id": a.id,
            "start_time": a.start_time.isoformat() if a.start_time else None,
            "duration_min": round((a.duration_s or 0) / 60, 1),
            "distance_km": round((a.distance_m or 0) / 1000, 1),
            "avg_power": a.avg_power,
        },
    }


@router.post("/test", response_model=FTPTestOut)
def record_ftp_test(payload: RecordFTPTest, db: Session = Depends(get_db)):
    """录入一次 FTP 测试结果"""
    if payload.method not in METHODS:
        raise HTTPException(400, f"未知方法: {payload.method}")
    if payload.ftp_w < 50 or payload.ftp_w > 600:
        raise HTTPException(400, "ftp_w 必须在 50-600 范围 (正常人类能力)")

    try:
        test_date = datetime.fromisoformat(payload.test_date)
    except ValueError:
        raise HTTPException(400, f"日期格式错误: {payload.test_date}")

    athlete = profile_store.get_or_create_athlete(db)
    w_per_kg = None
    if payload.weight_kg and payload.weight_kg > 0:
        w_per_kg = round(payload.ftp_w / payload.weight_kg, 2)

    t = FTPTest(
        athlete_id=athlete.id,
        test_date=test_date,
        method=payload.method,
        ftp_w=payload.ftp_w,
        confidence=payload.confidence,
        hr_bpm=payload.hr_bpm,
        weight_kg=payload.weight_kg,
        w_per_kg=w_per_kg,
        notes=payload.notes,
        source_activity_id=payload.source_activity_id,
        cp_w=payload.cp_w,
        w_prime_kj=payload.w_prime_kj,
    )
    db.add(t)
    db.commit()
    db.refresh(t)
    return _to_out(t, db)


@router.get("/history", response_model=list[FTPTestOut])
def list_history(days: int = 365, db: Session = Depends(get_db)):
    """FTP 测试历史"""
    athlete = profile_store.get_or_create_athlete(db)
    cutoff = datetime.utcnow() - timedelta(days=days)
    tests = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == athlete.id)
        .filter(FTPTest.test_date >= cutoff)
        .order_by(desc(FTPTest.test_date))
        .all()
    )
    return [_to_out(t, db) for t in tests]


@router.get("/recommend")
def recommend_next_test(db: Session = Depends(get_db)):
    """推荐下次测试时间

    训练学:
    - Base 期: 8-12 周测一次
    - Build 期: 6-8 周测一次
    - Peak/Taper: 不测, 等比赛后
    - 训练 4-6 周后, IF 平均 > 0.85 持续 → 该测
    """
    athlete = profile_store.get_or_create_athlete(db)
    last = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == athlete.id)
        .order_by(desc(FTPTest.test_date))
        .first()
    )

    now = datetime.utcnow()
    if not last:
        return {
            "days_since": None,
            "should_test": True,
            "reason": "从未测过, 建议尽快做第一次 FTP 测试建立基线",
            "recommended_method": "coggan_20min",
            "priority": "high",
        }

    days = (now.date() - last.test_date.date()).days
    last_ftp = last.ftp_w
    last_method = last.method

    # 看 IF 趋势
    cutoff = now - timedelta(days=14)
    activities = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete.id)
        .filter(Activity.start_time >= cutoff)
        .all()
    )
    ifs = []
    for a in activities:
        np_v = (a.metrics or {}).get("normalized_power") or (a.metrics or {}).get("np")
        if np_v and last_ftp > 0:
            ifs.append(np_v / last_ftp)
    avg_if = sum(ifs) / len(ifs) if ifs else None

    if days < 42:  # < 6 周
        priority = "low"
        reason = f"上次测试才 {days} 天前, FTP 短期内稳定, 6-8 周测一次即可"
        should = False
    elif days < 84:  # 6-12 周
        priority = "medium"
        if avg_if and avg_if > 0.88:
            reason = f"上次测试 {days} 天, 近期 IF 平均 {avg_if:.2f} 偏高, 可能已突破, 建议复测"
            should = True
        else:
            reason = f"上次测试 {days} 天前, 建议保持当前训练, 8-12 周测一次"
            should = False
    else:  # > 12 周
        priority = "high"
        if avg_if and avg_if > 0.90:
            reason = f"已 {days} 天未测, 近期 IF {avg_if:.2f} 接近极限, 强烈建议复测"
        else:
            reason = f"已 {days} 天未测, 建议尽快复测以校准训练区"
        should = True

    return {
        "days_since": days,
        "last_ftp_w": last_ftp,
        "last_method": last_method,
        "last_test_date": last.test_date.date().isoformat(),
        "avg_if_last_14d": round(avg_if, 2) if avg_if else None,
        "should_test": should,
        "reason": reason,
        "recommended_method": "coggan_20min",
        "priority": priority,
    }


@router.delete("/test/{test_id}")
def delete_test(test_id: int, db: Session = Depends(get_db)):
    t = db.get(FTPTest, test_id)
    if not t:
        raise HTTPException(404, f"测试 {test_id} 不存在")
    db.delete(t)
    db.commit()
    return {"ok": True, "id": test_id}


# ---------- helpers ----------

def _to_out(t: FTPTest, db: Session) -> FTPTestOut:
    now = datetime.utcnow()
    days_since = (now.date() - t.test_date.date()).days

    # 跟上一条对比
    prev = (
        db.query(FTPTest)
        .filter(FTPTest.athlete_id == t.athlete_id)
        .filter(FTPTest.test_date < t.test_date)
        .order_by(desc(FTPTest.test_date))
        .first()
    )
    change_w = None
    change_pct = None
    if prev:
        change_w = t.ftp_w - prev.ftp_w
        change_pct = round(change_w / prev.ftp_w * 100, 1) if prev.ftp_w > 0 else None

    return FTPTestOut(
        id=t.id,
        test_date=t.test_date.date().isoformat(),
        method=t.method,
        method_label=METHOD_INFO.get(t.method, {}).get("label", t.method),
        ftp_w=t.ftp_w,
        confidence=t.confidence,
        hr_bpm=t.hr_bpm,
        weight_kg=t.weight_kg,
        w_per_kg=t.w_per_kg,
        notes=t.notes,
        source_activity_id=t.source_activity_id,
        cp_w=t.cp_w,
        w_prime_kj=t.w_prime_kj,
        days_since=days_since,
        ftp_change_w=change_w,
        ftp_change_pct=change_pct,
    )
