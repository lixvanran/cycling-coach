"""Cycling Coach — 公路自行车 AI 教练

V0.2 架构:
- cycling_coach.core   — 业务核心(领域 + 服务 + 算法)
- cycling_coach.data   — 数据访问(parsers + sqlite repositories)
- cycling_coach.ai     — AI 层(providers + prompts + tools + orchestrator)
- cycling_coach.api    — HTTP API(FastAPI 入口 + routers)
- cycling_coach.worker — 后台任务(V0.3+)
- cycling_coach.config — 配置 + 日志
"""
__version__ = "0.2.0"
