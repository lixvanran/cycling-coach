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

    v0.1.0:默认 rollback journal 模式,避免挂载文件系统上 WAL 失败
    后续 V0.2 视情况再开 WAL
    """
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


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


def init_db() -> None:
    """建表 + 自动迁移

    V0.3.3 起:create_all 不会改老表 schema,所以先 create_all 再 auto_migrate
    """
    from . import models  # noqa: F401  注册表
    Base.metadata.create_all(engine)
    _auto_migrate()
    logger.info("数据库初始化完成")


def repair_db() -> dict:
    """一键修复:迁移 + 清空坏的 system 课程 + 重 seed

    适用于:用户老库升级后,内建课缺失/错乱
    """
    info: dict = {"actions": []}
    # 1. 迁移
    with engine.connect() as conn:
        for table, cols in _TABLE_COLUMNS.items():
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
