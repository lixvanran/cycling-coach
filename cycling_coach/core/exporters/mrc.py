"""MRC (Rouvy / MiniRoad workout) 导出器 — V0.7.1 增加课程导出

MRC 格式是 Rouvy (前身 VirtualTraining) 和 MiniRoad 用的训练课程文件:
- 文件名 .mrc
- 文本格式 (类似 CSV 但带元信息)
- 第一行 [COURSE HEADER] (可省略)
- 后续行: <duration_s> <intensity_pct> [<cadence>]

参考:
- Rouvy .mrc 规范
- MiniRoad 支持的 MRC 格式

格式示例:
[COURSE HEADER]
VERSION = 1
UNITS = METRIC
[END COURSE HEADER]
[COURSE DATA]
60 50
300 75
[END COURSE DATA]
"""
from __future__ import annotations
import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def _flatten_structure(structure: list[dict]) -> list[tuple[int, int]]:
    """flat / nested structure → [(duration_s, power_pct), ...]"""
    flat: list[tuple[int, int]] = []
    for step in structure:
        kind = step.get("kind", "main")
        if kind == "loop":
            reps = int(step.get("reps", 3))
            work = step.get("work", {})
            rest = step.get("rest")
            work_dur = int(work.get("duration_s", 60))
            work_pwr = int(work.get("power_pct_ftp") or 75)
            for _ in range(reps):
                flat.append((work_dur, work_pwr))
                if rest:
                    flat.append((int(rest.get("duration_s", 30)), int(rest.get("power_pct_ftp") or 50)))
        else:
            duration = int(step.get("duration_s", 60))
            power = int(step.get("power_pct_ftp") or 75)
            flat.append((duration, power))
    return flat


def export_mrc(
    title: str,
    description: str,
    structure: list[dict],
) -> str:
    """导出 MRC 格式 (Rouvy / MiniRoad / Wahoo SYSTM)

    Args:
        title: 课程标题
        description: 课程描述
        structure: 课程结构 (flat 或 nested)

    Returns:
        MRC 文本 (UTF-8)
    """
    flat = _flatten_structure(structure)
    lines = []
    lines.append("[COURSE HEADER]")
    lines.append("VERSION = 2")
    lines.append("UNITS = METRIC")
    lines.append(f"NAME = {title}")
    if description:
        lines.append(f"DESCRIPTION = {description}")
    lines.append("[END COURSE HEADER]")
    lines.append("")
    lines.append("[COURSE DATA]")
    for dur, pwr in flat:
        # MRC 格式: 时长(秒) + 强度(% FTP)
        lines.append(f"{dur} {pwr}")
    lines.append("[END COURSE DATA]")
    return "\n".join(lines)
