"""/api/chat/* V0.7.6: 通用 chat 会话管理 (含思维树)

V0.8.0: 业务逻辑已抽到 cycling_coach.core.services.ChatService
        本文件只剩 router 端点 (薄)
        异常统一走 AppError → main.py handler → JSON 响应
"""
from __future__ import annotations
import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, Query

from cycling_coach.api.dependencies import Services, get_services
from cycling_coach.core.services.chat import (
    CreateSessionRequest,
    SessionResponse,
    MessageResponse,
    AddMessageRequest,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chat", tags=["chat"])


# ============================================================
# 会话 CRUD
# ============================================================

@router.post("/sessions", response_model=SessionResponse)
def create_session(
    req: CreateSessionRequest,
    svc: Services = Depends(get_services),
):
    """创建 chat 会话"""
    return svc.chat.create_session(req)


@router.get("/sessions", response_model=List[SessionResponse])
def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session_type: Optional[str] = None,
    svc: Services = Depends(get_services),
):
    """列出会话 (按 updated_at 倒序)"""
    return svc.chat.list_sessions(limit=limit, offset=offset, session_type=session_type)


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: int,
    svc: Services = Depends(get_services),
):
    """删除会话 — cascade 自动删 messages"""
    return svc.chat.delete_session(session_id)


# ============================================================
# 消息
# ============================================================

@router.get("/sessions/{session_id}/messages", response_model=List[MessageResponse])
def get_messages(
    session_id: int,
    svc: Services = Depends(get_services),
):
    """获取会话的所有消息(按 id 升序)"""
    return svc.chat.get_messages(session_id)


@router.post("/sessions/{session_id}/messages", response_model=MessageResponse)
def add_message(
    session_id: int,
    req: AddMessageRequest,
    svc: Services = Depends(get_services),
):
    """往会话加消息(普通 chat / 思维树节点共用)"""
    return svc.chat.add_message(session_id, req)


@router.patch("/sessions/{session_id}/tree")
def update_tree(
    session_id: int,
    payload: dict,
    svc: Services = Depends(get_services),
):
    """更新会话的思维树快照 + 选中节点 (思维扩散器完成后调用)"""
    return svc.chat.update_tree(session_id, payload)
