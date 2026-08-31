"""知识库导入器

走 /workspace/kb_final/markdown/ 目录, 解析分类 + 文档 + 附件 + 切片 + FTS5
跑一次即可(V0.5 启动时若 import_status=False 自动跑)

V0.5 设计:
- chunk_size: 默认 500 字一段, 中间按段落切(避免切碎句子)
- attachment 启发式: < 30KB 或 width/height < 100 标记 is_likely_decoration
"""
from __future__ import annotations
import logging
import os
import re
from pathlib import Path
from typing import Optional

import yaml
from sqlalchemy import text
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite import engine
from cycling_coach.data.sqlite.models import (
    KbCategory, KbDocument, KbChunk, KbAttachment, KbDocAttachment
)

logger = logging.getLogger(__name__)

# 数据源根目录(V0.5 - 资料源打包在项目内 kb_source/)
# 兼容两种: 项目内 (推荐) 或沙箱硬路径 (开发)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PROJECT_KB = _PROJECT_ROOT / "kb_source" / "markdown"
_PROJECT_ATTACH = _PROJECT_ROOT / "kb_source" / "attachments"
_DEV_KB = Path("/workspace/kb_final/markdown")
_DEV_ATTACH = Path("/workspace/kb_final/attachments")

KB_ROOT = _PROJECT_KB if _PROJECT_KB.exists() else _DEV_KB
KB_ATTACH_DIR = _PROJECT_ATTACH if _PROJECT_ATTACH.exists() else _DEV_ATTACH

logger.info(f"知识库数据源: KB_ROOT={KB_ROOT}, KB_ATTACH_DIR={KB_ATTACH_DIR}")

# chunk 切分参数
CHUNK_TARGET_CHARS = 500       # 目标每段 ~500 字
CHUNK_MAX_CHARS = 1500         # 单段上限(超过强制切)
CHUNK_OVERLAP_CHARS = 80       # 段间重叠(避免切断上下文)

# 附件启发式阈值
ATTACH_MIN_SIZE_FOR_CONTENT = 30 * 1024  # 30KB 以下可能是 UI 装饰
ATTACH_MIN_DIMENSION = 100               # 宽高 < 100px 可能是 icon


# ---------- helpers ----------

def _category_code(name: str) -> str:
    """把分类名转成稳定 code: 去 emoji/标点/后缀 uuid"""
    s = re.sub(r"__[0-9a-f]{8}.*$", "", name)  # 去 __uuid 后缀
    s = re.sub(r"[^\w\u4e00-\u9fff]+", "_", s).strip("_")
    return s[:64] or "unknown"


def _title_clean(name: str) -> str:
    """从目录/文件名提取可读标题"""
    s = re.sub(r"__[0-9a-f]{8}.*$", "", name)
    s = re.sub(r"^[\d.]+\s*", "", s)
    s = s.replace("_", " ").strip()
    return s or name


def _extract_md_text(md: str) -> str:
    """把 markdown 转纯文本(去掉语法符号, 保留段落分隔)"""
    s = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", md)  # 图片
    s = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", s)  # 链接
    s = re.sub(r"```[\s\S]*?```", " ", s)  # 代码块
    s = re.sub(r"`[^`]+`", " ", s)  # 行内代码
    s = re.sub(r"^#+\s+", "", s, flags=re.MULTILINE)  # 标题
    s = re.sub(r"[*_~]+", "", s)  # 强调
    # 关键: 保留段落分隔(\n\n), 只压同行内连续空白
    s = re.sub(r"[ \t]+", " ", s)  # 同行多个空格/tab 压成单空格
    s = re.sub(r" *\n *", "\n", s)  # 行尾空格去掉
    s = re.sub(r"\n{3,}", "\n\n", s)  # 多空行压成 1 个空行
    return s.strip()


def _chunk_text(text: str) -> list[str]:
    """按段落切 chunk, 目标 ~500 字, 段间 80 字重叠"""
    if not text.strip():
        return []
    if len(text) <= CHUNK_MAX_CHARS:
        return [text.strip()]

    # 按段落(双换行)切
    paragraphs = re.split(r"\n\s*\n", text)
    chunks: list[str] = []
    cur = ""
    for p in paragraphs:
        p = p.strip()
        if not p:
            continue
        if not cur:
            cur = p
        elif len(cur) + len(p) + 2 <= CHUNK_TARGET_CHARS:
            cur = cur + "\n\n" + p
        else:
            chunks.append(cur)
            # 段间重叠: 取 cur 末尾 80 字
            overlap = cur[-CHUNK_OVERLAP_CHARS:] if len(cur) > CHUNK_OVERLAP_CHARS else cur
            cur = overlap + "\n\n" + p
    if cur:
        chunks.append(cur)
    return chunks


def _extract_attachments(md: str, doc_dir: Path) -> list[tuple[str, str]]:
    """从 markdown 提取 attachments 引用, 返回 [(filename, alt_text), ...]"""
    refs: list[tuple[str, str]] = []
    for m in re.finditer(r"!\[([^\]]*)\]\((attachments/[^)]+)\)", md):
        alt = m.group(1).strip()
        path = m.group(2)
        # path 是 attachments/xxx.png
        # doc_dir 是 _content.md 所在目录
        # 实际附件在 /workspace/kb_final/attachments/xxx.png (Part 1) 或子目录(Part 2)
        # 简单做法: 先去 /workspace/kb_final/attachments/ 直接找
        filename = os.path.basename(path)
        refs.append((filename, alt))
    return refs


def _detect_decoration(filepath: Path) -> bool:
    """启发式: < 30KB 或尺寸 < 100x100 视为可疑装饰"""
    try:
        size = filepath.stat().st_size
        if size < ATTACH_MIN_SIZE_FOR_CONTENT:
            return True
    except OSError:
        return True
    # 尝试读 PNG/JPG 尺寸
    try:
        with open(filepath, "rb") as f:
            head = f.read(32)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            w = int.from_bytes(head[16:20], "big")
            h = int.from_bytes(head[20:24], "big")
            if w < ATTACH_MIN_DIMENSION or h < ATTACH_MIN_DIMENSION:
                return True
        elif head[:2] == b"\xff\xd8":
            # JPEG: 找 SOF marker
            with open(filepath, "rb") as f:
                data = f.read()
            i = 2
            while i < len(data) - 1:
                if data[i] != 0xff:
                    i += 1
                    continue
                marker = data[i + 1]
                if 0xc0 <= marker <= 0xcf and marker not in (0xc4, 0xc8, 0xcc):
                    h = int.from_bytes(data[i + 5:i + 7], "big")
                    w = int.from_bytes(data[i + 7:i + 9], "big")
                    if w < ATTACH_MIN_DIMENSION or h < ATTACH_MIN_DIMENSION:
                        return True
                    break
                i += 2 + int.from_bytes(data[i + 2:i + 4], "big")
    except Exception:
        pass
    return False


def _resolve_attachment(filename: str) -> Optional[Path]:
    """从 /workspace/kb_final/attachments 找附件(可能分布在子目录)"""
    if not KB_ATTACH_DIR.exists():
        return None
    direct = KB_ATTACH_DIR / filename
    if direct.exists():
        return direct
    # 全目录找
    matches = list(KB_ATTACH_DIR.rglob(filename))
    return matches[0] if matches else None


# ---------- main import ----------

