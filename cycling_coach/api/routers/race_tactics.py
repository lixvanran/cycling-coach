"""比赛战术规划 API — V0.7.5.9

借鉴 TrainingPeaks Race Plan / WKO5 Race Day / GoldenCheetah 比赛计划
- 比赛战术会话 CRUD
- 消息历史
- 路书上传 (PDF/PNG/JPG)
- AI 战术建议 (复用 chat 流式 + KB 检索)

端点:
- GET    /api/race-tactics/sessions              所有会话
- POST   /api/race-tactics/sessions              创建会话
- GET    /api/race-tactics/sessions/{id}        会话详情 (含消息 + 附件)
- DELETE /api/race-tactics/sessions/{id}        删除
- PATCH  /api/race-tactics/sessions/{id}        更新 (比赛信息/最终策略)
- POST   /api/race-tactics/sessions/{id}/upload 上传路书
- DELETE /api/race-tactics/sessions/{id}/attachments/{att_id}  删除附件
- POST   /api/race-tactics/sessions/{id}/messages  发消息 (AI 流式回复)
- POST   /api/race-tactics/sessions/{id}/suggest   AI 自动生成战术建议
"""
from __future__ import annotations
import asyncio
import json
import logging
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from cycling_coach.ai.orchestrator import _retrieve_kb
from cycling_coach.ai.m3_client import get_m3
from cycling_coach.config.config import settings
from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import (
    RaceTacticsSession, RaceTacticsMessage, RaceTacticsAttachment,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/race-tactics", tags=["race-tactics"])

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
MAX_UPLOAD_SIZE = 20 * 1024 * 1024  # 20MB 路书


# ============== Pydantic ==============

class SessionIn(BaseModel):
    race_name: str = Field(..., max_length=128)
    race_date: Optional[datetime] = None
    distance_km: Optional[float] = None
    elevation_gain_m: Optional[int] = None
    race_type: Optional[str] = None  # road_race / crit / tt / gran_fondo / hill_climb
    priority: Optional[str] = None  # A / B / C
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


# ============== Helpers ==============

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
        base["messages"] = [_serialize_message(m) for m in s.messages]
        base["attachments"] = [_serialize_attachment(a) for a in s.attachments]
    return base


def _serialize_message(m: RaceTacticsMessage) -> dict:
    return {
        "id": m.id,
        "role": m.role,
        "content": m.content,
        "thinking": m.thinking,
        "rag_sources": m.rag_sources or [],
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _serialize_attachment(a: RaceTacticsAttachment) -> dict:
    return {
        "id": a.id,
        "file_name": a.file_name,
        "mime_type": a.mime_type,
        "size_bytes": a.size_bytes,
        "description": a.description,
        "has_extracted_text": bool(a.extracted_text),
        "created_at": a.created_at.isoformat() if a.created_at else None,
        "url": f"/api/race-tactics/attachments/{a.id}/download",
    }


def _build_system_prompt(s: RaceTacticsSession, athlete_ctx: dict, attachments: list) -> str:
    """V0.7.5.9: 比赛战术规划 system prompt

    借鉴 TrainingPeaks Race Plan + WKO5 Race Day + 潘震训练百科
    """
    return f"""你是 Cycling Coach 的比赛战术规划教练, 帮运动员规划具体比赛策略.

## 当前比赛信息
- 比赛名称: {s.race_name}
- 比赛日期: {s.race_date.isoformat() if s.race_date else '未定'}
- 距离: {s.distance_km or '?'} km
- 总爬升: {s.elevation_gain_m or '?'} m
- 比赛类型: {s.race_type or '公路赛'}
- 优先级: {s.priority or 'B'}
- 天气预报: {s.weather_forecast or '未填'}
- 路线描述: {s.course_profile or '未填'}

## 运动员画像
- FTP: {athlete_ctx.get('ftp', '?')} W
- 最大心率: {athlete_ctx.get('max_hr', '?')} bpm
- 体重: {athlete_ctx.get('weight_kg', '?')} kg
- W/kg: {round(athlete_ctx['ftp']/athlete_ctx['weight_kg'], 2) if athlete_ctx.get('ftp') and athlete_ctx.get('weight_kg') else '?'}

## 已上传路书
{chr(10).join([f"- {a.file_name} ({a.size_bytes//1024} KB)" for a in attachments]) or '无'}

## 你的任务
1. **分段配速**: 起步/爬坡/平路/冲刺各阶段目标功率和心率
2. **补给策略**: 碳水/水分/电解质摄入节奏 (按距离分段)
3. **风险预案**: 天气突变/机械故障/体能崩盘应对
4. **心理节奏**: 关键节点(破风/突围/集团)的取舍
5. **引用知识库**: 涉及训练学/比赛学内容时, 必须引用训练百科 (潘震教练) 并标注来源路径

## 回答风格
- 中文, 专业但不冷冰冰, 像老教练聊天
- 具体数字 (功率/心率/补给量), 不空谈
- 引用 KB 时用 [来源: 路径] 标注
- 多轮对话, 教练要回应用户追问, 不断精化战术
"""


# ============== 端点 ==============

@router.get("/sessions")
def list_sessions(db: Session = Depends(get_db)):
    """所有战术会话 (按更新时间倒序)"""
    athlete = profile_store.get_or_create_athlete(db)
    sessions = (
        db.query(RaceTacticsSession)
        .filter(RaceTacticsSession.athlete_id == athlete.id)
        .order_by(desc(RaceTacticsSession.updated_at))
        .all()
    )
    return {"items": [_serialize_session(s) for s in sessions], "total": len(sessions)}


@router.post("/sessions")
def create_session(payload: SessionIn, db: Session = Depends(get_db)):
    """创建比赛战术会话"""
    athlete = profile_store.get_or_create_athlete(db)
    s = RaceTacticsSession(
        athlete_id=athlete.id,
        race_name=payload.race_name,
        race_date=payload.race_date,
        distance_km=payload.distance_km,
        elevation_gain_m=payload.elevation_gain_m,
        race_type=payload.race_type,
        priority=payload.priority,
        weather_forecast=payload.weather_forecast,
        course_profile=payload.course_profile,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return {"ok": True, "session": _serialize_session(s, with_details=True)}


@router.get("/sessions/{session_id}")
def get_session(session_id: int, db: Session = Depends(get_db)):
    """会话详情 (含所有消息 + 附件)"""
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(RaceTacticsSession).filter(
        RaceTacticsSession.id == session_id,
        RaceTacticsSession.athlete_id == athlete.id
    ).first()
    if not s:
        raise HTTPException(404, f"会话不存在: {session_id}")
    return _serialize_session(s, with_details=True)


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, payload: SessionPatch, db: Session = Depends(get_db)):
    """更新会话 (比赛信息/最终策略)"""
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(RaceTacticsSession).filter(
        RaceTacticsSession.id == session_id,
        RaceTacticsSession.athlete_id == athlete.id
    ).first()
    if not s:
        raise HTTPException(404, f"会话不存在: {session_id}")
    update = payload.model_dump(exclude_unset=True)
    for k, v in update.items():
        setattr(s, k, v)
    db.commit()
    db.refresh(s)
    return {"ok": True, "session": _serialize_session(s, with_details=True)}


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int, db: Session = Depends(get_db)):
    """删除会话"""
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(RaceTacticsSession).filter(
        RaceTacticsSession.id == session_id,
        RaceTacticsSession.athlete_id == athlete.id
    ).first()
    if not s:
        raise HTTPException(404, f"会话不存在: {session_id}")
    # 删附件文件
    for att in s.attachments:
        try:
            Path(att.file_path).unlink(missing_ok=True)
        except Exception:
            pass
    db.delete(s)
    db.commit()
    return {"ok": True, "deleted": session_id}


@router.post("/sessions/{session_id}/upload")
async def upload_route_book(
    session_id: int,
    file: UploadFile = File(...),
    description: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """上传路书 (PDF/PNG/JPG/WEBP)"""
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(RaceTacticsSession).filter(
        RaceTacticsSession.id == session_id,
        RaceTacticsSession.athlete_id == athlete.id
    ).first()
    if not s:
        raise HTTPException(404, f"会话不存在: {session_id}")
    if not file.filename:
        raise HTTPException(400, "未提供文件名")
    safe_name = Path(file.filename).name
    ext = Path(safe_name).suffix.lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(400, f"不支持的文件类型: {ext}(仅 .pdf/.png/.jpg/.jpeg/.webp)")
    # 落盘
    workspace = Path(settings.workspace_dir).resolve()
    upload_dir = workspace / "race_books" / str(session_id)
    upload_dir.mkdir(parents=True, exist_ok=True)
    file_path = (upload_dir / safe_name).resolve()
    try:
        file_path.relative_to(upload_dir.resolve())
    except ValueError:
        raise HTTPException(400, f"文件路径不安全: {safe_name!r}")
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"文件过大 ({len(content)//1024//1024}MB), 限制 {MAX_UPLOAD_SIZE//1024//1024}MB")
    with open(file_path, "wb") as f:
        f.write(content)
    # 解析 (PDF 提取文字, 图片跳过)
    extracted_text = None
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(file_path))
            texts = []
            for page in reader.pages:
                texts.append(page.extract_text() or "")
            extracted_text = "\n".join(texts)[:50000]  # 限 50K
        except Exception as e:
            logger.warning(f"PDF 解析失败: {e}")
    att = RaceTacticsAttachment(
        session_id=s.id,
        file_name=safe_name,
        file_path=str(file_path),
        mime_type=file.content_type or "application/octet-stream",
        size_bytes=len(content),
        description=description,
        extracted_text=extracted_text,
    )
    db.add(att)
    db.commit()
    db.refresh(att)
    return {"ok": True, "attachment": _serialize_attachment(att)}


