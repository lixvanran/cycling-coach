"""backend.coach.tools - 工具层

V0.1.0:只实现 analyze_activity
V0.2: 加 generate_workout
V0.3: 加 track_progress
"""
from .analyze_activity import analyze_activity_tool

__all__ = ["analyze_activity_tool"]
