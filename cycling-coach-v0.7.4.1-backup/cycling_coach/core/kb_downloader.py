"""训练百科下载器 (V0.5.1 桌面模式)

- 检查 ~/.cycling-coach/kb/<kb_zip_name> 是否存在
- 不存在则从 settings.kb_download_url 下载
- 解压到 ~/.cycling-coach/kb/extracted/
- 后续 kb_importer 从 extracted/ 读 (而不是开发模式的 kb_source/)
"""
from __future__ import annotations
import hashlib
import logging
import os
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Callable, Optional

import httpx

from cycling_coach.config.config import settings

logger = logging.getLogger("cycling_coach.core.kb_downloader")

# 训练百科安装目录 (桌面模式: %USERPROFILE%/.cycling-coach/kb/)
def kb_install_dir() -> Path:
    """训练百科用户安装目录"""
    if sys.platform == "win32":
        base = Path(os.environ.get("USERPROFILE", str(Path.home())))
    else:
        base = Path.home()
    return base / ".cycling-coach" / "kb"


def kb_zip_path() -> Path:
    return kb_install_dir() / settings.kb_zip_name


def kb_extracted_dir() -> Path:
    return kb_install_dir() / "extracted"


def is_kb_installed() -> bool:
    """检查训练百科是否已安装"""
    extracted = kb_extracted_dir()
    if not extracted.exists():
        return False
    # 至少有 1 个 _content.md
    md_files = list(extracted.rglob("*_content.md"))
    return len(md_files) > 0


def download_kb(
    progress_cb: Optional[Callable[[int, int], None]] = None,
    force: bool = False,
) -> Path:
    """下载并解压训练百科
    Args:
        progress_cb: 进度回调 (downloaded_bytes, total_bytes)
        force: 强制重新下载
    Returns:
        解压根目录 (extracted/)
    """
    url = settings.kb_download_url
    if not url:
        raise ValueError("kb_download_url 未配置, 请在 .env 设置 CYCLING_COACH_KB_DOWNLOAD_URL")

    install_dir = kb_install_dir()
    install_dir.mkdir(parents=True, exist_ok=True)
    zip_path = kb_zip_path()

    if zip_path.exists() and not force and is_kb_installed():
        logger.info(f"训练百科已安装: {zip_path}")
        return kb_extracted_dir()

    # 下载
    logger.info(f"开始下载训练百科: {url}")
    logger.info(f"目标: {zip_path}")

    with httpx.stream("GET", url, follow_redirects=True, timeout=300.0) as resp:
        resp.raise_for_status()
        total = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 64 * 1024

        with open(zip_path, "wb") as f:
            for chunk in resp.iter_bytes(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_cb:
                        progress_cb(downloaded, total)

    sz_mb = zip_path.stat().st_size / 1024 / 1024
    logger.info(f"下载完成: {zip_path} ({sz_mb:.1f} MB)")

    # 解压
    extract_to = kb_extracted_dir()
    if extract_to.exists():
        shutil.rmtree(extract_to)
    extract_to.mkdir(parents=True, exist_ok=True)
    logger.info(f"解压中: {zip_path} -> {extract_to}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(extract_to)
    logger.info(f"解压完成: {extract_to}")

    return extract_to
