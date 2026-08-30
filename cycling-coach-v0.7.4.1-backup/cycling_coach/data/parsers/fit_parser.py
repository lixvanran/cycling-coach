"""FIT 文件解析器

fitparse 是 FIT 官方 Python 库,支持 Record / Lap / Session 完整解析
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import fitparse  # type: ignore

from .schema import Activity, Lap, Sample

logger = logging.getLogger(__name__)

# 一些 FIT 字段类型映射(timestamp / enum / 等)
_FIT_LAP_TRIGGER = {
    0: "manual", 1: "time", 2: "distance", 3: "position",
    4: "heart_rate", 5: "power", 6: "fitness_equipment", 7: "auto",
}


def _to_int(v) -> int | None:
    if v is None:
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _to_float(v) -> float | None:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _gv(msg, name, default=None):
    """安全的 msg.get_value — fitparse 1.2.0 不接受 default 参数,这里统一处理

    用法:`_gv(msg, 'manufacturer', '')` 等价于旧版 `msg.get_value('manufacturer', '')`
    """
    try:
        v = msg.get_value(name)
        if v is None:
            return default
        return v if v else default
    except (KeyError, AttributeError, TypeError):
        return default


def _normalize_dt(dt: datetime | None) -> datetime | None:
    """FIT 时间戳是 UTC,转成带时区的本地时间"""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


class FitParser:
    """FIT → Activity 解析器"""

    def parse_file(self, path: str | Path) -> Activity:
        path = Path(path)
        logger.info(f"开始解析 FIT: {path.name}")
        fitfile = fitparse.FitFile(str(path))
        return self._build_activity(fitfile, path=path)

    def parse_bytes(self, data: bytes, source_name: str = "uploaded.fit") -> Activity:
        """直接从字节流解析(上传场景)"""
        import io
        fitfile = fitparse.FitFile(io.BytesIO(data))
        return self._build_activity(fitfile, source_name=source_name)

    def _build_activity(
        self, fitfile: fitparse.FitFile, path: Path | None = None,
        source_name: str | None = None,
    ) -> Activity:
        # 1) Record messages → samples
        samples: list[Sample] = []
        start_time: datetime | None = None

        for msg in fitfile.get_messages("record"):
            t = _normalize_dt(msg.get_value("timestamp"))
            if t is None:
                continue
            if start_time is None:
                start_time = t
            offset = int((t - start_time).total_seconds())
            samples.append(Sample(
                t_offset=offset,
                power=_to_int(msg.get_value("power")),
                hr=_to_int(msg.get_value("heart_rate")),
                cadence=_to_int(msg.get_value("cadence")),
                speed=_to_float(msg.get_value("speed")),
                elevation=_to_float(msg.get_value("altitude")),
                lat=_to_float(msg.get_value("position_lat")),
                lon=_to_float(msg.get_value("position_long")),
                temperature=_to_int(msg.get_value("temperature")),
            ))

        # 2) Lap messages
        laps: list[Lap] = []
        for msg in fitfile.get_messages("lap"):
            start = _normalize_dt(msg.get_value("start_time"))
            if start is None or start_time is None:
                continue
            laps.append(Lap(
                start_offset=int((start - start_time).total_seconds()),
                duration_s=int(_to_int(msg.get_value("total_elapsed_time")) or 0),
                avg_power=_to_int(msg.get_value("avg_power")),
                avg_hr=_to_int(msg.get_value("avg_heart_rate")),
                avg_cadence=_to_int(msg.get_value("avg_cadence")),
                max_power=_to_int(msg.get_value("max_power")),
                max_hr=_to_int(msg.get_value("max_heart_rate")),
                distance_m=_to_float(msg.get_value("total_distance")),
                trigger=_FIT_LAP_TRIGGER.get(
                    _to_int(msg.get_value("start_trigger")) or 0, "manual"
                ),
            ))

        # 3) Session summary
        avg_power = max_power = avg_hr = max_hr = avg_cadence = None
        avg_speed = max_speed = distance_m = total_elevation_gain = None
        calories = duration_s = 0
        device = None

        for msg in fitfile.get_messages("session"):
            duration_s = _to_int(msg.get_value("total_elapsed_time")) or 0
            distance_m = _to_float(msg.get_value("total_distance"))
            avg_power = _to_int(msg.get_value("avg_power"))
            max_power = _to_int(msg.get_value("max_power"))
            avg_hr = _to_int(msg.get_value("avg_heart_rate"))
            max_hr = _to_int(msg.get_value("max_heart_rate"))
            avg_cadence = _to_int(msg.get_value("avg_cadence"))
            avg_speed = _to_float(msg.get_value("avg_speed"))
            max_speed = _to_float(msg.get_value("max_speed"))
            total_elevation_gain = _to_float(msg.get_value("total_ascent"))
            calories = _to_int(msg.get_value("total_calories")) or 0
            break  # 通常只有一个 session

        # 4) Device info
        for msg in fitfile.get_messages("device_info"):
            # fitparse 1.2.0: get_value 不接受 default 参数,用 _gv helper
            device = (
                f"{_gv(msg, 'manufacturer', '')} {_gv(msg, 'product_name', '')}".strip()
                or _gv(msg, "serial_number")
            )
            if device:
                break

        source = path.name if path else (source_name or "unknown.fit")
        activity = Activity(
            source="fit",
            start_time=start_time or datetime.now(timezone.utc),
            duration_s=duration_s,
            distance_m=distance_m,
            total_elevation_gain=total_elevation_gain,
            avg_power=avg_power,
            max_power=max_power,
            avg_hr=avg_hr,
            max_hr=max_hr,
            avg_cadence=avg_cadence,
            avg_speed=avg_speed,
            max_speed=max_speed,
            calories=calories,
            device=device,
            samples=samples,
            laps=laps,
            raw_meta={"file": source, "n_samples": len(samples), "n_laps": len(laps)},
        )
        logger.info(
            f"FIT 解析完成: {len(samples)} samples, {len(laps)} laps, "
            f"duration={duration_s}s, NP≈{avg_power}W"
        )
        return activity


def parse_fit(path: str | Path) -> Activity:
    """便捷函数"""
    return FitParser().parse_file(path)
