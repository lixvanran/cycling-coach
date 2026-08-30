"""V0.7.4: FIT Workout 导出 (训练台/码表)

借鉴:
- Garmin FIT Workout (官方 SDK Profile)
- Wahoo ELEMNT Bolt 训练课程
- Zwift 课程
- fit_tool 0.9.16 (python FIT SDK)

跟 V0.7.1 已有的 4 格式区别:
- ZWO: Zwift XML (interval + power)
- MRC: Rouvy 文本
- ERG: CompuTrainer/TrainerRoad 功率曲线
- JSON: 自有
- **FIT**: Garmin/Wahoo 训练课程 (WorkoutMessage + WorkoutStep)

应用: Garmin Edge 520/530/830/1030, Wahoo ELEMNT Roam/Bolt, Hammerhead Karoo
"""
from __future__ import annotations
import logging
import math
from datetime import datetime
from typing import Optional

from fit_tool.fit_file import FitFile
from fit_tool.fit_file_builder import FitFileBuilder
from fit_tool.profile.messages.file_id_message import FileIdMessage
from fit_tool.profile.messages.workout_message import WorkoutMessage
from fit_tool.profile.messages.workout_step_message import WorkoutStepMessage
from fit_tool.profile.profile_type import (
    FileType, Intensity, Manufacturer, Sport,
    WorkoutStepDuration, WorkoutStepTarget,
)

# duck typing: 接受任何有 segments 属性的对象

logger = logging.getLogger(__name__)


def export_fit_workout(
    workout: ParsedWorkout,
    workout_name: Optional[str] = None,
) -> bytes:
    """V0.7.4: 导出 FIT 训练课程 (Garmin/Wahoo)
    
    Args:
        workout: ParsedWorkout (来自 ZWO/MRC/ERG/JSON 解析)
        workout_name: 课程名
    
    Returns:
        FIT 文件二进制
    """
    builder = FitFileBuilder(auto_define=True)
    
    # 1. File ID
    file_id = FileIdMessage()
    file_id.type = FileType.WORKOUT
    file_id.manufacturer = Manufacturer.DEVELOPMENT.value
    file_id.product = 0
    file_id.time_created = round(datetime.now().timestamp() * 1000)
    file_id.serial_number = 0x12345678
    builder.add(file_id)
    
    # 2. Workout 步
    workout_steps: list[WorkoutStepMessage] = []
    
    for i, seg in enumerate(workout.segments):
        step = WorkoutStepMessage()
        step.workout_step_name = (seg.label or f"Step {i+1}")[:32]
        
        # 强度类型
        if "warm" in (seg.label or "").lower():
            step.intensity = Intensity.WARMUP
        elif "cool" in (seg.label or "").lower():
            step.intensity = Intensity.COOLDOWN
        elif "recovery" in (seg.label or "").lower() or "rest" in (seg.label or "").lower():
            step.intensity = Intensity.RECOVERY
        else:
            step.intensity = Intensity.ACTIVE
        
        # 时长
        step.duration_type = WorkoutStepDuration.TIME
        step.duration_time = float(seg.duration_s) if seg.duration_s else 60.0
        step.duration_value = 0
        
        # 目标: 优先用 power_w (绝对功率), 否则 OPEN
        if seg.power_w and seg.power_w > 0:
            step.target_type = WorkoutStepTarget.POWER
            step.target_value = int(seg.power_w)
            step.custom_target_power_low = int(seg.power_w * 0.95)  # -5%
            step.custom_target_power_high = int(seg.power_w * 1.05)  # +5%
        else:
            step.target_type = WorkoutStepTarget.OPEN
            step.target_value = 0
        
        workout_steps.append(step)
    
    # 3. Workout 主消息
    workout_msg = WorkoutMessage()
    workout_msg.workout_name = (workout_name or workout.name or f"Workout {datetime.now().strftime('%Y%m%d')}")[:32]
    workout_msg.sport = Sport.CYCLING
    workout_msg.num_valid_steps = len(workout_steps)
    builder.add(workout_msg)
    
    # 4. 加所有 step
    for step in workout_steps:
        builder.add(step)
    
    fit_file: FitFile = builder.build()
    return fit_file.to_bytes()
