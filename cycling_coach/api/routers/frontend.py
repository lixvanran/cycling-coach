"""前端静态资源挂载 (V0.5.1 桌面模式)

- dev 模式 (Vite 1420) 不挂载, 桌面模式 (PyInstaller) 自动挂载
- 在 lifespan 阶段才执行, 这样 settings.static_dir 已被 __main__ 设置好
"""
from __future__ import annotations
import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from cycling_coach.config.config import settings

logger = logging.getLogger("cycling_coach.api.routers.frontend")


def mount_frontend(app: FastAPI) -> None:
    """挂载前端静态资源 (桌面模式). idempotent.

    - GET /             -> index.html
    - GET /assets/*     -> 静态资源
    - GET /<other>      -> index.html (SPA fallback, 不抢 /api/*)
    """
    # 检查是否已经挂载过
    if any(getattr(r, "path", "") == "/" and getattr(r, "name", "") == "frontend_index" for r in app.routes):
        return

    static_dir = Path(settings.static_dir) if settings.static_dir else None
    if not static_dir or not static_dir.exists():
        logger.info(f"静态前端目录未配置或不存在: {static_dir} (dev 模式? Vite 走 1420)")
        return

    assets_dir = static_dir / "assets"
    if assets_dir.exists():
        # 注意: 重复 mount 同一个 path 会抛错, 先检查
        if not any(getattr(r, "path", "") == "/assets" for r in app.routes):
            app.mount("/assets", StaticFiles(directory=str(assets_dir)), name="assets")

    @app.get("/", name="frontend_index", include_in_schema=False)
    async def index():
        return FileResponse(str(static_dir / "index.html"))

    @app.get("/favicon.ico", name="frontend_favicon", include_in_schema=False)
    async def favicon():
        fav = static_dir / "favicon.ico"
        if fav.exists():
            return FileResponse(str(fav))
        return JSONResponse(status_code=204, content=None)

    @app.get("/{full_path:path}", name="frontend_spa_fallback", include_in_schema=False)
    async def spa_fallback(full_path: str):
        if full_path.startswith("api") or full_path.startswith("docs") or full_path.startswith("openapi"):
            return JSONResponse(status_code=404, content={"detail": "Not found"})
        candidate = static_dir / full_path
        if candidate.is_file():
            return FileResponse(str(candidate))
        idx = static_dir / "index.html"
        if idx.exists():
            return FileResponse(str(idx))
        return JSONResponse(status_code=404, content={"detail": "Not found"})

    logger.info(f"已挂载前端静态资源: {static_dir}")
