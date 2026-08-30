"""ERG (训练台 / TrainerRoad / CompuTrainer) 导出器 — V0.7.1 增加课程导出

ERG 格式 (CompuTrainer / TrainerRoad):
- 文件名 .erg
- 文本格式
- 第一行: <课程名> <描述> <间隔数>
- 后续行: <分钟> <功率 W>
"""
from __future__ import annotations
import logging
from typing import Iterable

logger = logging.getLogger(__name__)


def _flatten_to_erg(structure: list[dict], ftp: int = 250) -> list[tuple[float, int]]:
    """flat → [(minutes, watts), ...]"""
    flat: list[tuple[float, int]] = []
    for step in structure:
        kind = step.get("kind", "main")
        if kind == "loop":
            reps = int(step.get("reps", 3))
            work = step.get("work", {})
            rest = step.get("rest")
            work_min = int(work.get("duration_s", 60)) / 60
            work_pwr = int((work.get("power_pct_ftp") or 75) * ftp / 100)
            for _ in range(reps):
                flat.append((work_min, work_pwr))
                if rest:
                    rest_min = int(rest.get("duration_s", 30)) / 60
                    rest_pwr = int((rest.get("power_pct_ftp") or 50) * ftp / 100)
                    flat.append((rest_min, rest_pwr))
        else:
            duration_min = int(step.get("duration_s", 60)) / 60
            power_w = int((step.get("power_pct_ftp") or 75) * ftp / 100)
            flat.append((duration_min, power_w))
    return flat


def export_erg(
    title: str,
    description: str,
    structure: list[dict],
    ftp: int = 250,
) -> str:
    """导出 ERG 格式 (CompuTrainer / TrainerRoad)"""
    flat = _flatten_to_erg(structure, ftp)
    lines = [f"{title} {description or ''} {len(flat)}"]
    for minutes, watts in flat:
        lines.append(f"{minutes:.3f}\t{watts}")
    return "\n".join(lines) + "\n"
