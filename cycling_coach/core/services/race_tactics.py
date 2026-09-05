"""V0.8.0: 比赛战术规划业务层 (V0.7.5.9)

V0.8.0 范围: 占位 service, 完整重构留给后续版本
- 保留 session CRUD 接口签名, 让 router 可以平滑切到 svc.xx() 模式
- 异常统一用 NotFoundError / ValidationError

完整业务逻辑 (上传/AI 流式) 仍在 router, 因为强依赖 m3_client + orchestrator
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from cycling_coach.core.exceptions import NotFoundError, ValidationError
from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite.models import (
    RaceTacticsSession, RaceTacticsMessage, RaceTacticsAttachment,
)

logger = logging.getLogger(__name__)


# ============== DTO ==============

class SessionIn(BaseModel):
    race_name: str = Field(..., max_length=128)
    race_date: Optional[datetime] = None
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[int] = None
    race_type: Optional[str] = None
    priority: Optional[str] = None
    weather_forecast: Optional[str] = None
    course_profile: Optional[str] = None


class SessionPatch(BaseModel):
    race_name: Optional[str] = None
    race_date: Optional[datetime] = None
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[int] = None
    race_type: Optional[str] = None
    priority: Optional[str] = None
    weather_forecast: Optional[str] = None
    course_profile: Optional[str] = None
    final_strategy: Optional[str] = None
    status: Optional[str] = None


class MessageIn(BaseModel):
    content: str = Field(..., min_length=1)


# ============== Service ==============

class RaceTacticsService:
    """比赛战术会话服务 (V0.8.0 P1 占位, AI 流式后续重构)"""
    def __init__(self, db: Session):
        self.db = db

    def get_session(self, session_id: int) -> dict:
        s = self.db.get(RaceTacticsSession, session_id)
        if not s:
            raise NotFoundError(f"会话不存在: {session_id}")
        return _serialize_session(s, with_details=True)

    def list_sessions(self) -> list:
        athlete = profile_store.get_or_create_athlete(self.db)
        rows = (
            self.db.query(RaceTacticsSession)
            .filter(RaceTacticsSession.athlete_id == athlete.id)
            .order_by(desc(RaceTacticsSession.updated_at))
            .all()
        )
        return [_serialize_session(s) for s in rows]

    def create_session(self, req: SessionIn) -> dict:
        athlete = profile_store.get_or_create_athlete(self.db)
        s = RaceTacticsSession(
            athlete_id=athlete.id,
            race_name=req.race_name,
            race_date=req.race_date,
            distance_km=req.distance_km,
            elevation_gain_m=req.elevation_gain_m,
            race_type=req.race_type,
            priority=req.priority,
            weather_forecast=req.weather_forecast,
            course_profile=req.course_profile,
        )
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        return _serialize_session(s)

    def update_session(self, session_id: int, req: SessionPatch) -> dict:
        s = self.db.get(RaceTacticsSession, session_id)
        if not s:
            raise NotFoundError(f"会话不存在: {session_id}")
        payload = req.model_dump(exclude_unset=True)
        for k, v in payload.items():
            if hasattr(s, k):
                setattr(s, k, v)
        self.db.commit()
        self.db.refresh(s)
        return _serialize_session(s)

    def delete_session(self, session_id: int) -> dict:
        s = self.db.get(RaceTacticsSession, session_id)
        if not s:
            raise NotFoundError(f"会话不存在: {session_id}")
        self.db.delete(s)
        self.db.commit()
        return {"ok": True, "id": session_id}

    def add_message(self, session_id: int, req: MessageIn) -> dict:
        s = self.db.get(RaceTacticsSession, session_id)
        if not s:
            raise NotFoundError(f"会话不存在: {session_id}")
        m = RaceTacticsMessage(session_id=session_id, role="user", content=req.content)
        self.db.add(m)
        self.db.commit()
        self.db.refresh(m)
        return _serialize_message(m)

    def delete_attachment(self, session_id: int, att_id: int) -> dict:
        att = self.db.get(RaceTacticsAttachment, att_id)
        if not att:
            raise NotFoundError(f"附件不存在: {att_id}")
        if att.session_id != session_id:
            raise ValidationError("附件与会话不匹配")
        self.db.delete(att)
        self.db.commit()
        return {"ok": True, "id": att_id}


# ============== helpers ==============

def _serialize_session(s: RaceTacticsSession, with_details: bool = False) -> dict:
    base = {
        "id": s.id,
        "race_name": s.race_name,
        "race_date": s.race_date.isoformat() if s.race_date else None,
        "distance_km": s.distance_km,
        "elevation_gain_m": s.elevation_gain_m,
        "race_type": s.race_type,
        "priority": s.priority,
        "weather_forecast": s.weather_forecast,
        "course_profile": s.course_profile,
        "final_strategy": s.final_strategy,
        "status": s.status,
        "created_at": s.created_at.isoformat() if s.created_at else None,
        "updated_at": s.updated_at.isoformat() if s.updated_at else None,
        "message_count": len(s.messages) if s.messages else 0,
        "attachment_count": len(s.attachments) if s.attachments else 0,
    }
    if with_details:
        base["messages"] = [_serialize_message(m) for m in (s.messages or [])]
        base["attachments"] = [_serialize_attachment(a) for a in (s.attachments or [])]
    return base


def _serialize_message(m: RaceTacticsMessage) -> dict:
    return {
        "id": m.id,
        "session_id": m.session_id,
        "role": m.role,
        "content": m.content,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _serialize_attachment(a: RaceTacticsAttachment) -> dict:
    return {
        "id": a.id,
        "session_id": a.session_id,
        "filename": a.filename,
        "file_path": a.file_path,
        "mime_type": a.mime_type,
        "size_bytes": a.size_bytes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }
