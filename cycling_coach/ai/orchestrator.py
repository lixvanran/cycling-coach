"""AI 教练编排器 — v0.5 RAG + PMC

V0.3:自动注入 PMC 状态卡
V0.5:自动 RAG 检索知识库, top-3 chunks 注入 system prompt
"""
from __future__ import annotations
import logging
from typing import Generator

from .m3_client import get_m3, M3Error, M3AuthError, M3NetworkError, M3QuotaError
from .prompts.chat import build_chat_messages
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.pmc import get_pmc_today
from cycling_coach.data.sqlite.database import SessionLocal
from cycling_coach.data.sqlite.models import Athlete

logger = logging.getLogger(__name__)


def _retrieve_kb(user_message: str, top_k: int = 3) -> list[dict]:
    """V0.5: 从知识库 FTS5 检索 top-K chunks

    Returns: [{title, path, content, snippet}, ...]
    V0.5 后续: 若有 embedding, 走向量检索 + rerank
    """
    try:
        from sqlalchemy import text as _sql_text, or_ as _or
        from cycling_coach.data.sqlite import engine as _engine
        from cycling_coach.data.sqlite.models import KbChunk, KbDocument
        from cycling_coach.data.sqlite.database import SessionLocal as _SessionLocal
        # 1) 提取 query 关键词(英文/数字 + 中文 2-gram + 中文 ≥3 整词)
        import re
        terms = []
        for w in re.findall(r'[A-Za-z0-9]+', user_message):
            if len(w) >= 2:
                terms.append(w)
        for s in re.findall(r'[\u4e00-\u9fff]+', user_message):
            if len(s) >= 3:
                terms.append(s)
            for i in range(len(s) - 1):
                terms.append(s[i:i+2])
        seen = set()
        terms = [t for t in terms if not (t in seen or seen.add(t))][:8]
        if not terms:
            return []

        # 2) FTS5 全文索引(快, 有 rank)
        fts_q = " OR ".join(f'"{t}"*' for t in terms)
        fts_rows = []
        try:
            with _engine.connect() as conn:
                fts_rows = conn.execute(_sql_text("""
                    SELECT rowid, snippet(kb_chunks_fts, 0, '', '', '...', 16) as snippet, rank
                    FROM kb_chunks_fts
                    WHERE kb_chunks_fts MATCH :q
                    ORDER BY rank LIMIT :k
                """), {"q": fts_q, "k": top_k * 2}).fetchall()
        except Exception:
            fts_rows = []

        # 3) LIKE 模糊匹配(对单字/长 query 兜底)
        # 从 kb_chunks 找 content 含任意 term 的 chunk
        from sqlalchemy import or_
        like_q = SessionLocal().query(KbChunk, KbDocument).join(
            KbDocument, KbDocument.id == KbChunk.document_id
        )
        conds = []
        for t in terms:
            conds.append(KbChunk.content.contains(t))
        like_q = like_q.filter(or_(*conds)).limit(top_k * 2).all()

        # 4) 合并: 优先 FTS5 命中的, 其次 LIKE 命中的
        seen_ids = set()
        results = []
        for r in fts_rows:
            cid = r[0]
            if cid in seen_ids:
                continue
            seen_ids.add(cid)
            # 取 chunk + doc
            with SessionLocal() as s:
                pair = s.query(KbChunk, KbDocument).join(
                    KbDocument, KbDocument.id == KbChunk.document_id
                ).filter(KbChunk.id == cid).first()
            if pair:
                c, d = pair
                results.append({
                    "title": d.title,
                    "path": d.path,
                    "content": c.content,
                    "snippet": (r[1] if r[1] else c.content[:120] + "...")[:200],
                })
        if len(results) < top_k:
            for c, d in like_q:
                if d.id in seen_ids or len(results) >= top_k:
                    continue
                seen_ids.add(d.id)
                results.append({
                    "title": d.title,
                    "path": d.path,
                    "content": c.content,
                    "snippet": c.content[:200],
                })

        logger.info(f"RAG 命中 {len(results)} chunks (FTS5={len(fts_rows)} LIKE补={len(results)-len(fts_rows)}): {[r['title'][:30] for r in results]}")
        return results
    except Exception as e:
        logger.warning(f"RAG 检索失败(降级为空): {e}")
        return []
        # 取 chunk + doc 信息
        chunk_ids = [r[0] for r in rows]
        from cycling_coach.data.sqlite.models import KbChunk, KbDocument
        with SessionLocal() as s:
            chunks = s.query(KbChunk, KbDocument).join(
                KbDocument, KbDocument.id == KbChunk.document_id
            ).filter(KbChunk.id.in_(chunk_ids)).all()
        results = []
        for c, d in chunks:
            results.append({
                "title": d.title,
                "path": d.path,
                "content": c.content,
                "snippet": (c.content[:120] + "...") if len(c.content) > 120 else c.content,
            })
        logger.info(f"RAG 命中 {len(results)} chunks: {[r['title'][:30] for r in results]}")
        return results
    except Exception as e:
        logger.warning(f"RAG 检索失败(降级为空): {e}")
        return []


# 保留旧逻辑的尾部 (无效代码, 仅为兼容)
_ = rows if False else None


def _format_kb_block(retrieved: list[dict]) -> str:
    """把检索结果格式化成可注入的 system 段落"""
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


def stream_chat(
    history: list[dict],
    user_message: str,
) -> Generator[str, None, None]:
    """流式 chat 编排

    Yields:
      "data: <text>\n\n"  — 文本块(SSE 格式)
      "data: [DONE]\n\n"  — 结束
      "data: [ERROR] <msg>\n\n" — 错误
    """
    # 取 athlete 名字 + 今日 PMC(V0.3 新增)
    db = SessionLocal()
    try:
        athlete = profile_store.get_or_create_athlete(db)
        athlete_name = athlete.name
        try:
            pmc = get_pmc_today(db, athlete.id)
        except Exception as e:
            logger.warning(f"PMC 读取失败(降级为空): {e}")
            pmc = None
    finally:
        db.close()

    # V0.5: RAG 检索知识库
    retrieved = _retrieve_kb(user_message, top_k=3)
    kb_block = _format_kb_block(retrieved)

    system, messages = build_chat_messages(
        history, user_message,
        athlete_name=athlete_name,
        athlete_pmc=pmc,
        kb_block=kb_block,
    )
    m3 = get_m3()

    try:
        for chunk in m3.stream_chat(system, messages):
            # SSE 安全转义
            chunk_safe = chunk.replace("\n", "\\n")
            yield f"data: {chunk_safe}\n\n"
        # V0.5: 发送 RAG 引用源(供前端展示"📚 参考")
        if retrieved:
            import json
            sources_json = json.dumps([
                {"title": r.get("title", ""), "path": r.get("path", ""), "snippet": r.get("snippet", "")[:200]}
                for r in retrieved
            ], ensure_ascii=False)
            sources_safe = sources_json.replace("\n", "\\n")
            yield f"data: [SOURCES] {sources_safe}\n\n"
        yield "data: [DONE]\n\n"
    except (M3AuthError, M3QuotaError, M3NetworkError) as e:
        logger.error(f"chat 致命错: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
    except M3Error as e:
        logger.error(f"chat 错误: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
    except Exception as e:
        logger.exception(f"chat 未知错误: {e}")
        msg = str(e).replace("\n", " ")
        yield f"data: [ERROR] {msg}\n\n"
