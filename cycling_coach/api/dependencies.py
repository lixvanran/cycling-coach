"""V0.8.0: FastAPI 依赖注入层

设计:
- Services bundle 一次注入全套 service
- router 通过 Depends(get_services) 获取, 避免每个 service 单独 Depends
- service 内部用 self.db 操作, 事务边界由 FastAPI Depends 生命周期管
"""
from __future__ import annotations
from fastapi import Depends
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite import get_db
from cycling_coach.core.services import (
    ActivityService,
    ChatService,
    FTPService,
    KBService,
    TrainingService,
    MLService,
    RaceTacticsService,
    DiaryService,
)


class Services:
    """Service bundle, 一次注入全套"""
    def __init__(self, db: Session):
        self.db = db
        self.activity = ActivityService(db)
        self.chat = ChatService(db)
        self.ftp = FTPService(db)
        self.kb = KBService(db)
        self.training = TrainingService(db)
        self.ml = MLService(db)
        self.race_tactics = RaceTacticsService(db)
        self.diary = DiaryService(db)


def get_services(db: Session = Depends(get_db)) -> Services:
    """FastAPI 依赖: 注入 Services bundle

    用法:
        @router.get("")
        def list_activities(svc: Services = Depends(get_services)):
            return svc.activity.list_activities(...)
    """
    return Services(db)
