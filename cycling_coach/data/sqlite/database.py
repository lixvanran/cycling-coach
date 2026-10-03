"""SQLite + SQLAlchemy 初始化

参考 ZhangXuefeng-Agent 风格:单文件 DB + 自动 schema 迁移
"""
from __future__ import annotations
import logging
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from cycling_coach.config.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


def _db_path() -> str:
    """workspace/cycling_coach.sqlite"""
    workspace = Path(settings.workspace_dir).resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    db_file = workspace / "cycling_coach.sqlite"
    return f"sqlite:///{db_file}"


engine = create_engine(
    _db_path(),
    connect_args={"check_same_thread": False},
    echo=False,
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragma(dbapi_conn, _):
    """SQLite 性能优化 + 兼容性

    V0.7.6: 开启 WAL 模式, 提升并发读写
    - WAL: 读不阻塞写, 写不阻塞读
    - synchronous=NORMAL: 折中模式, 性能 + 安全性平衡
    - busy_timeout=5000: 锁等待 5s(避免 IMMEDIATE 锁快速失败)
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


# V0.7.5.4 DEV-19: 允许 _auto_migrate / repair_db 操作的表白名单
# 防止 text() SQL 注入 + 防止误操作业务表
_ALLOWED_TABLES: set[str] = {
    "workouts",
    "kb_chunks",
    "activities",
    "training_phases",
    # V0.7.6 新表(新增可加, 不要轻易删)
    "chat_sessions",
    "chat_messages",
    "ml_predictions",
    "ml_model_meta",
    # V0.8.2 B1-3: 阶段周模板
    "phase_workouts",
    # V0.8.3.1 P0: 加 athlete_id 列 (解决 phase_apply 创建的 planned 没有归属)
    "planned_workouts",
}


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


# 表 → 需要的列定义(用于自动迁移)
# 格式: (列名, SQLite DDL 类型 + 约束)
_TABLE_COLUMNS: dict[str, list[tuple[str, str]]] = {
    "workouts": [
        ("source", "VARCHAR(16) DEFAULT 'user'"),
        ("tags", "JSON"),
        ("intensity", "VARCHAR(32)"),
        ("is_template", "BOOLEAN DEFAULT 1"),
        ("description", "TEXT"),
        ("updated_at", "DATETIME"),
    ],
    "kb_chunks": [
        ("embedding", "BLOB"),  # V0.5 预留, 存 float32 列表
        ("embedding_model", "VARCHAR(64)"),  # 哪个模型生成的
        ("token_count", "INTEGER"),
    ],
    "activities": [
        ("rpe", "INTEGER"),  # V0.6.1 主观疲劳 Borg CR-10 (1-10)
        ("rpe_note", "VARCHAR(64)"),  # RPE 自定义标签
        ("tss", "FLOAT"),  # V0.7.5.3 DEV-6: 关键指标单独列 + 索引
        ("normalized_power", "INTEGER"),
        ("intensity_factor", "FLOAT"),
    ],
    "training_phases": [
        ("race_type", "VARCHAR(32)"),  # V0.7 比赛类型 TT/road_race/stage_race/gran_fondo/crit/hill_climb/other
        ("race_priority", "VARCHAR(16)"),  # V0.7 优先级 A/B/C
    ],
    # V0.8.3.1 P0: planned_workouts 加 athlete_id (老库 NULL 没关系, 新行必填)
    "planned_workouts": [
        ("athlete_id", "INTEGER REFERENCES athletes(id)"),
    ],
}


def _auto_migrate() -> None:
    """检测老表缺列 → 自动 ALTER 加上

    解决 V0.3.2 → V0.3.3 升级时,用户老库 workouts 表缺新列导致
    'no such column: workouts.source' 的 500 错误
    """
    with engine.connect() as conn:
        for table, cols in _TABLE_COLUMNS.items():
            try:
                # V0.7.5.4 DEV-19: 白名单
                if table not in _ALLOWED_TABLES:
                    logger.error(f"[迁移] 非法表名: {table!r}, 跳过")
                    continue
                existing = {
                    row[1]
                    for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                }
            except Exception:
                # 表本身不存在(新装),create_all 会建
                continue
            for col_name, col_ddl in cols:
                if col_name not in existing:
                    sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_ddl}"
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        logger.info(f"  [迁移] {table}.{col_name} 已添加")
                    except Exception as e:
                        logger.warning(f"  [迁移] {table}.{col_name} 失败: {e}")


def repair_db() -> dict:
    """一键修复:迁移 + 清空坏的 system 课程 + 重 seed

    适用于:用户老库升级后,内建课缺失/错乱
    """
    info: dict = {"actions": []}
    # 1. 迁移
    with engine.connect() as conn:
        for table, cols in _TABLE_COLUMNS.items():
            # V0.7.5.4 DEV-19: 白名单
            if table not in _ALLOWED_TABLES:
                info["actions"].append(f"SKIP illegal table: {table!r}")
                continue
            existing = {
                row[1]
                for row in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            }
            for col_name, col_ddl in cols:
                if col_name not in existing:
                    sql = f"ALTER TABLE {table} ADD COLUMN {col_name} {col_ddl}"
                    try:
                        conn.execute(text(sql))
                        conn.commit()
                        info["actions"].append(f"ALTER {table}.{col_name}")
                    except Exception as e:
                        info["actions"].append(f"FAIL {table}.{col_name}: {e}")
    # 2. 清掉 source 为空/错的 system 课程(用 raw SQL,绕过 ORM NOT NULL)
    with engine.connect() as conn:
        try:
            r = conn.execute(text("DELETE FROM workouts WHERE source = 'system'"))
            conn.commit()
            info["actions"].append(f"DELETE 旧 system 课: {r.rowcount} 条")
        except Exception as e:
            info["actions"].append(f"DELETE 失败: {e}")
    return info


def get_db() -> Session:
    """FastAPI 依赖"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def rebind_engine(db_url: str, *, create: bool = True) -> None:
    """V0.9.0: 把整个模块重绑到新的 SQLite 文件 (测试隔离用)

    为什么需要这个:
        `engine` / `SessionLocal` 是模块级单例, import 时就按
        `settings.workspace_dir` 建好了。测试想指向临时 DB 时,
        光改 `config.engine` 没用 — 没人读那个属性 (V0.7.6~V0.9.0
        的 6 个测试文件都踩过这个坑, 实际全在共用真实 workspace DB)。

    做了什么:
        1. 旧 engine dispose()
        2. 建新 engine + 重挂 `_set_sqlite_pragma` 事件监听 (WAL 等 PRAGMA)
        3. 重绑 `SessionLocal`
        4. 扫描 sys.modules, 把 by-value import 了旧 `SessionLocal` /
           `engine` 的模块一起打补丁
           (orchestrator / _activities_shared / analyze_activity 等)
        5. `create=True` 时建表 + 迁移 + 补索引

    生产代码不要调用 — 只有 tests/conftest.py 用。
    """
    import sys as _sys

    global engine, SessionLocal

    old_engine = engine
    old_session_local = SessionLocal

    # 1+2: 换 engine (复用模块级 listener 逻辑, 保证 PRAGMA 一致)
    engine = create_engine(
        db_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    event.listen(engine, "connect", _set_sqlite_pragma)

    # 3: 换 sessionmaker
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    # 4: 给 by-value import 的模块打补丁
    for _mod in list(_sys.modules.values()):
        if _mod is None:
            continue
        # 跳过本模块自己 (已经是新的)
        if getattr(_mod, "__name__", "") == __name__:
            continue
        try:
            if getattr(_mod, "SessionLocal", None) is old_session_local:
                _mod.SessionLocal = SessionLocal  # type: ignore[attr-defined]
            if getattr(_mod, "engine", None) is old_engine:
                _mod.engine = engine  # type: ignore[attr-defined]
        except Exception:
            # 某些模块 (只读 __getattr__ / 特殊对象) 不让 set, 跳过
            continue

    # 旧 engine 收尾 (在所有引用都换掉之后)
    try:
        old_engine.dispose()
    except Exception:
        pass

    # 5: 建表
    if create:
        init_db()

    logger.info(
        f"engine 已重绑: {db_url} "
        f"(patched {len(_sys.modules)} modules, SessionLocal 引用已同步)"
    )


def _ensure_indexes() -> None:
    """V0.7.6: 补全 ORM 声明了但 _auto_migrate 没建的索引

    ORM `index=True` 只能影响新表 create_all, 升级用户的老库缺这些索引
    - ix_activities_tss: ORDER BY tss DESC 用, 大表必备
    - ix_act_athlete_start: 复合 (athlete_id, start_time), 加速分页
    """
    _indexes = [
        "CREATE INDEX IF NOT EXISTS ix_activities_tss ON activities(tss)",
        "CREATE INDEX IF NOT EXISTS ix_activities_normalized_power ON activities(normalized_power)",
        "CREATE INDEX IF NOT EXISTS ix_act_athlete_start ON activities(athlete_id, start_time)",
        "CREATE INDEX IF NOT EXISTS ix_daily_metrics_athlete_date ON daily_metrics(athlete_id, date)",
        # V0.8.3.1 P0: planned_workouts 复合索引 (athlete + date 用于日历视图)
        "CREATE INDEX IF NOT EXISTS ix_planned_athlete_date ON planned_workouts(athlete_id, scheduled_date)",
    ]
    with engine.connect() as conn:
        for sql in _indexes:
            try:
                conn.execute(text(sql))
                conn.commit()
            except Exception as e:
                logger.warning(f"[索引迁移] 失败 {sql}: {e}")


def init_db() -> None:
    """建表 + 自动迁移 + 补索引

    V0.3.3 起:create_all 不会改老表 schema,所以先 create_all 再 auto_migrate
    V0.7.6 起: 再补 ORM 声明了但 create_all 没建的索引
    """
    from . import models  # noqa: F401  注册表
    Base.metadata.create_all(engine)
    _auto_migrate()
    _ensure_indexes()
    logger.info("数据库初始化完成")
