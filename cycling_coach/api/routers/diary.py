"""训练日记 API — V0.7.4.2 新增

借鉴知识库 [训练百科 - 训练日记 (caafd85d)] 模板:
- 训练感受 (轻松/正常/累/很累)
- 睡眠 (时长 + 质量)
- 心情
- 主观笔记 (markdown 自由格式)
- 装备/补记 / 疼痛 (选填)
- 关联活动 (选填)

端点:
- GET    /api/diary             最近 N 天日记 (默认 30)
- GET    /api/diary/{date}      某天日记
- POST   /api/diary             创建/更新 (upsert by date)
- DELETE /api/diary/{date}      删除
- GET    /api/diary/template    KB 训练日记模板 (从 KB 检索)
"""
from __future__ import annotations
import logging
from datetime import datetime, date, timedelta
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, ConfigDict
from sqlalchemy.orm import Session

from cycling_coach.data.sqlite.database import get_db
from cycling_coach.data.sqlite.models import TrainingDiary, Activity
from cycling_coach.core.profile import store as profile_store

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/diary", tags=["diary"])


# ============== Pydantic ==============

class DiaryIn(BaseModel):
    # V0.7.4.2 fix: 允许 partial update, None = 字段不传
    model_config = ConfigDict(extra="ignore")
    date: date
    training_feel: Optional[int] = Field(None, ge=1, le=5, description="1=很累 5=很轻松")
    mood: Optional[int] = Field(None, ge=1, le=5, description="1=很差 5=很好")
    sleep_h: Optional[float] = Field(None, ge=0, le=24)
    sleep_quality: Optional[int] = Field(None, ge=1, le=5)
    content: Optional[str] = Field(None, description="markdown 自由笔记")
    weather: Optional[str] = Field(None, max_length=64)
    equipment_notes: Optional[str] = Field(None, max_length=255)
    pain_notes: Optional[str] = Field(None, max_length=255)
    activity_id: Optional[int] = None


class DiaryOut(BaseModel):
    id: int
    date: date
    training_feel: Optional[int]
    mood: Optional[int]
    sleep_h: Optional[float]
    sleep_quality: Optional[int]
    content: Optional[str]
    weather: Optional[str]
    equipment_notes: Optional[str]
    pain_notes: Optional[str]
    activity_id: Optional[int]
    created_at: datetime
    updated_at: datetime


def _serialize(d: TrainingDiary) -> dict:
    return {
        "id": d.id,
        "date": d.date.isoformat(),
        "training_feel": d.training_feel,
        "mood": d.mood,
        "sleep_h": d.sleep_h,
        "sleep_quality": d.sleep_quality,
        "content": d.content,
        "weather": d.weather,
        "equipment_notes": d.equipment_notes,
        "pain_notes": d.pain_notes,
        "activity_id": d.activity_id,
        "created_at": d.created_at.isoformat() if d.created_at else None,
        "updated_at": d.updated_at.isoformat() if d.updated_at else None,
    }


# ============== 端点 ==============

@router.get("")
def list_diary(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db)):
    """最近 N 天日记 (默认 30 天)"""
    athlete = profile_store.get_or_create_athlete(db)
    since = date.today() - timedelta(days=days)
    rows = (
        db.query(TrainingDiary)
        .filter(TrainingDiary.athlete_id == athlete.id, TrainingDiary.date >= since)
        .order_by(TrainingDiary.date.desc())
        .all()
    )
    return {"items": [_serialize(r) for r in rows], "total": len(rows)}


