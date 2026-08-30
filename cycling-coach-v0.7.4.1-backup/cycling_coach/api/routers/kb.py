"""/api/kb - 知识库浏览/搜索/RAG

V0.5 设计:
- GET /api/kb/categories - 分类树
- GET /api/kb/documents/{id} - 文档详情 (markdown + 附件)
- GET /api/kb/by-path - 按 path 找
- GET /api/kb/search?q= - FTS5 搜索(返回 chunks + 文档)
- GET /api/kb/attachments/{id}/image - 图片流
- PATCH /api/kb/attachments/{id} - 改 is_visible (用户审核)
- GET /api/kb/stats - 总数
- POST /api/kb/reimport - 重新导入(开发)
"""
from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite import get_db
from cycling_coach.data.sqlite.models import (
    KbCategory, KbDocument, KbChunk, KbAttachment, KbDocAttachment
)
from cycling_coach.core.kb_importer import (
    import_knowledge_base, get_import_status
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kb", tags=["kb"])


# ---------- 分类树 ----------

@router.get("/categories")
def list_categories(db: Session = Depends(get_db)):
    """分类树(完整 9 分类 + 训练百科 10 章)"""
    cats = db.query(KbCategory).order_by(KbCategory.path).all()
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

@router.get("/documents")
def list_documents(
    path: Optional[str] = Query(None, description="父分类 path 前缀"),
    category_code: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列文档(按 path 前缀过滤)"""
    q = db.query(KbDocument)
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


@router.get("/documents/{doc_id}")
def get_document(
    doc_id: int,
    include_md: bool = Query(True, description="是否返回原始 markdown"),
    db: Session = Depends(get_db),
):
    """文档详情"""
    d = db.get(KbDocument, doc_id)
    if not d:
        raise HTTPException(404, "文档不存在")
    # 附件
    atts = db.query(KbAttachment, KbDocAttachment).join(
        KbDocAttachment, KbDocAttachment.attachment_id == KbAttachment.id
    ).filter(
        KbDocAttachment.document_id == doc_id,
        KbAttachment.is_visible == True,
    ).all()
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


@router.get("/by-path")
def get_document_by_path(
    path: str = Query(..., description="完整 path 例: 训练百科/1. 训练概述/训练的基本原则"),
    db: Session = Depends(get_db),
):
    """按 path 找文档"""
    d = db.query(KbDocument).filter(KbDocument.path == path).first()
    if not d:
        raise HTTPException(404, f"文档不存在: {path}")
    return get_document(d.id, db=db)


# ---------- 搜索 ----------

@router.get("/search")
def search(
    q: str = Query(..., min_length=1, description="搜索词"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """FTS5 全文搜索 - 返回匹配的 chunks + 所属文档

    中文按字分(unicode61),够用,未来可换 jieba
    V0.5: 同时支持 semantic 搜索(若 chunks 有 embedding)
    """
    if not q.strip():
        return {"results": [], "total": 0}

    # FTS5 搜索(用 prefix 匹配, 支持部分关键字)
    fts_query = " ".join([f'"{term}"*' for term in q.split() if term])
    try:
        rows = db.execute(text("""
            SELECT
                rowid,
                snippet(kb_chunks_fts, 0, '<mark>', '</mark>', '...', 32) as snippet,
                rank
            FROM kb_chunks_fts
            WHERE kb_chunks_fts MATCH :q
            ORDER BY rank
            LIMIT :lim
        """), {"q": fts_query, "lim": limit}).fetchall()
    except Exception as e:
        # FTS 语法问题
        logger.warning(f"FTS 搜索失败: {e}")
        return {"results": [], "total": 0, "error": str(e)}

    # 取对应 chunk + 文档
    chunk_ids = [r[0] for r in rows]
    snippet_map = {r[0]: r[1] for r in rows}
    chunks = db.query(KbChunk, KbDocument).join(
        KbDocument, KbDocument.id == KbChunk.document_id
    ).filter(KbChunk.id.in_(chunk_ids)).all() if chunk_ids else []

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
    return {
        "results": results,
        "total": len(results),
        "query": q,
    }


# ---------- 附件 ----------

@router.get("/attachments/by-name/{filename}")
def get_attachment_by_name(filename: str, db: Session = Depends(get_db)):
    """按 filename 找附件(markdown 里的 ![](attachments/xxx) 重写用)"""
    att = db.query(KbAttachment).filter(KbAttachment.filename == filename).first()
    if not att:
        raise HTTPException(404, f"附件不存在: {filename}")
    if not att.is_visible:
        raise HTTPException(403, "附件已隐藏(用户审核)")
    fp = Path(att.file_path)
    if not fp.exists():
        raise HTTPException(404, "文件丢失")
    return FileResponse(
        path=str(fp),
        media_type=att.mime_type or "application/octet-stream",
        filename=att.filename,
    )


@router.get("/attachments/{att_id}/image")
def get_attachment_image(att_id: int, db: Session = Depends(get_db)):
    """返回图片流(支持 Range)"""
    att = db.get(KbAttachment, att_id)
    if not att:
        raise HTTPException(404, "附件不存在")
    if not att.is_visible:
        raise HTTPException(403, "附件已隐藏(用户审核)")
    fp = Path(att.file_path)
    if not fp.exists():
        raise HTTPException(404, "文件丢失")
    return FileResponse(
        path=str(fp),
        media_type=att.mime_type or "application/octet-stream",
        filename=att.filename,
    )


class AttachmentPatch(BaseModel):
    is_visible: Optional[bool] = None
    is_likely_decoration: Optional[bool] = None


@router.patch("/attachments/{att_id}")
def patch_attachment(att_id: int, payload: AttachmentPatch, db: Session = Depends(get_db)):
    """用户审核切换可见性"""
    att = db.get(KbAttachment, att_id)
    if not att:
        raise HTTPException(404, "附件不存在")
    if payload.is_visible is not None:
        att.is_visible = payload.is_visible
    if payload.is_likely_decoration is not None:
        att.is_likely_decoration = payload.is_likely_decoration
    db.commit()
    return {
        "id": att.id,
        "filename": att.filename,
        "is_visible": att.is_visible,
        "is_likely_decoration": att.is_likely_decoration,
    }


@router.get("/attachments")
def list_attachments(
    is_visible: Optional[bool] = Query(None),
    is_likely_decoration: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """列附件(供审核界面)"""
    q = db.query(KbAttachment)
    if is_visible is not None:
        q = q.filter(KbAttachment.is_visible == is_visible)
    if is_likely_decoration is not None:
        q = q.filter(KbAttachment.is_likely_decoration == is_likely_decoration)
    total = q.count()
    atts = q.order_by(KbAttachment.use_count.desc(), KbAttachment.size_bytes.desc()).offset(offset).limit(limit).all()
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

@router.get("/stats")
def stats(db: Session = Depends(get_db)):
    """总数统计"""
    cat = db.query(KbCategory).count()
    doc = db.query(KbDocument).count()
    chunk = db.query(KbChunk).count()
    att = db.query(KbAttachment).count()
    att_visible = db.query(KbAttachment).filter(KbAttachment.is_visible == True).count()
    att_dec = db.query(KbAttachment).filter(KbAttachment.is_likely_decoration == True).count()
    return {
        "categories": cat,
        "documents": doc,
        "chunks": chunk,
        "attachments": att,
        "attachments_visible": att_visible,
        "attachments_likely_decoration": att_dec,
    }


@router.post("/reimport")
def reimport(db: Session = Depends(get_db)):
    """重新导入(开发用)"""
    try:
        info = import_knowledge_base()
        return {"ok": True, "info": info}
    except Exception as e:
        logger.exception("reimport failed")
        raise HTTPException(500, f"导入失败: {e}")


@router.get("/import-status")
def import_status(db: Session = Depends(get_db)):
    """检查是否已导入"""
    return get_import_status()