def import_knowledge_base(kb_root: Optional[Path] = None, attach_dir: Optional[Path] = None) -> dict:
    """导入知识库(可重复跑, 增量)
    Args:
        kb_root: 知识库 markdown 根目录 (默认 KB_ROOT)
        attach_dir: 知识库附件目录 (默认 KB_ATTACH_DIR)
    """
    root = kb_root or KB_ROOT
    att = attach_dir or KB_ATTACH_DIR
    if not root.exists():
        return {"ok": False, "error": f"KB root not found: {root}"}

    stats = {
        "categories": 0,
        "documents": 0,
        "chunks": 0,
        "attachments": 0,
        "doc_attachments": 0,
        "likely_decoration": 0,
        "errors": [],
    }

    # 1. 先把附件入 db (按 filename 去重)
    filename_to_attach: dict[str, int] = {}
    with Session(engine) as s:
        existing = {a.filename: a.id for a in s.query(KbAttachment).all()}
    # V0.7.5.4 DEV-20: 整批事务 (252 附件 → 1 commit, 失败回滚)
    pending_attachments: list[KbAttachment] = []
    if att.exists():
        for fp in att.rglob("*"):
            if not fp.is_file():
                continue
            fname = fp.name
            if fname in filename_to_attach:
                continue
            if fname in existing:
                filename_to_attach[fname] = existing[fname]
                continue
            try:
                size = fp.stat().st_size
                is_dec = _detect_decoration(fp)
                mime = "image/png" if fp.suffix.lower() == ".png" else \
                       "image/jpeg" if fp.suffix.lower() in (".jpg", ".jpeg") else \
                       "image/gif" if fp.suffix.lower() == ".gif" else \
                       "application/pdf" if fp.suffix.lower() == ".pdf" else \
                       "application/octet-stream"
                pending_attachments.append(KbAttachment(
                    filename=fname,
                    file_path=str(fp),
                    mime_type=mime,
                    size_bytes=size,
                    is_likely_decoration=is_dec,
                    is_visible=not is_dec,
                ))
            except Exception as e:
                stats["errors"].append(f"attachment {fname}: {e}")
        # 整批 commit
        if pending_attachments:
            try:
                with Session(engine) as s:
                    s.add_all(pending_attachments)
                    s.commit()
                    for a in pending_attachments:
                        s.refresh(a)
                        filename_to_attach[a.filename] = a.id
                        stats["attachments"] += 1
                        if a.is_likely_decoration:
                            stats["likely_decoration"] += 1
                logger.info(f"附件批量入库: {len(pending_attachments)} 个")
            except Exception as e:
                # 整批失败, 回滚 (SQLAlchemy Session context 自动 rollback)
                logger.error(f"附件批量入库失败, 已回滚: {e}")
                stats["errors"].append(f"attachments batch: {e}")
    logger.info(f"附件导入: {stats['attachments']} 个 ({stats['likely_decoration']} 装饰)")

    # 2. 走 markdown 目录, 建分类树 + 文档
    with Session(engine) as s:
        # 清空旧 categories/documents/chunks (重导入)
        s.query(KbChunk).delete()
        s.query(KbDocAttachment).delete()
        s.query(KbDocument).delete()
        s.query(KbCategory).delete()
        s.commit()
    category_id_map: dict[str, int] = {}  # path -> id
    category_path_map: dict[str, dict] = {}  # path -> {code, name, depth}

    # 遍历所有分类根目录
    for root_dir in sorted(root.iterdir()):
        if not root_dir.is_dir():
            continue
        root_name = root_dir.name
        root_code = _category_code(root_name)
        root_display = _title_clean(root_name)

        # 写根分类
        with Session(engine) as s:
            c = KbCategory(
                code=root_code,
                name=root_display,
                parent_code=None,
                path=root_display,
                depth=0,
                sort_order=0,
            )
            s.add(c)
            s.commit()
            s.refresh(c)
            category_id_map[root_display] = c.id
            category_path_map[root_display] = {"code": root_code, "name": root_display, "depth": 0}
        stats["categories"] += 1

        # 走子目录递归
        _walk_dir(
            s=None,  # 不用传,内部新建
            dir_path=root_dir,
            parent_display=root_display,
            parent_code=root_code,
            category_id_map=category_id_map,
            category_path_map=category_path_map,
            filename_to_attach=filename_to_attach,
            stats=stats,
        )

    # 3. 统计 doc_count (精确匹配 + 前缀匹配)
    with Session(engine) as s:
        all_cats = s.query(KbCategory).all()
        all_docs = s.query(KbDocument).all()
        # 按 path 分组
        docs_by_path_prefix: dict[str, int] = {}
        for d in all_docs:
            docs_by_path_prefix[d.path] = docs_by_path_prefix.get(d.path, 0) + 1
        # 任何 path 命中的 doc 算它的所有祖先
        path_to_ancestors: dict[str, list[str]] = {}
        for d in all_docs:
            parts = d.path.split("/")
            for i in range(1, len(parts) + 1):
                anc = "/".join(parts[:i])
                path_to_ancestors.setdefault(anc, [])
                if anc not in path_to_ancestors[anc]:
                    path_to_ancestors[anc].append(anc)
        # 直接数: 文档 path == cat.path OR 文档 path 以 cat.path + "/" 开头
        for cat in all_cats:
            cnt = sum(1 for d in all_docs
                     if d.path == cat.path or d.path.startswith(cat.path + "/"))
            cat.doc_count = cnt
        s.commit()

    # 4. 创建 FTS5 虚拟表 + 索引
    _setup_fts(engine)

    logger.info(f"导入完成: {stats}")
    return stats


