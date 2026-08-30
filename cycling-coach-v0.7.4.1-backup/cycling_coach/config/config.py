"""Cycling Coach 后端配置

参考 Photographer-Copilot 风格:集中 .env 配置 + 友好 mock 兜底
"""
from __future__ import annotations
import os
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # LLM(OpenRouter 兼容协议)
    m3_base_url: str = "https://openrouter.ai/api/v1"
    m3_api_key: Optional[str] = None
    m3_model: str = "minimax/minimax-m3"

    # 后端
    backend_host: str = "127.0.0.1"
    backend_port: int = 8765
    log_level: str = "INFO"

    # 前端(用于 CORS)
    frontend_port: int = 1420
    cors_origins: str = "http://localhost:1420,http://127.0.0.1:1420"

    # Workspace(相对于 backend 父目录,即启动器 cwd=ROOT)
    workspace_dir: str = "workspace"

    # 桌面应用模式 (PyInstaller 打包时 True)
    is_desktop: bool = False
    # 静态前端目录 (PyInstaller 打包时指向 _MEIPASS/frontend)
    static_dir: str = ""

    # V0.7.1: 开发模式 (True = 启用 dev router, False = 生产环境不挂载危险端点)
    # 默认 False: dev router 含 generate-mock / repair-db, 生产应关闭
    dev_mode: bool = False

    # 训练百科下载源 (首次启动从 URL 拉, 存到 ~/.cycling-coach/kb/)
    kb_download_url: str = ""  # 空表示内嵌导入 (开发模式)
    kb_zip_name: str = "kb-panzhen-v1.zip"

    @property
    def is_mock(self) -> bool:
        """没有 API key 时进入 mock 模式(对齐 P 项目)"""
        return not self.m3_api_key or not self.m3_api_key.strip()

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
