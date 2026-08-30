"""数据模型:统一 Activity / Sample / Lap schema

所有解析器(FIT/TCX/CSV)最终都输出 Activity,后续处理不关心来源
"""
from __future__ import annotations
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Sample(BaseModel):
    """1 秒一行的训练样本(MVP 用 1Hz,V0.2 可降采样存)"""
    t_offset: int = Field(..., description="相对 start_time 的秒数")
    power: Optional[int] = Field(None, description="功率 W")
    hr: Optional[int] = Field(None, description="心率 bpm")
    cadence: Optional[int] = Field(None, description="踏频 rpm")
    speed: Optional[float] = Field(None, description="速度 m/s")
    elevation: Optional[float] = Field(None, description="海拔 m")
    lat: Optional[float] = None
    lon: Optional[float] = None
    temperature: Optional[int] = None


class Lap(BaseModel):
    """一段间歇 / 分段"""
    start_offset: int
    duration_s: int
    avg_power: Optional[int] = None
    avg_hr: Optional[int] = None
    avg_cadence: Optional[int] = None
    max_power: Optional[int] = None
    max_hr: Optional[int] = None
    distance_m: Optional[float] = None
    label: Optional[str] = None  # 'Warmup' / 'Interval' / 'Recovery' / ...
    trigger: Optional[str] = None  # 'manual' / 'distance' / 'time' / ...


class Activity(BaseModel):
    """单次训练(统一 schema)"""
    source: str = Field(..., description="'fit' / 'tcx' / 'csv'")
    start_time: datetime
    duration_s: int
    distance_m: Optional[float] = None
    total_elevation_gain: Optional[float] = None
    avg_power: Optional[int] = None
    max_power: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    avg_cadence: Optional[int] = None
    avg_speed: Optional[float] = None
    max_speed: Optional[float] = None
    calories: Optional[int] = None
    device: Optional[str] = None
    samples: list[Sample] = Field(default_factory=list)
    laps: list[Lap] = Field(default_factory=list)
    raw_meta: dict = Field(default_factory=dict)