def _walk_dir(
    s, dir_path: Path, parent_display: str, parent_code: str,
    category_id_map: dict, category_path_map: dict,
    filename_to_attach: dict, stats: dict, depth: int = 1,
):
    """递归走目录 — 只在子目录实际包含文档或子分类时才建 category"""
    # 1. _content.md 在本目录
    content_md = dir_path / "_content.md"
    has_content = content_md.exists()
    if has_content:
        # 这是文章节点(目录本身就是一篇)
        _import_document(
            dir_path, content_md, parent_display, parent_code,
            category_id_map, filename_to_attach, stats, depth
        )

    # 2. 子目录
    children = sorted([d for d in dir_path.iterdir() if d.is_dir()])
    for child in children:
        child_name = child.name
        child_code = _category_code(child_name)
        child_display = _title_clean(child_name)
        child_path_display = f"{parent_display}/{child_display}"

        # 只在子目录"真有内容"时建 category
        # (即: 它本身有 _content.md OR 它有非空子目录)
        child_has_content = (child / "_content.md").exists()
        child_subdirs_with_content = []
        for sub in child.iterdir():
            if sub.is_dir() and _dir_has_any_content(sub):
                child_subdirs_with_content.append(sub)

        if not child_has_content and not child_subdirs_with_content:
            # 空目录, 跳过(不建 category)
            continue

        # 建分类节点
        with Session(engine) as sess:
            existing_cat = sess.query(KbCategory).filter(KbCategory.code == f"{parent_code}__{child_code}").first()
            if not existing_cat:
                c = KbCategory(
                    code=f"{parent_code}__{child_code}",
                    name=child_display,
                    parent_code=parent_code,
                    path=child_path_display,
                    depth=depth,
                    sort_order=0,
                )
                sess.add(c)
                sess.commit()
                sess.refresh(c)
                category_id_map[child_path_display] = c.id
            else:
                category_id_map[child_path_display] = existing_cat.id
        stats["categories"] += 1

        # 递归
        _walk_dir(
            None, child, child_path_display, f"{parent_code}__{child_code}",
            category_id_map, category_path_map, filename_to_attach, stats, depth + 1
        )


def _dir_has_any_content(d: Path) -> bool:
    """递归检查目录是否包含 _content.md 或有内容的子目录"""
    if (d / "_content.md").exists():
        return True
    for sub in d.iterdir():
        if sub.is_dir() and _dir_has_any_content(sub):
            return True
    return False


