"""V0.9.0: pytest 全局测试隔离

## 为什么有这个文件

V0.7.6 ~ V0.9.0 期间, `tests/` 下 6 个测试文件各自这么写"隔离":

    cfg.engine = new_engine          # ← 死代码

但 `cycling_coach/data/sqlite/database.py` 从来没读过 `config.engine`,
真正的 DB 是模块级 `engine` / `SessionLocal` 单例, import 时就按
`settings.workspace_dir` 建好了。后果:

- 谁的测试文件先被 import, 谁决定所有测试共用哪个 DB
- 单独跑某个文件 → 通过 (env `WORKSPACE_DIR` 恰好在 import 前生效)
- 一起跑 → 互相污染 / 写进真实 workspace DB → `readonly database` 报错

V0.9.0 加了 `database.rebind_engine()` 真正重绑整个模块,
这个 conftest 统一收口, 各测试文件不再各写各的。

## 用法

测试文件里删掉自己的 `_setup_module` engine hack, 改成:

    from tests.conftest import use_temp_db

    @pytest.fixture(scope="module", autouse=True)
    def _db():
        use_temp_db()

或者直接用现成 fixture:

    def test_x(isolated_db):
        ...   # isolated_db = 一个已建好表的 db url
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, ".")


# ---------------------------------------------------------------- session 级
# 必须在任何测试模块 import `cycling_coach.data.sqlite.database` 之前设好,
# 否则模块级 engine 会按真实 workspace 路径建出来。
_SESSION_TMP = Path(tempfile.mkdtemp(prefix="cc_pytest_"))
os.environ.setdefault("M3_API_KEY", "")          # 测试不发真实 LLM 请求
os.environ["WORKSPACE_DIR"] = str(_SESSION_TMP)


@pytest.fixture(scope="session")
def session_tmpdir() -> Path:
    return _SESSION_TMP


# ---------------------------------------------------------------- module 级
def use_temp_db(name: str | None = None) -> str:
    """把 database 模块重绑到一个全新的临时 SQLite, 建好表, 返回 db url

    在测试文件的 module 级 autouse fixture 里调用:

        @pytest.fixture(scope="module", autouse=True)
        def _db():
            use_temp_db()
    """
    from cycling_coach.data.sqlite.database import rebind_engine

    slug = (name or "mod").replace("/", "_").replace(" ", "_")
    db_dir = _SESSION_TMP / slug
    db_dir.mkdir(parents=True, exist_ok=True)
    db_url = f"sqlite:///{db_dir / 'test.sqlite'}"

    # settings.workspace_dir 也要跟上, 否则少数走 _db_path() 的代码会跑偏
    from cycling_coach.config import config as cfg
    cfg.settings.workspace_dir = str(db_dir)

    rebind_engine(db_url, create=True)
    return db_url


@pytest.fixture()
def isolated_db():
    """function 级隔离 — 每个 test 一个全新 DB

    比 module 级更干净, 但慢 (每个 test 都建表)。
    适合测"数据会互相影响"的场景 (IDOR / 归属校验)。
    """
    import uuid
    return use_temp_db(f"fn_{uuid.uuid4().hex[:8]}")


@pytest.fixture()
def client():
    """FastAPI TestClient (配合 isolated_db 用)"""
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    return TestClient(app)


@pytest.fixture()
def db():
    """一个已建好表的 SQLAlchemy Session"""
    from cycling_coach.data.sqlite.database import SessionLocal
    s = SessionLocal()
    yield s
    s.close()
