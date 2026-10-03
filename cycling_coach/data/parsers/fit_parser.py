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


# V0.9.0: FIT 单位换算 — 审计笔记
#
# 实测结论 (tests/test_fit_pipeline_v090.py::TestFitUnitConversion 验证):
#   fitparse **已经**应用了 FIT profile 里的 scale/offset, 直接返回人类单位:
#     total_distance      写 30600  → 读 30600.0   (m)
#     total_elapsed_time  写 3600   → 读 3600.0    (s, 不是 ms)
#     speed / altitude / total_ascent              同样已是人类单位
#   所以这些字段**不需要**再除 1000。之前审计时误判过一次, 原因是
#   测试 fixture 自己写了 duration*1000 造成双倍缩放, 误以为是 parser 的锅。
#
# 真正需要手动换算的只有 semicircles 类字段:
#   position_lat / position_long → 1 semicircle = 180° / 2^31
#   实测: 写 31.2304° → 读 372593185 (semicircles 原值), 必须自己转。


def _semicircles_to_deg(value) -> float | None:
    """FIT semicircles → 度 (position_lat / position_long)

    1 semicircle = 180° / 2^31
    """
    v = _to_int(value)
    if v is None:
        return None
    return v * (180.0 / (2 ** 31))


class FitParser:
    """FIT → Activity 解析器"""

    def parse_file(self, path: str | Path) -> Activity:
        path = Path(path)
        logger.info(f"开始解析 FIT: {path.name}")
        try:
            fitfile = fitparse.FitFile(str(path))
        except fitparse.utils.FitHeaderError as e:
            # V0.7.4.2: iGPSport 等国产码表常出现 FIT 头异常, 友好错误
            raise ValueError(
                f"FIT 文件头错误 (设备: {path.name}): {e}. "
                "可能原因: 1) 文件损坏 2) 不支持的码表固件版本 3) 导出中断"
            ) from e
        except Exception as e:
            raise ValueError(
                f"FIT 解析失败 (设备: {path.name}): {type(e).__name__}: {e}"
            ) from e
        return self._build_activity(fitfile, path=path)

    def parse_bytes(self, data: bytes, source_name: str = "uploaded.fit") -> Activity:
        """直接从字节流解析(上传场景)"""
        import io
        try:
            fitfile = fitparse.FitFile(io.BytesIO(data))
        except fitparse.utils.FitHeaderError as e:
            raise ValueError(
                f"FIT 文件头错误 ({source_name}): {e}. "
                "可能原因: 1) 文件损坏 2) iGPSport/行者等国产码表固件版本 3) 导出中断"
            ) from e
        except Exception as e:
            raise ValueError(
                f"FIT 解析失败 ({source_name}): {type(e).__name__}: {e}"
            ) from e
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
                lat=_semicircles_to_deg(msg.get_value("position_lat")),
                lon=_semicircles_to_deg(msg.get_value("position_long")),
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
                duration_s=_to_int(msg.get_value("total_elapsed_time")) or 0,
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

        # 3b) V0.9.0 稳定性: session 缺失时的 record 流兜底
        #
        # 历史问题: 某些导出 (部分国产码表 / 第三方工具 / 被截断的导出)
        # 只有 record 消息没有 session 汇总。原来这里全部留 0/None,
        # 结果: 时长 0、距离 None、功率 None → TSS None → PMC 全 0,
        # 而上层 watcher 还报"导入成功"。用户看到成功提示 + 空的运动列表。
        #
        # 现在: 从 record 流自己算总量兜底, 并且记录 fallback_used 供上层提示。
        fallback_used = False
        if duration_s == 0 and len(samples) >= 1:
            fallback_used = True
            # 时长 = 末样本 offset - 首样本 offset + 采样间隔中位数
            # (只取末样本 offset 会少一个间隔: 1Hz × 2400 点应得 2400s 而不是 2399s)
            if len(samples) >= 2:
                gaps = [
                    samples[i].t_offset - samples[i - 1].t_offset
                    for i in range(1, len(samples))
                    if samples[i].t_offset is not None
                    and samples[i - 1].t_offset is not None
                ]
                gaps = [g for g in gaps if g > 0]
                median_gap = sorted(gaps)[len(gaps) // 2] if gaps else 1
                duration_s = int(
                    (samples[-1].t_offset or 0) - (samples[0].t_offset or 0) + median_gap
                )
            else:
                duration_s = int(samples[0].t_offset or 0)
            powers = [s.power for s in samples if s.power is not None]
            if powers and avg_power is None:
                avg_power = int(round(sum(powers) / len(powers)))
            if max_power is None and powers:
                max_power = max(powers)
            hrs = [s.hr for s in samples if s.hr is not None]
            if avg_hr is None and hrs:
                avg_hr = int(round(sum(hrs) / len(hrs)))
            if max_hr is None and hrs:
                max_hr = max(hrs)
            cads = [s.cadence for s in samples if s.cadence is not None]
            if avg_cadence is None and cads:
                avg_cadence = int(round(sum(cads) / len(cads)))
            if distance_m is None:
                # Sample 没有累计距离字段(record.distance 没被采集),
                # 用 speed 对时间做梯形积分 —— 对速度噪声更稳
                spd = [(s.t_offset, s.speed) for s in samples if s.speed is not None]
                if len(spd) >= 2:
                    total = 0.0
                    for i in range(1, len(spd)):
                        dt = spd[i][0] - spd[i - 1][0]
                        if dt > 0:
                            total += (spd[i][1] + spd[i - 1][1]) / 2.0 * dt
                    distance_m = round(total, 1)
            if total_elevation_gain is None:
                elevs = [s.elevation for s in samples if s.elevation is not None]
                if len(elevs) >= 2:
                    deltas = [
                        max(0.0, elevs[i] - elevs[i - 1])
                        for i in range(1, len(elevs))
                    ]
                    total_elevation_gain = round(sum(deltas), 1)
            logger.warning(
                f"FIT 缺 session 汇总, 已从 {len(samples)} 条 record 回算: "
                f"duration={duration_s}s avg_power={avg_power} dist={distance_m}"
            )

        # 4) Device info (V0.7.4.2 改: 兼容 iGPSport/行者 等国产码表)
        for msg in fitfile.get_messages("device_info"):
            # fitparse 1.2.0: get_value 不接受 default 参数
            # 国产码表 (iGPSport/行者/IGPSPORT) 可能用字符串而非 enum, 需 try-except
            try:
                manufacturer_raw = msg.get_value("manufacturer")
            except Exception:
                manufacturer_raw = None
            try:
                product_raw = msg.get_value("product_name") or msg.get_value("product")
            except Exception:
                product_raw = None
            try:
                serial_raw = msg.get_value("serial_number")
            except Exception:
                serial_raw = None
            # 字符串化 (兼容字符串 + 数字 enum)
            parts = []
            if manufacturer_raw is not None:
                parts.append(str(manufacturer_raw))
            if product_raw is not None:
                parts.append(str(product_raw))
            if serial_raw is not None and not parts:
                parts.append(str(serial_raw))
            device = " ".join(parts).strip() or None
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
            raw_meta={
                "file": source,
                "n_samples": len(samples),
                "n_laps": len(laps),
                # V0.9.0: 标记"汇总是从 record 流回算的"。
                # 上层 (service.upload) 读这个字段, 在返回里带上 warning,
                # 让用户知道这条数据是重建的而不是设备原始汇总 ——
                # 静默重建等于骗人, TP 那种"数据可信"的产品不能这么干。
                "reconstructed": fallback_used,
            },
        )
        logger.info(
            f"FIT 解析完成: {len(samples)} samples, {len(laps)} laps, "
            f"duration={duration_s}s, NP≈{avg_power}W"
        )
        return activity


def parse_fit(path: str | Path) -> Activity:
    """便捷函数"""
    return FitParser().parse_file(path)
