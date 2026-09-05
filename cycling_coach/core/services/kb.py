"""V0.8.0: 知识库 (KB) 业务层

覆盖端点 (kb.py 的全部):
- GET    /api/kb/categories
- GET    /api/kb/documents
- GET    /api/kb/documents/{id}
- GET    /api/kb/by-path
- GET    /api/kb/search
- GET    /api/kb/attachments
- GET    /api/kb/attachments/by-name/{filename}
- GET    /api/kb/attachments/{att_id}/image
- PATCH  /api/kb/attachments/{att_id}
- GET    /api/kb/stats
- POST   /api/kb/reimport
- GET    /api/kb/import-status

文件流 (image/by-name) 走 service.get_attachment_file() 返回 Path, 由 router 转 FileResponse
"""
from __future__ import annotations
import logging
import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from cycling_coach.config.config import settings
from cycling_coach.core.exceptions import NotFoundError, ForbiddenError
from cycling_coach.core.kb_importer import (
    import_knowledge_base, get_import_status,
)
from cycling_coach.data.sqlite.models import (
    KbCategory, KbDocument, KbChunk, KbAttachment, KbDocAttachment,
)

logger = logging.getLogger(__name__)


# ============== DTO ==============

class AttachmentPatch(BaseModel):
    is_visible: Optional[bool] = None
    is_likely_decoration: Optional[bool] = None


# ============== 路径校验 ==============

_KB_ATTACH_BASE = None
def _get_attach_base() -> Path:
    """懒加载 KB 附件根目录"""
    global _KB_ATTACH_BASE
    if _KB_ATTACH_BASE is None:
        _KB_ATTACH_BASE = Path(settings.workspace_dir).resolve() / "kb_attachments"
    return _KB_ATTACH_BASE


def _assert_safe_path(fp: Path) -> Path:
    """断言附件路径在 KB 附件根目录内, 防止越界读文件"""
    base = _get_attach_base()
    resolved = fp.resolve()
    try:
        resolved.relative_to(base)
    except ValueError:
        logger.error(f"KB 附件路径越界: {fp} (resolve={resolved}, base={base})")
        raise ForbiddenError(f"附件路径不安全: {fp.name}")
    return resolved


# ============== Service ==============

