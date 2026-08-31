"""V0.7.4: 第三方平台同步 API (Strava / Garmin / Wahoo)

V0.7.4 状态: 接口预留, 暂不实现 OAuth
- 列出支持的平台 (Strava 已接好骨架, 状态 disabled)
- V0.8+ 实装 OAuth + 数据拉取

端点:
- GET  /api/sync/providers          支持的平台列表
- GET  /api/sync/strava/auth        OAuth 入口 (V0.8+)
- GET  /api/sync/strava/callback    OAuth callback (V0.8+)
- GET  /api/sync/strava/status      同步状态
- POST /api/sync/strava/disconnect  断开
- GET  /api/sync/strava/activities  已同步活动列表
- POST /api/sync/strava/sync        手动触发同步
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.core.profile import store as profile_store
from cycling_coach.core.sync import SyncStatus
from cycling_coach.core.sync.base import ProviderInfo
from cycling_coach.core.sync.strava import get_strava_provider

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.get("/providers")
def list_providers(db: Session = Depends(get_db)):
    """V0.7.4: 列出已支持/已预留的同步平台
    
    Strava: 已预留接口, V0.8+ 实现
    Garmin: 规划中
    Wahoo: 规划中
    """
    strava = get_strava_provider()
    
    providers = [
        {
            "name": "strava",
            "display_name": "Strava",
            "icon": "🟠",  # 暂用 emoji, V0.8+ 用 SVG
            "description": "全球最大骑行社区, 自动同步活动",
            "status": SyncStatus.DISCONNECTED.value,
            "enabled": False,  # V0.7.4 暂未启用
            "auth_url": None,  # V0.8+ 给
            "scopes": ["activity:read_all"],
            "last_sync": None,
            "activity_count": 0,
            "config_required": {
                "STRAVA_CLIENT_ID": "从 https://www.strava.com/settings/api 创建应用获取",
                "STRAVA_CLIENT_SECRET": "同上",
            },
            "todo_note": "V0.8+ 实现. 当前接口已预留, OAuth + 数据拉取 + 数据库表都规划好.",
        },
        {
            "name": "garmin",
            "display_name": "Garmin Connect",
            "icon": "🔵",
            "description": "Garmin 设备官方云, 活动/健康数据",
            "status": SyncStatus.DISCONNECTED.value,
            "enabled": False,
            "auth_url": None,
            "scopes": [],
            "last_sync": None,
            "activity_count": 0,
            "config_required": {},
            "todo_note": "V0.9+ 规划. 需合作伙伴计划.",
        },
        {
            "name": "wahoo",
            "display_name": "Wahoo Cloud",
            "icon": "🟢",
            "description": "Wahoo 训练台/码表, 室内外活动",
            "status": SyncStatus.DISCONNECTED.value,
            "enabled": False,
            "auth_url": None,
            "scopes": [],
            "last_sync": None,
            "activity_count": 0,
            "config_required": {},
            "todo_note": "V0.9+ 规划.",
        },
    ]
    return {
        "providers": providers,
        "total": len(providers),
        "v072_status": "接口预留, V0.8+ 实现",
    }


@router.get("/strava/status")
def strava_status(db: Session = Depends(get_db)):
    """V0.7.4: Strava 同步状态
    
    V0.7.4: 总返回 disconnected (未实装)
    V0.8+: 读 sync_connections 表返回真实状态
    """
    strava = get_strava_provider()
    return {
        "provider": "strava",
        "display_name": "Strava",
        "status": SyncStatus.DISCONNECTED.value,
        "enabled": False,
        "last_sync": None,
        "activity_count": 0,
        "athlete_id": None,  # V0.8+ 填
        "config_ok": strava.client_id is not None and strava.client_secret is not None,
        "message": "V0.7.4 接口预留, V0.8+ 实现. 配置 STRAVA_CLIENT_ID/SECRET 后启用.",
    }


@router.get("/strava/auth")
def strava_auth_start(redirect_uri: Optional[str] = None):
    """V0.7.4: Strava OAuth 入口
    
    V0.7.4: 501 Not Implemented
    V0.8+: 跳 strava.com/oauth/authorize
    """
    raise HTTPException(501, detail={
        "ok": False, "code": "not_implemented",
        "message": "Strava OAuth V0.8+ 推出. 当前接口预留.",
        "planned_version": "V0.8+",
        "config_hint": "设置 STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET 后启用",
    })


@router.get("/strava/callback")
def strava_oauth_callback(code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None):
    """V0.7.4: Strava OAuth callback
    
    V0.7.4: 501 Not Implemented
    V0.8+: 换 access_token + 存数据库
    """
    if error:
        raise HTTPException(400, f"Strava OAuth 错误: {error}")
    raise HTTPException(501, detail={
        "ok": False, "code": "not_implemented",
        "message": "Strava OAuth callback V0.8+ 推出.",
        "planned_version": "V0.8+",
    })


@router.post("/strava/disconnect")
def strava_disconnect():
    """V0.7.4: 断开 Strava (V0.8+ 实现)"""
    raise HTTPException(501, detail={
        "ok": False, "code": "not_implemented",
        "message": "Strava V0.8+ 推出.",
        "planned_version": "V0.8+",
    })


@router.get("/strava/activities")
def strava_activities(
    days: int = Query(30, ge=1, le=365),
    db: Session = Depends(get_db),
):
    """V0.7.4: 已同步的 Strava 活动列表 (V0.8+ 实现)
    
    V0.7.4: 空列表 + 说明
    V0.8+: 读 sync_external_activities 表
    """
    return {
        "activities": [],
        "total": 0,
        "days": days,
        "message": "V0.7.4 暂未同步. V0.8+ 实装后这里显示 Strava 拉来的活动.",
    }


@router.post("/strava/sync")
def strava_sync_now(db: Session = Depends(get_db)):
    """V0.7.4: 手动触发同步 (V0.8+ 实现)"""
    raise HTTPException(501, detail={
        "ok": False, "code": "not_implemented",
        "message": "Strava V0.8+ 推出.",
        "planned_version": "V0.8+",
    })
