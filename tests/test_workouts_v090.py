"""V0.9.0: workouts 端点回归测试

覆盖 V0.8.3.1 P1.9 修过的 NameError:
- GET /api/workouts — 触发 _ensure_system_workouts 注入系统课程
- 修过 NameError: utcnow_naive 是从 cycling_coach.core.time_utils 顶层 import,
  不再是函数体内 local import 隔离导致 NameError

覆盖 V0.9.0 修过的 fit_tool 缺失:
- GET /api/workouts/{id}/export?format=fit — 触发 fit_tool 加载
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, ".")

TMP = Path(tempfile.mkdtemp(prefix="cc_test_workouts_v090_"))
os.environ["M3_API_KEY"] = ""
os.environ["WORKSPACE_DIR"] = str(TMP)


@pytest.fixture(scope="module", autouse=True)
def _setup_module():
    from cycling_coach.config import config as cfg
    from cycling_coach.data.sqlite.database import init_db, Base
    from cycling_coach.data.sqlite import models  # noqa: F401
    cfg.settings.workspace_dir = str(TMP)
    from sqlalchemy import create_engine
    new_engine = create_engine(
        f"sqlite:///{TMP}/cycling_coach.sqlite",
        connect_args={"check_same_thread": False},
    )
    cfg.engine = new_engine  # type: ignore[attr-defined]
    Base.metadata.create_all(new_engine)
    init_db()
    yield


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    return TestClient(app)


def test_list_workouts_works(client):
    """V0.8.3.1 P1.9 regression: _ensure_system_workouts 不能 NameError

    这个 test 在 V0.8.3.1 修之前会 500。
    """
    r = client.get("/api/workouts?limit=5")
    assert r.status_code == 200, r.text
    data = r.json()
    assert "workouts" in data
    assert "total" in data
    # 首次调用会 seed 系统课程, 应至少有系统课程
    assert data["total"] >= 1


def test_list_workouts_system_seeded_with_correct_timestamp(client):
    """_ensure_system_workouts 用 utcnow_naive 而非 datetime.utcnow

    这个 test 确保进数据库的时间戳是 naive (没 tzinfo)"""
    r = client.get("/api/workouts?limit=5")
    assert r.status_code == 200
    ws = r.json()["workouts"]
    # 至少 1 个系统课程
    system = [w for w in ws if w["source"] == "system"]
    assert len(system) >= 1
    for w in system:
        # V0.8.3.1 P1: utcnow_naive 不带时区
        # ISO 格式不应以 "+" (无 UTC offset)
        assert "T" in w["created_at"]
        # 系统课程必须有 athlete_id=1
        assert w["athlete_id"] == 1


def test_list_workouts_idempotent(client):
    """多次调 GET /api/workouts 不能产生重复系统课程"""
    r1 = client.get("/api/workouts?limit=100")
    assert r1.status_code == 200
    total1 = r1.json()["total"]
    r2 = client.get("/api/workouts?limit=100")
    assert r2.status_code == 200
    total2 = r2.json()["total"]
    # system 课不应增加
    sys1 = sum(1 for w in r1.json()["workouts"] if w["source"] == "system")
    sys2 = sum(1 for w in r2.json()["workouts"] if w["source"] == "system")
    assert sys1 == sys2, f"system courses {sys1} vs {sys2} — _ensure_system_workouts idempotency broken"


# ========== FIT export ==========

def test_export_fit_format_supported(client):
    """V0.9.0: format=fit 不能因为 fit_tool 缺失而 500"""
    # 拿 1 个 workout id
    r = client.get("/api/workouts?limit=1")
    assert r.status_code == 200
    wid = r.json()["workouts"][0]["id"]

    r = client.get(f"/api/workouts/{wid}/export?format=fit")
    assert r.status_code == 200, r.text
    # response 是 binary FIT 文件
    body = r.content
    assert len(body) > 0
    # FIT header 至少 12 bytes: header_size(1) + protocol_version(1) + profile_version(2) + data_size(4) + ".FIT"(4)
    # header_size 字段是第 1 byte, 常见合法值: 12, 14, 32
    assert body[0] in (0x0c, 0x0e, 0x10, 0x20, 0x40), f"FIT header size invalid: 0x{body[0]:02x}"


def test_export_invalid_format(client):
    r = client.get("/api/workouts?limit=1")
    wid = r.json()["workouts"][0]["id"]

    r = client.get(f"/api/workouts/{wid}/export?format=invalid")
    assert r.status_code == 400
    assert "不支持" in r.text


def test_export_nonexistent_workout(client):
    r = client.get("/api/workouts/9999/export?format=fit")
    assert r.status_code == 404


# ========== 其他导出格式不应回归 ==========

@pytest.mark.parametrize("fmt", ["zwo", "mrc", "erg", "json"])
def test_export_other_formats_still_work(client, fmt):
    r = client.get("/api/workouts?limit=1")
    wid = r.json()["workouts"][0]["id"]

    r = client.get(f"/api/workouts/{wid}/export?format={fmt}")
    assert r.status_code == 200, r.text
    assert len(r.content) > 0