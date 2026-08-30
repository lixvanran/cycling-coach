"""Strava 同步接口 (V0.7.4 预留, V0.8+ 实现)

参考: https://developers.strava.com/

OAuth 流程 (V0.8+):
1. 用户点"连接 Strava" → GET /api/sync/strava/auth?state=xxx → 跳 strava.com/oauth/authorize
2. 用户授权 → strava 跳回 /api/sync/strava/callback?code=xxx&state=xxx
3. 后端 POST https://www.strava.com/oauth/token (client_id + client_secret + code)
4. 存 access_token + refresh_token + expires_at
5. 拉活动: GET https://www.strava.com/api/v3/athlete/activities?after=ts&before=ts&page=1&per_page=200

V0.7.4 状态: 接口定义, 未实现 OAuth client
- 需要 .env: STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET
- 需要数据库表: sync_connections (provider, athlete_id, access_token, refresh_token, expires_at)
- 需要 cron job: 定时刷新 token + 拉新活动
"""
from __future__ import annotations
import logging
from datetime import datetime
from typing import Optional

from .base import ExternalActivity, SyncError, SyncProvider

logger = logging.getLogger(__name__)


class StravaProvider(SyncProvider):
    """Strava 同步 Provider (V0.7.4 预留)
    
    V0.7.4: 接口骨架, raise NotImplementedError
    V0.8+: 实现
    """
    
    # Strava API 配置
    AUTH_URL = "https://www.strava.com/oauth/authorize"
    TOKEN_URL = "https://www.strava.com/oauth/token"
    API_BASE = "https://www.strava.com/api/v3"
    
    # OAuth scopes
    SCOPES = ["activity:read_all", "activity:write"]  # 读所有活动 + 写 (上传)
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """初始化 (V0.8+ 从 .env 读)
        
        Args:
            client_id: Strava 应用 Client ID (从 https://www.strava.com/settings/api 拿)
            client_secret: Strava 应用 Client Secret
        """
        self.client_id = client_id
        self.client_secret = client_secret
        if not client_id or not client_secret:
            logger.warning(
                "Strava 未配置: 缺 STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET. "
                "V0.8+ 实装. 详细: https://www.strava.com/settings/api"
            )
    
    @property
    def name(self) -> str:
        return "strava"
    
    @property
    def display_name(self) -> str:
        return "Strava"
    
    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        """OAuth 授权 URL (V0.8+ 实现)"""
        raise NotImplementedError(
            "Strava 同步 V0.8+ 实现. 当前 V0.7.4 预留接口."
        )
    
    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """OAuth code → token (V0.8+ 实现)"""
        raise NotImplementedError("V0.8+")
    
    def refresh_token(self, refresh_token: str) -> dict:
        """刷新 access_token (V0.8+ 实现)"""
        raise NotImplementedError("V0.8+")
    
    def fetch_activities(
        self, access_token: str, after: datetime, before: Optional[datetime] = None
    ) -> list[ExternalActivity]:
        """拉取 Strava 活动列表 (V0.8+ 实现)
        
        计划:
        - GET /api/v3/athlete/activities?after={after_epoch}&before={before_epoch}&per_page=200
        - 翻页: page=1, 2, 3, ... 直到返回空
        - 转 ExternalActivity
        
        Strava 字段映射:
        - id → external_id
        - start_date → start_time
        - elapsed_time → duration_s
        - distance → distance_m
        - average_watts → avg_power
        - max_watts → max_power
        - average_heartrate → avg_hr
        - max_heartrate → max_hr
        - average_cadence → avg_cadence
        - total_elevation_gain → total_elevation_gain
        - average_speed → avg_speed
        """
        raise NotImplementedError("V0.8+")
    
    def fetch_activity_detail(self, access_token: str, activity_id: str) -> ExternalActivity:
        """拉取单个活动详情 (V0.8+ 实现)"""
        raise NotImplementedError("V0.8+")
    
    def disconnect(self, access_token: str) -> bool:
        """撤销 Strava 授权 (V0.8+ 实现)
        
        计划: POST https://www.strava.com/oauth/deauthorize
        """
        raise NotImplementedError("V0.8+")


# V0.7.4: 默认实例
_default_strava = None

def get_strava_provider() -> StravaProvider:
    """获取 Strava Provider 单例"""
    global _default_strava
    if _default_strava is None:
        import os
        _default_strava = StravaProvider(
            client_id=os.environ.get("STRAVA_CLIENT_ID"),
            client_secret=os.environ.get("STRAVA_CLIENT_SECRET"),
        )
    return _default_strava
