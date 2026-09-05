"""V0.8.0: Chat 业务层 (V0.7.6 通用 chat 持久化)

覆盖端点:
- POST   /api/chat/sessions                    create_session
- GET    /api/chat/sessions                    list_sessions
- GET    /api/chat/sessions/{id}/messages      get_messages
- POST   /api/chat/sessions/{id}/messages      add_message
- PATCH  /api/chat/sessions/{id}/tree          update_tree
- DELETE /api/chat/sessions/{id}               delete_session
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional, List

from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from cycling_coach.core.exceptions import NotFoundError
from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)


# ============== DTO ==============

class CreateSessionRequest(BaseModel):
    title: str = Field("新对话", max_length=128)
    session_type: str = Field("general", pattern="^(general|race_tactics|training_plan|diffuse_thinking)$")
    tree_params: Optional[dict] = None


class SessionResponse(BaseModel):
    id: int
    title: str
    session_type: str
    status: str
    created_at: str
    updated_at: str
    message_count: int


class MessageResponse(BaseModel):
    id: int
    role: str
    content: str
    parent_id: Optional[int]
    node_path: Optional[str]
    thought_kind: Optional[str]
    score: Optional[float]
    status: str
    thinking: Optional[str]
    rag_sources: Optional[list]
    tokens_in: Optional[int]
    tokens_out: Optional[int]
    error: Optional[str]
    created_at: str


class AddMessageRequest(BaseModel):
    role: str = Field(..., pattern="^(user|assistant|system|tool|agent_a|agent_b)$")
    content: str
    parent_id: Optional[int] = None
    node_path: Optional[str] = None
    thought_kind: Optional[str] = None
    score: Optional[float] = None
    status: str = "active"
    thinking: Optional[str] = None
    rag_sources: Optional[list] = None
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None


# ============== Service ==============

class ChatService:
    """Chat 会话 + 消息服务

    当前 MVP: 单 athlete, 用 profile_store.get_or_create_athlete 取
    """
    def __init__(self, db: Session):
        self.db = db

    # ---------- 会话 CRUD ----------

    def create_session(self, req: CreateSessionRequest) -> dict:
        athlete = profile_store.get_or_create_athlete(self.db)
        s = ChatSession(
            athlete_id=athlete.id,
            title=req.title,
            session_type=req.session_type,
            tree_params=req.tree_params,
            status="active",
        )
        self.db.add(s)
        self.db.commit()
        self.db.refresh(s)
        logger.info(f"chat session 创建: id={s.id} title={s.title} type={s.session_type}")
        return {
            "id": s.id,
            "title": s.title,
            "session_type": s.session_type,
            "status": s.status,
            "created_at": s.created_at.isoformat(),
            "updated_at": s.updated_at.isoformat(),
            "message_count": 0,
        }

    def list_sessions(
        self,
        limit: int = 20,
        offset: int = 0,
        session_type: Optional[str] = None,
    ) -> List[dict]:
        athlete = profile_store.get_or_create_athlete(self.db)
        q = self.db.query(ChatSession).filter(ChatSession.athlete_id == athlete.id)
        if session_type:
            q = q.filter(ChatSession.session_type == session_type)
        q = q.order_by(desc(ChatSession.updated_at))
        rows = q.offset(offset).limit(limit).all()
        return [
            {
                "id": s.id,
                "title": s.title,
                "session_type": s.session_type,
                "status": s.status,
                "created_at": s.created_at.isoformat(),
                "updated_at": s.updated_at.isoformat(),
                "message_count": len(s.messages),
            }
            for s in rows
        ]

    def delete_session(self, session_id: int) -> dict:
        athlete = profile_store.get_or_create_athlete(self.db)
        s = self.db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.athlete_id == athlete.id,
        ).first()
        if not s:
            raise NotFoundError("session not found")
        self.db.delete(s)  # cascade 删 messages
        self.db.commit()
        logger.info(f"chat session 删除: id={session_id}")
        return {"ok": True}

    # ---------- 消息 ----------

    def get_messages(self, session_id: int) -> List[dict]:
        athlete = profile_store.get_or_create_athlete(self.db)
        s = self.db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.athlete_id == athlete.id,
        ).first()
        if not s:
            raise NotFoundError("session not found")
        rows = (
            self.db.query(ChatMessage)
            .filter(ChatMessage.session_id == session_id)
            .order_by(ChatMessage.id.asc())
            .all()
        )
        return [_serialize_message(m) for m in rows]

    def add_message(self, session_id: int, req: AddMessageRequest) -> dict:
        athlete = profile_store.get_or_create_athlete(self.db)
        s = self.db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.athlete_id == athlete.id,
        ).first()
        if not s:
            raise NotFoundError("session not found")
        m = ChatMessage(
            session_id=session_id,
            role=req.role, content=req.content,
            parent_id=req.parent_id, node_path=req.node_path,
            thought_kind=req.thought_kind, score=req.score,
            status=req.status, thinking=req.thinking, rag_sources=req.rag_sources,
            tokens_in=req.tokens_in, tokens_out=req.tokens_out,
        )
        self.db.add(m)
        s.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
        self.db.commit()
        self.db.refresh(m)
        return _serialize_message(m)

    def update_tree(self, session_id: int, payload: dict) -> dict:
        """更新会话的思维树快照 + 选中节点"""
        athlete = profile_store.get_or_create_athlete(self.db)
        s = self.db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.athlete_id == athlete.id,
        ).first()
        if not s:
            raise NotFoundError("session not found")
        s.tree_snapshot = payload.get("tree_snapshot")
        s.selected_node_id = payload.get("selected_node_id")
        if "status" in payload:
            s.status = payload.get("status", s.status)
        self.db.commit()
        self.db.refresh(s)
        logger.info(f"chat session 思维树更新: id={s.id} selected={s.selected_node_id}")
        return {"ok": True, "session_id": s.id, "status": s.status}


# ============== helpers ==============

def _serialize_message(m: ChatMessage) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "parent_id": m.parent_id,
        "node_path": m.node_path,
        "thought_kind": m.thought_kind,
        "score": m.score,
        "status": m.status,
        "thinking": m.thinking,
        "rag_sources": m.rag_sources,
        "tokens_in": m.tokens_in,
        "tokens_out": m.tokens_out,
        "error": m.error,
        "created_at": m.created_at.isoformat(),
    }