@router.get("/template")
def get_diary_template():
    """KB 训练日记模板 (从训练百科 - 训练日记 文档)

    借鉴: 训练学文献 (潘震 / TrainingPeaks / WKO5 Daily Notes)
    """
    return {
        "title": "训练日记模板",
        "source": "训练百科 - 训练日记 (caafd85d) · 潘震",
        "fields": [
            {"key": "training_feel", "label": "训练感受", "type": "rating",
             "min": 1, "max": 5, "scale": "1=很累 → 5=很轻松",
             "tip": "记录这堂课 (或当日) 整体感受, 课程是不是太轻松或太难"},
            {"key": "mood", "label": "心情", "type": "rating",
             "min": 1, "max": 5, "scale": "1=很差 → 5=很好",
             "tip": "白天工作/生活里可能影响训练的情绪"},
            {"key": "sleep_h", "label": "睡眠时长 (小时)", "type": "number",
             "tip": "前一晚睡眠时长, 是判断恢复状态的重要指标"},
            {"key": "sleep_quality", "label": "睡眠质量", "type": "rating",
             "min": 1, "max": 5, "scale": "1=很差 → 5=很好",
             "tip": "是否做梦 / 中途是否醒来 / 醒来身体酸痛/无感"},
            {"key": "content", "label": "主观笔记 (Markdown)", "type": "textarea",
             "tip": "热身时肌肉酸痛? 间歇从第几组开始心脏难受? 冲刺用了什么齿比? 感觉是否全力?"},
            {"key": "weather", "label": "天气", "type": "text", "tip": "气温/风向/降雨, 影响功率输出"},
            {"key": "equipment_notes", "label": "装备/补记", "type": "text",
             "tip": "更换了车座/骑行服? 吃了几个胶? 喝水量?"},
            {"key": "pain_notes", "label": "疼痛记录", "type": "text",
             "tip": "不影响骑车但产生不适的问题 (如牙疼/落枕)"},
            {"key": "activity_id", "label": "关联活动", "type": "activity",
             "tip": "如当日有训练活动, 关联起来便于复盘"},
        ],
        "prompts": [
            "刚开始热身, 已经能感受到肌肉酸痛",
            "间歇训练, 从第几组开始心脏难受 / 呼吸困难 / 肌肉酸痛",
            "间歇训练, 感觉休息时间太长 / 太短",
            "间歇时长/组数/功率目标, 还可以增加 / 需要缩减",
            "什么时候开始感觉饥饿",
            "冲刺使用了什么齿比档位",
            "感觉是否全力",
            "低踏频爬坡能不能坚持",
            "弯道敢不敢切过",
        ],
        "daily_factors": [
            "睡眠情况",
            "白天上班/上学时收到批评",
            "跟人吵架",
            "吃了平时很少吃的食物",
            "身体有一些不影响骑车但会产生一些疼痛不适的问题 (例如牙疼)",
            "更换了骑行服/车座等装备",
            "骑得太累晚上睡不好",
            "失眠",
            "临时有其他安排",
            "前一天力量训练",
        ],
    }


@router.get("/{date_str}")
def get_diary_by_date(date_str: str, db: Session = Depends(get_db)):
    """某天的日记 (YYYY-MM-DD)"""
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, f"日期格式错误: {date_str} (需 YYYY-MM-DD)")
    athlete = profile_store.get_or_create_athlete(db)
    d = (
        db.query(TrainingDiary)
        .filter(TrainingDiary.athlete_id == athlete.id, TrainingDiary.date == target)
        .first()
    )
    if not d:
        return {"date": date_str, "exists": False, "item": None}
    return {"date": date_str, "exists": True, "item": _serialize(d)}


@router.post("")
def upsert_diary(req: DiaryIn, db: Session = Depends(get_db)):
    """创建或更新某天的日记 (upsert)"""
    athlete = profile_store.get_or_create_athlete(db)
    # 找现有
    d = (
        db.query(TrainingDiary)
        .filter(TrainingDiary.athlete_id == athlete.id, TrainingDiary.date == req.date)
        .first()
    )
    # 校验 activity_id 存在
    if req.activity_id is not None:
        a = db.get(Activity, req.activity_id)
        if not a:
            raise HTTPException(400, f"活动不存在: id={req.activity_id}")
    if d is None:
        d = TrainingDiary(athlete_id=athlete.id, date=req.date)
        db.add(d)
    # V0.7.4.2 fix: 用 model_dump(exclude_unset=True) 区分"没传"和"传了 null/空"
    # 这样 partial update 不会清空未传字段
    payload = req.model_dump(exclude_unset=True)
    payload.pop("date", None)  # date 已经用作 upsert key
    for k, v in payload.items():
        if k in ("training_feel", "mood", "sleep_h", "sleep_quality", "content",
                 "weather", "equipment_notes", "pain_notes", "activity_id"):
            setattr(d, k, v)
    db.commit()
    db.refresh(d)
    return {"ok": True, "item": _serialize(d)}


@router.delete("/{date_str}")
def delete_diary(date_str: str, db: Session = Depends(get_db)):
    """删除某天的日记"""
    try:
        target = datetime.strptime(date_str, "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(400, f"日期格式错误: {date_str} (需 YYYY-MM-DD)")
    athlete = profile_store.get_or_create_athlete(db)
    d = (
        db.query(TrainingDiary)
        .filter(TrainingDiary.athlete_id == athlete.id, TrainingDiary.date == target)
        .first()
    )
    if not d:
        raise HTTPException(404, f"该日无日记: {date_str}")
    db.delete(d)
    db.commit()
    return {"ok": True, "deleted": date_str}