@router.delete("/sessions/{session_id}/attachments/{att_id}")
def delete_attachment(session_id: int, att_id: int, db: Session = Depends(get_db)):
    """删除附件"""
    athlete = profile_store.get_or_create_athlete(db)
    att = db.get(RaceTacticsAttachment, att_id)
    if not att or att.session_id != session_id:
        raise HTTPException(404, f"附件不存在: {att_id}")
    s = db.get(RaceTacticsSession, session_id)
    if not s or s.athlete_id != athlete.id:
        raise HTTPException(403, "无权操作")
    try:
        Path(att.file_path).unlink(missing_ok=True)
    except Exception:
        pass
    db.delete(att)
    db.commit()
    return {"ok": True, "deleted": att_id}


@router.get("/attachments/{att_id}/download")
def download_attachment(att_id: int, db: Session = Depends(get_db)):
    """下载附件"""
    from fastapi.responses import FileResponse
    att = db.get(RaceTacticsAttachment, att_id)
    if not att:
        raise HTTPException(404, f"附件不存在: {att_id}")
    fp = Path(att.file_path)
    if not fp.exists():
        raise HTTPException(404, "文件已丢失")
    return FileResponse(
        path=str(fp),
        media_type=att.mime_type,
        filename=att.file_name,
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int,
    payload: MessageIn,
    db: Session = Depends(get_db),
):
    """发送消息, AI 流式回复 (SSE)

    Yields:
      "data: <text>\n\n"  — 文本块
      "data: [DONE]\n\n"  — 结束
      "data: [SOURCES] <json>\n\n" — RAG 引用源
      "data: [ERROR] <msg>\n\n" — 错误
    """
    from fastapi.responses import StreamingResponse
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(RaceTacticsSession).filter(
        RaceTacticsSession.id == session_id,
        RaceTacticsSession.athlete_id == athlete.id
    ).first()
    if not s:
        raise HTTPException(404, f"会话不存在: {session_id}")
    # 存 user 消息
    user_msg = RaceTacticsMessage(
        session_id=s.id, role="user", content=payload.content,
    )
    db.add(user_msg)
    db.commit()
    db.refresh(user_msg)

    # 异步: 拼 prompt → 调 AI → 流式返回
    from cycling_coach.core.coaching.context import build_athlete_context, build_ftp_context
    athlete_ctx = build_athlete_context(db)
    ftp_ctx = build_ftp_context(db, athlete.id) or {}
    athlete_ctx.update(ftp_ctx)

    # RAG 检索 (比赛战术相关)
    query = f"{s.race_name} {s.race_type or ''} 比赛战术 {payload.content}"
    retrieved = _retrieve_kb(query, top_k=4)
    rag_sources = [
        {"title": r["title"], "path": r["path"], "snippet": r["snippet"]}
        for r in retrieved
    ]

    system_prompt = _build_system_prompt(s, athlete_ctx, s.attachments)
    # 加 RAG 上下文
    if retrieved:
        rag_block = "\n## 知识库参考 (V0.7.5.9 RAG 比赛战术)\n"
        for i, r in enumerate(retrieved, 1):
            rag_block += f"### [{i}] {r['title']}\n来源: {r['path']}\n{r['snippet']}\n\n"
        system_prompt += rag_block
    # 加附件提取文本
    if s.attachments:
        attach_block = "\n## 附件提取内容\n"
        for att in s.attachments:
            if att.extracted_text:
                attach_block += f"### {att.file_name}\n{att.extracted_text[:3000]}\n\n"
        system_prompt += attach_block
    # 历史消息
    history = []
    for m in s.messages[-10:]:  # 最近 10 条
        history.append({"role": m.role, "content": m.content})
    history.append({"role": "user", "content": payload.content})

    async def gen():
        full_text = ""
        try:
            m3 = get_m3()
            # V0.7.5.9 修: stream_chat 签名 (system, messages, *, temperature, max_tokens)
            messages_for_ai = history  # history 已含当前 user
            for chunk in m3.stream_chat(
                system=system_prompt,
                messages=messages_for_ai,
                temperature=0.7,
            ):
                full_text += chunk
                yield f"data: {chunk}\n\n"
            # 存 assistant 消息
            asst = RaceTacticsMessage(
                session_id=s.id,
                role="assistant",
                content=full_text,
                rag_sources=rag_sources,
            )
            db.add(asst)
            s.updated_at = datetime.utcnow()
            db.commit()
            # 推送 sources
            yield f"data: [SOURCES] {json.dumps(rag_sources, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception(f"race_tactics chat 异常: {e}")
            yield "data: [ERROR] AI 响应失败, 请重试\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/sessions/{session_id}/suggest")
