"""V0.8.0: Service 业务层

设计:
- 每个业务域一个 Service 类 (ActivityService / ChatService / ...)
- 接收 db: Session, 封装所有 ORM 操作 + 业务规则
- 抛 AppError 子类, 不直接 raise HTTPException (router 也不用管)
- 单测可绕过 HTTP, 直接 service.method() 验证逻辑

职责划分:
- router: 接参 + 调 service + 返回 (薄)
- service: 业务逻辑 + DB 操作
- model: ORM schema
- core.metrics / core.ml / core.profile: 算法 + 工具

注入方式: 见 cycling_coach/api/dependencies.py 的 Services bundle
"""
from .activity import ActivityService
from .chat import ChatService
from .ftp import FTPService
from .kb import KBService
from .training import TrainingService
from .ml import MLService
from .race_tactics import RaceTacticsService
from .diary import DiaryService

__all__ = [
    "ActivityService",
    "ChatService",
    "FTPService",
    "KBService",
    "TrainingService",
    "MLService",
    "RaceTacticsService",
    "DiaryService",
]
