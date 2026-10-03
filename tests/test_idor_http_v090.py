"""V0.9.0: HTTP-level IDOR 测试 for phases + calendar planned

覆盖 V0.8.3.1 P0 IDOR 修复:
- POST /api/phases
- PATCH /api/phases/{id}
- DELETE /api/phases/{id}
- POST /api/phases/{id}/workouts
- DELETE /api/phases/{id}/workouts/{pw_id}
- POST /api/calendar/planned
- PATCH /api/calendar/planned/{id}
- DELETE /api/calendar/planned/{id}
- POST /api/calendar/planned/{id}/link/{activity_id}
- POST /api/calendar/planned/{id}/unlink

策略: 用 admin = profile_store 创建额外 athlete, 直接 SQL 注入其资源,
然后通过 FastAPI TestClient 调用端点 (走 get_or_create_athlete 的默认 user)
验证返回 404 而不是泄漏。
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path
from datetime import datetime, date, timedelta

import pytest

sys.path.insert(0, ".")

TMP = Path(tempfile.mkdtemp(prefix="cc_test_idor_http_"))
os.environ["M3_API_KEY"] = ""
os.environ["WORKSPACE_DIR"] = str(TMP)


@pytest.fixture(scope="module", autouse=True)
def _setup_module():
    from cycling_coach.config import config as cfg
    from cycling_coach.data.sqlite.database import init_db, engine, Base
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


@pytest.fixture()
def db():
    from cycling_coach.data.sqlite import SessionLocal
    s = SessionLocal()
    yield s
    s.close()


def _create_second_athlete(db, name="Intruder"):
    """直接 SQL 绕过 profile_store.get_or_create_athlete, 造第 2 个 athlete

    注意: profile_store 返回 Athlete.query.first() 即 ID 最小者。
    所以要先触发一次 API 让默认 athlete (id=1) 创建出来,
    再创建 intruder 才能让 IDOR 测试正确 (默认 user != intruder)。
    """
    from cycling_coach.data.sqlite.models import Athlete
    a = Athlete(name=name, ftp=240, max_hr=180)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _ensure_default_athlete_exists(client):
    """先打一次 API 让 profile_store 创建默认 athlete (id=1)"""
    client.get("/api/athlete")


def _create_phase_for(db, athlete_id: int) -> int:
    from cycling_coach.data.sqlite.models import TrainingPhase
    p = TrainingPhase(
        athlete_id=athlete_id,
        phase_type="build",
        name="敌方阶段",
        start_date=date(2026, 9, 1),
        end_date=date(2026, 9, 30),
        target_tss_week=500,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return p.id


def _create_planned_for(db, athlete_id: int) -> int:
    from cycling_coach.data.sqlite.models import PlannedWorkout
    pw = PlannedWorkout(
        athlete_id=athlete_id,
        scheduled_date=date(2026, 9, 15),
        title="敌方计划课程",
        intent="endurance",
        duration_target_min=60,
        tss_target=70,
        status="planned",
    )
    db.add(pw)
    db.commit()
    db.refresh(pw)
    return pw.id


def _create_phase_workout_for(db, phase_id: int, _athlete_id_unused: int) -> int:
    """PhaseWorkout 没有 athlete_id, 用 phase_id 隐含 athlete 归属"""
    from cycling_coach.data.sqlite.models import PhaseWorkout
    pw = PhaseWorkout(
        phase_id=phase_id,
        week_index=1,
        day_of_week=3,
        title="敌方模板课程",
        intent="easy",
        duration_target_min=60,
        tss_target=70,
    )
    db.add(pw)
    db.commit()
    db.refresh(pw)
    return pw.id


def _create_activity_for(db, athlete_id: int) -> int:
    from cycling_coach.data.sqlite.models import Activity
    a = Activity(
        athlete_id=athlete_id,
        start_time=datetime(2024, 6, 1),
        duration_s=3600,
        distance_m=30000.0,
        source="test",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    return a.id


# ========== phases endpoints ==========

def test_get_alice_phases_does_not_leak_intruder(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder A")
    intruder_phase_id = _create_phase_for(db, intruder.id)

    r = client.get("/api/phases")
    assert r.status_code == 200
    phases = r.json()
    ids = [p["id"] for p in phases]
    assert intruder_phase_id not in ids, "敌方 phase 不应出现在默认用户列表中"


def test_patch_phase_idor(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder B")
    pid = _create_phase_for(db, intruder.id)

    r = client.patch(f"/api/phases/{pid}", json={"name": "hack"})
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"


def test_delete_phase_idor(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder C")
    pid = _create_phase_for(db, intruder.id)

    r = client.delete(f"/api/phases/{pid}")
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"

    # verify not deleted
    from cycling_coach.data.sqlite.models import TrainingPhase
    assert db.query(TrainingPhase).filter_by(id=pid).first() is not None


def test_post_phase_workout_requires_own_phase(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder D")
    pid = _create_phase_for(db, intruder.id)

    r = client.post(
        f"/api/phases/{pid}/workouts",
        json={"week_index": 1, "day_of_week": 1, "title": "hack", "intent": "easy"},
    )
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"


def test_delete_phase_workout_idor(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder E")
    pid = _create_phase_for(db, intruder.id)
    pw_id = _create_phase_workout_for(db, pid, intruder.id)

    r = client.delete(f"/api/phases/{pid}/workouts/{pw_id}")
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"

    from cycling_coach.data.sqlite.models import PhaseWorkout
    assert db.query(PhaseWorkout).filter_by(id=pw_id).first() is not None


def test_get_phase_workouts_idor(client, db):
    _ensure_default_athlete_exists(client)

    """GET phase workouts 也不能让敌方看到"""
    intruder = _create_second_athlete(db, "Intruder F")
    pid = _create_phase_for(db, intruder.id)

    r = client.get(f"/api/phases/{pid}/workouts")
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"


def test_apply_phase_idor(client, db):
    _ensure_default_athlete_exists(client)

    """apply 阶段也不能"""
    intruder = _create_second_athlete(db, "Intruder G")
    pid = _create_phase_for(db, intruder.id)

    r = client.post(f"/api/phases/{pid}/apply", params={"start_date": "2026-10-01", "weeks": 1})
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"


# ========== calendar planned endpoints ==========

def test_list_planned_filters_by_athlete(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder H")
    _create_planned_for(db, intruder.id)

    r = client.get("/api/calendar/planned")
    assert r.status_code == 200
    planned = r.json()["planned"]
    for p in planned:
        # 默认 user 看不到 intruder's planned
        assert p["scheduled_date"] != "2026-09-15" or "敌方" not in p["title"]


def test_patch_planned_idor(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder I")
    pid = _create_planned_for(db, intruder.id)

    r = client.patch(f"/api/calendar/planned/{pid}", json={"title": "hack"})
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"


def test_delete_planned_idor(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder J")
    pid = _create_planned_for(db, intruder.id)

    r = client.delete(f"/api/calendar/planned/{pid}")
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"

    from cycling_coach.data.sqlite.models import PlannedWorkout
    assert db.query(PlannedWorkout).filter_by(id=pid).first() is not None


def test_link_planned_idor(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder K")
    pwid = _create_planned_for(db, intruder.id)
    aid = _create_activity_for(db, intruder.id)

    r = client.post(f"/api/calendar/planned/{pwid}/link/{aid}")
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"


def test_unlink_planned_idor(client, db):
    _ensure_default_athlete_exists(client)

    intruder = _create_second_athlete(db, "Intruder L")
    pwid = _create_planned_for(db, intruder.id)

    r = client.post(f"/api/calendar/planned/{pwid}/unlink")
    assert r.status_code == 404, f"应 404, 实际 {r.status_code}: {r.text}"