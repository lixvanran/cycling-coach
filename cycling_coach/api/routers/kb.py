"""/api/kb - 知识库浏览/搜索/RAG

V0.8.0: 业务逻辑抽到 cycling_coach.core.services.KBService
        本文件只剩 router 端点 (薄)
        文件流端点 (image / by-name) 用 service.get_attachment_file() 拿 Path 再 FileResponse

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
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse

from cycling_coach.api.dependencies import Services, get_services
from cycling_coach.core.services.kb import AttachmentPatch

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/kb", tags=["kb"])


# ---------- 分类树 ----------

@router.get("/categories")
def list_categories(svc: Services = Depends(get_services)):
    """分类树(完整 9 分类 + 训练百科 10 章)"""
    return svc.kb.list_categories()


# ---------- 文档 ----------

@router.get("/documents")
def list_documents(
    path: Optional[str] = Query(None, description="父分类 path 前缀"),
    category_code: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    svc: Services = Depends(get_services),
):
    """列文档(按 path 前缀过滤)"""
    return svc.kb.list_documents(
        path=path, category_code=category_code, limit=limit, offset=offset,
    )


@router.get("/documents/{doc_id}")
def get_document(
    doc_id: int,
    include_md: bool = Query(True, description="是否返回原始 markdown"),
    svc: Services = Depends(get_services),
):
    """文档详情"""
    return svc.kb.get_document(doc_id, include_md=include_md)


@router.get("/by-path")
def get_document_by_path(
    path: str = Query(..., description="完整 path 例: 训练百科/1. 训练概述/训练的基本原则"),
    svc: Services = Depends(get_services),
):
    """按 path 找文档"""
    return svc.kb.get_document_by_path(path)


# ---------- 搜索 ----------

@router.get("/search")
def search(
    q: str = Query(..., min_length=1, description="搜索词"),
    limit: int = Query(20, ge=1, le=100),
    svc: Services = Depends(get_services),
):
    """FTS5 全文搜索 - 返回匹配的 chunks + 所属文档"""
    return svc.kb.search(q=q, limit=limit)


# ---------- 附件 ----------

@router.get("/attachments/by-name/{filename}")
def get_attachment_by_name(
    filename: str,
    svc: Services = Depends(get_services),
):
    """按 filename 找附件(markdown 里的 ![](attachments/xxx) 重写用)"""
    fp, media_type, fname = svc.kb.get_attachment_by_name(filename)
    return FileResponse(path=str(fp), media_type=media_type, filename=fname)


@router.get("/attachments/{att_id}/image")
def get_attachment_image(
    att_id: int,
    svc: Services = Depends(get_services),
):
    """返回图片流(支持 Range)"""
    fp, media_type, fname = svc.kb.get_attachment_file(att_id)
    return FileResponse(path=str(fp), media_type=media_type, filename=fname)


@router.patch("/attachments/{att_id}")
def patch_attachment(
    att_id: int,
    payload: AttachmentPatch,
    svc: Services = Depends(get_services),
):
    """用户审核切换可见性"""
    return svc.kb.patch_attachment(att_id, payload)


@router.get("/attachments")
def list_attachments(
    is_visible: Optional[bool] = Query(None),
    is_likely_decoration: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    svc: Services = Depends(get_services),
):
    """列附件(供审核界面)"""
    return svc.kb.list_attachments(
        is_visible=is_visible, is_likely_decoration=is_likely_decoration,
        limit=limit, offset=offset,
    )


# ---------- 统计 + 导入 ----------

@router.get("/stats")
def stats(svc: Services = Depends(get_services)):
    """总数统计"""
    return svc.kb.stats()


@router.post("/reimport")
def reimport(svc: Services = Depends(get_services)):
    """重新导入(开发用)"""
    return svc.kb.reimport()


@router.get("/import-status")
def import_status(svc: Services = Depends(get_services)):
    """检查是否已导入"""
    return svc.kb.import_status()
