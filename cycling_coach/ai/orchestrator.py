"""AI 教练编排器 — v0.5 RAG + PMC + v0.8 multi-mind 集成

V0.3: 自动注入 PMC 状态卡
V0.5: 自动 RAG 检索知识库, top-3 chunks 注入 system prompt
V0.7.5.2: 抽 build_chat_context 统一 6 块 (DEV-7 + DEV-10)
V0.8.0: 拆 3 个 pipeline 路由 mode
        - mode="rag"      (默认): 6 块上下文 + RAG + LLM (V0.7.x 行为)
        - mode="workflow": HTTP 调 multi-mind :8766 /run, 拿流式结果
        - mode="chat":     6 块上下文 + 直接 LLM, 不 RAG
"""
from __future__ import annotations
import asyncio
import json
import logging
from typing import Generator, Optional, Literal

import httpx
from sqlalchemy.orm import Session

from .m3_client import get_m3, M3Error, M3AuthError, M3NetworkError, M3QuotaError
from .prompts.chat import build_chat_messages
from cycling_coach.core.profile import store as profile_store
from cycling_coach.data.sqlite.database import SessionLocal
from cycling_coach.data.sqlite.models import ChatSession, ChatMessage
from cycling_coach.config.config import settings

logger = logging.getLogger(__name__)

__all__ = [
    "stream_chat",
    "rag_pipeline",
    "chat_pipeline",
    "workflow_pipeline",
]


# =================================================================
# 共享工具: 6 块上下文
# =================================================================

def _get_athlete_ctx(db: Session) -> dict:
    """拿 athlete + 6 块上下文 (profile/pmc/acwr/rpe/phase/ftp)
    与 V0.7.5.2 的 build_chat_context 保持一致
    V0.8.0: 防御性处理 — 把 None 转成 0/默认值, 避免 build_chat_messages 内部
    _format_pmc_block 等对 None 做 < 比较崩
    """
    athlete = profile_store.get_or_create_athlete(db)
    from cycling_coach.core.coaching.context import build_chat_context
    ctx = build_chat_context(db, athlete.id)

    def _safe(d: dict | None) -> dict:
        """把 None 转成 {}, 字段缺 None 转 0"""
        if not d:
            return {}
        return {k: (0 if v is None else v) for k, v in d.items()}

    return {
        "athlete_id": athlete.id,
        "athlete_name": ctx.get("athlete", {}).get("name") or "Rider",
        "athlete_exp": ctx.get("athlete", {}).get("experience") or "未填",
        "athlete_max_hr": ctx.get("athlete", {}).get("max_hr") or 0,
        "athlete_lthr": ctx.get("athlete", {}).get("lthr") or 0,
        "athlete_ftp": ctx.get("athlete", {}).get("ftp") or 0,
        "pmc": _safe(ctx.get("pmc")),
        "acwr": _safe(ctx.get("acwr")),
        "rpe_7d": _safe(ctx.get("rpe_7d")),
        "phase": ctx.get("phase") or {},
        "ftp_info": ctx.get("ftp") or {},
    }


def _athlete_ctx_to_payload(ctx: dict) -> dict:
    """V0.8.0: 把 athlete ctx 序列化成 multi-mind context (dict)"""
    return {
        "athlete_name": ctx["athlete_name"],
        "experience": ctx["athlete_exp"],
        "ftp": ctx["athlete_ftp"],
        "max_hr": ctx["athlete_max_hr"],
        "lthr": ctx["athlete_lthr"],
        "pmc": ctx["pmc"],
        "acwr": ctx["acwr"],
        "rpe_7d": ctx["rpe_7d"],
        "phase": ctx["phase"],
        "ftp_info": ctx["ftp_info"],
    }


# =================================================================
# RAG 检索
# =================================================================

