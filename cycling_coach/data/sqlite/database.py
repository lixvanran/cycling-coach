"""SQLite + SQLAlchemy 初始化

参考 ZhangXuefeng-Agent 风格:单文件 DB + 自动 schema 迁移
"""
from __future__ import annotations
import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session

from cycling_coach.config.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


# 迁移前备份保留份数。备份目录不写死 —— 从实际 DB 文件路径推导,
# 否则 engine 一旦被重绑(测试 / 多 workspace)备份就会存到错误的地方。
_BACKUP_KEEP = 5


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
        # V0.9.0: 上传去重 (老行为 NULL, 新行必填)
        ("file_sha256", "VARCHAR(64)"),
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
    #
    # ⚠️ 光换模块全局的 SessionLocal 不够。测试里几乎都写的是:
    #       from ...database import SessionLocal
    #       ...  # 在函数体里用它
    #    那是 by-value import, 会把对象绑成一个**局部名字**,
    #    下面第 4 步的模块 patch 改不到它(那个名字不在任何模块 __dict__ 里)。
    #
    #    实测(2026-10-06): 第二个测试 use_temp_db("probe2") 之后,
    #    engine 指向 probe2, 但那个测试拿到的 SessionLocal 仍绑着 probe1
    #    → "no such table: athletes"。
    #
    #    所以额外**原地改写旧 sessionmaker 的 bind**, 让所有旧引用
    #    (不管在哪个模块、哪个作用域) 都自动指向新 engine。
    if old_session_local is not None and hasattr(old_session_local, "kw"):
        try:
            old_session_local.kw["bind"] = engine
        except Exception:
            pass

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
        # V0.9.0: 上传去重按 file_sha256 查。ORM 声明了 index=True 但那只对
        # create_all 建的新表生效, 老库升级后这个索引不存在 -> 每次上传全表扫描。
        "CREATE INDEX IF NOT EXISTS ix_activities_file_sha256 ON activities(file_sha256)",
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


def _backup_before_migrate() -> str | None:
    """迁移前给数据库文件打一份带时间戳的备份。

    用户的训练数据是这个软件里唯一不可再生的东西。ALTER TABLE 本身不会写坏
    SQLite 文件, 但迁移可能因为磁盘满 / 杀软锁文件 / 权限不足而中断, 或
    迁移逻辑本身有 bug。一旦炸了而没有备份, 用户几年数据就没了。

    策略: 只在"确实存在缺失列"时才备份 (干净库不产生垃圾文件),
          保留最近 N 份, 失败只记日志不阻断启动。
    """
    try:
        db_path = Path(engine.url.database or "")
    except Exception:
        return None
    if not db_path or not db_path.is_file():
        return None  # 新装, 还没有文件

    # 备份放在 DB 旁边, 跟着实际文件走
    backup_dir = db_path.parent / "db_backups"
    # 先判断是否真的需要迁移, 避免每次启动都复制一份几百 MB 的库
    needs = False
    try:
        with engine.connect() as conn:
            for table, cols in _TABLE_COLUMNS.items():
                if table not in _ALLOWED_TABLES:
                    continue
                try:
                    existing = {
                        row[1]
                        for row in conn.execute(
                            text(f"PRAGMA table_info({table})")
                        ).fetchall()
                    }
                except Exception:
                    continue
                if any(c not in existing for c, _ in cols):
                    needs = True
                    break
    except Exception as e:
        logger.warning(f"[备份] 迁移前检查失败, 跳过备份: {e}")
        return None
    if not needs:
        return None

    try:
        backup_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        dest = backup_dir / f"pre-migrate-{stamp}{db_path.suffix}"
        _wal_safe_backup(db_path, dest)
        # 备份完必须验一下真的有数据 —— 空备份比没有备份更坏,
        # 因为它会让用户以为"我有备份", 真出事时才发现是空的。
        if _backup_is_sane(dest):
            logger.info(f"  [备份] 迁移前已备份数据库 -> {dest.name}")
        else:
            logger.warning(
                f"[备份] {dest.name} 校验不通过(可能是空库), 仍保留但请留意"
            )
        # 只留最近 5 份, 免得磁盘被备份吃满
        olds = sorted(backup_dir.glob("pre-migrate-*.sqlite*"), reverse=True)
        for old in olds[_BACKUP_KEEP:]:
            try:
                old.unlink()
            except OSError:
                pass
        return str(dest)
    except Exception as e:
        # 备份失败不阻断启动, 但必须留下痕迹, 否则用户出事时无从追溯
        logger.warning(f"[备份] 备份失败(将直接迁移): {e}")
        return None


def _wal_safe_backup(src: Path, dest: Path) -> None:
    """拷 SQLite 库, 且必须处理 WAL。

    V0.9.0 第一版这里用的是 `shutil.copy2(db_path, dest)` —— 那是错的。
    本项目给每个连接都开了 `PRAGMA journal_mode=WAL`, 未 checkpoint 的数据
    存在 `xxx.sqlite-wal` 里, 不在主库文件里。直接 copy2 主库:
      - 拷出来可能只有 4096 字节(刚建库)或缺最近的数据
      - 而 `stop.py` 每次都用 taskkill /F 强杀, WAL 未 checkpoint 是常态
    结果就是: 备份文件存在、大小看着正常, 打开发现没有表。
    空备份比没备份更危险 —— 它骗用户以为有退路。

    正解: 用 SQLite 官方的 backup API, 它走 SQLite 自己的读事务,
    会把 WAL 内容一并纳入, 产出事务一致的快照。
    """
    import sqlite3

    s = sqlite3.connect(f"file:{src}?mode=ro", uri=True, timeout=10.0)
    try:
        d = sqlite3.connect(str(dest))
        try:
            s.backup(d)
        finally:
            d.close()
    finally:
        s.close()


def _backup_is_sane(dest: Path) -> bool:
    """验证备份不是空的。备份完不验 = 没备份。"""
    import sqlite3

    try:
        c = sqlite3.connect(str(dest))
        try:
            names = [
                r[0] for r in c.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            ]
            if "activities" not in names:
                return False
            n = c.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
            return True if n is not None else False
        finally:
            c.close()
    except Exception as e:
        logger.warning(f"[备份] 校验备份失败: {e}")
        return False


def init_db() -> None:
    """建表 + 自动迁移 + 补索引

    V0.3.3 起:create_all 不会改老表 schema,所以先 create_all 再 auto_migrate
    V0.7.6 起: 再补 ORM 声明了但 create_all 没建的索引
    V0.9.0 起: 迁移前自动备份, 见 _backup_before_migrate
    """
    from . import models  # noqa: F401  注册表
    Base.metadata.create_all(engine)
    _backup_before_migrate()
    _auto_migrate()
    _ensure_indexes()
    logger.info("数据库初始化完成")
