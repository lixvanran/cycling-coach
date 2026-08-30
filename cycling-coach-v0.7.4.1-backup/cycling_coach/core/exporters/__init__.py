"""课程导出器 — V0.7.1 增加课程导出功能

支持:
- ZWO (Zwift workout XML)
- MRC (Rouvy / MiniRoad 训练课程)
- ERG (训练台通用)
- JSON (自用)

参考:
- Zwift workout XML: http://www.zwift.com/news/workout-xml-spec
- MRC: https://www.rouvy.com/blog/mrc-file-format (W' + duration_min)
- ERG: CompuTrainer / TrainerRoad 标准
"""
from .zwo import export_zwo
from .mrc import export_mrc
from .erg import export_erg
from .fit import export_fit_workout

__all__ = ["export_zwo", "export_mrc", "export_erg", "export_fit_workout"]
