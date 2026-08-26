"""backend.coach - AI 教练 Agent

V0.1.0:单工具 analyze_activity + 同步调用
V0.1.1:加 orchestrator + 流式 chat
V0.4:多轮工具循环
"""
from . import m3_client, prompts, tools, orchestrator
from .m3_client import M3Client, get_m3, M3Error, M3AuthError, M3NetworkError
from .orchestrator import stream_chat

__all__ = [
    "m3_client", "prompts", "tools", "orchestrator",
    "M3Client", "get_m3", "M3Error", "M3AuthError", "M3NetworkError",
    "stream_chat",
]