async def ai_suggest(
    session_id: int,
    db: Session = Depends(get_db),
):
    """AI 自动生成战术建议 (基于比赛信息 + 路书 + KB, 不需要用户输入)

    适合: 创建会话后, 用户先点一下看 AI 怎么想, 再开始讨论
    """
    athlete = profile_store.get_or_create_athlete(db)
    s = db.query(RaceTacticsSession).filter(
        RaceTacticsSession.id == session_id,
        RaceTacticsSession.athlete_id == athlete.id
    ).first()
    if not s:
        raise HTTPException(404, f"会话不存在: {session_id}")
    from cycling_coach.core.coaching.context import build_athlete_context, build_ftp_context
    athlete_ctx = build_athlete_context(db)
    ftp_ctx = build_ftp_context(db, athlete.id) or {}
    athlete_ctx.update(ftp_ctx)

    # RAG 检索
    query = f"{s.race_name} 比赛战术 配速 补给 风险 {s.race_type or ''} 距离 {s.distance_km or ''} 爬升 {s.elevation_gain_m or ''}"
    retrieved = _retrieve_kb(query, top_k=5)
    rag_sources = [
        {"title": r["title"], "path": r["path"], "snippet": r["snippet"]}
        for r in retrieved
    ]
    system_prompt = _build_system_prompt(s, athlete_ctx, s.attachments)
    if retrieved:
        rag_block = "\n## 知识库参考\n"
        for i, r in enumerate(retrieved, 1):
            rag_block += f"### [{i}] {r['title']}\n来源: {r['path']}\n{r['snippet']}\n\n"
        system_prompt += rag_block
    if s.attachments:
        attach_block = "\n## 附件提取\n"
        for att in s.attachments:
            if att.extracted_text:
                attach_block += f"### {att.file_name}\n{att.extracted_text[:3000]}\n\n"
        system_prompt += attach_block

    user_msg = "请基于比赛信息、路书和我的训练数据, 给我一个完整的比赛战术规划. 包括分段配速、补给、风险预案."

    async def gen():
        full_text = ""
        try:
            m3 = get_m3()
            # V0.7.5.9 修: 签名 (system, messages, *)
            for chunk in m3.stream_chat(
                system=system_prompt,
                messages=[{"role": "user", "content": user_msg}],
                temperature=0.7,
            ):
                full_text += chunk
                yield f"data: {chunk}\n\n"
            # 存消息 (role=assistant)
            asst = RaceTacticsMessage(
                session_id=s.id, role="assistant", content=full_text, rag_sources=rag_sources,
            )
            db.add(asst)
            # 默认 final_strategy = 这次的建议
            s.final_strategy = full_text
            s.updated_at = datetime.utcnow()
            db.commit()
            yield f"data: [SOURCES] {json.dumps(rag_sources, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
        except Exception as e:
            logger.exception(f"suggest 异常: {e}")
            yield "data: [ERROR] AI 生成失败\n\n"

    return StreamingResponse(
        gen(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
