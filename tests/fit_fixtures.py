"""V0.9.0: 真实 FIT 测试 fixture 生成器

## 审计发现了什么 (以及什么不是 bug)

**真 bug 1: `normalized_power` 零填充** (cycling_coach/core/metrics/power.py)
老实现先把点塞进 1Hz 数组 (`np.zeros(duration)`) 再按 `idx = t - t_min` 填。
采样间隔 > 1s 时窗口内大量是 0:
    1s 采样 → NP 200 ✅   2s → 100   5s → 40   10s → 20   30s → 7
主流码表录 1Hz 所以平时看不出来, 但 2s 以上的设备/丢样本场景直接腰斩。

**真 bug 2: `position_lat/long` 没从 semicircles 换算**
写 31.2304° → 读出 372593185 (半圆原值), 任何路线图都会画到地球另一边。
目前 lat/lon 还没被消费 (没做路线图), 是潜伏 bug。

**真 bug 3: FIT 缺 session 汇总时静默返回 0**
只有 record 没有 session 的导出, 时长/距离/功率全是 0 或 None,
而 watcher 还报"导入成功"。用户看到成功提示 + 空列表 + 全 0 的 PMC。

**曾误判 (已排除): duration 毫秒/秒**
一度以为 `total_elapsed_time` 被当秒用导致 1000× 虚高。**这是我的误判** ——
决定性实验 (见 test_fit_pipeline_v090.py::TestFitUnitConversion):
fitparse 已经应用了 profile 的 scale, 传秒回秒, 传距离回距离。
当时的现象是因为 fixture 自己写了 `duration*1000` 造成双倍缩放。

## 这个模块做什么

用 `fit_tool` 现场合成**带 session/lap 汇总消息**的 FIT, 数值完全已知
(比如: 60 分钟恒定 200W), 供测试断言**具体数值**而不是"不为空"。

真实码表 (Garmin / Wahoo / iGPSport) 导出的 FIT 都带 session + lap,
所以这个 fixture 才是有代表性的。

## fit_tool 单位约定 (踩过的坑)

`fit_tool` 的 Message 字段**按 profile 的 display unit 收值**, 它内部自己
做 scale 换算。所以:
- `total_elapsed_time` / `total_timer_time` 传**秒** (不是毫秒)
- `total_distance` 传**米**
- `position_lat/long` 传**度**

写成 `duration_s * 1000` 会双倍缩放, 然后误以为是 parser 的锅。
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path


def _semicircles(deg: float) -> float:
    """度 → FIT semicircles

    注意: `fit_tool` 的 RecordMessage.position_lat 收的是**度**,
    它内部自己乘 2^31/180 转成 semicircles 编码。
    所以这里原样返回度, 写进文件后读出来才是 semicircles (给 parser 测换算用)。
    """
    return deg


def build_fit(
    path: str | Path,
    *,
    duration_s: int = 3600,
    avg_power: int = 200,
    avg_hr: int = 145,
    cadence: int = 88,
    sample_interval_s: int = 1,
    start: datetime | None = None,
    with_session: bool = True,
    with_lap: bool = True,
    speed_mps: float | None = None,
    power_jitter: int = 0,
    seed: int = 0,
) -> dict:
    """生成一个数值完全已知的 FIT 文件

    Args:
        duration_s:        骑行时长 (秒)
        avg_power:         平均功率 (W)
        sample_interval_s: record 采样间隔 —— 1 = 主流码表; 5/10 用于测稀疏采样
        with_session:      False = 只写 record (模拟缺汇总的第三方导出)
        with_lap:          False = 不写 lap
        power_jitter:      功率随机抖动幅度 (W), 0 = 恒定功率
        speed_mps:         速度 (m/s), None = 由 avg_power 粗估

    Returns:
        dict with the ground-truth values written into the file,
        供测试直接对照断言。
    """
    import random

    from fit_tool.fit_file_builder import FitFileBuilder
    from fit_tool.profile.messages.file_id_message import FileIdMessage
    from fit_tool.profile.messages.lap_message import LapMessage
    from fit_tool.profile.messages.record_message import RecordMessage
    from fit_tool.profile.messages.session_message import SessionMessage

    rng = random.Random(seed)
    start = start or datetime(2026, 8, 1, 6, 0, 0, tzinfo=timezone.utc)
    if speed_mps is None:
        # 粗略反推: 200W 大概 8-9 m/s
        speed_mps = max(1.0, (avg_power / 25.0) * 1.0)

    builder = FitFileBuilder(auto_define=True, min_string_size=50)
    fid = FileIdMessage()
    fid.type = 4  # activity
    fid.manufacturer = 1
    fid.product = 1
    builder.add(fid)

    dist_m = 0.0
    total_ascent = 0.0
    n_samples = 0
    for s in range(0, duration_s, sample_interval_s):
        rec = RecordMessage()
        rec.timestamp = int((start + timedelta(seconds=s)).timestamp() * 1000)
        p = avg_power + (rng.randint(-power_jitter, power_jitter) if power_jitter else 0)
        rec.power = max(0, p)
        rec.heart_rate = avg_hr
        rec.cadence = cadence
        rec.speed = speed_mps
        rec.distance = int(dist_m)
        rec.altitude = 100.0
        rec.position_lat = _semicircles(31.2304)
        rec.position_long = _semicircles(121.4737)
        builder.add(rec)
        dist_m += speed_mps * sample_interval_s
        total_ascent += 0.0
        n_samples += 1

    if with_lap:
        lap = LapMessage()
        lap.timestamp = int((start + timedelta(seconds=duration_s)).timestamp() * 1000)
        lap.start_time = int(start.timestamp() * 1000)
        lap.total_elapsed_time = duration_s
        lap.total_timer_time = duration_s
        lap.total_distance = int(dist_m)
        lap.avg_power = avg_power
        lap.max_power = avg_power
        lap.avg_heart_rate = avg_hr
        lap.max_heart_rate = avg_hr
        lap.avg_cadence = cadence
        lap.total_ascent = 0
        lap.sport = 2
        builder.add(lap)

    if with_session:
        ses = SessionMessage()
        ses.timestamp = int((start + timedelta(seconds=duration_s)).timestamp() * 1000)
        ses.start_time = int(start.timestamp() * 1000)
        # fit_tool 按 profile scale 处理: 这里传**秒**, 它内部 ×1000 存成毫秒
        # (实测: 传 3600 → fitparse 读回 3600.0 秒)
        ses.total_elapsed_time = duration_s
        ses.total_timer_time = duration_s
        ses.total_distance = int(dist_m)
        ses.avg_power = avg_power
        ses.max_power = avg_power
        ses.avg_heart_rate = avg_hr
        ses.max_heart_rate = avg_hr
        ses.avg_cadence = cadence
        ses.total_calories = 900
        ses.total_ascent = 0
        ses.sport = 2
        builder.add(ses)

    builder.build().to_file(str(path))

    return {
        "path": str(path),
        "duration_s": duration_s,
        "avg_power": avg_power,
        "avg_hr": avg_hr,
        "distance_m": dist_m,
        "sample_interval_s": sample_interval_s,
        "n_samples": n_samples,
        "with_session": with_session,
        "with_lap": with_lap,
        "speed_mps": speed_mps,
        "start": start,
    }
