"""V0.7.4: 第三方平台同步接口 (Strava / Garmin / Wahoo)

V0.7.4 状态: 接口预留, 暂不实现
- 定义 SyncProvider abstract class
- Strava 同步方法签名 (auth, fetch_activities, parse)
- V0.8+ 实现具体 OAuth + 数据拉取

借鉴:
- Strava API v3: https://developers.strava.com/
- Garmin Connect API (需要合作伙伴)
- Wahoo Cloud API
"""
from .base import SyncProvider, SyncStatus, SyncError
from .strava import StravaProvider

__all__ = ["SyncProvider", "SyncStatus", "SyncError", "StravaProvider"]
