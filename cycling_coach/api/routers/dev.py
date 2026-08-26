"""/api/dev - 开发用端点

V0.1.0 提供:
- 生成模拟活动(无真实 FIT 时也能看 UI 效果)
"""
from __future__ import annotations
import logging
import math
import random
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import Activity
from cycling_coach.data.parsers.schema import Sample, Lap
from cycling_coach.core.metrics import compute_metrics
from cycling_coach.core.profile import store as profile_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/dev", tags=["dev"])


# ---------- Mock 活动生成器 ----------

PROFILES = {
    "z2_long": {
        "name": "Z2 长距离 90min",
        "duration_s": 90 * 60,
        "ftp_pct": 0.65,  # 65% FTP
        "variability": 0.05,
        "hr_drift": 8,  # bpm 漂移
    },
    "threshold": {
        "name": "阈值训练 4×8min",
        "duration_s": 70 * 60,
        "ftp_pct": 0.92,
        "variability": 0.10,
        "intervals": [(8, 0.95), (3, 0.55)] * 4 + [(10, 0.55)],  # 工作+休息
    },
    "vo2max": {
        "name": "VO2max 5×3min",
        "duration_s": 55 * 60,
        "ftp_pct": 1.20,
        "variability": 0.08,
        "intervals": [(3, 1.30), (3, 0.55)] * 5 + [(10, 0.55)],
    },
    "recovery": {
        "name": "主动恢复 45min",
        "duration_s": 45 * 60,
        "ftp_pct": 0.50,
        "variability": 0.08,
    },
    "hills": {
        "name": "爬坡间歇 6×5min @ 8%",
        "duration_s": 75 * 60,
        "ftp_pct": 0.85,
        "variability": 0.12,
        "elevation_gain": 1200,
    },
}


def _generate_samples(profile: dict) -> list[Sample]:
    """根据 profile 生成 1Hz 样本"""
    duration = profile["duration_s"]
    base = profile["ftp_pct"]
    var = profile.get("variability", 0.05)
    intervals = profile.get("intervals")

    samples = []
    base_hr = 130
    hr_max = 180
    base_cadence = 88

    t = 0
    if intervals:
        # 有结构化间歇
        for dur_min, intensity in intervals:
            for _ in range(dur_min * 60):
                p = base * (1 + 0.4 * intensity) * (1 + random.uniform(-var, var))
                # 把 p 标定为 %FTP,等乘 athlete.ftp
                hr = int(base_hr + (hr_max - base_hr) * intensity * 0.8)
                hr += int(random.gauss(0, 2))
                cad = int(base_cadence + random.randint(-3, 5) - (5 if intensity > 1.0 else 0))
                elev = (profile.get("elevation_gain", 0) / duration) * t
                samples.append(Sample(
                    t_offset=t,
                    power=int(200 * p),  # 暂时写死,后面会重算
                    hr=hr, cadence=cad, speed=8.0 + p * 5,
                    elevation=elev, lat=None, lon=None,
                ))
                t += 1
                if t >= duration:
                    break
            if t >= duration:
                break
    else:
        for t in range(duration):
            drift = profile.get("hr_drift", 0) * (t / duration)
            p = base * (1 + random.uniform(-var, var))
            hr = int(base_hr + 30 * p + drift)
            cad = int(base_cadence + random.randint(-3, 3))
            elev = (profile.get("elevation_gain", 0) / duration) * t
            samples.append(Sample(
                t_offset=t,
                power=int(200 * p),
                hr=hr, cadence=cad, speed=8.0 + p * 5,
                elevation=elev, lat=None, lon=None,
            ))

    # 补齐到 duration(以防 intervals 不到)
    while len(samples) < duration:
        samples.append(Sample(
            t_offset=len(samples), power=120, hr=110, cadence=85,
            speed=7.0, elevation=0.0, lat=None, lon=None,
        ))
    return samples[:duration]


def _scale_samples_to_ftp(samples: list[Sample], ftp: int) -> list[Sample]:
    """把生成的 power(基于 200W 标定)缩放到真实 FTP"""
    out = []
    for s in samples:
        # 之前 power 写的是 200 × p(标定),现在换算成 真实值
        real_p = int((s.power or 0) / 200 * ftp)
        out.append(Sample(**{**s.model_dump(), "power": real_p}))
    return out


def _make_laps(samples: list[Sample], duration_s: int) -> list[Lap]:
    """简单分 lap(每 10 分钟一段)"""
    laps = []
    seg = 600
    for i in range(0, duration_s, seg):
        chunk = [s for s in samples if i <= s.t_offset < i + seg]
        if not chunk:
            continue
        laps.append(Lap(
            start_offset=i,
            duration_s=min(seg, duration_s - i),
            avg_power=int(sum(s.power or 0 for s in chunk) / len(chunk)),
            avg_hr=int(sum(s.hr or 0 for s in chunk) / len(chunk)),
            avg_cadence=int(sum(s.cadence or 0 for s in chunk) / len(chunk)),
            label=f"Lap {i // seg + 1}",
        ))
    return laps