def _retrieve_kb(user_message: str, top_k: int = 3) -> list[dict]:
    """V0.7.1 修订: FTS5 + 关键词加权"""
    import re
    from sqlalchemy import text as _sql_text, or_ as _or
    from cycling_coach.data.sqlite import engine as _engine
    from cycling_coach.data.sqlite.models import KbChunk, KbDocument
    from cycling_coach.data.sqlite.database import SessionLocal

    STOPWORDS = {"的", "了", "是", "在", "和", "与", "或", "及", "把", "给", "我", "你", "他", "她", "它", "这", "那", "吗", "啊", "呢", "吧"}
    CYCLING_KEYWORDS = {
        "ftp": 1.5, "tss": 1.5, "np": 1.5, "if": 1.5, "ctl": 1.5, "atl": 1.5, "tsb": 1.5,
        "功率": 1.5, "心率": 1.5, "踏频": 1.5, "海拔": 1.5, "爬坡": 1.5, "冲刺": 1.5,
        "间歇": 1.5, "恢复": 1.3, "减量": 1.3, "taper": 1.3, "基础期": 1.3, "强化期": 1.3,
        "巅峰": 1.3, "周期化": 1.5, "阈值": 1.5, "无氧": 1.3, "有氧": 1.3, "配速": 1.3,
        "v02": 1.5, "wbal": 1.5, "w'": 1.5, "decoupling": 1.5, "acwr": 1.5, "rpe": 1.5,
    }
    terms_with_weight: list[tuple[str, float]] = []
    seen_t: set[str] = set()

    for w in re.findall(r'[A-Za-z][A-Za-z0-9_]+', user_message):
        wl = w.lower()
        if len(wl) >= 2 and wl not in seen_t:
            seen_t.add(wl)
            terms_with_weight.append((wl, CYCLING_KEYWORDS.get(wl, 1.0)))

    for s in re.findall(r'[\u4e00-\u9fff]+', user_message):
        if len(s) >= 2 and s not in STOPWORDS and s not in seen_t:
            seen_t.add(s)
            terms_with_weight.append((s, CYCLING_KEYWORDS.get(s, 1.5)))
        for i in range(len(s) - 1):
            g = s[i:i+2]
            if g not in STOPWORDS and g not in seen_t:
                seen_t.append(g) if False else seen_t.add(g)
                terms_with_weight.append((g, CYCLING_KEYWORDS.get(g, 0.8)))

    terms_with_weight.sort(key=lambda x: x[1], reverse=True)
    terms = [t for t, _ in terms_with_weight[:8]]
    if not terms:
        return []

    fts_q = " OR ".join(f'"{t}"*' for t in terms)
    fts_rows: list = []
    try:
        with _engine.connect() as conn:
            fts_rows = conn.execute(_sql_text("""
                SELECT rowid, snippet(kb_chunks_fts, 0, '', '', '...', 16) as snippet, rank
                FROM kb_chunks_fts
                WHERE kb_chunks_fts MATCH :q
                ORDER BY rank LIMIT :k
            """), {"q": fts_q, "k": top_k * 2}).fetchall()
    except Exception as e:
        logger.debug(f"FTS5 检索失败: {e}")

    fts_cids = [r[0] for r in fts_rows]
    fts_snippets = {r[0]: r[1] for r in fts_rows}
    fts_pair_by_cid: dict[int, tuple] = {}

    if fts_cids:
        try:
            with SessionLocal() as s:
                rows = (
                    s.query(KbChunk, KbDocument)
                    .join(KbDocument, KbDocument.id == KbChunk.document_id)
                    .filter(KbChunk.id.in_(fts_cids))
                    .all()
                )
                fts_pair_by_cid = {c.id: (c, d) for c, d in rows}
        except Exception as e:
            logger.debug(f"FTS chunk 查询失败: {e}")

    like_results: list[tuple] = []
    try:
        with SessionLocal() as s:
            conds = [KbChunk.content.contains(t) for t in terms]
            like_results = (
                s.query(KbChunk, KbDocument)
                .join(KbDocument, KbDocument.id == KbChunk.document_id)
                .filter(_or(*conds))
                .limit(top_k * 2)
                .all()
            )
    except Exception as e:
        logger.debug(f"LIKE 检索失败: {e}")

    seen_cids: set[int] = set()
    results: list[dict] = []

    for cid in fts_cids:
        if cid in seen_cids or len(results) >= top_k:
            continue
        seen_cids.add(cid)
        pair = fts_pair_by_cid.get(cid)
        if not pair:
            continue
        c, d = pair
        snip = fts_snippets.get(cid) or c.content[:200]
        results.append({
            "title": d.title,
            "path": d.path,
            "content": c.content,
            "snippet": snip[:200],
        })

    if len(results) < top_k:
        for c, d in like_results:
            if c.id in seen_cids or len(results) >= top_k:
                continue
            seen_cids.add(c.id)
            results.append({
                "title": d.title,
                "path": d.path,
                "content": c.content,
                "snippet": c.content[:200],
            })

    logger.info(
        f"RAG 命中 {len(results)} chunks "
        f"(FTS5={len(fts_rows)} LIKE补={len(results)-len(fts_rows)}): "
        f"{[r['title'][:30] for r in results]}"
    )
    return results


