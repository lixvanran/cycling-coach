"""/api/chat/* V0.7.6: 通用 chat 会话管理 (含思维树)

V0.7.6 Foundation 1.0: 通用 chat 持久化 + ML 预测基础设施

设计要点:
- /api/chat/sessions — 会话 CRUD (list / create / delete)
- /api/chat/sessions/{id}/messages — 消息持久化 (增 / 查)
- /api/chat/sessions/{id}/tree — 思维树快照更新 (思维扩散器完成后调用)
- 当前 MVP: 单 athlete, 直接用 profile_store.get_or_create_athlete 取
- 后续多用户: 加 X-Athlete-Id header 路由
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sqlalchemy import desc

from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import ChatSession, ChatMessage

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


# ============================================================
# Pydantic schemas
# ============================================================

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


# ============================================================
# 会话 CRUD
# ============================================================

@router.post("/sessions", response_model=SessionResponse)
def create_session(req: CreateSessionRequest, db: Session = Depends(get_db)):
    """创建 chat 会话

    session_type:
    - general: 普通对话
    - race_tactics: 比赛战术(预留, 当前走 race_tactics 表)
    - training_plan: 训练计划讨论
    - diffuse_thinking: 思维扩散器(后续版本启用)
    """
    athlete = profile_store.get_or_create_athlete(db)
    s = ChatSession(
        athlete_id=athlete.id,
        title=req.title,
        session_type=req.session_type,
        tree_params=req.tree_params,
        status="active",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    logger.info(f"chat session 创建: id={s.id} title={s.title} type={s.session_type}")
    return SessionResponse(
        id=s.id, title=s.title, session_type=s.session_type, status=s.status,
        created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat(),
        message_count=0,
    )


@router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session_type: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """列出会话 (按 updated_at 倒序)

    可选 session_type 过滤(general / race_tactics / training_plan / diffuse_thinking)
    """
    athlete = profile_store.get_or_create_athlete(db)
    q = db.query(ChatSession).filter(ChatSession.athlete_id == athlete.id)
    if session_type:
        q = q.filter(ChatSession.session_type == session_type)
    q = q.order_by(desc(ChatSession.updated_at))
    rows = q.offset(offset).limit(limit).all()
    return [
        SessionResponse(
            id=s.id, title=s.title, session_type=s.session_type, status=s.status,
            created_at=s.created_at.isoformat(), updated_at=s.updated_at.isoformat(),
            message_count=len(s.messages),
        )
        for s in rows
    ]


@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages(session_id: int, db: Session = Depends(get_db)):
    """获取会话的所有消息(按 id 升序, 时间顺序)"""
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.athlete_id == athlete.id,
    ).first()
    if not s:
        raise HTTPException(404, "session not found")
    rows = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.id.asc()).all()
    return [
        MessageResponse(
            id=m.id, role=m.role, content=m.content, parent_id=m.parent_id,
            node_path=m.node_path, thought_kind=m.thought_kind, score=m.score,
            status=m.status, thinking=m.thinking, rag_sources=m.rag_sources,
            tokens_in=m.tokens_in, tokens_out=m.tokens_out, error=m.error,
            created_at=m.created_at.isoformat(),
        )
        for m in rows
    ]


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
def add_message(session_id: int, req: AddMessageRequest, db: Session = Depends(get_db)):
    """往会话加消息(普通 chat / 思维树节点共用)

    思维树场景: client 维护 parent_id / node_path / thought_kind / score,
    服务端纯持久化, 不做树结构校验(由调用方负责)
    """
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.athlete_id == athlete.id,
    ).first()
    if not s:
        raise HTTPException(404, "session not found")
    m = ChatMessage(
        session_id=session_id,
        role=req.role, content=req.content,
        parent_id=req.parent_id, node_path=req.node_path,
        thought_kind=req.thought_kind, score=req.score,
        status=req.status, thinking=req.thinking, rag_sources=req.rag_sources,
        tokens_in=req.tokens_in, tokens_out=req.tokens_out,
    )
    db.add(m)
    s.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    db.commit()
    db.refresh(m)
    return MessageResponse(
        id=m.id, role=m.role, content=m.content, parent_id=m.parent_id,
        node_path=m.node_path, thought_kind=m.thought_kind, score=m.score,
        status=m.status, thinking=m.thinking, rag_sources=m.rag_sources,
        tokens_in=m.tokens_in, tokens_out=m.tokens_out, error=m.error,
        created_at=m.created_at.isoformat(),
    )


@router.patch("/sessions/{session_id}/tree")
def update_tree(session_id: int, payload: dict, db: Session = Depends(get_db)):
    """更新会话的思维树快照 + 选中节点 (思维扩散器完成后调用)

    payload 字段:
    - tree_snapshot: dict  (完整节点树)
    - selected_node_id: int (最终选中节点)
    - status: str (active / completed / cancelled)
    """
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.athlete_id == athlete.id,
    ).first()
    if not s:
        raise HTTPException(404, "session not found")
    s.tree_snapshot = payload.get("tree_snapshot")
    s.selected_node_id = payload.get("selected_node_id")
    if "status" in payload:
        s.status = payload.get("status", s.status)
    db.commit()
    db.refresh(s)
    logger.info(f"chat session 思维树更新: id={s.id} selected={s.selected_node_id}")
    return {"ok": True, "session_id": s.id, "status": s.status}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """删除会话 — cascade 自动删 messages (V0.7.6 模型 relationship 上设了)"""
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.athlete_id == athlete.id,
    ).first()
    if not s:
        raise HTTPException(404, "session not found")
    db.delete(s)  # cascade 删 messages
    db.commit()
    logger.info(f"chat session 删除: id={session_id}")
    return {"ok": True}
