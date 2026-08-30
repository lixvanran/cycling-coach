"""Cycling Coach — 公路自行车 AI 教练

V0.7.1 架构 (持续演进):
- cycling_coach.core   — 业务核心(领域 + 服务 + 算法)
  - metrics: NP/IF/TSS, W'bal, FTP, ACWR, Pa:HR Decoupling,
             PMC, RPE, Periodization, Polarized, Insights
  - profile: 运动员档案 + 训练学
  - exporters: 课程导出 (ZWO / MRC / ERG / JSON)
- cycling_coach.data   — 数据访问
  - parsers: FIT / TCX / WKO CSV
  - sqlite: ORM + 迁移
- cycling_coach.ai     — AI 层(orchestrator + 训练学 prompt)
- cycling_coach.api    — HTTP API(FastAPI 入口 + routers)
- cycling_coach.config — 配置 + 日志
"""
from ._version import __version__

__all__ = ["__version__"]