def _format_kb_block(retrieved: list[dict]) -> str:
    if not retrieved:
        return ""
    lines = ["## 知识库参考 (V0.5 RAG, 自动从潘震(公路车教练)知识库检索)\n"]
    for i, r in enumerate(retrieved, 1):
        lines.append(f"### [{i}] {r['title']}")
        lines.append(f"来源: {r['path']}")
        lines.append(f"内容摘要: {r['snippet']}")
        lines.append(f"完整内容:\n{r['content']}\n")
    lines.append("---\n回答时如涉及训练方法/原则/术语,优先引用上面的知识库内容并标注来源路径。")
    return "\n".join(lines)


# =================================================================
# chat_messages 持久化
# =================================================================

def _ensure_session(db: Session, athlete_id: int, session_id: Optional[int], mode: str) -> ChatSession:
    """确保有 ChatSession (按 mode 决定 session_type)"""
    session: Optional[ChatSession] = None
    if session_id:
        session = db.query(ChatSession).filter(
            ChatSession.id == session_id,
            ChatSession.athlete_id == athlete_id,
        ).first()
    if not session:
        stype_map = {
            "rag": "general",
            "workflow": "diffuse_thinking",
            "chat": "general",
        }
        title_prefix = {
            "rag": "RAG 对话",
            "workflow": "战术规划 (multi-mind)",
            "chat": "闲聊",
        }
        session = ChatSession(
            athlete_id=athlete_id,
            title=title_prefix.get(mode, "新对话"),
            session_type=stype_map.get(mode, "general"),
            status="active",
        )
        db.add(session)
        db.flush()
        logger.info(f"[{mode}] 自动建 session: id={session.id}")
    return session


def _persist_user_msg(db: Session, session: ChatSession, content: str) -> ChatMessage:
    m = ChatMessage(session_id=session.id, role="user", content=content)
    db.add(m)
    db.flush()
    return m


def _persist_assistant_msg(
    db: Session,
    session: ChatSession,
    content: str,
    *,
    parent_id: Optional[int] = None,
    node_path: Optional[str] = None,
    thought_kind: Optional[str] = None,
    score: Optional[float] = None,
    rag_sources: Optional[list] = None,
    tokens_in: Optional[int] = None,
    tokens_out: Optional[int] = None,
    thinking: Optional[str] = None,
    status: str = "selected",
) -> ChatMessage:
    m = ChatMessage(
        session_id=session.id,
        role="assistant",
        content=content,
        parent_id=parent_id,
        node_path=node_path,
        thought_kind=thought_kind,
        score=score,
        rag_sources=rag_sources,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        thinking=thinking,
        status=status,
    )
    db.add(m)
    db.flush()
    return m


def _persist_workflow_node(
    db: Session,
    session: ChatSession,
    content: str,
    *,
    parent_id: Optional[int] = None,
    node_path: str,
    thought_kind: str,
    role: str = "agent_a",
    score: Optional[float] = None,
) -> ChatMessage:
    m = ChatMessage(
        session_id=session.id,
        role=role,
        content=content,
        parent_id=parent_id,
        node_path=node_path,
        thought_kind=thought_kind,
        score=score,
        status="active",
    )
    db.add(m)
    db.flush()
    return m


# =================================================================
# 3 个 pipeline
# =================================================================

