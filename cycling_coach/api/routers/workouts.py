"""/api/workouts — 训练课程库(Library) CRUD + 系统课程 seed

V0.3.3 设计:
- system 课程(athlete_id=NULL): 内置 30+ 经典课程,所有人共享,只读
- user 课程(athlete_id=X): 用户自建,可改可删
- ai 课程(预留): 未来 AI 排课生成
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import select, or_, and_
from sqlalchemy.orm import Session

from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import Workout, PlannedWorkout, PlanPeriod

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/workouts", tags=["workouts"])


# ---------- Schemas ----------

class StepIn(BaseModel):
    """单段课程步骤"""
    kind: str = "main"  # warmup/main/recovery/cooldown
    duration_s: int = Field(..., ge=10, le=36000)
    power_pct_ftp: Optional[int] = Field(None, ge=0, le=300)  # %FTP
    hr_pct_lthr: Optional[int] = Field(None, ge=0, le=200)  # %LTHR
    cadence_rpm: Optional[int] = Field(None, ge=0, le=200)
    label: Optional[str] = None
    repeat: int = 1  # 该步骤重复次数(用于间歇)


class WorkoutCreate(BaseModel):
    title: str = Field(..., max_length=128)
    goal: str = "endurance"  # endurance/tempo/threshold/vo2max/recovery/race
    intensity: Optional[str] = None
    duration_min: int = Field(..., ge=5, le=600)
    structure: list[StepIn] = []
    tags: list[str] = []
    description: Optional[str] = None
    is_template: bool = True


class WorkoutUpdate(BaseModel):
    title: Optional[str] = None
    goal: Optional[str] = None
    intensity: Optional[str] = None
    duration_min: Optional[int] = None
    structure: Optional[list[StepIn]] = None
    tags: Optional[list[str]] = None
    description: Optional[str] = None
    is_template: Optional[bool] = None


def _serialize_workout(w: Workout, include_structure: bool = True) -> dict:
    return {
        "id": w.id,
        "athlete_id": w.athlete_id,
        "activity_id": w.activity_id,
        "title": w.title,
        "goal": w.goal,
        "intensity": w.intensity,
        "duration_min": w.duration_min,
        "structure": w.structure if include_structure else None,
        "source": w.source,
        "tags": w.tags or [],
        "is_template": w.is_template,
        "description": w.description,
        "erg_text": w.erg_text,
        "zwo_text": w.zwo_text,
        "rationale": w.rationale,
        "created_at": w.created_at.isoformat() if w.created_at else None,
        "updated_at": w.updated_at.isoformat() if w.updated_at else None,
    }


# ---------- 系统课程 seed(30+ 经典训练) ----------

SYSTEM_WORKOUTS: list[dict] = [
    # ===== 恢复 =====
    {
        "title": "主动恢复 30min @ Z1",
        "goal": "recovery", "intensity": "recovery", "duration_min": 30,
        "description": "促进血液循环,清除代谢废物。可以放在高强度训练后一天。",
        "tags": ["recovery", "easy", "z1"],
        "structure": [
            {"kind": "main", "duration_s": 1800, "power_pct_ftp": 50, "cadence_rpm": 85, "label": "轻松踩"},
        ],
    },
    {
        "title": "主动恢复 45min @ Z1",
        "goal": "recovery", "intensity": "recovery", "duration_min": 45,
        "description": "较长版本的恢复训练,适合高强度周后。",
        "tags": ["recovery", "easy", "z1"],
        "structure": [
            {"kind": "main", "duration_s": 2700, "power_pct_ftp": 55, "cadence_rpm": 85, "label": "轻松踩"},
        ],
    },

    # ===== 耐力 =====
    {
        "title": "Z2 长距离 60min",
        "goal": "endurance", "intensity": "endurance", "duration_min": 60,
        "description": "基础有氧,Z2 区间。重点是稳定心率和踏频。",
        "tags": ["z2", "endurance", "base"],
        "structure": [
            {"kind": "warmup", "duration_s": 600, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 3000, "power_pct_ftp": 65, "cadence_rpm": 88, "label": "Z2 稳定"},
            {"kind": "cooldown", "duration_s": 300, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "Z2 长距离 90min",
        "goal": "endurance", "intensity": "endurance", "duration_min": 90,
        "description": "基础有氧长距离 90min。Base 期核心训练。",
        "tags": ["z2", "endurance", "base", "long"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 4500, "power_pct_ftp": 65, "cadence_rpm": 88, "label": "Z2 长距离"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "Z2 长距离 120min",
        "goal": "endurance", "intensity": "endurance", "duration_min": 120,
        "description": "基础有氧长距离 2 小时。适合周末拉练。",
        "tags": ["z2", "endurance", "base", "long", "weekend"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 6300, "power_pct_ftp": 65, "cadence_rpm": 88, "label": "Z2 长距离"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "Z2 长距离 180min (3h)",
        "goal": "endurance", "intensity": "endurance", "duration_min": 180,
        "description": "长距离 3 小时。基础期和耐力赛备战核心。",
        "tags": ["z2", "endurance", "long", "century-prep"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 9900, "power_pct_ftp": 65, "cadence_rpm": 88, "label": "Z2 长时间"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "Z2 起伏路 90min",
        "goal": "endurance", "intensity": "endurance", "duration_min": 90,
        "description": "Z2 区间 + 起伏路段,模拟真实地形。",
        "tags": ["z2", "endurance", "hills"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 4500, "power_pct_ftp": 70, "cadence_rpm": 80, "label": "起伏 Z2"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },

    # ===== 节奏 =====
    {
        "title": "节奏训练 2×20min @ Z3",
        "goal": "tempo", "intensity": "tempo", "duration_min": 75,
        "description": "经典 2×20 节奏训练,甜蜜点训练,提升 FTP。",
        "tags": ["sweet-spot", "tempo", "z3", "ftp-builder"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 1200, "power_pct_ftp": 88, "cadence_rpm": 88, "label": "节奏 1"},
            {"kind": "recovery", "duration_s": 600, "power_pct_ftp": 55, "label": "间歇"},
            {"kind": "main", "duration_s": 1200, "power_pct_ftp": 88, "cadence_rpm": 88, "label": "节奏 2"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "节奏训练 3×15min @ Z3",
        "goal": "tempo", "intensity": "tempo", "duration_min": 80,
        "description": "3×15 节奏训练,稍短节奏区间适合 Build 期。",
        "tags": ["sweet-spot", "tempo", "z3"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 900, "power_pct_ftp": 88, "cadence_rpm": 88, "label": "节奏 1"},
            {"kind": "recovery", "duration_s": 360, "power_pct_ftp": 55, "label": "恢复"},
            {"kind": "main", "duration_s": 900, "power_pct_ftp": 88, "cadence_rpm": 88, "label": "节奏 2"},
            {"kind": "recovery", "duration_s": 360, "power_pct_ftp": 55, "label": "恢复"},
            {"kind": "main", "duration_s": 900, "power_pct_ftp": 88, "cadence_rpm": 88, "label": "节奏 3"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },

    # ===== 阈值 =====
    {
        "title": "阈值训练 2×12min @ 95% FTP",
        "goal": "threshold", "intensity": "threshold", "duration_min": 70,
        "description": "经典阈值训练,提升乳酸阈值。",
        "tags": ["threshold", "ftp", "ltp"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 720, "power_pct_ftp": 95, "cadence_rpm": 90, "label": "阈值 1"},
            {"kind": "recovery", "duration_s": 720, "power_pct_ftp": 50, "label": "恢复"},
            {"kind": "main", "duration_s": 720, "power_pct_ftp": 95, "cadence_rpm": 90, "label": "阈值 2"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "阈值训练 4×8min @ 95% FTP",
        "goal": "threshold", "intensity": "threshold", "duration_min": 70,
        "description": "4×8min 阈值间歇。Build 期核心课。",
        "tags": ["threshold", "ftp", "ltp", "intervals"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 480, "power_pct_ftp": 95, "cadence_rpm": 90, "label": "阈值 1"},
            {"kind": "recovery", "duration_s": 240, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 480, "power_pct_ftp": 95, "cadence_rpm": 90, "label": "阈值 2"},
            {"kind": "recovery", "duration_s": 240, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 480, "power_pct_ftp": 95, "cadence_rpm": 90, "label": "阈值 3"},
            {"kind": "recovery", "duration_s": 240, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 480, "power_pct_ftp": 95, "cadence_rpm": 90, "label": "阈值 4"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "阈值训练 2×20min @ 90% FTP",
        "goal": "threshold", "intensity": "threshold", "duration_min": 80,
        "description": "2×20 长阈值,稍低于 FTP,可持续性更好。",
        "tags": ["threshold", "ftp", "long"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 1200, "power_pct_ftp": 90, "cadence_rpm": 88, "label": "阈值长 1"},
            {"kind": "recovery", "duration_s": 600, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 1200, "power_pct_ftp": 90, "cadence_rpm": 88, "label": "阈值 2"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },

    # ===== VO2 =====
    {
        "title": "VO2max 5×3min @ 120% FTP",
        "goal": "vo2max", "intensity": "vo2max", "duration_min": 55,
        "description": "经典 VO2max 训练,5×3min 高强度间歇,提升最大摄氧量。",
        "tags": ["vo2", "vo2max", "intervals", "aerobic-capacity"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 180, "power_pct_ftp": 120, "cadence_rpm": 92, "label": "VO2 1"},
            {"kind": "recovery", "duration_s": 180, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 180, "power_pct_ftp": 120, "cadence_rpm": 92, "label": "VO2 2"},
            {"kind": "recovery", "duration_s": 180, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 180, "power_pct_ftp": 120, "cadence_rpm": 92, "label": "VO2 3"},
            {"kind": "recovery", "duration_s": 180, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 180, "power_pct_ftp": 120, "cadence_rpm": 92, "label": "VO2 4"},
            {"kind": "recovery", "duration_s": 180, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 180, "power_pct_ftp": 120, "cadence_rpm": 92, "label": "VO2 5"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "VO2max 4×4min @ 115% FTP",
        "goal": "vo2max", "intensity": "vo2max", "duration_min": 60,
        "description": "4×4min VO2max,稍长版本。",
        "tags": ["vo2", "vo2max", "intervals"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 240, "power_pct_ftp": 115, "cadence_rpm": 90, "label": "VO2 1"},
            {"kind": "recovery", "duration_s": 240, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 240, "power_pct_ftp": 115, "cadence_rpm": 90, "label": "VO2 2"},
            {"kind": "recovery", "duration_s": 240, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 240, "power_pct_ftp": 115, "cadence_rpm": 90, "label": "VO2 3"},
            {"kind": "recovery", "duration_s": 240, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 240, "power_pct_ftp": 115, "cadence_rpm": 90, "label": "VO2 4"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "VO2max 8×2min @ 130% FTP",
        "goal": "vo2max", "intensity": "vo2max", "duration_min": 50,
        "description": "8×2min 高强度短间歇,神经肌肉刺激。",
        "tags": ["vo2", "vo2max", "intervals", "short"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 130, "cadence_rpm": 95, "label": "VO2 1"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 130, "cadence_rpm": 95, "label": "VO2 2"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 130, "cadence_rpm": 95, "label": "VO2 3"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 130, "cadence_rpm": 95, "label": "VO2 4"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 130, "cadence_rpm": 95, "label": "VO2 5"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 130, "cadence_rpm": 95, "label": "VO2 6"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 130, "cadence_rpm": 95, "label": "VO2 7"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 130, "cadence_rpm": 95, "label": "VO2 8"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "VO2max 30/15s 间歇 × 12",
        "goal": "vo2max", "intensity": "vo2max", "duration_min": 40,
        "description": "30s 全力 + 15s 恢复 × 12。极短间歇,神经肌肉+VO2 双重刺激。",
        "tags": ["vo2", "vo2max", "tabata", "sprint"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 30, "power_pct_ftp": 150, "cadence_rpm": 100, "label": "30s 全力", "repeat": 12},
            {"kind": "recovery", "duration_s": 15, "power_pct_ftp": 50, "label": "15s 恢复", "repeat": 12},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },

    # ===== 爬坡 =====
    {
        "title": "爬坡间歇 6×5min @ 8%",
        "goal": "endurance", "intensity": "tempo", "duration_min": 75,
        "description": "6×5min 爬坡间歇,爬坡赛备战核心。",
        "tags": ["climbing", "hills", "intervals", "gravity"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 300, "power_pct_ftp": 85, "cadence_rpm": 70, "label": "爬坡 1"},
            {"kind": "recovery", "duration_s": 300, "power_pct_ftp": 50, "label": "下坡恢复"},
            {"kind": "main", "duration_s": 300, "power_pct_ftp": 85, "cadence_rpm": 70, "label": "爬坡 2"},
            {"kind": "recovery", "duration_s": 300, "power_pct_ftp": 50, "label": "下坡恢复"},
            {"kind": "main", "duration_s": 300, "power_pct_ftp": 85, "cadence_rpm": 70, "label": "爬坡 3"},
            {"kind": "recovery", "duration_s": 300, "power_pct_ftp": 50, "label": "下坡恢复"},
            {"kind": "main", "duration_s": 300, "power_pct_ftp": 85, "cadence_rpm": 70, "label": "爬坡 4"},
            {"kind": "recovery", "duration_s": 300, "power_pct_ftp": 50, "label": "下坡恢复"},
            {"kind": "main", "duration_s": 300, "power_pct_ftp": 85, "cadence_rpm": 70, "label": "爬坡 5"},
            {"kind": "recovery", "duration_s": 300, "power_pct_ftp": 50, "label": "下坡恢复"},
            {"kind": "main", "duration_s": 300, "power_pct_ftp": 85, "cadence_rpm": 70, "label": "爬坡 6"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "短陡坡 10×1min @ 12%",
        "goal": "vo2max", "intensity": "vo2max", "duration_min": 60,
        "description": "10×1min 短陡坡,高踏频低齿比,模拟瓦莱达奥斯塔风格。",
        "tags": ["climbing", "hills", "intervals", "short", "high-cadence"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 60, "power_pct_ftp": 110, "cadence_rpm": 80, "label": "陡坡 1", "repeat": 10},
            {"kind": "recovery", "duration_s": 60, "power_pct_ftp": 50, "label": "下坡恢复", "repeat": 10},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "长坡 3×15min @ 6%",
        "goal": "endurance", "intensity": "tempo", "duration_min": 90,
        "description": "3×15min 长坡,模拟阿尔卑斯山口长坡。",
        "tags": ["climbing", "hills", "long", "endurance"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 900, "power_pct_ftp": 75, "cadence_rpm": 65, "label": "长坡 1"},
            {"kind": "recovery", "duration_s": 600, "power_pct_ftp": 50, "label": "下坡恢复"},
            {"kind": "main", "duration_s": 900, "power_pct_ftp": 75, "cadence_rpm": 65, "label": "长坡 2"},
            {"kind": "recovery", "duration_s": 600, "power_pct_ftp": 50, "label": "下坡恢复"},
            {"kind": "main", "duration_s": 900, "power_pct_ftp": 75, "cadence_rpm": 65, "label": "长坡 3"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },

    # ===== 冲刺/神经 =====
    {
        "title": "神经肌肉冲刺 6×10s",
        "goal": "vo2max", "intensity": "vo2max", "duration_min": 45,
        "description": "6×10s 全力冲刺 + 充足恢复,激活神经肌肉通路。",
        "tags": ["sprint", "neuromuscular", "short", "fresh-legs"],
        "structure": [
            {"kind": "warmup", "duration_s": 1500, "power_pct_ftp": 50, "label": "充分热身"},
            {"kind": "main", "duration_s": 10, "power_pct_ftp": 200, "cadence_rpm": 110, "label": "10s 全力", "repeat": 6},
            {"kind": "recovery", "duration_s": 180, "power_pct_ftp": 50, "label": "3min 恢复", "repeat": 6},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "站立冲刺 8×30s @ 150% FTP",
        "goal": "vo2max", "intensity": "vo2max", "duration_min": 50,
        "description": "8×30s 站立冲刺,低踏频大力,模拟冲刺终点。",
        "tags": ["sprint", "standing", "intervals"],
        "structure": [
            {"kind": "warmup", "duration_s": 1500, "power_pct_ftp": 50, "label": "充分热身"},
            {"kind": "main", "duration_s": 30, "power_pct_ftp": 150, "cadence_rpm": 70, "label": "站立冲刺", "repeat": 8},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇", "repeat": 8},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },

    # ===== 比赛 =====
    {
        "title": "40km 计时赛模拟 (60min @ 95% FTP)",
        "goal": "race", "intensity": "threshold", "duration_min": 60,
        "description": "40km TT 模拟赛。60 分钟稳定 95% FTP。",
        "tags": ["race", "tt", "time-trial", "race-simulation"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 3600, "power_pct_ftp": 95, "cadence_rpm": 90, "label": "TT 模拟"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "Criterium 45min 高强度",
        "goal": "race", "intensity": "vo2max", "duration_min": 60,
        "description": "45 分钟绕圈赛模拟,持续高强度。",
        "tags": ["race", "criterium", "high-intensity"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 2700, "power_pct_ftp": 100, "cadence_rpm": 88, "label": "绕圈赛"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "爬坡赛 30min 阈值",
        "goal": "race", "intensity": "threshold", "duration_min": 60,
        "description": "30 分钟爬坡赛,稳在阈值。",
        "tags": ["race", "climbing", "threshold"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 1800, "power_pct_ftp": 95, "cadence_rpm": 70, "label": "爬坡赛"},
            {"kind": "recovery", "duration_s": 600, "power_pct_ftp": 50, "label": "下坡恢复"},
            {"kind": "main", "duration_s": 300, "power_pct_ftp": 110, "label": "终点冲刺"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },

    # ===== Cross/Tempo =====
    {
        "title": "Cross 训练 60min 越野骑行",
        "goal": "endurance", "intensity": "endurance", "duration_min": 60,
        "description": "越野/混合路面训练,提升综合能力。",
        "tags": ["cross", "mixed", "skills"],
        "structure": [
            {"kind": "main", "duration_s": 3600, "power_pct_ftp": 70, "cadence_rpm": 85, "label": "混合路面"},
        ],
    },
    {
        "title": "Sweet Spot 60min @ 88% FTP",
        "goal": "tempo", "intensity": "tempo", "duration_min": 75,
        "description": "单段 60 分钟甜蜜点训练。",
        "tags": ["sweet-spot", "tempo", "z3"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 3600, "power_pct_ftp": 88, "cadence_rpm": 88, "label": "甜蜜点 60min"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "金字塔间歇 1-2-3-2-1min @ 120%",
        "goal": "vo2max", "intensity": "vo2max", "duration_min": 50,
        "description": "经典金字塔间歇,1-2-3-2-1 分钟。",
        "tags": ["vo2", "intervals", "pyramid"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 60, "power_pct_ftp": 120, "label": "1min"},
            {"kind": "recovery", "duration_s": 60, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 120, "label": "2min"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 180, "power_pct_ftp": 120, "label": "3min"},
            {"kind": "recovery", "duration_s": 180, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 120, "power_pct_ftp": 120, "label": "2min"},
            {"kind": "recovery", "duration_s": 120, "power_pct_ftp": 50, "label": "间歇"},
            {"kind": "main", "duration_s": 60, "power_pct_ftp": 120, "label": "1min"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "Lactate Clearance 3×10min @ 90% FTP",
        "goal": "threshold", "intensity": "threshold", "duration_min": 80,
        "description": "3×10 分钟稍低于 FTP,提升乳酸清除能力。",
        "tags": ["threshold", "lactate", "ltp"],
        "structure": [
            {"kind": "warmup", "duration_s": 900, "power_pct_ftp": 50, "label": "热身"},
            {"kind": "main", "duration_s": 600, "power_pct_ftp": 90, "cadence_rpm": 88, "label": "乳酸 1"},
            {"kind": "recovery", "duration_s": 360, "power_pct_ftp": 55, "label": "间歇"},
            {"kind": "main", "duration_s": 600, "power_pct_ftp": 90, "cadence_rpm": 88, "label": "乳酸 2"},
            {"kind": "recovery", "duration_s": 360, "power_pct_ftp": 55, "label": "间歇"},
            {"kind": "main", "duration_s": 600, "power_pct_ftp": 90, "cadence_rpm": 88, "label": "乳酸 3"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
    {
        "title": "FTP Test 60min 全力",
        "goal": "race", "intensity": "threshold", "duration_min": 75,
        "description": "60 分钟 FTP 测试。充分热身后的全力 60 分钟。",
        "tags": ["test", "ftp", "assessment"],
        "structure": [
            {"kind": "warmup", "duration_s": 1500, "power_pct_ftp": 50, "label": "充分热身"},
            {"kind": "main", "duration_s": 60, "power_pct_ftp": 80, "label": "2min 渐进"},
            {"kind": "recovery", "duration_s": 60, "power_pct_ftp": 50, "label": "调整"},
            {"kind": "main", "duration_s": 60, "power_pct_ftp": 90, "label": "1min 渐进"},
            {"kind": "recovery", "duration_s": 60, "power_pct_ftp": 50, "label": "调整"},
            {"kind": "main", "duration_s": 3600, "power_pct_ftp": 100, "label": "FTP Test 60min"},
            {"kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45, "label": "冷身"},
        ],
    },
]


def _ensure_system_workouts(db: Session) -> int:
    """首次启动时 seed 系统课程(已存在则跳过)

    V0.3.3 修复:system 课程用 athlete_id=1(默认 athlete)+ source='system' 区分
    不再用 athlete_id=NULL(SQLite 改 NOT NULL 要 12 步重整表)
    """
    existing = db.execute(
        select(Workout).where(Workout.source == "system").limit(1)
    ).scalar_one_or_none()
    if existing:
        return 0
    from sqlalchemy import text as _sql_text
    from datetime import datetime as _dt
    now = _dt.utcnow().isoformat()
    count = 0
    for wo in SYSTEM_WORKOUTS:
        db.execute(_sql_text("""
            INSERT INTO workouts
                (athlete_id, source, title, goal, intensity, duration_min, structure,
                 tags, description, is_template, rationale, created_at, updated_at)
            VALUES
                (1, 'system', :title, :goal, :intensity, :duration, :structure,
                 :tags, :desc, 1, :rationale, :now, :now)
        """), {
            "title": wo["title"],
            "goal": wo["goal"],
            "intensity": wo.get("intensity"),
            "duration": wo["duration_min"],
            "structure": __import__("json").dumps(wo["structure"], ensure_ascii=False),
            "tags": __import__("json").dumps(wo.get("tags", []), ensure_ascii=False),
            "desc": wo.get("description"),
            "rationale": wo.get("description"),
            "now": now,
        })
        count += 1
    db.commit()
    logger.info(f"系统课程 seed 完成: {count} 个")
    return count


# ---------- Routes ----------

@router.get("")
def list_workouts(
    q: Optional[str] = Query(None, description="搜索标题/描述/标签"),
    goal: Optional[str] = Query(None, description="按目标过滤:recovery/endurance/tempo/threshold/vo2max/race"),
    intensity: Optional[str] = Query(None),
    tag: Optional[str] = Query(None),
    source: Optional[str] = Query(None, description="system/user/ai,默认全返"),
    only_templates: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """列出课程库(系统 + 当前用户的自建)"""
    athlete = profile_store.get_or_create_athlete(db)
    # 首次跑顺便 seed
    _ensure_system_workouts(db)

    stmt = select(Workout)
    # 可见性:system 课程(全部可见) OR 当前 athlete 的 user/ai 课程
    stmt = stmt.where(or_(
        Workout.source == "system",
        and_(
            Workout.source.in_(["user", "ai"]),
            Workout.athlete_id == athlete.id,
        ),
    ))
    if goal:
        stmt = stmt.where(Workout.goal == goal)
    if intensity:
        stmt = stmt.where(Workout.intensity == intensity)
    if source:
        stmt = stmt.where(Workout.source == source)
    if only_templates:
        stmt = stmt.where(Workout.is_template.is_(True))
    if tag:
        # JSON 数组内包含 tag(JSON_CONTAINS)
        # SQLite: 简单做法是用 LIKE,因为 tags 是 JSON 数组
        stmt = stmt.where(Workout.tags.like(f'%"{tag}"%'))
    if q:
        # 标题/描述/标签模糊匹配
        like = f"%{q}%"
        stmt = stmt.where(or_(
            Workout.title.like(like),
            Workout.description.like(like),
            Workout.tags.like(like),
        ))
    stmt = stmt.order_by(Workout.source.asc(), Workout.title.asc()).limit(limit)
    rows = db.execute(stmt).scalars().all()
    return {
        "workouts": [_serialize_workout(w) for w in rows],
        "total": len(rows),
    }


@router.get("/tags")
def list_tags(db: Session = Depends(get_db)):
    """返回所有可用的标签(去重)"""
    athlete = profile_store.get_or_create_athlete(db)
    _ensure_system_workouts(db)
    rows = db.execute(
        select(Workout)
        .where(or_(
            Workout.source == "system",
            and_(
                Workout.source.in_(["user", "ai"]),
                Workout.athlete_id == athlete.id,
            ),
        ))
    ).scalars().all()
    all_tags: set[str] = set()
    for w in rows:
        if w.tags:
            for t in w.tags:
                all_tags.add(t)
    return {"tags": sorted(all_tags)}


@router.get("/goals")
def list_goals(db: Session = Depends(get_db)):
    """返回所有 goal 分类"""
    return {
        "goals": [
            {"key": "recovery", "label": "恢复", "color": "sky"},
            {"key": "endurance", "label": "耐力", "color": "emerald"},
            {"key": "tempo", "label": "节奏", "color": "amber"},
            {"key": "threshold", "label": "阈值", "color": "orange"},
            {"key": "vo2max", "label": "VO2", "color": "red"},
            {"key": "race", "label": "比赛", "color": "fuchsia"},
        ]
    }


@router.get("/{workout_id}")
def get_workout(workout_id: int, db: Session = Depends(get_db)):
    """单个课程详情"""
    w = db.get(Workout, workout_id)
    if not w:
        raise HTTPException(404, "课程不存在")
    return _serialize_workout(w)


@router.post("")
def create_workout(payload: WorkoutCreate, db: Session = Depends(get_db)):
    """创建课程(用户自建)"""
    athlete = profile_store.get_or_create_athlete(db)
    structure = [s.model_dump() for s in payload.structure]
    w = Workout(
        athlete_id=athlete.id,
        source="user",
        title=payload.title,
        goal=payload.goal,
        intensity=payload.intensity,
        duration_min=payload.duration_min,
        structure=structure,
        tags=payload.tags,
        description=payload.description,
        is_template=payload.is_template,
    )
    db.add(w)
    db.commit()
    db.refresh(w)
    return _serialize_workout(w)


@router.patch("/{workout_id}")
def update_workout(workout_id: int, payload: WorkoutUpdate, db: Session = Depends(get_db)):
    """更新课程(仅本人 + 非 system)"""
    athlete = profile_store.get_or_create_athlete(db)
    w = db.get(Workout, workout_id)
    if not w:
        raise HTTPException(404, "课程不存在")
    if w.source == "system":
        raise HTTPException(403, "系统课程只读,请先复制再修改")
    if w.athlete_id is not None and w.athlete_id != athlete.id:
        raise HTTPException(403, "无权修改他人课程")
    for k, v in payload.model_dump(exclude_unset=True).items():
        if k == "structure" and v is not None:
            v = [s if isinstance(s, dict) else s for s in v]
        setattr(w, k, v)
    db.commit()
    db.refresh(w)
    return _serialize_workout(w)


@router.delete("/{workout_id}")
def delete_workout(workout_id: int, db: Session = Depends(get_db)):
    """删除课程(仅本人 + 非 system)"""
    athlete = profile_store.get_or_create_athlete(db)
    w = db.get(Workout, workout_id)
    if not w:
        raise HTTPException(404, "课程不存在")
    if w.source == "system":
        raise HTTPException(403, "系统课程不能删除")
    if w.athlete_id is not None and w.athlete_id != athlete.id:
        raise HTTPException(403, "无权删除他人课程")
    db.delete(w)
    db.commit()
    return {"ok": True, "id": workout_id}


@router.post("/{workout_id}/duplicate")
def duplicate_workout(
    workout_id: int, new_title: Optional[str] = None, db: Session = Depends(get_db)
):
    """复制一个课程(系统课程必须 duplicate 才能改)"""
    athlete = profile_store.get_or_create_athlete(db)
    src = db.get(Workout, workout_id)
    if not src:
        raise HTTPException(404, "课程不存在")
    if src.source not in ("system", "user", "ai"):
        raise HTTPException(400, f"未知 source: {src.source}")
    if src.source != "system" and src.athlete_id is not None and src.athlete_id != athlete.id:
        raise HTTPException(403, "无权复制他人课程")
    new_w = Workout(
        athlete_id=athlete.id,
        source="user",
        title=new_title or f"{src.title} (副本)",
        goal=src.goal,
        intensity=src.intensity,
        duration_min=src.duration_min,
        structure=list(src.structure or []),
        tags=list(src.tags or []),
        description=src.description,
        is_template=True,
        rationale=src.rationale,
    )
    db.add(new_w)
    db.commit()
    db.refresh(new_w)
    return _serialize_workout(new_w)


@router.post("/{workout_id}/schedule")
def schedule_workout_to_calendar(
    workout_id: int,
    scheduled_date: str = Query(..., description="YYYY-MM-DD"),
    period_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """把课程直接排到日历某天(创建 PlannedWorkout)

    system 课也能排(schedule 不会改 workout 本身)
    """
    from datetime import date as _date
    athlete = profile_store.get_or_create_athlete(db)
    w = db.get(Workout, workout_id)
    if not w:
        raise HTTPException(404, "课程不存在")
    planned = PlannedWorkout(
        scheduled_date=_date.fromisoformat(scheduled_date),
        title=w.title,
        intent=w.intensity or w.goal,
        duration_target_min=w.duration_min,
        tss_target=int(w.duration_min * 60 / 3600 * 100 * {
            "recovery": 0.5, "endurance": 0.65, "tempo": 0.85,
            "threshold": 0.95, "vo2max": 1.2, "race": 0.95,
        }.get(w.intensity or w.goal, 0.7)),
        period_id=period_id,
        workout_id=w.id,
    )
    db.add(planned)
    db.commit()
    db.refresh(planned)
    # auto-link
    from .calendar import _try_auto_link
    _try_auto_link(db, planned)
    db.commit()
    return {"planned_id": planned.id, "ok": True}


# ---------- AI 排课预留(V0.3.3 先 stub,V0.5 实装) ----------

@router.get("/{workout_id}/export")
def export_workout(
    workout_id: int,
    format: str = Query("zwo", description="zwo / mrc / erg / fit / json"),
    db: Session = Depends(get_db),
):
    """导出课程为训练台通用格式 (V0.7.1 增加课程导出)

    支持 (V0.7.4):
    - zwo: Zwift / Rouvy 训练课程 XML
    - mrc: Rouvy / MiniRoad 训练课程文本
    - erg: CompuTrainer / TrainerRoad 通用格式
    - fit: Garmin Edge / Wahoo ELEMNT 训练课程 (V0.7.4 新加)
    - json: 自有 JSON (含完整 structure)
    """
    w = db.get(Workout, workout_id)
    if not w:
        raise HTTPException(404, f"课程 {workout_id} 不存在")

    fmt = format.lower()
    if fmt not in ("zwo", "mrc", "erg", "fit", "json"):
        raise HTTPException(400, f"不支持的格式: {format} (zwo/mrc/erg/fit/json)")

    # 课程结构 (flat 或 nested)
    structure = w.structure or []
    title = w.title
    description = w.description or ""
    # ASCII safe (latin-1 兼容)
    import re
    import unicodedata
    safe_title = re.sub(r"[\s]+", "_", unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii"))[:50] or "workout"

    athlete = profile_store.get_or_create_athlete(db)
    ftp = athlete.ftp or 250

    if fmt == "zwo":
        from cycling_coach.core.exporters.zwo import export_zwo
        content = export_zwo(title, description, structure, author="Cycling Coach")
        media_type = "application/xml"
        filename = f"{safe_title}.zwo"
    elif fmt == "mrc":
        from cycling_coach.core.exporters.mrc import export_mrc
        content = export_mrc(title, description, structure)
        media_type = "text/plain"
        filename = f"{safe_title}.mrc"
    elif fmt == "erg":
        from cycling_coach.core.exporters.erg import export_erg
        content = export_erg(title, description, structure, ftp=ftp)
        media_type = "text/plain"
        filename = f"{safe_title}.erg"
    elif fmt == "fit":
        from cycling_coach.core.exporters.fit import export_fit_workout
        # 构造 duck-type workout 对象
        # power_w 缺失时, 用 power_pct_ftp * FTP 算
        class _Seg:
            def __init__(self, s, ftp):
                self.label = s.get("label") or s.get("name") or "Step"
                self.duration_s = s.get("duration_s") or s.get("duration") or 60
                p_w = s.get("power_w") or 0
                p_pct = s.get("power_pct_ftp") or s.get("power_pct") or 0
                # 如果有 pct 但没 w, 用 FTP 算
                if p_w == 0 and p_pct > 0:
                    # pct 是 0-100 整数, 50 = 50% FTP
                    p_w = int(p_pct * ftp / 100) if p_pct > 1 else int(p_pct * ftp)
                self.power_w = p_w
                self.power_pct = (p_pct / 100) if p_pct > 1 else p_pct
                self.zone = s.get("zone") or "Z2"
        class _WO:
            def __init__(self, name, segs):
                self.name = name
                self.segments = segs
        wo = _WO(title, [_Seg(s, ftp) for s in structure if isinstance(s, dict)])
        content = export_fit_workout(wo, workout_name=safe_title)
        media_type = "application/octet-stream"
        filename = f"{safe_title}.fit"
    else:  # json
        import json
        content = json.dumps({
            "title": title,
            "description": description,
            "goal": w.goal,
            "intensity": w.intensity,
            "duration_min": w.duration_min,
            "structure": structure,
            "tags": w.tags or [],
            "exported_at": datetime.utcnow().isoformat(),
            "source": "cycling-coach",
        }, ensure_ascii=False, indent=2)
        media_type = "application/json"
        filename = f"{safe_title}.json"

    from fastapi.responses import Response
    # content: 文本格式 (zwo/mrc/erg/json) 是 str, fit 是 bytes
    if isinstance(content, bytes):
        content_bytes = content
    else:
        content_bytes = content.encode("utf-8")
    return Response(
        content=content_bytes,
        media_type=media_type,
        headers={
            "Content-Disposition": f'attachment; filename="{safe_title}.{fmt}"',
            "Content-Length": str(len(content_bytes)),
        },
    )


@router.post("/ai-schedule")
def ai_schedule_stub(
    plan_id: int = Query(..., description="目标 plan_id"),
    week_start: str = Query(..., description="YYYY-MM-DD 周一日期"),
    db: Session = Depends(get_db),
):
    """AI 排课 — 预留接口

    V0.3.3:返回 501 Not Implemented
    V0.5:实装 — 调用 AI 生成 weekly_plan → 写入 PlanAIDraft → 用户确认后 apply
    """
    raise HTTPException(
        status_code=501,
        detail={
            "ok": False,
            "code": "not_implemented",
            "message": "AI 排课尚未实装, V0.7.6+ 推出",
            "endpoint": "POST /api/workouts/ai-schedule",
            "plan_id": plan_id,
            "week_start": week_start,
            "planned_version": "V0.7.6+",
        }
    )
