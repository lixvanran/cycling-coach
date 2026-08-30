"""第三方同步接口 (V0.7.4 预留, V0.8+ 实现)"""
from __future__ import annotations
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

logger = logging.getLogger(__name__)


class SyncError(Exception):
    """同步错误基类"""
    pass


class SyncStatus(str, Enum):
    """同步状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    SYNCING = "syncing"
    ERROR = "error"


@dataclass
class ProviderInfo:
    """平台信息 (前端展示)"""
    name: str           # "strava"
    display_name: str   # "Strava"
    icon: str           # emoji or url
    auth_url: str       # OAuth 入口
    scopes: list[str]   # OAuth scopes
    status: SyncStatus
    last_sync: Optional[datetime] = None
    activity_count: int = 0
    enabled: bool = False  # V0.7.4: False (待 V0.8+ 实现)


@dataclass
class ExternalActivity:
    """外部活动数据 (统一格式)"""
    external_id: str
    source: str          # "strava" | "garmin" | "wahoo"
    start_time: datetime
    duration_s: int
    distance_m: float
    avg_power: Optional[int] = None
    max_power: Optional[int] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    avg_cadence: Optional[int] = None
    total_elevation_gain: Optional[float] = None
    avg_speed: Optional[float] = None
    file_url: Optional[str] = None  # FIT/TCX 下载链接
    raw: dict = field(default_factory=dict)


class SyncProvider(ABC):
    """第三方平台同步抽象基类
    
    V0.7.4: 接口预留, V0.8+ 实现
    V0.8+ 计划:
    - StravaProvider (OAuth + 活动拉取)
    - GarminProvider (OAuth + 活动拉取)
    - WahooProvider (OAuth + 活动拉取)
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """平台标识 (strava/garmin/wahoo)"""
        ...
    
    @property
    @abstractmethod
    def display_name(self) -> str:
        """显示名"""
        ...
    
    @abstractmethod
    def get_auth_url(self, state: str, redirect_uri: str) -> str:
        """OAuth 授权 URL"""
        ...
    
    @abstractmethod
    def exchange_code(self, code: str, redirect_uri: str) -> dict:
        """OAuth code → token (返回 access_token, refresh_token, expires_at)"""
        ...
    
    @abstractmethod
    def refresh_token(self, refresh_token: str) -> dict:
        """刷新 access_token"""
        ...
    
    @abstractmethod
    def fetch_activities(
        self, access_token: str, after: datetime, before: Optional[datetime] = None
    ) -> list[ExternalActivity]:
        """拉取活动列表"""
        ...
    
    @abstractmethod
    def fetch_activity_detail(self, access_token: str, activity_id: str) -> ExternalActivity:
        """拉取单个活动详情"""
        ...
    
    @abstractmethod
    def disconnect(self, access_token: str) -> bool:
        """撤销授权"""
        ...
