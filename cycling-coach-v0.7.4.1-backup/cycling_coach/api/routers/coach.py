"""/api/coach - AI 教练对话(SSE 流式)

v0.1.1:基础 chat,流式输出。后续 V0.4 接工具调用
"""
from __future__ import annotations
import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from cycling_coach.ai import stream_chat

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/coach", tags=["coach"])


class ChatMessage(BaseModel):
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = []
    message: str  # 当前用户输入


@router.post("/chat")
def chat(req: ChatRequest):
    """流式对话 — 返回 SSE

    客户端用 fetch + ReadableStream 读
    每个 chunk 形如: `data: <text>\\n\\n`
    结束: `data: [DONE]\\n\\n`
    错误: `data: [ERROR] <msg>\\n\\n`
    """
    history = [{"role": m.role, "content": m.content} for m in req.messages]

    def gen():
        try:
            for chunk in stream_chat(history, req.message):
                yield chunk
        except Exception as e:
            logger.exception(f"chat 流异常: {e}")
            yield f"data: [ERROR] {str(e)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx: 不缓冲
        },
    )