def _import_document(
    dir_path: Path, content_md: Path, parent_display: str, parent_code: str,
    category_id_map: dict, filename_to_attach: dict, stats: dict, depth: int,
):
    """导入一篇文档"""
    try:
        raw = content_md.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        stats["errors"].append(f"read {content_md}: {e}")
        return

    # 标题: 取 _content.md 第一行 # 标题 或 用目录名
    m = re.search(r"^#\s+(.+?)$", raw, re.MULTILINE)
    if m:
        title = m.group(1).strip()
        # 去掉 emoji 和特殊符号
        title = re.sub(r"^[^\w\u4e00-\u9fff]+", "", title)
    else:
        title = _title_clean(dir_path.name)

    # 路径 (避免 title 与 parent 末段重复)
    if parent_display.endswith(f"/{title}"):
        doc_path = parent_display
    else:
        doc_path = f"{parent_display}/{title}"

    # 提取纯文本 + 切片
    text = _extract_md_text(raw)
    chunks = _chunk_text(text)

    # 写文档
    with Session(engine) as sess:
        d = KbDocument(
            category_code=parent_code.split("__")[0],
            path=doc_path,
            title=title,
            depth=depth,
            parent_path=parent_display,
            content_md=raw,
            content_text=text,
            chunk_count=len(chunks),
        )
        sess.add(d)
        sess.commit()
        sess.refresh(d)
        doc_id = d.id
        stats["documents"] += 1

        # 写 chunks
        for i, ck in enumerate(chunks):
            ch = KbChunk(
                document_id=doc_id,
                chunk_index=i,
                content=ck,
                token_count=len(ck),  # 简化: 字符数 ~ token
            )
            sess.add(ch)
        sess.commit()
        stats["chunks"] += len(chunks)

        # 提取附件关联
        refs = _extract_attachments(raw, dir_path)
        seen_att = set()
        for fname, alt in refs:
            att_id = filename_to_attach.get(fname)
            if not att_id or att_id in seen_att:
                continue
            seen_att.add(att_id)
            da = KbDocAttachment(
                document_id=doc_id,
                attachment_id=att_id,
                alt_text=alt or None,
            )
            sess.add(da)
        sess.commit()
        # 更新附件 use_count
        for att_id in seen_att:
            att = sess.get(KbAttachment, att_id)
            if att:
                att.use_count += 1
        sess.commit()
        stats["doc_attachments"] += len(seen_att)

        # 更新 doc.attachment_count
        d.attachment_count = len(seen_att)
        sess.commit()


def _setup_fts(engine, full_rebuild: bool = False):
    """创建/更新 FTS5 虚拟表

    V0.7.5.3 DEV-16: 增量更新 (INSERT OR REPLACE), 避免 DROP TABLE 全量重建
    - full_rebuild=False (默认): 检测 kb_chunks_fts 是否存在, 增量同步
    - full_rebuild=True: 完全重建 (用户手动触发 / 升级时)
    """
    with engine.begin() as conn:
        # 检查表是否存在
        exists = conn.execute(text(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='kb_chunks_fts'"
        )).scalar()
        if not exists or full_rebuild:
            if exists and full_rebuild:
                conn.execute(text("DROP TABLE IF EXISTS kb_chunks_fts"))
                logger.info("FTS5 全量重建 (full_rebuild=True)")
            conn.execute(text("""
                CREATE VIRTUAL TABLE kb_chunks_fts USING fts5(
                    content,
                    title,
                    category_path,
                    tokenize = 'unicode61 remove_diacritics 2'
                )
            """))
            conn.execute(text("""
                INSERT INTO kb_chunks_fts(rowid, content, title, category_path)
                SELECT c.id, c.content, d.title, d.path
                FROM kb_chunks c
                JOIN kb_documents d ON d.id = c.document_id
            """))
            logger.info("FTS5 索引: 全量填充完成")
        else:
            inserted = conn.execute(text("""
                INSERT OR REPLACE INTO kb_chunks_fts(rowid, content, title, category_path)
                SELECT c.id, c.content, d.title, d.path
                FROM kb_chunks c
                JOIN kb_documents d ON d.id = c.document_id
            """)).rowcount
            deleted = conn.execute(text("""
                DELETE FROM kb_chunks_fts
                WHERE rowid NOT IN (SELECT id FROM kb_chunks)
            """)).rowcount
            logger.info(f"FTS5 增量: 插入/更新 {inserted} 行, 删除 {deleted} orphan")
    with engine.connect() as conn:
        cnt = conn.execute(text("SELECT COUNT(*) FROM kb_chunks_fts")).scalar()
    logger.info(f"FTS5 索引: {cnt} 行")
    return cnt



def get_import_status() -> dict:
    """看是否已经导入过"""
    with Session(engine) as s:
        cat_cnt = s.query(KbCategory).count()
        doc_cnt = s.query(KbDocument).count()
        chunk_cnt = s.query(KbChunk).count()
        att_cnt = s.query(KbAttachment).count()
    return {
        "imported": cat_cnt > 0 or doc_cnt > 0,
        "categories": cat_cnt,
        "documents": doc_cnt,
        "chunks": chunk_cnt,
        "attachments": att_cnt,
    }
