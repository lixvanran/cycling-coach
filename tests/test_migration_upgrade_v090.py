"""V0.9.0: 老用户升级路径测试

## 为什么单独写这个文件

V0.9.0 之前的**所有**测试 (含我自己的 200 个) 用的都是全新空库 ——
`use_temp_db()` 直接 `rebind_engine(create=True)`, 表是新的, 列是全的。

也就是说: **"用户从 V0.8.1 升级到 V0.9.0" 这条路径从来没被测过。**
而这恰恰是事故率最高的路径, 因为:

- 老库的 `activities` 表**没有** `file_sha256` 这一列 (V0.9.0 才加的, 用来做上传去重)
- 老库可能还缺 `tss` / `normalized_power` / `intensity_factor` 等 V0.7.5 加的列
- ORM 查询 `Activity.file_sha256` 时, 老库上会直接 `no such column` → 全站 500

用户在 Windows 上双击升级, 打开就是一片 500, 而他不会去看 log 知道原因。

本文件用**真实的老 schema** 建库, 塞真实数据, 然后跑真实的 `init_db()`,
断言: 数据一条不丢 + 新列到位 + 老行兼容 + 迁移前有备份。

## 不 mock 任何东西
全部走真实 SQLite 文件 + 真实 `init_db()`。
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from tests.conftest import _SESSION_TMP

# V0.8.1 时期的 activities 表: 有 V0.7.5 加的 tss/NP/IF, 但**没有** file_sha256
# (file_sha256 是 V0.9.0 为了上传去重才加的)
OLD_ACTIVITIES_DDL = """
CREATE TABLE activities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    athlete_id INTEGER,
    source VARCHAR(32),
    file_name VARCHAR(255),
    file_path VARCHAR(1024),
    start_time DATETIME,
    duration_s INTEGER,
    distance_m FLOAT,
    total_elevation_gain FLOAT,
    avg_power INTEGER,
    max_power INTEGER,
    avg_hr INTEGER,
    max_hr INTEGER,
    avg_cadence INTEGER,
    max_cadence INTEGER,
    avg_speed FLOAT,
    max_speed FLOAT,
    calories INTEGER,
    rpe INTEGER,
    rpe_note VARCHAR(64),
    device VARCHAR(64),
    metrics TEXT,
    tss FLOAT,
    normalized_power INTEGER,
    intensity_factor FLOAT,
    samples_json TEXT,
    laps_json TEXT,
    report TEXT,
    report_status VARCHAR(32),
    created_at DATETIME,
    FOREIGN KEY(athlete_id) REFERENCES athletes (id)
)
"""

OLD_ATHLETES_DDL = """
CREATE TABLE athletes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name VARCHAR(64),
    ftp INTEGER,
    weight_kg FLOAT,
    created_at DATETIME
)
"""


@pytest.fixture()
def legacy_db(tmp_path: Path):
    """造一个真实的 V0.8.1 老库, 含 3 条训练记录

    刻意不建 file_sha256 列, 模拟真实的老用户库。
    """
    db_dir = tmp_path / "legacy_ws"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_file = db_dir / "cycling_coach.sqlite"

    con = sqlite3.connect(db_file)
    con.execute(OLD_ATHLETES_DDL)
    con.execute(OLD_ACTIVITIES_DDL)
    con.execute(
        "INSERT INTO athletes (id, name, ftp, weight_kg, created_at) "
        "VALUES (1, '老用户', 280, 68.0, '2024-01-01 08:00:00')"
    )
    # 3 条真实感的训练数据
    for i, (dur, dist, ap) in enumerate(
        [(3600, 45000.0, 210), (5400, 68000.0, 195), (2700, 30000.0, 240)], start=1
    ):
        con.execute(
            "INSERT INTO activities "
            "(id, athlete_id, source, file_name, file_path, start_time, duration_s, "
            " distance_m, avg_power, avg_hr, tss, normalized_power, created_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (
                i, 1, "garmin", f"ride_{i}.fit", f"/old/path/ride_{i}.fit",
                f"2024-06-0{i} 07:30:00", dur, dist, ap, 150 + i,
                85.0 + i, 220 + i, f"2024-06-0{i} 09:00:00",
            ),
        )
    con.commit()
    con.close()
    return db_file


def _rebind_to(db_file: Path, create: bool = True) -> None:
    from cycling_coach.config import config as cfg
    from cycling_coach.data.sqlite import database as D

    cfg.settings.workspace_dir = str(db_file.parent)
    D.rebind_engine(f"sqlite:///{db_file}", create=create)


def _cols(db_file: Path, table: str) -> set[str]:
    con = sqlite3.connect(db_file)
    try:
        return {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    finally:
        con.close()


# ========================================================================


def test_老库缺少_file_sha256(legacy_db):
    """先确认测试前提成立: 老库确实没有这一列"""
    assert "file_sha256" not in _cols(legacy_db, "activities")


def test_迁移后新增列到位(legacy_db):
    _rebind_to(legacy_db, create=True)
    from cycling_coach.data.sqlite import database as D

    D.init_db()
    cols = _cols(legacy_db, "activities")
    assert "file_sha256" in cols, "V0.9.0 上传去重依赖这一列, 迁移没加上 = 全站 500"
    D.rebind_engine(f"sqlite:///{_SESSION_TMP / 'scratch.sqlite'}", create=True)


def test_迁移后数据一条不丢(legacy_db):
    """最关键的一条: 升级绝不能吃掉用户数据"""
    _rebind_to(legacy_db, create=True)
    from cycling_coach.data.sqlite import database as D

    D.init_db()
    con = sqlite3.connect(legacy_db)
    try:
        rows = con.execute(
            "SELECT id, duration_s, distance_m, avg_power, tss FROM activities "
            "ORDER BY id"
        ).fetchall()
    finally:
        con.close()

    assert len(rows) == 3, f"数据条数变了: {len(rows)} (应为 3)"
    assert rows[0][1] == 3600
    assert rows[1][1] == 5400
    assert rows[2][1] == 2700
    assert rows[0][3] == 210
    assert rows[0][4] == 86.0
    D.rebind_engine(f"sqlite:///{_SESSION_TMP / 'scratch.sqlite'}", create=True)


def test_老行新列为NULL且不报错(legacy_db):
    """老数据没有 sha256, 必须是 NULL 而不是崩

    这里是真实事故点: ORM 读 file_sha256 时老库没这列 -> OperationalError。
    """
    _rebind_to(legacy_db, create=True)
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.data.sqlite.models import Activity
    from cycling_coach.data.sqlite import database as D

    D.init_db()
    db = SessionLocal()
    try:
        acts = db.query(Activity).order_by(Activity.id).all()
        assert len(acts) == 3
        for a in acts:
            assert a.file_sha256 is None, "老行应为 NULL, 上传去重要能容忍这种情况"
    finally:
        db.close()
        D.rebind_engine(f"sqlite:///{_SESSION_TMP / 'scratch.sqlite'}", create=True)


def test_迁移前自动备份(legacy_db):
    """迁移前必须有备份, 否则炸库 = 用户几年训练数据没了"""
    _rebind_to(legacy_db, create=True)
    from cycling_coach.data.sqlite import database as D

    D.init_db()
    backup_dir = legacy_db.parent / "db_backups"
    backups = list(backup_dir.glob("pre-migrate-*.sqlite*"))
    assert backups, f"没有生成迁移前备份: {backup_dir} 不存在或为空"

    b = backups[0]
    assert b.stat().st_size > 0, "备份文件是空的"
    # 备份里必须是迁移**前**的表 —— 没有 file_sha256
    assert "file_sha256" not in _cols(b, "activities"), "备份是迁移后才拷的, 等于没备份"
    # 但数据在
    con = sqlite3.connect(b)
    try:
        n = con.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    finally:
        con.close()
    assert n == 3
    D.rebind_engine(f"sqlite:///{_SESSION_TMP / 'scratch.sqlite'}", create=True)


def test_干净库不产生备份垃圾(tmp_path):
    """已是最新 schema 的库不该每次启动都复制一份几百 MB 出来"""
    db_dir = tmp_path / "clean_ws"
    db_dir.mkdir(parents=True, exist_ok=True)
    db_file = db_dir / "cycling_coach.sqlite"

    _rebind_to(db_file, create=True)
    from cycling_coach.data.sqlite import database as D

    D.init_db()          # 第一次: 建全新表
    D.init_db()          # 第二次: 已无缺失列, 不应备份
    assert not (db_dir / "db_backups").exists() or not list(
        (db_dir / "db_backups").glob("pre-migrate-*.sqlite*")
    ), "无迁移需求却仍在生成备份, 会持续吃磁盘"
    D.rebind_engine(f"sqlite:///{_SESSION_TMP / 'scratch.sqlite'}", create=True)


def test_迁移幂等_连跑三次不炸(legacy_db):
    """用户可能反复点 start.bat, 迁移必须可重复执行"""
    _rebind_to(legacy_db, create=True)
    from cycling_coach.data.sqlite import database as D

    for _ in range(3):
        D.init_db()
    con = sqlite3.connect(legacy_db)
    try:
        n = con.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    finally:
        con.close()
    assert n == 3
    D.rebind_engine(f"sqlite:///{_SESSION_TMP / 'scratch.sqlite'}", create=True)


def test_WAL未checkpoint时备份仍有数据(legacy_db):
    """回归: 第一版备份用 shutil.copy2, 在 WAL 模式下拷出来是空的。

    触发条件不是边缘情况 —— stop.py 每次都 taskkill /F 强杀,
    WAL 未 checkpoint 是常态。空备份比没备份更坏: 它让用户以为有退路。

    这里刻意不开 checkpoint, 直接模拟"刚被强杀"的状态。
    """
    import sqlite3
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).parent.parent))
    from cycling_coach.data.sqlite.database import _wal_safe_backup, _backup_is_sane

    # 模拟 WAL: 关掉自动 checkpoint, 写数据后不合并
    con = sqlite3.connect(legacy_db, isolation_level=None)
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA wal_autocheckpoint=0")
    for i in range(4, 9):
        con.execute(
            "INSERT INTO activities (id, athlete_id, start_time, duration_s, avg_power) "
            "VALUES (?,?,?,?,?)",
            (i, 1, f"2024-06-0{i} 07:30:00", 1000 + i, 200 + i),
        )
    con.close()
    # 不做任何 checkpoint

    wal = legacy_db.with_name(legacy_db.name + "-wal")
    dest = legacy_db.parent / "wal_backup_test.sqlite"
    if dest.exists():
        dest.unlink()
    _wal_safe_backup(legacy_db, dest)

    assert dest.exists() and dest.stat().st_size > 0
    assert _backup_is_sane(dest), "备份里没有 activities 表 = 空备份"
    c = sqlite3.connect(dest)
    try:
        n = c.execute("SELECT COUNT(*) FROM activities").fetchone()[0]
    finally:
        c.close()
    assert n == 8, f"备份只拿到 {n} 条, 应该是 8 条 (含 WAL 里未落盘的 5 条)"
    dest.unlink()
    for p in (wal, legacy_db.with_name(legacy_db.name + "-shm")):
        if p.exists():
            p.unlink()
