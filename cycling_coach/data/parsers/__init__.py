"""backend.parsers - 数据解析层

V0.1.0:仅实现 FIT。TCX / CSV 留 V1.0。
"""
from .schema import Activity, Sample, Lap
from .fit_parser import FitParser, parse_fit

__all__ = ["Activity", "Sample", "Lap", "FitParser", "parse_fit"]
