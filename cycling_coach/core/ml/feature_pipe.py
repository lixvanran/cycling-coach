"""特征工程: 从 Activity + Athlete 拼一行特征 (对齐 lixvanran/ftp-predictor)

V0.8.0 升级: 12 维 → 20 维, 跟 ftp-predictor 模型对齐

20 维特征 (顺序固定, 必须跟 best_model.joblib['feature_cols'] 一致):
  distance, moving_time, average_heartrate,
  HR Zone 1-5,         # 5 区 Coggan (按 max_hr 划分)
  kilojoules,
  Power Zone 1-11      # 11 区 Strava (按 FTP 划分)

数据是**周/月聚合**累计值 (不是单次骑行秒级)。本模块:
1. 拉 14 天窗口内所有活动
2. 累加 distance / moving_time / kilojoules
3. 累加 HR/Power zone 秒数 (5 区和 11 区)
4. average_heartrate = 移动时间加权平均 bpm
5. zone 映射: Coggan 7 区 → Strava 11 区 (Power)

zone 映射规则 (Power Zone 11 Strava 标准 vs Coggan 7 区):
  Strava 11 区 范围  vs  Coggan 7 区
  ─────────────────────────────────────
  PZ 1  <55%   AR        →  Coggan Z1
  PZ 2  55-75% Endurance →  Coggan Z2
  PZ 3  75-90% Tempo     →  Coggan Z3
  PZ 4  90-105% Thresh   →  Coggan Z4
  PZ 5  105-120% VO2     →  Coggan Z5 (前半)
  PZ 6  120-150% Anaer   →  Coggan Z6
  PZ 7  150-200%         →  Coggan Z7 (前半)
  PZ 8  200-300%         →  Coggan Z7 (中段)
  PZ 9  300-400%         →  Coggan Z7 (中段)
  PZ 10 400-500%         →  Coggan Z7 (后段)
  PZ 11 >500%  Peak      →  Coggan Z7 (极端尾段)

HR Zone 5 区 (Coggan, 按 max_hr):
  HZ 1  <60%   Recovery
  HZ 2  60-70% Endurance
  HZ 3  70-80% Tempo
  HZ 4  80-90% Threshold
  HZ 5  >90%   VO2

HR 7→5 映射 (Karvonen 7 区按 LTHR → Coggan 5 区按 max_hr):
  Karvonen 7 区 (基于 LTHR)              Coggan 5 区
  ──────────────────────────────────────────────────
  Z1  <81%   Active Recovery           →  HZ 1
  Z2  81-89% Endurance                 →  HZ 2
  Z3  90-93% Tempo                     →  HZ 3
  Z4  94-99% Threshold                 →  HZ 4
  Z5  100-102% Above Threshold         →  HZ 4
  Z6  103-105% Anaerobic               →  HZ 5
  Z7  >106%  VO2 Max                   →  HZ 5
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Activity, Athlete


# ============================================================
# V0.8.0: 20 维特征 (对齐 ftp-predictor)
# ============================================================
# 注: 列顺序必须跟 ftp-predictor best_model.joblib['feature_cols'] 完全一致
FEATURE_SCHEMA: dict[str, str] = {
    # 基础 (3 维)
    "distance": "float",                    # 距离 (m, 窗口累计)
    "moving_time": "float",                 # 移动时间 (s, 窗口累计)
    "average_heartrate": "float",          # 平均心率 (bpm, 移动时间加权)
    # HR Zones 1-5 (5 维, 秒数)
    "HR Zone 1": "float",  # 恢复区
    "HR Zone 2": "float",  # 基础耐力
    "HR Zone 3": "float",  # 节奏
    "HR Zone 4": "float",  # 阈值
    "HR Zone 5": "float",  # 无氧
    # 能量 (1 维)
    "kilojoules": "float",                 # 训练功 (kJ, 窗口累计)
    # Power Zones 1-11 (11 维, 秒数)
    "Power Zone 1": "float",  # 主动恢复 (<55% FTP)
    "Power Zone 2": "float",  # 耐力基础 (55-75% FTP)
    "Power Zone 3": "float",  # 节奏 (75-90% FTP)
    "Power Zone 4": "float",  # 阈值下 (90-105% FTP)
    "Power Zone 5": "float",  # 阈值 (105-120% FTP)
    "Power Zone 6": "float",  # VO2 (120-150% FTP)
    "Power Zone 7": "float",  # 无氧 (150-200% FTP)
    "Power Zone 8": "float",  # 神经肌肉 (200-300% FTP)
    "Power Zone 9": "float",  # 冲刺 (300-400% FTP)
    "Power Zone 10": "float", # 极限 (400-500% FTP)
    "Power Zone 11": "float", # 峰值 (>500% FTP)
}

# 期望顺序 (列名, 跟 ftp-predictor 一致)
FEATURE_COLUMNS: list[str] = list(FEATURE_SCHEMA.keys())

# 默认聚合窗口 (天)
DEFAULT_WINDOW_DAYS = 14

# ============================================================
# Zone 映射
# ============================================================

# Power Zone 7 区 (Coggan) → 11 区 (Strava) 映射比例
# 按 FTP 占比边界估算
# Coggan 7 区边界: [0, 0.55, 0.75, 0.90, 1.05, 1.20, 1.50, +inf]
# Strava 11 区边界: [0, 0.55, 0.75, 0.90, 1.05, 1.20, 1.50, 2.0, 3.0, 4.0, 5.0, +inf]
#
# 输出: dict[strava_11_idx, dict[coggan_7_zone, weight]]
# weight 含义: 该 Strava 区从对应的 Coggan 区拿多少比例
# 同一 Coggan 区的 weight 之和应 = 1.0
_POWER_7_TO_11: dict[int, dict[int, float]] = {
    # Strava PZ 1 (0~0.55)        = Coggan Z1 (0~0.55)
    1: {1: 1.0},
    # Strava PZ 2 (0.55~0.75)     = Coggan Z2
    2: {2: 1.0},
    # Strava PZ 3 (0.75~0.90)     = Coggan Z3
    3: {3: 1.0},
    # Strava PZ 4 (0.90~1.05)     = Coggan Z4
    4: {4: 1.0},
    # Strava PZ 5 (1.05~1.20)     = Coggan Z5 (1.05~1.20 整段)
    5: {5: 1.0},
    # Strava PZ 6 (1.20~1.50)     = Coggan Z6 (1.20~1.50 整段)
    6: {6: 1.0},
    # Strava PZ 7 (1.50~2.0)      = Coggan Z7 (1.50~2.0)
    7: {7: 0.5},
    # Strava PZ 8 (2.0~3.0)       = Coggan Z7 (2.0~3.0)
    8: {7: 0.3},
    # Strava PZ 9 (3.0~4.0)       = Coggan Z7 (3.0~4.0)
    9: {7: 0.1},
    # Strava PZ 10 (4.0~5.0)      = Coggan Z7 (4.0~5.0)
    10: {7: 0.05},
    # Strava PZ 11 (>5.0)         = Coggan Z7 (>5.0)
    11: {7: 0.05},
}

# HR Zone 7 区 (Karvonen) → 5 区 (Coggan max_hr) 映射
# Karvonen 7 区基于 LTHR: <81, 81-89, 90-93, 94-99, 100-102, 103-105, >106
# Coggan 5 区基于 max_hr: <60, 60-70, 70-80, 80-90, >90
# 经验映射: 用 FTP/HR 比例, Karvonen 中高区合并到 Coggan 高区
_HR_7_TO_5: dict[int, int] = {
    1: 1,  # Karvonen Z1 → Coggan HZ 1
    2: 2,  # Karvonen Z2 → Coggan HZ 2
    3: 3,  # Karvonen Z3 → Coggan HZ 3
    4: 4,  # Karvonen Z4 → Coggan HZ 4
    5: 4,  # Karvonen Z5 (Above Threshold) → Coggan HZ 4
    6: 5,  # Karvonen Z6 (Anaerobic) → Coggan HZ 5
    7: 5,  # Karvonen Z7 (VO2 Max) → Coggan HZ 5
}


# ============================================================
# 工具
# ============================================================

def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _power_zones_7_to_11(zones_7: dict[str, int]) -> dict[str, int]:
    """Coggan 7 区 (Z1-Z7 秒数) → Strava 11 区 (Power Zone 1-11 秒数)

    Args:
        zones_7: {"Z1": 100, "Z2": 200, ..., "Z7": 50} (秒数)

    Returns:
        {"Power Zone 1": 100, "Power Zone 2": 200, ..., "Power Zone 11": 0}
    """
    out: dict[str, int] = {f"Power Zone {i}": 0 for i in range(1, 12)}
    for strava_idx, coggan_map in _POWER_7_TO_11.items():
        total = 0
        for coggan_z, weight in coggan_map.items():
            sec = zones_7.get(f"Z{coggan_z}", 0)
            total += sec * weight
        out[f"Power Zone {strava_idx}"] = int(total)
    return out


def _hr_zones_7_to_5(zones_7: dict[str, int]) -> dict[str, int]:
    """Karvonen 7 区 (Z1-Z7) → Coggan 5 区 (HR Zone 1-5)"""
    out: dict[str, int] = {f"HR Zone {i}": 0 for i in range(1, 6)}
    for karvonen_z, coggan_hz in _HR_7_TO_5.items():
        sec = zones_7.get(f"Z{karvonen_z}", 0)
        out[f"HR Zone {coggan_hz}"] += int(sec)
    return out


def _hr_zones_5_passthrough(zones_5: dict[str, int]) -> dict[str, int]:
    """已经是 Coggan 5 区时直接映射 (key 名是 Z1-Z5)"""
    return {f"HR Zone {i}": int(zones_5.get(f"Z{i}", 0)) for i in range(1, 6)}


def _power_zones_7_passthrough(zones_7: dict[str, int]) -> dict[str, int]:
    """已经是 Coggan 7 区时直接 7→11 转换"""
    return _power_zones_7_to_11(zones_7)


# ============================================================
# 核心: 构造一行 20 维特征
# ============================================================

def build_feature_row(
    db: Session,
    athlete_id: int,
    activity_id: Optional[int] = None,
    ref_date: Optional[datetime] = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> tuple[list[float], list[str]]:
    """构造一行 20 维特征 (对齐 ftp-predictor)

    流程:
    1. 拉 ref_date 前 [window_days] 天内的活动
    2. 累加 distance / moving_time / kilojoules / zone 秒数
    3. 加权平均心率 (按 moving_time)
    4. zone 映射: 7→11 (Power), 7→5 (HR)
    5. 顺序 = FEATURE_COLUMNS (跟 best_model.feature_cols 一致)

    Args:
        db: SQLAlchemy Session
        athlete_id: 运动员 id
        activity_id: 可选, 单活动预测时 (用该活动 metrics 替代窗口聚合)
        ref_date: 参考日期, None 用现在
        window_days: 聚合窗口天数, 默认 14

    Returns:
        (values, columns) — values 长度 20, 顺序对齐 columns

    Raises:
        ValueError: 无活动数据
    """
    ref = ref_date or _utcnow()
    columns = FEATURE_COLUMNS  # 20 维固定顺序

    # 拿 athlete (用于 ftp / max_hr fallback)
    athlete = db.query(Athlete).filter(Athlete.id == athlete_id).first()
    if not athlete:
        raise ValueError(f"运动员不存在: athlete_id={athlete_id}")

    # 单活动预测模式: 直接用该活动 metrics
    if activity_id:
        activity = db.query(Activity).filter(Activity.id == activity_id).first()
        if not activity:
            raise ValueError(f"活动不存在: activity_id={activity_id}")
        return _activity_row_to_features(activity, athlete)

    # 窗口聚合模式
    cutoff = ref - timedelta(days=window_days)
    activities = (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .filter(Activity.start_time >= cutoff)
        .filter(Activity.start_time <= ref)
        .order_by(Activity.start_time)
        .all()
    )
    if not activities:
        raise ValueError(
            f"数据不足: {window_days} 天内无活动 (athlete_id={athlete_id})"
        )
    return _activities_to_features(activities, athlete)


def _activity_row_to_features(
    activity: Activity, athlete: Athlete
) -> tuple[list[float], list[str]]:
    """从单个 Activity 直接拿 metrics 拼一行 (跳过聚合)

    用于: 实时预测, 拿最近一次活动的 20 维
    注: 单次活动的 distance/moving_time 远小于 2 周累计, 跟训练分布不匹配
    但 ftp-predictor 是树模型, 抗 scale 差异, 仍能给出合理预测
    """
    metrics = activity.metrics or {}
    pz_7 = metrics.get("power_zones", {}) or {}
    hz_5_or_7 = metrics.get("hr_zones", {}) or {}

    # Power zones: 7→11
    if pz_7:
        pz_11 = _power_zones_7_passthrough(pz_7)
    else:
        pz_11 = {f"Power Zone {i}": 0 for i in range(1, 12)}

    # HR zones: 5 (Coggan max_hr) 或 7 (Karvonen lthr) → 5
    if hz_5_or_7:
        n_zones = len([k for k in hz_5_or_7 if k.startswith("Z")])
        if n_zones >= 7:
            hz_5 = _hr_zones_7_to_5(hz_5_or_7)
        else:
            hz_5 = _hr_zones_5_passthrough(hz_5_or_7)
    else:
        hz_5 = {f"HR Zone {i}": 0 for i in range(1, 6)}

    # kilojoules: 多个来源, fallback 链
    kj = _extract_kilojoules(activity, metrics)

    # distance / moving_time / hr
    distance_m = float(activity.distance_m or 0)
    moving_time_s = float(activity.duration_s or 0)
    avg_hr = float(activity.avg_hr or 0)

    return _compose_features(
        distance_m=distance_m,
        moving_time_s=moving_time_s,
        avg_hr=avg_hr,
        kilojoules=kj,
        hr_zones_5=hz_5,
        power_zones_11=pz_11,
    )


def _extract_kilojoules(activity: Activity, metrics: dict) -> float:
    """从多个可能位置拿 kilojoules

    优先级:
    1. metrics.power.kilojoules (V0.8.0 写入的, e.g. export_features 测试)
    2. metrics.total_kj (compute_metrics 早期格式)
    3. 从 avg_power × duration_s 计算 (W × s / 1000 = kJ)
    """
    pwr = metrics.get("power", {}) or {}
    if pwr.get("kilojoules"):
        return float(pwr["kilojoules"])
    if metrics.get("total_kj"):
        return float(metrics["total_kj"])
    # 兜底: 平均功率 × 时间
    if activity.avg_power and activity.duration_s:
        return float(activity.avg_power) * float(activity.duration_s) / 1000.0
    return 0.0


def _activities_to_features(
    activities: list, athlete: Athlete
) -> tuple[list[float], list[str]]:
    """从窗口内多个 Activity 聚合一行 20 维特征"""
    total_distance = 0.0
    total_moving_time = 0.0
    weighted_hr_sum = 0.0
    total_kj = 0.0

    # 累加 zone 秒数
    pz_11 = {f"Power Zone {i}": 0 for i in range(1, 12)}
    hz_5 = {f"HR Zone {i}": 0 for i in range(1, 6)}

    for a in activities:
        total_distance += float(a.distance_m or 0)
        mt = float(a.duration_s or 0)
        total_moving_time += mt

        hr = float(a.avg_hr or 0)
        weighted_hr_sum += hr * mt

        metrics = a.metrics or {}
        total_kj += _extract_kilojoules(a, metrics)

        pz_7 = metrics.get("power_zones", {}) or {}
        if pz_7:
            for k, v in _power_zones_7_passthrough(pz_7).items():
                pz_11[k] += v

        hz_raw = metrics.get("hr_zones", {}) or {}
        if hz_raw:
            n_zones = len([k for k in hz_raw if k.startswith("Z")])
            if n_zones >= 7:
                hz_mapped = _hr_zones_7_to_5(hz_raw)
            else:
                hz_mapped = _hr_zones_5_passthrough(hz_raw)
            for k, v in hz_mapped.items():
                hz_5[k] += v

    avg_hr = weighted_hr_sum / total_moving_time if total_moving_time > 0 else 0.0

    return _compose_features(
        distance_m=total_distance,
        moving_time_s=total_moving_time,
        avg_hr=avg_hr,
        kilojoules=total_kj,
        hr_zones_5=hz_5,
        power_zones_11=pz_11,
    )


def _compose_features(
    distance_m: float,
    moving_time_s: float,
    avg_hr: float,
    kilojoules: float,
    hr_zones_5: dict[str, int],
    power_zones_11: dict[str, int],
) -> tuple[list[float], list[str]]:
    """按 FEATURE_COLUMNS 顺序拼 20 维"""
    feat_map = {
        "distance": float(distance_m),
        "moving_time": float(moving_time_s),
        "average_heartrate": float(avg_hr),
        "kilojoules": float(kilojoules),
    }
    feat_map.update({k: float(v) for k, v in hr_zones_5.items()})
    feat_map.update({k: float(v) for k, v in power_zones_11.items()})

    values = [feat_map[col] for col in FEATURE_COLUMNS]
    return values, FEATURE_COLUMNS
