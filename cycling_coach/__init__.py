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

V0.8.2: 预留 desktop 模式入口
- 未来 Tauri/Electron 集成时, 通过 apps/web/src/lib/platform.ts 抽象层
- 后端 service 层无需改动 (HTTP API 已暴露完整功能)
- 见 __main__.py / api/main.py 顶部注释
"""
from ._version import __version__

# Desktop 模式 marker — 未来 desktop 启动时设置 sys._CYCLING_COACH_DESKTOP = True
# __main__.py 据此切换 uvicorn 路径 vs ASGI 直接挂载路径
__desktop_app_marker__ = "__CYCLING_COACH_DESKTOP__"

__all__ = ["__version__", "__desktop_app_marker__"]
