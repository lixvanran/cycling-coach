"""WKO/CSV 解析器 — V0.7.1 补遗漏 + 加数据格式

支持 GoldenCheetah/TrainingPeaks/WKO 导出的 CSV 格式 (2 种):
1. **WKO Detail** (高级): 含 Time / Power / Cadence / HR / Speed / Altitude / Distance / Torque 等
2. **WKO Summary** (简化): 仅 summary 数据, 没 samples, 直接入库

WKO 格式 (GoldenCheetah 导出):
- 第一行是 "Export of xxx" 注释
- 第 2 行是日期
- 第 3 行是 "Summary" header
- 数据行: "secs, watts, km, km/h, rpm, bpm, alt, lat, lon, ..." 等
- 用 "###DETAIL###" 切分 Summary vs Detail

参考:
- GoldenCheetah WKO format: https://github.com/GoldenCheetah/GoldenCheetah/wiki/CSV-Export
- TrainingPeaks Workout CSV
"""
from __future__ import annotations
import csv
import io
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from .schema import Activity, Lap, Sample

logger = logging.getLogger(__name__)


def _parse_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    # 常见格式: "2024-09-15 10:00:00" / "2024-09-15T10:00:00" / "2024-09-15 10:00"
    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%Y-%m-%dT%H:%M",
        "%Y/%m/%d %H:%M:%S",
        "%Y/%m/%d %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M",
    ):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _f(v: str | None) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _i(v: str | None) -> int | None:
    f = _f(v)
    return int(f) if f is not None else None


