"""/api/coach - AI 教练对话 (SSE 流式)

v0.1.1: 基础 chat, 流式输出
v0.4:    多轮工具循环
v0.7.x:  6 块上下文 + RAG
v0.8.0:  加 mode 路由 (rag/workflow/chat)
         - rag (默认): V0.7.x 行为
         - workflow:  调 multi-mind :8766 /run, 拿 6 agent 思维扩散
         - chat:      纯 LLM, 不 RAG
"""
from __future__ import annotations
import json
import logging
from typing import Optional, Literal

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from cycling_coach.ai import stream_chat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/coach", tags=["coach"])


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = []
    message: str  # 当前用户输入
    # V0.8.0: mode 路由
    # - "rag" (默认): 6 块上下文 + RAG 检索 + LLM
    # - "workflow":  HTTP 调 multi-mind :8766, 跑 6-agent 思维扩散
    # - "chat":      6 块上下文 + 直接 LLM, 不 RAG
    mode: Literal["rag", "workflow", "chat"] = Field(
        default="rag",
        description="chat 模式: rag (RAG 检索) / workflow (multi-mind 思维扩散) / chat (纯 LLM)",
    )
    # 可选: 客户端已有 session_id (前端从 /api/chat/sessions 拿) — 用于持久化
    session_id: Optional[int] = None


@router.post("/chat")
def chat(req: ChatRequest):
    """流式对话 — 返回 SSE

    客户端用 fetch + ReadableStream 读
    帧格式:
      - data: [SESSION] <id>\\n\\n           ← V0.8.0: session_id 给前端
      - data: <text>\\n\\n                    ← LLM 流式输出
      - data: [SOURCES] <json>\\n\\n          ← RAG 引用源 (仅 mode=rag)
      - data: [NODE] <json>\\n\\n             ← multi-mind 阶段节点 (仅 mode=workflow)
      - data: [FINAL] <json>\\n\\n            ← multi-mind 最终输出 (仅 mode=workflow)
      - data: [FALLBACK] <msg>\\n\\n          ← 降级提示 (multi-mind 不可达)
      - data: [DONE]\\n\\n                    ← 结束
      - data: [ERROR] <msg>\\n\\n             ← 错误
    """
    history = [{"role": m.role, "content": m.content} for m in req.messages]

    def gen():
        try:
            for chunk in stream_chat(
                history,
                req.message,
                mode=req.mode,
                session_id=req.session_id,
            ):
                yield chunk
        except Exception as e:
            logger.exception(f"chat 流异常 mode={req.mode}: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx: 不缓冲
        },
    )
