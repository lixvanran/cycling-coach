"""TCX (Training Center XML) 解析器 — V0.7 补遗漏

TCX 是 Garmin Training Center 标准导出格式, V0.7 起支持上传
支持字段: GPS (lat/lon) + 海拔 + 心率 + 功率 + 踏频 + 速度 + 距离 + 配速

参考:
- TCX 规范 (Garmin) — http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2/
- Garmin Extensions: Watts / Cadence / Speed / RunCadence
"""
from __future__ import annotations
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree as ET

from .schema import Activity, Lap, Sample

logger = logging.getLogger(__name__)

# TCX 命名空间
_TCX_NS = {
    "ns": "http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2",
    "ns2": "http://www.garmin.com/xmlschemas/ActivityExtension/v2",
    "ns3": "http://www.garmin.com/xmlschemas/ProfileExtension/v1",
}


def _parse_dt(s: str | None) -> datetime | None:
    """TCX 时间格式: 2024-09-15T10:00:00.000Z 或 2024-09-15T10:00:00+08:00"""
    if not s:
        return None
    s = s.strip()
    # 兼容 .000Z 形式
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc).replace(tzinfo=None)
    except Exception as e:
        logger.warning(f"TCX 时间解析失败: {s} ({e})")
        return None


def _int(v) -> int | None:
    if v is None or v == "":
        return None
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _float(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _first_text(elem: ET.Element, path: str) -> str | None:
    """用 ns 前缀找子元素文本"""
    for p in path.split("|"):
        e = elem.find(p, _TCX_NS)
        if e is not None and e.text:
            return e.text.strip()
    return None


def _first_int(elem: ET.Element, path: str) -> int | None:
    return _int(_first_text(elem, path))


def _first_float(elem: ET.Element, path: str) -> float | None:
    return _float(_first_text(elem, path))


class TcxParser:
    """TCX 解析器 (V0.7 新加数据格式)

    支持: .tcx 文件 (Garmin Training Center)
    输出: Activity (统一 schema)
    """

    def parse_file(self, path: Path) -> Activity:
        return self.parse_bytes(Path(path).read_bytes(), source_name=path.name)

    def parse_bytes(self, data: bytes, source_name: str = "uploaded.tcx") -> Activity:
        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            raise ValueError(f"TCX XML 解析失败: {e}") from e

        # 找 Activities/Activity (可能有 Author / Activities 嵌套)
        activities = root.findall(".//ns:Activity", _TCX_NS)
        if not activities:
            raise ValueError("TCX 文件不含 Activity 节点")

        # 取第一个 (一个 TCX 文件多个 Activity 罕见)
        act_elem = activities[0]
        sport = _first_text(act_elem, "ns:Sport")
        if sport:
            logger.info(f"TCX 运动类型: {sport}")

        # ID + Lap
        activity_id = _first_text(act_elem, "ns:Id")
        lap_elems = act_elem.findall("ns:Lap", _TCX_NS)

        start_time = _parse_dt(activity_id) if activity_id else None

        # 聚合所有 Trackpoint
        samples: list[Sample] = []
        max_hr = 0
        max_power = 0
        max_speed = 0.0
        max_cadence = 0
        sum_power = 0
        n_power = 0
        sum_hr = 0
        n_hr = 0
        sum_cadence = 0
        n_cadence = 0
        sum_speed = 0.0
        n_speed = 0
        total_distance = 0.0
        last_lat: float | None = None
        last_lon: float | None = None
        elev_gain = 0.0
        last_elev: float | None = None
        first_time: datetime | None = None

        for tp in act_elem.iter("{http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2}Trackpoint"):
            t = _parse_dt(_first_text(tp, "ns:Time"))
            if t is None:
                continue
            if first_time is None:
                first_time = t
                if start_time is None:
                    start_time = t

            t_offset = int((t - first_time).total_seconds())

            # 位置
            pos = tp.find("ns:Position", _TCX_NS)
            lat = _float(_first_text(pos, "ns:LatitudeDegrees")) if pos is not None else None
            lon = _float(_first_text(pos, "ns:LongitudeDegrees")) if pos is not None else None

            # 海拔
            elev = _first_float(tp, "ns:AltitudeMeters")

            # 距离
            dist = _first_float(tp, "ns:DistanceMeters")

            # 心率
            hr = _first_int(tp, "ns:HeartRateBpm|ns:Value")

            # 功率 (Garmin Extensions)
            pwr = _first_int(
                tp, "ns:Extensions/ns2:TPX/ns2:Watts|ns:Extensions/ns2:ActivityLapExtension/ns2:Watts"
            )

            # 速度 (Garmin Extensions) — 优先 m/s
            speed = _first_float(
                tp, "ns:Extensions/ns2:TPX/ns2:Speed|ns:Extensions/ns2:Speed"
            )

            # 踏频
            cad = _first_int(
                tp, "ns:Extensions/ns2:TPX/ns2:RunCadence|ns:Extensions/ns2:TPX/ns2:Cadence|ns:Extensions/ns2:Cadence"
            )

            samples.append(Sample(
                t_offset=t_offset,
                power=pwr,
                hr=hr,
                cadence=cad,
                speed=speed,
                elevation=elev,
                lat=lat,
                lon=lon,
            ))

            if hr is not None:
                max_hr = max(max_hr, hr)
                sum_hr += hr
                n_hr += 1
            if pwr is not None:
                max_power = max(max_power, pwr)
                sum_power += pwr
                n_power += 1
            if cad is not None:
                max_cadence = max(max_cadence, cad)
                sum_cadence += cad
                n_cadence += 1
            if speed is not None:
                max_speed = max(max_speed, speed)
                sum_speed += speed
                n_speed += 1
            if dist is not None:
                total_distance = max(total_distance, dist)
            if elev is not None and last_elev is not None:
                d_elev = elev - last_elev
                if d_elev > 0:
                    elev_gain += d_elev
            if elev is not None:
                last_elev = elev

        # 距离 fallback: 累加 (last - first)
        if total_distance == 0 and samples:
            first = samples[0]
            last = samples[-1]
            if first.lat is not None and last.lat is not None:
                from math import radians, sin, cos, asin
                # Haversine 累加
                pass  # 简单跳过, 距离由 DistanceMeters 提供

        # 解析 Lap
        laps: list[Lap] = []
        for le in lap_elems:
            lap_start = _parse_dt(_first_text(le, "ns:StartTime"))
            lap_dur = _first_float(le, "ns:TotalTimeSeconds")
            lap_dist = _first_float(le, "ns:DistanceMeters")
            lap_cal = _first_int(le, "ns:Calories")
            lap_max_hr = _first_int(le, "ns:MaximumHeartRateBpm|ns:Value")
            lap_avg_hr = _first_int(le, "ns:AverageHeartRateBpm|ns:Value")
            lap_max_pwr = _first_int(le, "ns:Extensions/ns2:LX/ns2:MaximumWatts|ns:Extensions/ns2:ActivityLapExtension/ns2:MaximumWatts")
            lap_avg_pwr = _first_int(le, "ns:Extensions/ns2:LX/ns2:AverageWatts|ns:Extensions/ns2:ActivityLapExtension/ns2:AverageWatts")
            lap_max_cad = _first_int(le, "ns:Extensions/ns2:LX/ns2:MaximumCadence|ns:Extensions/ns2:ActivityLapExtension/ns2:MaximumCadence")
            lap_avg_cad = _first_int(le, "ns:Extensions/ns2:LX/ns2:AverageCadence|ns:Extensions/ns2:ActivityLapExtension/ns2:AverageCadence")
            lap_start_offset = 0
            if lap_start and first_time:
                lap_start_offset = int((lap_start - first_time).total_seconds())
            laps.append(Lap(
                start_offset=lap_start_offset,
                duration_s=_int(lap_dur) or 0,
                avg_power=lap_avg_pwr,
                avg_hr=lap_avg_hr,
                avg_cadence=lap_avg_cad,
                max_power=lap_max_pwr,
                max_hr=lap_max_hr,
                distance_m=lap_dist,
                label=None,  # TCX 没有标准 label
                trigger=None,
            ))

        if not samples:
            raise ValueError("TCX 文件不含任何 Trackpoint")

        if start_time is None:
            start_time = first_time or datetime.utcnow()

        # 时长
        duration_s = int((samples[-1].t_offset)) if samples else 0
        if duration_s == 0 and first_time and start_time:
            duration_s = int((samples[-1].t_offset))

        # 平均值
        avg_power = round(sum_power / n_power) if n_power else None
        avg_hr = round(sum_hr / n_hr) if n_hr else None
        avg_cadence = round(sum_cadence / n_cadence) if n_cadence else None
        avg_speed = round(sum_speed / n_speed, 2) if n_speed else None

        logger.info(
            f"TCX 解析完成: {len(samples)} samples, "
            f"{duration_s}s, {total_distance:.0f}m, "
            f"avg_pwr={avg_power}, avg_hr={avg_hr}, "
            f"max_pwr={max_power}, max_hr={max_hr}"
        )

        return Activity(
            source="tcx",
            start_time=start_time,
            duration_s=duration_s,
            distance_m=total_distance if total_distance > 0 else None,
            total_elevation_gain=elev_gain if elev_gain > 0 else None,
            avg_power=avg_power,
            max_power=max_power if max_power > 0 else None,
            avg_hr=avg_hr,
            max_hr=max_hr if max_hr > 0 else None,
            avg_cadence=avg_cadence,
            avg_speed=avg_speed,
            max_speed=max_speed if max_speed > 0 else None,
            calories=None,  # TCX Lap 里有, 但 Activity 顶层不直接聚合
            device="tcx-import",
            samples=samples,
            laps=laps,
            raw_meta={"sport": sport, "source_file": source_name},
        )

def parse_tcx(data: bytes, source_name: str = 'uploaded.tcx') -> Activity:
    return TcxParser().parse_bytes(data, source_name)

