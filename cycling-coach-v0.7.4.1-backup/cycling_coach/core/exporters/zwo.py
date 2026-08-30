"""ZWO (Zwift workout XML) 导出器 — V0.7.1 增加课程导出

Zwift workout XML 格式:
- 文件名 .zwo
- 顶层 <workout_file>
- <author> / <name> / <description> / <sportType> / <workout>
- <workout> 含 <SteadyState> / <Warmup> / <Cooldown> / <IntervalsT> / <FreeRide> 等
- <IntervalsT> 含 repeat + IntervalsT 子元素, 表示重复

参考:
- Zwift workout XML spec: https://github.com/zoffline/zwift-offline/blob/master/docs/WorkoutFile.md
- TrainerRoad .zwo 导出

支持输入 (前端 BuilderPage structure):
- flat: [{kind, duration_s, power_pct_ftp?}, ...] — 系统课程
- nested: [{kind: "loop", reps, work, rest}, ...] — 用户 Builder 课程
"""
from __future__ import annotations
import logging
from xml.etree import ElementTree as ET
from xml.dom import minidom
from typing import Iterable, Union

logger = logging.getLogger(__name__)

# Step kind → ZWO element type 映射
# 借鉴 Zwift workout XML 规范
def _kind_to_zwo_type(kind: str) -> str:
    return {
        "warmup": "Warmup",
        "cooldown": "Cooldown",
        "main": "SteadyState",
        "recovery": "SteadyState",  # ZWO 没有独立 recovery, 复用 SteadyState
    }.get(kind, "SteadyState")


def _seconds_to_zwo_time(seconds: int) -> int:
    """ZWO duration 是秒 (整数)"""
    return int(seconds)


def _ftp_to_zwo_power(power_pct_ftp: float | None) -> int:
    """ZWO power 是 % FTP (0-1000), 250 = 2.5x FTP"""
    if power_pct_ftp is None:
        return 100  # 默认 100% FTP
    return int(power_pct_ftp * 10)  # 75% FTP → 750


def _build_block(step: dict) -> ET.Element:
    """flat step → ZWO element"""
    kind = step.get("kind", "main")
    duration = _seconds_to_zwo_time(step.get("duration_s", 60))
    power = _ftp_to_zwo_power(step.get("power_pct_ftp"))
    zwo_type = _kind_to_zwo_type(kind)

    el = ET.Element(zwo_type, {
        "Duration": str(duration),
        "Power": str(power),
    })
    return el


def _build_loop_block(loop: dict) -> ET.Element:
    """loop block → ZWO <IntervalsT>"""
    reps = int(loop.get("reps", 3))
    work = loop.get("work", {})
    rest = loop.get("rest")
    label = loop.get("label", f"循环 {reps}×")

    intervals_t = ET.Element("IntervalsT", {
        "Repeat": str(reps),
        "OnDuration": str(_seconds_to_zwo_time(work.get("duration_s", 60))),
        "OnPower": str(_ftp_to_zwo_power(work.get("power_pct_ftp"))),
        "OffDuration": str(_seconds_to_zwo_time(rest.get("duration_s", 30)) if rest else 30),
        "OffPower": str(_ftp_to_zwo_power(rest.get("power_pct_ftp") if rest else 50)),
    })
    return intervals_t


def export_zwo(
    title: str,
    description: str,
    structure: list[dict],
    author: str = "Cycling Coach",
) -> str:
    """导出 ZWO 格式 (Zwift / Rouvy / 训练台通用)

    Args:
        title: 课程标题
        description: 课程描述
        structure: 课程结构 (flat 或 nested, 见模块 docstring)
        author: 作者

    Returns:
        XML 字符串 (符合 Zwift workout XML 规范)
    """
    workout_file = ET.Element("workout_file")

    # 元信息
    ET.SubElement(workout_file, "author").text = author
    ET.SubElement(workout_file, "name").text = title
    ET.SubElement(workout_file, "description").text = description or title
    ET.SubElement(workout_file, "sportType").text = "bike"
    ET.SubElement(workout_file, "tags")

    # 课程主体
    workout = ET.SubElement(workout_file, "workout")

    for step in structure:
        kind = step.get("kind", "main")
        if kind == "loop":
            workout.append(_build_loop_block(step))
        else:
            workout.append(_build_block(step))

    # 美化 XML 输出
    rough_string = ET.tostring(workout_file, encoding="unicode")
    reparsed = minidom.parseString(rough_string)
    return reparsed.toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")