def rag_pipeline(
    history: list[dict],
    user_message: str,
    *,
    session_id: Optional[int] = None,
) -> Generator[str, None, None]:
    """mode=rag: 6 块上下文 + RAG 检索 + LLM 流式 (V0.7.x 行为)"""
    # 1) 拿 athlete ctx
    db = SessionLocal()
    try:
        ctx = _get_athlete_ctx(db)
        athlete_id = ctx["athlete_id"]
        session = _ensure_session(db, athlete_id, session_id, "rag")
        user_msg = _persist_user_msg(db, session, user_message)
        session_id_persisted = session.id
        user_msg_id = user_msg.id
        db.commit()
    finally:
        db.close()

    # 2) RAG 检索
    retrieved = _retrieve_kb(user_message, top_k=3)
    kb_block = _format_kb_block(retrieved)

    # 3) 拼 system + messages
    system, messages = build_chat_messages(
        history, user_message,
        athlete_name=ctx["athlete_name"],
        athlete_exp=ctx["athlete_exp"],
        athlete_max_hr=ctx["athlete_max_hr"],
        athlete_lthr=ctx["athlete_lthr"],
        athlete_ftp=ctx["athlete_ftp"],
        athlete_pmc=ctx["pmc"],
        athlete_acwr=ctx["acwr"],
        athlete_rpe_7d=ctx["rpe_7d"],
        athlete_phase=ctx["phase"],
        athlete_ftp_info=ctx["ftp_info"],
        kb_block=kb_block,
    )

    yield f"data: [SESSION] {session_id_persisted}\n\n"

    # 4) 流式 LLM
    m3 = get_m3()
    full_text = ""
    try:
        for chunk in m3.stream_chat(system, messages):
            chunk_safe = chunk.replace("\n", "\\n")
            full_text += chunk
            yield f"data: {chunk_safe}\n\n"
    except (M3AuthError, M3QuotaError, M3NetworkError) as e:
        logger.error(f"rag chat 致命错: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
        return
    except M3Error as e:
        logger.error(f"rag chat 错误: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
        return
    except Exception as e:
        logger.exception(f"rag chat 未知错误: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
        return

    if retrieved:
        sources_json = json.dumps([
            {"title": r.get("title", ""), "path": r.get("path", ""), "snippet": r.get("snippet", "")[:200]}
            for r in retrieved
        ], ensure_ascii=False)
        sources_safe = sources_json.replace("\n", "\\n")
        yield f"data: [SOURCES] {sources_safe}\n\n"

    try:
        db = SessionLocal()
        try:
            session = db.get(ChatSession, session_id_persisted)
            if session:
                _persist_assistant_msg(
                    db, session, full_text,
                    parent_id=user_msg_id,
                    node_path=f"{user_msg_id}",
                    thought_kind="final",
                    rag_sources=[
                        {"title": r.get("title", ""), "path": r.get("path", ""), "snippet": r.get("snippet", "")[:200]}
                        for r in retrieved
                    ] if retrieved else None,
                )
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"rag chat 持久化失败: {e}")

    yield "data: [DONE]\n\n"


def chat_pipeline(
    history: list[dict],
    user_message: str,
    *,
    session_id: Optional[int] = None,
) -> Generator[str, None, None]:
    """mode=chat: 6 块上下文 + 直接 LLM, 不 RAG"""
    db = SessionLocal()
    try:
        ctx = _get_athlete_ctx(db)
        athlete_id = ctx["athlete_id"]
        session = _ensure_session(db, athlete_id, session_id, "chat")
        user_msg = _persist_user_msg(db, session, user_message)
        session_id_persisted = session.id
        user_msg_id = user_msg.id
        db.commit()
    finally:
        db.close()

    system, messages = build_chat_messages(
        history, user_message,
        athlete_name=ctx["athlete_name"],
        athlete_exp=ctx["athlete_exp"],
        athlete_max_hr=ctx["athlete_max_hr"],
        athlete_lthr=ctx["athlete_lthr"],
        athlete_ftp=ctx["athlete_ftp"],
        athlete_pmc=ctx["pmc"],
        athlete_acwr=ctx["acwr"],
        athlete_rpe_7d=ctx["rpe_7d"],
        athlete_phase=ctx["phase"],
        athlete_ftp_info=ctx["ftp_info"],
        kb_block="",  # V0.8.0: chat 模式不 RAG
    )

    yield f"data: [SESSION] {session_id_persisted}\n\n"

    m3 = get_m3()
    full_text = ""
    try:
        for chunk in m3.stream_chat(system, messages):
            chunk_safe = chunk.replace("\n", "\\n")
            full_text += chunk
            yield f"data: {chunk_safe}\n\n"
    except (M3AuthError, M3QuotaError, M3NetworkError) as e:
        logger.error(f"chat 致命错: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
        return
    except M3Error as e:
        logger.error(f"chat 错误: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
        return
    except Exception as e:
        logger.exception(f"chat 未知错误: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
        return

    try:
        db = SessionLocal()
        try:
            session = db.get(ChatSession, session_id_persisted)
            if session:
                _persist_assistant_msg(
                    db, session, full_text,
                    parent_id=user_msg_id,
                    node_path=f"{user_msg_id}",
                    thought_kind="final",
                )
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"chat 持久化失败: {e}")

    yield "data: [DONE]\n\n"


def workflow_pipeline(
    history: list[dict],
    user_message: str,
    *,
    session_id: Optional[int] = None,
) -> Generator[str, None, None]:
    """mode=workflow: HTTP 调 multi-mind :8766 /run, 流式转发 SSE 帧"""
    db = SessionLocal()
    try:
        ctx = _get_athlete_ctx(db)
        athlete_id = ctx["athlete_id"]
        session = _ensure_session(db, athlete_id, session_id, "workflow")
        user_msg = _persist_user_msg(db, session, user_message)
        session_id_persisted = session.id
        user_msg_id = user_msg.id
        db.commit()
    finally:
        db.close()

    payload = {
        "pipeline": settings.multi_mind_pipeline,
        "task": user_message,
        "context": _athlete_ctx_to_payload(ctx),
        "stream": True,
    }
    url = f"{settings.multi_mind_url.rstrip('/')}/run"

    yield f"data: [SESSION] {session_id_persisted}\n\n"

    nodes_collected: list[dict] = []
    final_output: str = ""
    tokens_in: Optional[int] = None
    tokens_out: Optional[int] = None
    error_msg: Optional[str] = None

    try:
        nodes_collected, final_output, tokens_in, tokens_out, error_msg = _call_multi_mind_sync(
            url, payload, settings.multi_mind_timeout
        )
    except Exception as e:
        logger.exception(f"workflow pipeline 内部异常: {e}")
        error_msg = f"workflow internal error: {e}"

    if error_msg:
        logger.warning(f"workflow 调 multi-mind 失败: {error_msg}")
        if settings.multi_mind_fallback_to_rag:
            yield f"data: [FALLBACK] multi-mind 不可达 ({error_msg}), 降级到 RAG 模式\n\n"
            yield from rag_pipeline(history, user_message, session_id=session_id_persisted)
            return
        else:
            yield f"data: [ERROR] multi-mind 不可达: {error_msg}\n\n"
            return

    for idx, node in enumerate(nodes_collected):
        evt = node.get("event", "node")
        stage = node.get("stage", "unknown")
        node_safe = json.dumps(node, ensure_ascii=False, default=str).replace("\n", "\\n")

        if evt == "error":
            yield f"data: [ERROR] {node_safe}\n\n"
            continue
        else:
            yield f"data: [NODE] {node_safe}\n\n"

        try:
            db = SessionLocal()
            try:
                session = db.get(ChatSession, session_id_persisted)
                if session:
                    thought_kind = {
                        "router": "evaluate",
                        "decomposer": "decompose",
                        "executor": "explore",
                        "integrator_aggressive": "synthesize",
                        "integrator_conservative": "synthesize",
                        "critic": "evaluate",
                    }.get(stage, "explore")

                    score = None
                    if stage == "critic" and node.get("content_preview"):
                        score = min(1.0, len(node["content_preview"]) / 500.0)
                    elif stage == "decomposer" and node.get("n_subtasks"):
                        score = min(1.0, node["n_subtasks"] / 5.0)

                    role = "agent_b" if "conservative" in stage else "agent_a"

                    _persist_workflow_node(
                        db, session,
                        content=json.dumps(node, ensure_ascii=False, default=str),
                        parent_id=user_msg_id,
                        node_path=f"{user_msg_id}.{idx}",
                        thought_kind=thought_kind,
                        role=role,
                        score=score,
                    )
                    db.commit()
            finally:
                db.close()
        except Exception as e:
            logger.warning(f"workflow 节点持久化失败: {e}")

    final_payload = json.dumps({"content": final_output[:5000]}, ensure_ascii=False).replace("\n", "\\n")
    yield f"data: [FINAL] {final_payload}\n\n"

    try:
        db = SessionLocal()
        try:
            session = db.get(ChatSession, session_id_persisted)
            if session:
                _persist_assistant_msg(
                    db, session, final_output,
                    parent_id=user_msg_id,
                    node_path=f"{user_msg_id}.final",
                    thought_kind="final",
                    score=1.0,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    status="selected",
                )
                session.status = "completed"
                db.commit()
        finally:
            db.close()
    except Exception as e:
        logger.warning(f"workflow final 持久化失败: {e}")

    yield "data: [DONE]\n\n"


def _call_multi_mind_sync(
    url: str,
    payload: dict,
    timeout: float,
) -> tuple[list[dict], str, Optional[int], Optional[int], Optional[str]]:
    """同步调 multi-mind :8766, 流式读 SSE"""
    def _run() -> tuple[list[dict], str, Optional[int], Optional[int], Optional[str]]:
        async def _do() -> tuple[list[dict], str, Optional[int], Optional[int], Optional[str]]:
            nodes: list[dict] = []
            final = ""
            t_in: Optional[int] = None
            t_out: Optional[int] = None
            err: Optional[str] = None
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    async with client.stream("POST", url, json=payload) as resp:
                        if resp.status_code != 200:
                            err = f"multi-mind HTTP {resp.status_code}"
                            return nodes, final, t_in, t_out, err
                        buffer = ""
                        async for chunk in resp.aiter_text():
                            buffer += chunk
                            while "\n\n" in buffer:
                                frame, buffer = buffer.split("\n\n", 1)
                                line = frame.strip()
                                if not line.startswith("data:"):
                                    continue
                                line = line[len("data:"):].strip()
                                if line.startswith("[NODE]"):
                                    body = line[len("[NODE]"):].strip()
                                elif line.startswith("[DONE]"):
                                    body = line[len("[DONE]"):].strip()
                                elif line.startswith("[ERROR]"):
                                    body = line[len("[ERROR]"):].strip()
                                else:
                                    body = line
                                try:
                                    obj = json.loads(body)
                                except Exception:
                                    obj = {"raw": body[:200]}
                                ev = obj.get("event", "node")
                                if ev == "done":
                                    final = obj.get("final_output", final)
                                    t_in = obj.get("tokens", 0) // 2
                                    t_out = obj.get("tokens", 0) - (t_in or 0)
                                elif ev == "error":
                                    err = obj.get("message", "unknown")
                                else:
                                    nodes.append(obj)
            except httpx.ConnectError as e:
                err = f"connect: {e}"
            except httpx.ReadTimeout as e:
                err = f"timeout: {e}"
            except httpx.HTTPError as e:
                err = f"http: {e}"
            except Exception as e:
                err = f"unknown: {e}"
            return nodes, final, t_in, t_out, err
        return asyncio.run(_do())

    try:
        return _run()
    except Exception as e:
        return [], "", None, None, f"runner error: {e}"


# =================================================================
# 总入口
# =================================================================

def stream_chat(
    history: list[dict],
    user_message: str,
    *,
    mode: Literal["rag", "workflow", "chat"] = "rag",
    session_id: Optional[int] = None,
) -> Generator[str, None, None]:
    """V0.8.0: mode 路由入口"""
    if mode == "workflow":
        return workflow_pipeline(history, user_message, session_id=session_id)
    elif mode == "chat":
        return chat_pipeline(history, user_message, session_id=session_id)
    else:
        return rag_pipeline(history, user_message, session_id=session_id)