@router.post("/generate-mock")
def generate_mock_activity(
    profile_key: str = "z2_long",
    db: Session = Depends(get_db),
):
    """生成一个 mock 活动入库(用于演示 / 开发)"""
    if profile_key not in PROFILES:
        return {"ok": False, "error": f"未知 profile: {profile_key},可选: {list(PROFILES.keys())}"}

    profile = PROFILES[profile_key]
    athlete = profile_store.get_or_create_athlete(db)
    ftp = athlete.ftp or 250

    samples = _generate_samples(profile)
    samples = _scale_samples_to_ftp(samples, ftp)
    laps = _make_laps(samples, profile["duration_s"])

    # 汇总
    valid_p = [s.power for s in samples if s.power]
    valid_hr = [s.hr for s in samples if s.hr]
    avg_power = int(sum(valid_p) / len(valid_p)) if valid_p else None
    avg_hr = int(sum(valid_hr) / len(valid_hr)) if valid_hr else None
    distance_m = (samples[-1].speed or 8) * profile["duration_s"] if samples else 0

    # 构造 Pydantic Activity(给 compute_metrics 用)
    from cycling_coach.data.parsers.schema import Activity as PydActivity
    pa = PydActivity(
        source="mock",
        start_time=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=random.randint(0, 6)),
        duration_s=profile["duration_s"],
        distance_m=distance_m,
        total_elevation_gain=profile.get("elevation_gain", 0),
        avg_power=avg_power,
        max_power=max(valid_p, default=None),
        avg_hr=avg_hr,
        max_hr=max(valid_hr, default=None),
        avg_cadence=int(sum(s.cadence for s in samples if s.cadence) / len(samples)) if samples else None,
        avg_speed=8.0,
        max_speed=None,
        calories=int(profile["duration_s"] / 60 * (8 * ftp / 200)),
        device="Mock Generator",
        samples=samples,
        laps=laps,
    )
    metrics = compute_metrics(
        pa,
        ftp=ftp,
        max_hr=athlete.max_hr,
        lthr=athlete.lthr,
    )

    db_act = Activity(
        athlete_id=athlete.id,
        source="mock",
        file_name=f"mock_{profile_key}.json",
        file_path=None,
        start_time=pa.start_time,
        duration_s=pa.duration_s,
        distance_m=pa.distance_m,
        total_elevation_gain=pa.total_elevation_gain,
        avg_power=pa.avg_power,
        max_power=pa.max_power,
        avg_hr=pa.avg_hr,
        max_hr=pa.max_hr,
        avg_cadence=pa.avg_cadence,
        avg_speed=pa.avg_speed,
        max_speed=pa.max_speed,
        calories=pa.calories,
        device="Mock Generator",
        metrics=metrics,
        samples_json=[s.model_dump() for s in samples[:7200]],
        laps_json=[lap.model_dump() for lap in laps],
        report_status="pending",
    )
    db.add(db_act)
    db.commit()
    db.refresh(db_act)
    logger.info(f"生成 mock 活动: id={db_act.id} profile={profile_key}")

    return {
        "ok": True,
        "id": db_act.id,
        "name": profile["name"],
        "metrics": metrics,
    }


@router.get("/mock-profiles")
def list_mock_profiles():
    return {"profiles": [{"key": k, "name": v["name"]} for k, v in PROFILES.items()]}


@router.post("/repair-db")
def repair_db_endpoint(db: Session = Depends(get_db)):
    """一键修复:迁移表 + 清理+重 seed 系统课程

    用户从 V0.3.2 升到 V0.3.3 时,老库 workouts 表缺新列,会触发
    'no such column: workouts.source' 的 500 错误。

    这个端点:
    1. ALTER TABLE 加缺失列
    2. DELETE 旧的(可能是半截的) system 课
    3. 重新 seed 29 个系统课程

    调用方法:POST /api/dev/repair-db
    """
    from cycling_coach.data.sqlite import repair_db as _repair_db
    from cycling_coach.api.routers.workouts import _ensure_system_workouts

    info = _repair_db()
    seeded = _ensure_system_workouts(db)
    info["actions"].append(f"re-seed 系统课程: {seeded} 个")

    # 校验最终状态
    from sqlalchemy import text as _sql_text
    cnt = db.execute(_sql_text(
        "SELECT source, COUNT(*) FROM workouts GROUP BY source"
    )).fetchall()
    info["final_count"] = {row[0]: row[1] for row in cnt}
    info["ok"] = True
    return info
