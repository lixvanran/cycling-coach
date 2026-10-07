"""个体画像存储 / 读取

MVP:单用户,只维护一个 athlete;FTP / max_hr 是核心字段
"""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.models import Athlete, Activity

logger = logging.getLogger(__name__)


def get_or_create_athlete(db: Session) -> Athlete:
    """始终返回第 1 个 athlete(没有就建)

    🔴 V0.9.0-07: 原来创建占位车手时写死 `ftp=250, max_hr=185`。
    界面上于是显示 "车手 Rider · FTP 250W" —— 看起来像测出来的,
    而这个用户**一次训练都没导入过**。

    ## 为什么这个假值比之前那些更严重

    FTP 是**所有训练区间的基准**。实测 Coggan 7 区:

        按假 FTP 250:  Z2 138-188W   Z4 225-262W
        若真实 FTP 180: Z2  99-135W   Z4 162-189W   ← 阈值区差 74W

    用户按界面显示的区间骑, 会**一直在错误的区间里骑**,
    而且极化、时间在区间分布、负荷达成率全部偏。

    更糟的是**它让我的测试体系也失效了**: 我所有"零数据"测试都从
    `get_or_create_athlete` 起步, 所以每个测试车手都带着这个假 FTP。
    我在指标层扫了 30 多个编造值, 却没发现**数据入口**这里是假的 ——
    因为我的尺子本身建立在这个假值上。

    ## 现在

    占位车手不带任何编造的生理数据。ftp/max_hr 保持 None,
    界面显示"未设置", 并引导去 FTP 校准或用导入的训练数据估算。
    """
    a = db.query(Athlete).first()
    if a is None:
        # 只给名字。ftp / max_hr 留 None —— 那是"未知", 不是"0"也不是"250"。
        a = Athlete(name="Rider")
        db.add(a)
        db.commit()
        db.refresh(a)
        logger.info(f"创建默认 athlete: id={a.id} (FTP/最大心率待用户设置或估算)")
    return a


def update_athlete(
    db: Session, athlete_id: int, **fields
) -> Athlete:
    a = db.query(Athlete).get(athlete_id)
    if not a:
        raise ValueError(f"athlete {athlete_id} not found")
    for k, v in fields.items():
        if hasattr(a, k):
            setattr(a, k, v)
    db.commit()
    db.refresh(a)
    logger.info(f"更新 athlete {athlete_id}: {fields}")
    return a


def get_training_history(
    db: Session, athlete_id: int, limit: int = 30
) -> list[Activity]:
    """最近的训练(用于画像聚合)"""
    return (
        db.query(Activity)
        .filter(Activity.athlete_id == athlete_id)
        .order_by(Activity.start_time.desc())
        .limit(limit)
        .all()
    )
