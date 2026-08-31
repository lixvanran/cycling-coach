"""ORM 模型

表:
- athletes: 运动员(单用户 MVP,只有 1 行)
- activities: 训练记录
- daily_metrics: 每日聚合指标 + PMC(V0.3 新增)
- workouts: AI 生成的训练课程
- preferences: 用户偏好 / 配置
"""
from __future__ import annotations
from datetime import datetime, timezone, date as _date


def _utcnow() -> datetime:
    """Python 3.12+ 兼容的 UTC now(去掉 tzinfo,因为 SQLAlchemy DateTime 默认 naive)"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
from typing import Optional

from sqlalchemy import (
    Integer, String, Float, DateTime, Text, ForeignKey, JSON, Boolean, Date, Index, LargeBinary
)
from sqlalchemy.types import BLOB as _BLOB  # 兼容别名
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Athlete(Base):
    """运动员(单用户 MVP)"""
    __tablename__ = "athletes"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), default="Rider")
    ftp: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    ftp_estimated: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    lthr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    height_cm: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    activities: Mapped[list["Activity"]] = relationship(back_populates="athlete")


class Activity(Base):
    """单次训练"""
    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)

    # 基础
    source: Mapped[str] = mapped_column(String(16))  # fit/tcx/csv
    file_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    start_time: Mapped[datetime] = mapped_column(DateTime, index=True)
    duration_s: Mapped[int] = mapped_column(Integer)

    # 设备给出的统计
    distance_m: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    total_elevation_gain: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    avg_power: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_power: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    max_hr: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_cadence: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    avg_speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    max_speed: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    calories: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # RPE 主观疲劳 (Borg CR-10, 1-10), 训练后 30min 内填
    rpe: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # RPE 标签 (用户自填, e.g. "腿很沉", "状态好")
    rpe_note: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    device: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    # 我们算的指标(JSON,前端拿来直接渲染)
    metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # V0.7.5.3 DEV-6: 关键指标单独列 + 索引 (避免全表扫描)
    tss: Mapped[Optional[float]] = mapped_column(Float, nullable=True, index=True)
    normalized_power: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    intensity_factor: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    # 组合索引 (athlete + start_time) 用于 Dashboard / Trends
    __table_args__ = (
        Index("ix_act_athlete_start", "athlete_id", "start_time"),
    )
    # 1Hz 样本(只存最近 1 小时的完整数据,大量数据走文件)
    samples_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    laps_json: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # AI 报告
    report: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    report_status: Mapped[str] = mapped_column(String(16), default="pending")
    # pending → analyzing → done | failed

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    athlete: Mapped[Athlete] = relationship(back_populates="activities")


class Workout(Base):
    """训练课程(模板库 + 用户自建)

    V0.3.3 扩展:
    - source: system(内置) | user(自建) | ai(未来 AI 排课生成)
    - tags: 标签数组 ["sweet-spot", "climbing", ...],供 AI 排课 + 搜索用
    - is_template: True=可作为模板复用,False=一次性课程
    - 关联到 PlannedWorkout 时,workout_id 是外键
    """
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("athletes.id"), index=True, nullable=True
    )
    # system 课程 athlete_id = NULL(所有人共享)
    activity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("activities.id"), nullable=True
    )

    title: Mapped[str] = mapped_column(String(128))
    goal: Mapped[str] = mapped_column(String(64))  # 爬坡/冲刺/恢复/...
    duration_min: Mapped[int] = mapped_column(Integer)
    structure: Mapped[list] = mapped_column(JSON)  # 课程结构(分段时间)

    # V0.3.3 新增
    source: Mapped[str] = mapped_column(String(16), default="user")  # system/user/ai
    tags: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)  # ["sweet-spot", "vo2"]
    intensity: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # recovery/endurance/tempo/threshold/vo2max/race
    is_template: Mapped[bool] = mapped_column(Boolean, default=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    erg_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    zwo_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class PlanAIDraft(Base):
    """AI 排课草稿(预留,先不用)

    当用户点"AI 帮我排下周课表"时,AI 生成:
    1. 一组 PlannedWorkout 候选(还没写入 PlannedWorkout)
    2. 用户确认后,从 PlanAIDraft "apply" 到 PlannedWorkout

    字段说明:
    - plan_id: 关联到哪个训练周期
    - week_start: 哪一周(周一)
    - proposed_workouts: [{date, title, intent, duration_target_min, tss_target, source_workout_id?}, ...]
    - ai_rationale: AI 解释为什么这么排
    - status: draft | applied | discarded
    """
    __tablename__ = "plan_ai_drafts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("plan_periods.id"), index=True)
    week_start: Mapped[_date] = mapped_column(Date)
    proposed_workouts: Mapped[list] = mapped_column(JSON)
    ai_rationale: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class PlanPeriod(Base):
    """训练周期(Base / Build / Peak / Taper / Recovery)

    一次大计划可以包含多个周期,每个周期有自己的目标。
    例: 6 周 Base → 4 周 Build → 2 周 Peak → 1 周 Taper
    """
    __tablename__ = "plan_periods"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)

    name: Mapped[str] = mapped_column(String(128))           # "春季 Base 期"
    period_type: Mapped[str] = mapped_column(String(32))    # base/build/peak/taper/recovery/race
    start_date: Mapped[_date] = mapped_column(Date, index=True)
    end_date: Mapped[_date] = mapped_column(Date)
    target_event: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)  # 目标赛事
    weekly_hours_target: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    workouts: Mapped[list["PlannedWorkout"]] = relationship(
        back_populates="period",
        # 不级联:删除 plan 时保留 planned(只解绑 period_id),用户能继续看到历史
        cascade="save-update",
    )


class PlannedWorkout(Base):
    """日历上的一次计划课

    可以引用 Workout(结构化课程),也可以只是一个简易标题。
    实际执行后可关联到 Activity(自动匹配或手动关联)。
    """
    __tablename__ = "planned_workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    period_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("plan_periods.id"), index=True, nullable=True,
    )
    workout_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("workouts.id"), nullable=True,
    )
    actual_activity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("activities.id"), nullable=True,
    )

    scheduled_date: Mapped[_date] = mapped_column(Date, index=True)
    title: Mapped[str] = mapped_column(String(128))         # 简易课表
    intent: Mapped[str] = mapped_column(String(32))         # 训练意图: recovery/endurance/tempo/...
    duration_target_min: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tss_target: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 状态机
    # - planned: 已计划,未到时间
    # - done: 已完成(关联了 activity)
    # - skipped: 跳过
    # - moved: 改期
    status: Mapped[str] = mapped_column(String(16), default="planned")
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    period: Mapped[Optional["PlanPeriod"]] = relationship(back_populates="workouts")
    workout: Mapped[Optional["Workout"]] = relationship()
    actual_activity: Mapped[Optional["Activity"]] = relationship()


class Preference(Base):
    """用户偏好(KV)"""
    __tablename__ = "preferences"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text)  # JSON 字符串
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


class DailyMetric(Base):
    """每日聚合指标 + PMC (Performance Management Chart)

    CTL/ATL/TSB 是 TrainingPeaks 的核心数据:
    - CTL (Chronic Training Load) = 42 天 EWMA,代表"形态 / 体能"
    - ATL (Acute Training Load)    = 7 天 EWMA,代表"短期疲劳"
    - TSB (Training Stress Balance) = CTL - ATL,代表"状态"
        正值 → 准备好比赛 / 状态良好
        负值 → 累积疲劳 / 建议恢复
    - ramp_rate = 7 天 CTL 斜率(每周 CTL 变化量),衡量"训练趋势"
        > 7 TSS/wk = 快速提升(注意过训)
        < 0 = 减量/恢复
    """
    __tablename__ = "daily_metrics"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    date: Mapped[_date] = mapped_column(Date, index=True)

    # 当日训练负荷
    tss: Mapped[float] = mapped_column(Float, default=0.0)
    activity_count: Mapped[int] = mapped_column(Integer, default=0)
    duration_s: Mapped[int] = mapped_column(Integer, default=0)

    # PMC 三条线
    ctl: Mapped[float] = mapped_column(Float, default=0.0)
    atl: Mapped[float] = mapped_column(Float, default=0.0)
    tsb: Mapped[float] = mapped_column(Float, default=0.0)

    # 趋势
    ramp_rate: Mapped[float] = mapped_column(Float, default=0.0)  # 7d CTL 斜率 (TSS/wk)

    # 主观/可穿戴数据(留口,先 nullable)
    sleep_h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    hrv_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rpe: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 1-10
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )

    __table_args__ = (
        Index("ix_daily_metrics_athlete_date", "athlete_id", "date", unique=True),
    )


# ===================== 知识库 (V0.5) =====================

class KbCategory(Base):
    """知识库分类树

    例如:
    - 训练百科 (root)
      - 1. 训练概述 (chapter)
        - 训练的基本原则 (article)
          - (article)
    """
    __tablename__ = "kb_categories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)  # 内部编码
    name: Mapped[str] = mapped_column(String(128))  # 显示名
    parent_code: Mapped[Optional[str]] = mapped_column(String(64), index=True)  # 父 code
    path: Mapped[str] = mapped_column(String(512), index=True)  # 完整路径 (用于面包屑)
    depth: Mapped[int] = mapped_column(Integer, default=0)  # 0=root, 1=chapter, 2=section, 3=article
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    doc_count: Mapped[int] = mapped_column(Integer, default=0)  # 该分类下文档数
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class KbDocument(Base):
    """知识库文档(每篇 _content.md 一条)

    path 用 / 分隔,例: 训练百科/1. 训练概述/训练的基本原则
    """
    __tablename__ = "kb_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    category_code: Mapped[str] = mapped_column(String(64), index=True)  # 顶层分类
    path: Mapped[str] = mapped_column(String(1024), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(256))
    depth: Mapped[int] = mapped_column(Integer, default=0)  # 0=root(章节), 1+ = 文章
    parent_path: Mapped[Optional[str]] = mapped_column(String(1024), index=True)
    content_md: Mapped[str] = mapped_column(Text)  # 原始 markdown
    content_text: Mapped[str] = mapped_column(Text)  # 纯文本 (用于搜索 + AI)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    attachment_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class KbChunk(Base):
    """知识库切片(每 ~500 字一段)

    用于 FTS5 全文搜索 + V0.5 Embedding RAG
    embedding BLOB 字段 V0.5 接 embedding API 时填充
    """
    __tablename__ = "kb_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True)
    chunk_index: Mapped[int] = mapped_column(Integer)  # 文档内切片序号
    content: Mapped[str] = mapped_column(Text)
    token_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # V0.5 预留 embedding
    embedding: Mapped[Optional[bytes]] = mapped_column(LargeBinary, nullable=True)  # float32 list, V0.5 填充
    embedding_model: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class KbAttachment(Base):
    """知识库附件(图/PDF等)"""
    __tablename__ = "kb_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filename: Mapped[str] = mapped_column(String(256), unique=True)  # 原始 uuid.png
    file_path: Mapped[str] = mapped_column(String(512))  # 服务端磁盘路径
    mime_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    size_bytes: Mapped[int] = mapped_column(Integer)
    width: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    height: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_likely_decoration: Mapped[bool] = mapped_column(Boolean, default=False)  # < 30KB 或小尺寸启发式
    is_visible: Mapped[bool] = mapped_column(Boolean, default=True)  # 用户可切换
    use_count: Mapped[int] = mapped_column(Integer, default=0)  # 被多少 .md 引用
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class KbDocAttachment(Base):
    """文档 ↔ 附件 关联(从 markdown 的 ![](attachments/xxx) 解析)"""
    __tablename__ = "kb_doc_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("kb_documents.id", ondelete="CASCADE"), index=True)
    attachment_id: Mapped[int] = mapped_column(ForeignKey("kb_attachments.id", ondelete="CASCADE"), index=True)
    alt_text: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)


class TrainingPhase(Base):
    """训练周期阶段 (Periodization)

    V0.6.1: Base / Build / Peak / Taper / Recovery / Race
    跟 Joe Friel Periodization 框架对齐
    """
    __tablename__ = "training_phases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)

    # 阶段类型
    phase_type: Mapped[str] = mapped_column(String(32))  # base/build/peak/taper/recovery/race/rest
    name: Mapped[str] = mapped_column(String(64))  # e.g. "春季基础期 W1-W4"

    # 时间范围
    start_date: Mapped[datetime] = mapped_column(DateTime)
    end_date: Mapped[datetime] = mapped_column(DateTime)

    # 目标
    target_tss_week: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 周目标 TSS
    target_ftp_w: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # 阶段目标 FTP
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 比赛: 关联特定比赛日
    is_race: Mapped[bool] = mapped_column(Boolean, default=False)
    race_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # TT / road_race / stage_race / gran_fondo / crit / hill_climb / other
    race_priority: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # A (最重要) / B / C

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class FTPTest(Base):
    """FTP 测试记录 (V0.6.1)

    4 种协议:
    - coggan_20min: Coggan 20min 测试
    - carmichael_8min: Carmichael 8min × 2
    - cp_3param: Morton 3 参数临界功率
    - ramp: Ramp Test 递增测试
    """
    __tablename__ = "ftp_tests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)

    test_date: Mapped[datetime] = mapped_column(DateTime, index=True)
    method: Mapped[str] = mapped_column(String(32))
    ftp_w: Mapped[int] = mapped_column(Integer)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)

    # 配套数据
    hr_bpm: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    w_per_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_activity_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # CP 3-param 专属
    cp_w: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    w_prime_kj: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)





class TrainingDiary(Base):
    """V0.7.4.2: 训练日记 (借鉴 KB 训练百科模板)

    字段设计 (潘震教练训练日记模板):
    - training_feel: 1-5 (1=很累, 5=很轻松)
    - mood: 1-5 (心情, 1=很差, 5=很好)
    - sleep_h: float (睡眠时长, 小时)
    - sleep_quality: 1-5 (睡眠质量, KB 模板字段)
    - content: text (markdown 自由笔记)
    - weather: str (天气, 选填)
    - equipment_notes: str (装备/补记, 选填)
    - pain_notes: str (疼痛记录, 选填)
    - activity_id: int (关联活动, 选填)
    - 关联 (date, athlete_id) 唯一
    """
    __tablename__ = "training_diary"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    activity_id: Mapped[Optional[int]] = mapped_column(ForeignKey("activities.id"), nullable=True, index=True)
    date: Mapped[_date] = mapped_column(Date, index=True)

    training_feel: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mood: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    sleep_h: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sleep_quality: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    weather: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    equipment_notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    pain_notes: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    __table_args__ = (
        Index("ix_diary_athlete_date", "athlete_id", "date", unique=True),
    )


class RaceTacticsSession(Base):
    """V0.7.5.9: 比赛战术规划会话

    借鉴 TrainingPeaks Race Plan / WKO5 Race Day:
    - athlete 创建比赛战术会话, 关联具体比赛
    - 跟教练 (AI) 多轮对话, 商讨战术
    - 可上传路书 (PDF/PNG/JPG) 作为上下文
    """
    __tablename__ = "race_tactics_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    # 比赛基本信息
    race_name: Mapped[str] = mapped_column(String(128))
    race_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    distance_km: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    elevation_gain_m: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    race_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)  # road_race / crit / tt / gran_fondo / hill_climb
    priority: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)  # A / B / C
    # 路况/天气
    weather_forecast: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    course_profile: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # 路线描述 (文本)
    # AI 战术建议 (最终版本)
    final_strategy: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 状态
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / planned / completed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    # 关联
    messages: Mapped[list["RaceTacticsMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="RaceTacticsMessage.created_at"
    )
    attachments: Mapped[list["RaceTacticsAttachment"]] = relationship(
        back_populates="session", cascade="all, delete-orphan", order_by="RaceTacticsAttachment.created_at"
    )


class RaceTacticsMessage(Base):
    """比赛战术对话消息 (user / assistant)"""
    __tablename__ = "race_tactics_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("race_tactics_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(16))  # user / assistant / system
    content: Mapped[str] = mapped_column(Text)
    # AI 检索的 KB 引用 (JSON 数组 [{title, path, snippet}])
    rag_sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    thinking: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # AI 思考过程
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["RaceTacticsSession"] = relationship(back_populates="messages")


class RaceTacticsAttachment(Base):
    """比赛路书附件 (PDF/PNG/JPG)"""
    __tablename__ = "race_tactics_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(ForeignKey("race_tactics_sessions.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(255))
    file_path: Mapped[str] = mapped_column(String(512))
    mime_type: Mapped[str] = mapped_column(String(64))
    size_bytes: Mapped[int] = mapped_column(Integer)
    # 描述
    description: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    # OCR 提取的文本 (PDF 解析后供 RAG 用)
    extracted_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    session: Mapped["RaceTacticsSession"] = relationship(back_populates="attachments")


# ===== V0.7.6 Foundation 1.0: 通用 chat 持久化 + ML 预测基础设施 =====

class ChatSession(Base):
    """通用 chat 会话(给思维扩散器/普通 chat 共用)

    区别于 RaceTacticsSession: 这是通用对话,不带比赛上下文
    V0.7.6 引入, 给后续思维扩散器 / 多 agent 推理持久化用
    """
    __tablename__ = "chat_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    title: Mapped[str] = mapped_column(String(128), default="新对话")
    # 类型: general / race_tactics / training_plan / diffuse_thinking
    session_type: Mapped[str] = mapped_column(String(32), default="general")
    # 思维树参数(JSON): {"beam_width": 4, "max_depth": 5, ...}
    tree_params: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # 思维树快照(JSON): 完整节点树, 给前端可视化
    tree_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # 选中的最佳节点 id(思维扩散器最终答案)
    selected_node_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")  # active / completed / cancelled
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, onupdate=_utcnow)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session", cascade="all, delete-orphan"
    )


class ChatMessage(Base):
    """chat 消息,支持思维树节点结构"""
    __tablename__ = "chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("chat_sessions.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(String(16))  # user / assistant / system / tool / agent_a / agent_b
    content: Mapped[str] = mapped_column(Text)
    # 思维树专用字段(普通 chat 留空)
    parent_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    node_path: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)  # "root.0.2.1"
    thought_kind: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # decompose / explore / synthesize / evaluate / final
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    # active / pruned / selected / cancelled
    # 思维内容(reasoning / 内部推理)
    thinking: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # RAG 引用源 [{title, path, snippet}]
    rag_sources: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # token 统计
    tokens_in: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_out: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # 错误信息
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class MLPrediction(Base):
    """ML 模型预测结果归档

    每次推理写一行, 留作回溯 + 评估 ML 模型精度
    """
    __tablename__ = "ml_predictions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    athlete_id: Mapped[int] = mapped_column(ForeignKey("athletes.id"), index=True)
    # 模型元数据
    model_name: Mapped[str] = mapped_column(String(64), index=True)  # "ftp_predictor" / "readiness_ranker"
    model_version: Mapped[str] = mapped_column(String(32))  # "v1-gbm-conformal-2026-08-31"
    model_format: Mapped[str] = mapped_column(String(16), default="joblib")  # joblib / pt / onnx
    # 预测任务
    target: Mapped[str] = mapped_column(String(32))  # "ftp_w" / "readiness" / "race_time"
    predicted_value: Mapped[float] = mapped_column(Float)
    # 置信区间(80%)
    lower_80: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    upper_80: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_label: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    # high / medium / low(基于样本量)
    # 特征快照(留 1 周可回溯, 大数据后续用 parquet)
    feature_snapshot: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # 关联上下文(可选)
    activity_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("activities.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # 推理耗时 ms
    inference_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow, index=True)


class MLModelMeta(Base):
    """ML 模型元数据 + 版本管理

    单用户 MVP: 全局模型(athlete_id=NULL), 多用户时按 athlete 区分
    """
    __tablename__ = "ml_model_meta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    task_name: Mapped[str] = mapped_column(String(64), index=True)  # "ftp_predictor"
    version: Mapped[str] = mapped_column(String(32))  # "v1.0.0" (semver)
    model_path: Mapped[str] = mapped_column(String(512))  # 相对 settings.ml_models_dir
    model_format: Mapped[str] = mapped_column(String(16))  # joblib / pt / onnx
    # 训练信息
    training_date: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    training_samples_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    training_metrics: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # {"mae": 8.5, "r2": 0.78, "mape": 0.04}
    # 特征 schema(列顺序 + 类型, 推理时强校验)
    feature_schema: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # {"ctl": "float", "hrv_7d_avg": "float|null", ...}
    feature_columns: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)
    # ["ctl", "atl", "tsb", ...]
    # 状态
    athlete_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("athletes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=_utcnow, onupdate=_utcnow
    )


