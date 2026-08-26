"""Cycling Coach 后端入口

参考 Photographer-Copilot main.py 风格:
- FastAPI lifespan
- CORS
- /api/diagnose
- 所有日志走 setup_logging
- 桌面模式 (PyInstaller): mount 静态前端 + SPA fallback
"""
from __future__ import annotations
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse

from cycling_coach.config.config import settings
from cycling_coach.config.logging import setup_logging
from cycling_coach.data.sqlite import init_db
from .routers import activities, athlete, dashboard, diagnose, dev, coach, pmc, plans, calendar, workouts, kb, trends, phases, ftp, insights
from .routers.frontend import mount_frontend


WORKSPACE = Path(settings.workspace_dir).resolve()
LOG_FILE = WORKSPACE / ".logs" / "sidecar.log"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时:配日志 + 建表"""
    setup_logging(settings.log_level, LOG_FILE)
    logger = logging.getLogger("cycling_coach.api.main")
    logger.info("=" * 50)
    logger.info(f"Cycling Coach Sidecar v{'0.5.1' if settings.is_desktop else '0.5.0'} 启动")
    logger.info(f"Mock 模式: {settings.is_mock}")
    if not settings.is_mock:
        logger.info(f"M3 model: {settings.m3_model}")
    logger.info(f"Workspace: {WORKSPACE}")
    if settings.is_desktop:
        logger.info(f"Static dir: {settings.static_dir}")
    init_db()
    # V0.5: 知识库自动导入(若未导入) + 每次启动检查 FTS5 表是否存在
    # V0.5.1: 桌面模式先从 URL 下载到 ~/.cycling-coach/kb/
    try:
        from cycling_coach.core.kb_importer import get_import_status, import_knowledge_base
        from sqlalchemy import text
        from cycling_coach.data.sqlite import engine as _db_engine
        st = get_import_status()
        if not st["imported"]:
            logger.info("知识库未导入, 开始首次导入...")
            # 桌面模式: 先下载
            kb_root = None
            kb_attach = None
            if settings.is_desktop and settings.kb_download_url:
                from cycling_coach.core.kb_downloader import (
                    download_kb, kb_extracted_dir, is_kb_installed
                )
                if is_kb_installed():
                    logger.info(f"训练百科已安装: {kb_extracted_dir()}")
                else:
                    def _on_progress(d: int, t: int) -> None:
                        if t > 0:
                            pct = d * 100 // t
                            logger.info(f"下载训练百科: {d // 1024}KB / {t // 1024}KB ({pct}%)")
                    extracted = download_kb(progress_cb=_on_progress)
                    kb_root = extracted / "markdown"
                    kb_attach = extracted / "attachments"
            info = import_knowledge_base(kb_root=kb_root, attach_dir=kb_attach)
            logger.info(f"知识库导入完成: docs={info.get('documents')}, chunks={info.get('chunks')}, atts={info.get('attachments')}")
        else:
            logger.info(f"知识库已导入: cats={st['categories']} docs={st['documents']} chunks={st['chunks']} atts={st['attachments']}")
            # 检查 FTS5 虚拟表是否存在(可能在旧 db 中缺失)
            with _db_engine.connect() as conn:
                r = conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='kb_chunks_fts'"))
                has_fts = r.first() is not None
            if not has_fts and st.get("chunks", 0) > 0:
                logger.warning("kb_chunks_fts 缺失, 重建中...")
                from cycling_coach.core.kb_importer import _setup_fts
                _setup_fts(_db_engine)
                logger.info("kb_chunks_fts 重建完成")
    except Exception as e:
        logger.warning(f"知识库自动导入跳过: {e}")
    logger.info("=" * 50)
    # V0.5.1 桌面模式: 挂载前端静态资源 (此时 settings.static_dir 已就绪)
    try:
        mount_frontend(app)
    except Exception as e:
        logger.warning(f"前端静态资源挂载失败: {e}")
    yield
    logger.info("Sidecar 关闭")


app = FastAPI(
    title="Cycling Coach API",
    description="公路自行车 AI 教练 · 后端",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(activities.router)
app.include_router(athlete.router)
app.include_router(dashboard.router)
app.include_router(diagnose.router)
app.include_router(dev.router)
app.include_router(coach.router)
app.include_router(pmc.router)
app.include_router(plans.router)
app.include_router(calendar.router)
app.include_router(workouts.router)
app.include_router(kb.router)
app.include_router(trends.router)
app.include_router(phases.router)
app.include_router(ftp.router)
app.include_router(insights.router)