class KBService:
    """知识库业务服务"""
    def __init__(self, db: Session):
        self.db = db

    # ---------- 分类树 ----------

    def list_categories(self) -> dict:
        cats = self.db.query(KbCategory).order_by(KbCategory.path).all()
        items = [
            {
                "id": c.id,
                "code": c.code,
                "name": c.name,
                "parent_code": c.parent_code,
                "path": c.path,
                "depth": c.depth,
                "doc_count": c.doc_count,
            }
            for c in cats
        ]
        return {"categories": items, "total": len(items)}

    # ---------- 文档 ----------

    def list_documents(
        self,
        path: Optional[str] = None,
        category_code: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        q = self.db.query(KbDocument)
        if path:
            q = q.filter(KbDocument.path.like(path + "/%"))
        if category_code:
            q = q.filter(KbDocument.category_code == category_code)
        total = q.count()
        docs = q.order_by(KbDocument.path).offset(offset).limit(limit).all()
        return {
            "documents": [
                {
                    "id": d.id,
                    "path": d.path,
                    "title": d.title,
                    "depth": d.depth,
                    "parent_path": d.parent_path,
                    "chunk_count": d.chunk_count,
                    "attachment_count": d.attachment_count,
                }
                for d in docs
            ],
            "total": total,
        }

    def get_document(self, doc_id: int, include_md: bool = True) -> dict:
        d = self.db.get(KbDocument, doc_id)
        if not d:
            raise NotFoundError("文档不存在")
        atts = (
            self.db.query(KbAttachment, KbDocAttachment)
            .join(KbDocAttachment, KbDocAttachment.attachment_id == KbAttachment.id)
            .filter(
                KbDocAttachment.document_id == doc_id,
                KbAttachment.is_visible == True,
            )
            .all()
        )
        attachments = [
            {
                "id": att.id,
                "filename": att.filename,
                "alt_text": da.alt_text,
                "mime_type": att.mime_type,
                "size_bytes": att.size_bytes,
                "is_likely_decoration": att.is_likely_decoration,
                "image_url": f"/api/kb/attachments/{att.id}/image",
            }
            for att, da in atts
        ]
        return {
            "id": d.id,
            "path": d.path,
            "title": d.title,
            "depth": d.depth,
            "parent_path": d.parent_path,
            "category_code": d.category_code,
            "content_md": d.content_md if include_md else None,
            "content_text": d.content_text,
            "chunk_count": d.chunk_count,
            "attachment_count": d.attachment_count,
            "attachments": attachments,
        }

    def get_document_by_path(self, path: str) -> dict:
        d = self.db.query(KbDocument).filter(KbDocument.path == path).first()
        if not d:
            raise NotFoundError(f"文档不存在: {path}")
        return self.get_document(d.id)

    # ---------- 搜索 ----------

    def search(self, q: str, limit: int = 20) -> dict:
        """FTS5 全文搜索"""
        if not q.strip():
            return {"results": [], "total": 0}

        fts_query = " ".join([f'"{term}"*' for term in q.split() if term])
        try:
            rows = self.db.execute(
                text("""
                    SELECT
                        rowid,
                        snippet(kb_chunks_fts, 0, '<mark>', '</mark>', '...', 32) as snippet,
                        rank
                    FROM kb_chunks_fts
                    WHERE kb_chunks_fts MATCH :q
                    ORDER BY rank
                    LIMIT :lim
                """),
                {"q": fts_query, "lim": limit},
            ).fetchall()
        except Exception as e:
            logger.warning(f"FTS 搜索失败: {e}")
            return {"results": [], "total": 0, "error": str(e)}

        chunk_ids = [r[0] for r in rows]
        snippet_map = {r[0]: r[1] for r in rows}
        chunks = (
            self.db.query(KbChunk, KbDocument)
            .join(KbDocument, KbDocument.id == KbChunk.document_id)
            .filter(KbChunk.id.in_(chunk_ids))
            .all()
            if chunk_ids else []
        )
        results = []
        for c, d in chunks:
            results.append({
                "chunk_id": c.id,
                "document_id": d.id,
                "document_path": d.path,
                "document_title": d.title,
                "chunk_index": c.chunk_index,
                "snippet": snippet_map.get(c.id, c.content[:160]),
                "content": c.content,
            })
        return {"results": results, "total": len(results), "query": q}

    # ---------- 附件 ----------

    def get_attachment_file(self, att_id: int) -> tuple[Path, str, str]:
        """返回 (file_path, media_type, filename), router 包装 FileResponse"""
        att = self.db.get(KbAttachment, att_id)
        if not att:
            raise NotFoundError("附件不存在")
        if not att.is_visible:
            raise ForbiddenError("附件已隐藏(用户审核)")
        fp = Path(att.file_path)
        fp = _assert_safe_path(fp)
        if not fp.exists():
            raise NotFoundError("文件丢失")
        return fp, att.mime_type or "application/octet-stream", att.filename

    def get_attachment_by_name(self, filename: str) -> tuple[Path, str, str]:
        att = self.db.query(KbAttachment).filter(KbAttachment.filename == filename).first()
        if not att:
            raise NotFoundError(f"附件不存在: {filename}")
        if not att.is_visible:
            raise ForbiddenError("附件已隐藏(用户审核)")
        fp = Path(att.file_path)
        fp = _assert_safe_path(fp)
        if not fp.exists():
            raise NotFoundError("文件丢失")
        return fp, att.mime_type or "application/octet-stream", att.filename

    def patch_attachment(self, att_id: int, payload: AttachmentPatch) -> dict:
        att = self.db.get(KbAttachment, att_id)
        if not att:
            raise NotFoundError("附件不存在")
        if payload.is_visible is not None:
            att.is_visible = payload.is_visible
        if payload.is_likely_decoration is not None:
            att.is_likely_decoration = payload.is_likely_decoration
        self.db.commit()
        return {
            "id": att.id,
            "filename": att.filename,
            "is_visible": att.is_visible,
            "is_likely_decoration": att.is_likely_decoration,
        }

    def list_attachments(
        self,
        is_visible: Optional[bool] = None,
        is_likely_decoration: Optional[bool] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        q = self.db.query(KbAttachment)
        if is_visible is not None:
            q = q.filter(KbAttachment.is_visible == is_visible)
        if is_likely_decoration is not None:
            q = q.filter(KbAttachment.is_likely_decoration == is_likely_decoration)
        total = q.count()
        atts = (
            q.order_by(KbAttachment.use_count.desc(), KbAttachment.size_bytes.desc())
            .offset(offset).limit(limit).all()
        )
        return {
            "attachments": [
                {
                    "id": a.id,
                    "filename": a.filename,
                    "mime_type": a.mime_type,
                    "size_bytes": a.size_bytes,
                    "use_count": a.use_count,
                    "is_visible": a.is_visible,
                    "is_likely_decoration": a.is_likely_decoration,
                    "image_url": f"/api/kb/attachments/{a.id}/image",
                }
                for a in atts
            ],
            "total": total,
        }

    # ---------- 统计 + 导入 ----------

    def stats(self) -> dict:
        cat = self.db.query(KbCategory).count()
        doc = self.db.query(KbDocument).count()
        chunk = self.db.query(KbChunk).count()
        att = self.db.query(KbAttachment).count()
        att_visible = self.db.query(KbAttachment).filter(KbAttachment.is_visible == True).count()
        att_dec = self.db.query(KbAttachment).filter(KbAttachment.is_likely_decoration == True).count()
        return {
            "categories": cat,
            "documents": doc,
            "chunks": chunk,
            "attachments": att,
            "attachments_visible": att_visible,
            "attachments_likely_decoration": att_dec,
        }

    def reimport(self) -> dict:
        try:
            info = import_knowledge_base()
            return {"ok": True, "info": info}
        except Exception as e:
            logger.exception("reimport failed")
            from cycling_coach.core.exceptions import BusinessError
            raise BusinessError(f"导入失败: {e}", code="import_failed", status=500)

    def import_status(self) -> dict:
        return get_import_status()
