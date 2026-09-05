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

from fastapi import FastAPI, Request
from cycling_coach import __version__
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from cycling_coach.config.config import settings
from cycling_coach.config.logging import setup_logging
from cycling_coach.core.exceptions import AppError
from cycling_coach.data.sqlite import init_db
from .routers import activities, athlete, dashboard, diagnose, dev, coach, pmc, plans, calendar, workouts, kb, trends, phases, ftp, insights, race_prep, hrv, recommendations, reports, sync, diary, race_tactics
from .routers.chat import router as chat_router  # V0.7.6 通用 chat 持久化
from .routers.ml import router as ml_router  # V0.7.6 ML 推理端点
from .routers.frontend import mount_frontend


WORKSPACE = Path(settings.workspace_dir).resolve()
LOG_FILE = WORKSPACE / ".logs" / "sidecar.log"

# V0.7.4 fix: logger 提前到模块级 (dev_mode 警告在 lifespan 外)
_logger = logging.getLogger("cycling_coach.api.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时:配日志 + 建表"""
    setup_logging(settings.log_level, LOG_FILE)
    logger = _logger
    logger.info("=" * 50)
    logger.info(f"Cycling Coach Sidecar v{__version__} 启动 (desktop={settings.is_desktop})")
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
        # V0.7.5.7 A-14: 用户首启失败时, 给出明确提示
        logger.warning(f"知识库自动导入失败: {e}", exc_info=False)
        # 把"知识库缺失"状态暴露到 /api/diagnose, 前端可查
        _KB_IMPORT_ERROR = str(e)
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
    version=__version__,
    lifespan=lifespan,
)


# V0.8.0: 统一 AppError handler
# 业务异常 (NotFoundError / ValidationError / ...) 在 service 层抛,
# handler 自动转 JSON 响应 {ok: false, code, message, ...}
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status,
        content=exc.to_dict(),
    )


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# V0.7.5.3 DEV-3: 上传文件大小限制 (DoS 防护)
class FileSizeLimitMiddleware(BaseHTTPMiddleware):
    """限制 /api/*/upload 端点上传文件大小, 防止 DoS
    
    FIT/TCX 高采样率 1h 文件 5-20MB, 8h Gran Fondo 30-80MB, 50MB 限制足够.
    50MB = 52428800 bytes
    """
    MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB
    
    async def dispatch(self, request, call_next):
        if request.method == "POST" and "/upload" in request.url.path:
            cl = request.headers.get("content-length")
            if cl and cl.isdigit() and int(cl) > self.MAX_UPLOAD_SIZE:
                size_mb = int(cl) / 1024 / 1024
                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": f"文件过大 ({size_mb:.1f}MB), 限制 50MB. "
                                  f"如需更大, 请编辑 cycling_coach/api/main.py 的 MAX_UPLOAD_SIZE"
                    }
                )
        return await call_next(request)


app.add_middleware(FileSizeLimitMiddleware)

app.include_router(activities.router)
app.include_router(athlete.router)
app.include_router(dashboard.router)
app.include_router(diagnose.router)
# V0.7.1: dev router 仅在 dev_mode=True 时挂载 (含 generate-mock / repair-db, 生产应关闭)
if settings.dev_mode:
    app.include_router(dev.router)
    _logger.warning("Dev mode ON — dev router 已挂载 (含 generate-mock / repair-db)")
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
app.include_router(race_prep.router)
app.include_router(hrv.router)
app.include_router(recommendations.router)
app.include_router(reports.router)
app.include_router(sync.router)
app.include_router(diary.router)
app.include_router(race_tactics.router)
# V0.7.6: 通用 chat 持久化 (chat_sessions / chat_messages / 思维树)
app.include_router(chat_router)
# V0.7.6: ML 推理端点 (FTP 预测 + 模型注册/激活)
app.include_router(ml_router)


# ---------- 版本号端点 (前端 SSOT) ----------
@app.get("/api/version", tags=["meta"])
def get_version():
    """返回后端版本号 (前端从 pyproject.toml 单一真相源读)"""
    from cycling_coach import __version__
    return {
        "version": __version__,
        "service": "cycling-coach-backend",
        "name": "Cycling Coach",
    }
