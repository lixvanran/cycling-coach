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
    """V0.7.1 修订: 从知识库 FTS5 + 关键词加权 检索 top-K chunks

    Returns: [{title, path, content, snippet}, ...]

    修订点 (相对 V0.5):
    - 删死代码 (旧 LIKE 分支和冗余 except)
    - 修 Session 泄漏 (用 with, 一次连接拿全)
    - seen_ids 统一用 chunk id (之前 FTS 跟 LIKE 混用 chunk id 跟 doc id)
    - FTS 命中后用 IN(...) 一次查, 避免 N+1
    - 训练学关键词白名单加权 (FTP / TSS / 周期化 等)
    - 中文停用词过滤
    """
    import re
    from sqlalchemy import text as _sql_text, or_ as _or
    from cycling_coach.data.sqlite import engine as _engine
    from cycling_coach.data.sqlite.models import KbChunk, KbDocument
    from cycling_coach.data.sqlite.database import SessionLocal

    # 1) 关键词提取 + 训练学术语加权
    STOPWORDS = {"的", "了", "是", "在", "和", "与", "或", "及", "把", "给", "我", "你", "他", "她", "它", "这", "那", "吗", "啊", "呢", "吧"}
    CYCLING_KEYWORDS = {
        # 中文 (权重 1.5x)
        "ftp": 1.5, "tss": 1.5, "np": 1.5, "if": 1.5, "ctl": 1.5, "atl": 1.5, "tsb": 1.5,
        "功率": 1.5, "心率": 1.5, "踏频": 1.5, "海拔": 1.5, "爬坡": 1.5, "冲刺": 1.5,
        "间歇": 1.5, "恢复": 1.3, "减量": 1.3, "taper": 1.3, "基础期": 1.3, "强化期": 1.3,
        "巅峰": 1.3, "周期化": 1.5, "阈值": 1.5, "无氧": 1.3, "有氧": 1.3, "配速": 1.3,
        "v02": 1.5, "wbal": 1.5, "w'": 1.5, "decoupling": 1.5, "acwr": 1.5, "rpe": 1.5,
    }
    terms_with_weight: list[tuple[str, float]] = []
    seen_t: set[str] = set()

    # 英文/数字 单词 (≥2 字符)
    for w in re.findall(r'[A-Za-z][A-Za-z0-9_]+', user_message):
        wl = w.lower()
        if len(wl) >= 2 and wl not in seen_t:
            seen_t.add(wl)
            terms_with_weight.append((wl, CYCLING_KEYWORDS.get(wl, 1.0)))

    # 中文整词 (≥2 字符) + 2-gram
    for s in re.findall(r'[\u4e00-\u9fff]+', user_message):
        if len(s) >= 2 and s not in STOPWORDS and s not in seen_t:
            seen_t.add(s)
            terms_with_weight.append((s, CYCLING_KEYWORDS.get(s, 1.0)))
        for i in range(len(s) - 1):
            g = s[i:i+2]
            if g not in STOPWORDS and g not in seen_t:
                seen_t.add(g)
                terms_with_weight.append((g, CYCLING_KEYWORDS.get(g, 0.8)))

    # 取权重 top-8
    terms_with_weight.sort(key=lambda x: x[1], reverse=True)
    terms = [t for t, _ in terms_with_weight[:8]]
    if not terms:
        return []

    # 2) FTS5 全文索引 (快, 有 rank)
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

    # 3) 一次 IN 查询拿全部 chunk + doc (避免 N+1)
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

    # 4) LIKE 模糊匹配兜底 (单 session 拿全)
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

    # 5) 合并去重: seen_ids 统一用 chunk id (KChunk.id)
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
        athlete_exp = getattr(athlete, "experience", None) or "未填"
        athlete_max_hr = athlete.max_hr
        athlete_lthr = athlete.lthr
        athlete_ftp = athlete.ftp
        try:
            pmc = get_pmc_today(db, athlete.id)
        except Exception as e:
            logger.warning(f"PMC 读取失败(降级为空): {e}")
            pmc = None

        # V0.7.1 补遗漏: 注入 ACWR + RPE 7d + 当前周期 + 最新 FTP
        try:
            from cycling_coach.core.metrics.acwr import get_acwr_overview
            acwr = get_acwr_overview(db, days=90)
        except Exception as e:
            logger.debug(f"ACWR 读取失败: {e}")
            acwr = None

        try:
            from sqlalchemy import desc
            from datetime import timedelta
            from cycling_coach.data.sqlite.models import Activity, TrainingPhase, FTPTest
            now = datetime.utcnow()
            cutoff_7d = now - timedelta(days=7)
            rpe_acts = (
                db.query(Activity)
                .filter(Activity.athlete_id == athlete.id)
                .filter(Activity.start_time >= cutoff_7d)
                .filter(Activity.rpe.isnot(None))
                .all()
            )
            if rpe_acts:
                rpe_avg = round(sum(a.rpe for a in rpe_acts) / len(rpe_acts), 1)
                rpe_high = sum(1 for a in rpe_acts if a.rpe >= 7)
                rpe_7d = {
                    "avg": rpe_avg,
                    "count": len(rpe_acts),
                    "high_count": rpe_high,
                    "days": sorted({a.start_time.date().isoformat() for a in rpe_acts})[-7:],
                }
            else:
                rpe_7d = None
        except Exception as e:
            logger.debug(f"RPE 7d 读取失败: {e}")
            rpe_7d = None

        try:
            from cycling_coach.core.metrics.periodization import derive_phase
            current_phase_info = derive_phase(db, athlete.id)
        except Exception as e:
            logger.debug(f"周期 读取失败: {e}")
            current_phase_info = None

        try:
            latest_ftp = (
                db.query(FTPTest)
                .filter(FTPTest.athlete_id == athlete.id)
                .order_by(desc(FTPTest.test_date))
                .first()
            )
            ftp_info = {
                "ftp_w": latest_ftp.ftp_w if latest_ftp else athlete_ftp,
                "test_date": latest_ftp.test_date.date().isoformat() if latest_ftp else None,
                "method": latest_ftp.method if latest_ftp else "默认",
            } if (latest_ftp or athlete_ftp) else None
        except Exception as e:
            logger.debug(f"FTP 读取失败: {e}")
            ftp_info = None
    finally:
        db.close()

    # V0.5: RAG 检索知识库
    retrieved = _retrieve_kb(user_message, top_k=3)
    kb_block = _format_kb_block(retrieved)

    system, messages = build_chat_messages(
        history, user_message,
        athlete_name=athlete_name,
        athlete_exp=athlete_exp,
        athlete_max_hr=athlete_max_hr,
        athlete_lthr=athlete_lthr,
        athlete_ftp=athlete_ftp,
        athlete_pmc=pmc,
        athlete_acwr=acwr,
        athlete_rpe_7d=rpe_7d,
        athlete_phase=current_phase_info,
        athlete_ftp_info=ftp_info,
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