class WkoCsvParser:
    """WKO/GoldenCheetah/TrainingPeaks CSV 解析器 (V0.7.1 新加数据格式)

    支持:
    - GoldenCheetah WKO Detail (含 Time/Power/HR/Cadence/Speed/Altitude/Distance)
    - GoldenCheetah WKO Summary
    - TrainingPeaks Workout CSV (basic)
    """

    def parse_file(self, path: Path) -> Activity:
        return self.parse_bytes(Path(path).read_bytes(), source_name=path.name)

    def parse_bytes(self, data: bytes, source_name: str = "uploaded.csv") -> Activity:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = data.decode("latin-1", errors="replace")

        lines = text.splitlines()
        if not lines:
            raise ValueError("CSV 文件为空")

        # 检测格式: 找 "###DETAIL###" 或 "seconds" / "secs" / "time"
        has_detail_marker = any("###DETAIL###" in ln for ln in lines)
        first_line = lines[0].lower()

        # WKO 格式: 第一行是 "Export of..." 或 "WKO" 注释
        is_wko = "wko" in first_line or "export" in first_line or has_detail_marker

        if has_detail_marker:
            return self._parse_wko_detail(lines, source_name)
        elif is_wko:
            return self._parse_wko_summary(lines, source_name)
        else:
            # 尝试 generic CSV (header + rows)
            return self._parse_generic_csv(text, source_name)

    def _parse_wko_detail(self, lines: list[str], source_name: str) -> Activity:
        """WKO Detail: 含 Time/Power/HR/Cadence/Speed/Altitude/Distance"""
        # 找 detail 段
        start_idx = 0
        for i, ln in enumerate(lines):
            if "###DETAIL###" in ln:
                start_idx = i + 1
                break

        # 找 header (在 detail 段的若干行内)
        header: list[str] = []
        data_start = start_idx
        for j in range(start_idx, min(start_idx + 10, len(lines))):
            cells = [c.strip().lower() for c in lines[j].split(",")]
            if "secs" in cells or "seconds" in cells or "time" in cells:
                header = cells
                data_start = j + 1
                break

        if not header:
            raise ValueError("WKO Detail 未找到数据 header (secs/seconds/time)")

        # 找列索引
        col = {h: i for i, h in enumerate(header)}

        def gv(row, key, default=None):
            idx = col.get(key)
            if idx is None or idx >= len(row):
                return default
            return row[idx].strip()

        samples: list[Sample] = []
        max_hr = 0
        max_power = 0
        max_speed = 0.0
        max_cadence = 0
        sum_p = 0
        n_p = 0
        sum_h = 0
        n_h = 0
        sum_c = 0
        n_c = 0
        sum_s = 0.0
        n_s = 0
        elev_gain = 0.0
        last_elev: float | None = None
        total_distance = 0.0

        # 找 WKO header 中的日期 (一般第 2 行)
        start_time: datetime | None = None
        for i in range(min(5, len(lines))):
            m = re.search(r"\d{4}-\d{2}-\d{2}", lines[i])
            if m:
                start_time = _parse_dt(lines[i].strip())
                if start_time:
                    break

        for i in range(data_start, len(lines)):
            row = lines[i].split(",")
            if len(row) < 2 or not row[0].strip():
                continue

            # 优先用 secs/seconds/time
            t = _i(gv(row, "secs")) or _i(gv(row, "seconds")) or _i(gv(row, "time"))
            if t is None:
                continue

            pwr = _i(gv(row, "watts")) or _i(gv(row, "power"))
            hr = _i(gv(row, "bpm")) or _i(gv(row, "hr")) or _i(gv(row, "heart rate")) or _i(gv(row, "heart_rate"))
            cad = _i(gv(row, "rpm")) or _i(gv(row, "cadence"))
            speed = _f(gv(row, "km/h")) or _f(gv(row, "kph")) or _f(gv(row, "speed"))
            elev = _f(gv(row, "alt")) or _f(gv(row, "altitude")) or _f(gv(row, "elevation"))
            lat = _f(gv(row, "lat")) or _f(gv(row, "latitude"))
            lon = _f(gv(row, "lon")) or _f(gv(row, "lng")) or _f(gv(row, "longitude"))
            dist = _f(gv(row, "km")) or _f(gv(row, "distance"))

            # 速度单位: WKO 是 km/h, 转 m/s
            speed_ms = (speed / 3.6) if speed is not None else None

            samples.append(Sample(
                t_offset=t,
                power=pwr,
                hr=hr,
                cadence=cad,
                speed=speed_ms,
                elevation=elev,
                lat=lat,
                lon=lon,
            ))

            if hr is not None:
                max_hr = max(max_hr, hr)
                sum_h += hr
                n_h += 1
            if pwr is not None:
                max_power = max(max_power, pwr)
                sum_p += pwr
                n_p += 1
            if cad is not None:
                max_cadence = max(max_cadence, cad)
                sum_c += cad
                n_c += 1
            if speed_ms is not None:
                max_speed = max(max_speed, speed_ms)
                sum_s += speed_ms
                n_s += 1
            if dist is not None and dist > total_distance:
                total_distance = dist
            if elev is not None and last_elev is not None:
                d_elev = elev - last_elev
                if d_elev > 0:
                    elev_gain += d_elev
            if elev is not None:
                last_elev = elev

        if not samples:
            raise ValueError("WKO Detail 不含任何数据行")

        # 单位换算: km -> m
        total_distance_m = total_distance * 1000 if total_distance > 0 and (total_distance < 1000) else total_distance

        duration_s = samples[-1].t_offset
        if start_time is None:
            start_time = datetime.utcnow()

        avg_power = round(sum_p / n_p) if n_p else None
        avg_hr = round(sum_h / n_h) if n_h else None
        avg_cadence = round(sum_c / n_c) if n_c else None
        avg_speed = round(sum_s / n_s, 2) if n_s else None

        logger.info(
            f"WKO Detail 解析完成: {len(samples)} samples, {duration_s}s, "
            f"avg_pwr={avg_power}, avg_hr={avg_hr}, max_pwr={max_power}"
        )

        return Activity(
            source="csv",
            start_time=start_time,
            duration_s=duration_s,
            distance_m=total_distance_m if total_distance_m > 0 else None,
            total_elevation_gain=elev_gain if elev_gain > 0 else None,
            avg_power=avg_power,
            max_power=max_power if max_power > 0 else None,
            avg_hr=avg_hr,
            max_hr=max_hr if max_hr > 0 else None,
            avg_cadence=avg_cadence,
            avg_speed=avg_speed,
            max_speed=max_speed if max_speed > 0 else None,
            calories=None,
            device="wko-csv-import",
            samples=samples,
            laps=[],
            raw_meta={"format": "wko_detail", "source_file": source_name},
        )

    def _parse_wko_summary(self, lines: list[str], source_name: str) -> Activity:
        """WKO Summary: 仅 summary, 没 samples"""
        # Summary 一般在文件头
        # 找 "Date,Time" 或 "Time,Duration" 之类的 row
        summary = {}
        for ln in lines[:30]:
            if "," in ln:
                parts = ln.split(",", 1)
                if len(parts) == 2:
                    k, v = parts[0].strip().lower(), parts[1].strip()
                    if k and v:
                        summary[k] = v

        # 找日期
        start_time = None
        for k in ("date", "when", "start time", "start_time"):
            if k in summary:
                start_time = _parse_dt(summary[k])
                if start_time:
                    break

        # 找时长
        duration_s = 0
        for k in ("duration", "total time", "totaltime", "elapsed"):
            if k in summary:
                v = summary[k]
                # 1:23:45 / 1h23m / 5400 (秒)
                m = re.match(r"(\d+):(\d+):(\d+)", v)
                if m:
                    h, mn, sec = map(int, m.groups())
                    duration_s = h * 3600 + mn * 60 + sec
                    break
                m = re.match(r"(\d+)h(\d+)m?", v)
                if m:
                    h, mn = map(int, m.groups())
                    duration_s = h * 3600 + mn * 60
                    break
                duration_s = _i(v) or 0
                if duration_s > 0:
                    break

        # 距离 (km)
        distance_m = None
        for k in ("distance", "km", "total distance"):
            if k in summary:
                km = _f(summary[k])
                if km is not None:
                    distance_m = km * 1000
                    break

        # 平均功率
        avg_power = None
        for k in ("avg watts", "avg power", "average power", "watts"):
            if k in summary:
                avg_power = _i(summary[k])
                if avg_power is not None:
                    break

        max_power = None
        for k in ("max watts", "max power", "maximum power", "peak"):
            if k in summary:
                max_power = _i(summary[k])
                if max_power is not None:
                    break

        avg_hr = None
        for k in ("avg bpm", "avg hr", "average hr", "bpm"):
            if k in summary:
                avg_hr = _i(summary[k])
                if avg_hr is not None:
                    break

        max_hr = None
        for k in ("max bpm", "max hr", "maximum hr"):
            if k in summary:
                max_hr = _i(summary[k])
                if max_hr is not None:
                    break

        logger.info(
            f"WKO Summary 解析完成: {duration_s}s, "
            f"avg_pwr={avg_power}, avg_hr={avg_hr}, max_pwr={max_power}"
        )

        return Activity(
            source="csv",
            start_time=start_time or datetime.utcnow(),
            duration_s=duration_s,
            distance_m=distance_m,
            avg_power=avg_power,
            max_power=max_power,
            avg_hr=avg_hr,
            max_hr=max_hr,
            samples=[],
            laps=[],
            raw_meta={"format": "wko_summary", "source_file": source_name, "summary": summary},
        )

    def _parse_generic_csv(self, text: str, source_name: str) -> Activity:
        """Generic CSV fallback: header + 数据行, 时间戳格式"""
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        if not rows:
            raise ValueError("CSV 文件不含数据")

        # 找常见列名
        cols = {k.lower().strip(): k for k in rows[0].keys()}

        def get(row, *keys, default=None):
            for k in keys:
                kl = k.lower()
                if kl in cols:
                    return row.get(cols[kl])
            return default

        # 时间列
        time_col = None
        for k in ("time", "timestamp", "elapsed", "secs", "seconds"):
            if k in cols:
                time_col = k
                break
        if not time_col:
            raise ValueError("CSV 找不到时间列 (time/timestamp/elapsed/secs)")

        samples = []
        max_hr = 0
        max_power = 0
        sum_p = 0
        n_p = 0
        sum_h = 0
        n_h = 0
        max_speed = 0.0

        for row in rows:
            t = _i(row[cols[time_col]])
            if t is None:
                continue

            pwr = _i(get(row, "power", "watts"))
            hr = _i(get(row, "hr", "bpm", "heart_rate"))
            cad = _i(get(row, "cadence", "rpm"))
            speed = _f(get(row, "speed"))
            elev = _f(get(row, "elevation", "altitude", "alt"))
            lat = _f(get(row, "lat", "latitude"))
            lon = _f(get(row, "lon", "lng", "longitude"))

            samples.append(Sample(
                t_offset=t, power=pwr, hr=hr, cadence=cad,
                speed=speed, elevation=elev, lat=lat, lon=lon,
            ))

            if hr:
                max_hr = max(max_hr, hr)
                sum_h += hr
                n_h += 1
            if pwr:
                max_power = max(max_power, pwr)
                sum_p += pwr
                n_p += 1
            if speed:
                max_speed = max(max_speed, speed)

        if not samples:
            raise ValueError("CSV 不含任何有效数据行")

        duration_s = samples[-1].t_offset
        return Activity(
            source="csv",
            start_time=datetime.utcnow(),
            duration_s=duration_s,
            avg_power=round(sum_p / n_p) if n_p else None,
            max_power=max_power if max_power > 0 else None,
            avg_hr=round(sum_h / n_h) if n_h else None,
            max_hr=max_hr if max_hr > 0 else None,
            samples=samples,
            laps=[],
            raw_meta={"format": "generic_csv", "source_file": source_name},
        )


# 便捷函数
def parse_wko_csv(data: bytes, source_name: str = "uploaded.csv") -> Activity:
    return WkoCsvParser().parse_bytes(data, source_name)
