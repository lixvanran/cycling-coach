"""V0.8.1 批 2: IDOR 防护测试

每个 service 的 ID 类操作, 都强制 scope 到当前 athlete。
本测试创建 2 个 athlete, 互相访问对方资源, 应该都失败。
"""
from __future__ import annotations
from datetime import datetime
import pytest
from sqlalchemy.orm import Session

from cycling_coach.core.services.activity import ActivityService
from cycling_coach.core.services.training import TrainingService
from cycling_coach.core.services.ftp import FTPService
from cycling_coach.core.services.race_tactics import RaceTacticsService
from cycling_coach.data.sqlite.models import (
    Athlete, Activity, PlanPeriod, Workout, FTPTest, RaceTacticsSession,
)
from cycling_coach.core.exceptions import NotFoundError


def _create_athlete(db: Session, name: str) -> Athlete:
    """跳过 profile_store.get_or_create_athlete, 直接造第 2 个 athlete"""
    a = Athlete(name=name)
    db.add(a)
    db.commit()
    db.refresh(a)
    return a


def _swap_athlete(svc, new_athlete: Athlete):
    """绕过 profile_store.get_or_create_athlete 的固定逻辑,
    直接换 service 的 self.athlete 属性, 模拟 '当前用户是 new_athlete'。
    单用户 MVP 下, 真实调用链都是用 get_or_create 返回的 athlete;
    这里为了 IDOR 测试, 强制切换测试两个 athlete 上下文。
    """
    svc.athlete = new_athlete


@pytest.fixture(scope="module", autouse=True)
def _setup_module():
    """V0.9.0: 这个文件之前完全没有隔离 — 直接 init_db() 打真实 workspace DB

    跟其他测试文件一起跑时会因为 `readonly database` / 数据互相污染而全挂。
    改成 conftest.use_temp_db() + function 级 DB 重建。
    """
    from tests.conftest import use_temp_db
    use_temp_db("idor_v081")
    yield


@pytest.fixture
def db():
    """每个 test 一个全新 DB — IDOR 测试最怕数据串味

    V0.9.0: 原来复用 module 级 DB, 6 个 test 之间 athlete 越建越多,
    `profile_store` 的 `Athlete.query.first()` 会拿到别的 test 建的 athlete。
    """
    import uuid
    from tests.conftest import use_temp_db
    from cycling_coach.data.sqlite.database import SessionLocal

    use_temp_db(f"idor_fn_{uuid.uuid4().hex[:8]}")
    s = SessionLocal()
    yield s
    s.close()


def test_activity_idor_cross_user(db):
    """Alice 创建一个活动, Bob 用同样 ID 查不到"""
    alice = _create_athlete(db, "Alice")
    bob = _create_athlete(db, "Bob")
    # 直接造 1 个活动 (绕过 upload parser, 测试只关注 IDOR 路径)
    a = Activity(
        athlete_id=alice.id,
        start_time=datetime(2024, 6, 1, 8, 0, 0),
        duration_s=3600,
        distance_m=30000.0,
        avg_power=200,
        normalized_power=210,
        avg_hr=145,
        avg_cadence=90,
        tss=70,
        source="test",
    )
    db.add(a)
    db.commit()
    db.refresh(a)
    alice_activity_id = a.id

    # Bob 试图访问 Alice 的活动 ID
    svc_bob = ActivityService(db)
    _swap_athlete(svc_bob, bob)
    with pytest.raises(NotFoundError):
        svc_bob.get_activity(alice_activity_id)
    with pytest.raises(NotFoundError):
        svc_bob.delete_activity(alice_activity_id)
    with pytest.raises(NotFoundError):
        svc_bob.update_rpe(alice_activity_id, {"rpe": 5})


def test_list_activities_only_own(db):
    """list_activities 只返回当前 athlete 的活动"""
    alice = _create_athlete(db, "Alice")
    bob = _create_athlete(db, "Bob")
    # Alice 造 1 个活动
    a = Activity(
        athlete_id=alice.id, start_time=datetime(2024, 6, 1, 8, 0, 0),
        duration_s=3600, distance_m=30000.0, source="test",
    )
    db.add(a)
    db.commit()
    # Bob 列表 (空)
    svc_b = ActivityService(db)
    _swap_athlete(svc_b, bob)
    from cycling_coach.core.services.activity import ActivityFilters
    res = svc_b.list_activities(ActivityFilters(limit=50))
    assert res["total"] == 0
    # Alice 列表 (1 个)
    svc_a = ActivityService(db)
    _swap_athlete(svc_a, alice)
    res = svc_a.list_activities(ActivityFilters(limit=50))
    assert res["total"] == 1


def test_plan_idor(db):
    alice = _create_athlete(db, "Alice")
    bob = _create_athlete(db, "Bob")
    svc_a = TrainingService(db)
    _swap_athlete(svc_a, alice)
    p = svc_a.create_plan(__import__("cycling_coach.core.services.training", fromlist=["PlanCreate"]).PlanCreate(
        name="Alice 计划", period_type="base",
        start_date="2024-06-01", end_date="2024-08-31",
    ))
    alice_plan_id = p["id"]
    svc_b = TrainingService(db)
    _swap_athlete(svc_b, bob)
    with pytest.raises(NotFoundError):
        svc_b.get_plan(alice_plan_id)
    with pytest.raises(NotFoundError):
        svc_b.delete_plan(alice_plan_id)


def test_workout_user_only_modify_own(db):
    """用户课程: Alice 创建, Bob 不能改/删"""
    alice = _create_athlete(db, "Alice")
    bob = _create_athlete(db, "Bob")
    svc_a = TrainingService(db)
    _swap_athlete(svc_a, alice)
    w = svc_a.create_workout(__import__("cycling_coach.core.services.training", fromlist=["WorkoutCreate"]).WorkoutCreate(
        title="Alice 课程", goal="endurance", intensity="Z2",
        duration_min=60, structure=[], tags=[], description="", is_template=False,
    ))
    wid = w["id"]
    svc_b = TrainingService(db)
    _swap_athlete(svc_b, bob)
    from cycling_coach.core.services.training import WorkoutUpdate
    with pytest.raises(NotFoundError):
        svc_b.update_workout(wid, WorkoutUpdate(title="hack"))
    with pytest.raises(NotFoundError):
        svc_b.delete_workout(wid)
    # 但 get_workout 读自己的 / 系统的都允许 → Alice 的课程 Bob 看不到
    with pytest.raises(NotFoundError):
        svc_b.get_workout(wid)


def test_ftp_test_idor(db):
    alice = _create_athlete(db, "Alice")
    bob = _create_athlete(db, "Bob")
    # 直接造一个 FTPTest 绕过 service
    ft = FTPTest(
        athlete_id=alice.id,
        test_date=datetime(2024, 6, 1),
        method="coggan_20min",
        ftp_w=240,
        hr_bpm=165,
        weight_kg=68.0,
        notes="",
    )
    db.add(ft)
    db.commit()
    db.refresh(ft)
    alice_test_id = ft.id
    svc_b = FTPService(db)
    _swap_athlete(svc_b, bob)
    with pytest.raises(NotFoundError):
        svc_b.delete_test(alice_test_id)


def test_race_tactics_idor(db):
    alice = _create_athlete(db, "Alice")
    bob = _create_athlete(db, "Bob")
    s = RaceTacticsSession(
        athlete_id=alice.id,
        race_name="Alice race",
        race_date=datetime(2024, 8, 1),
        distance_km=80.0,
        elevation_gain_m=1200,
        race_type="road",
        priority="A",
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    alice_sid = s.id
    svc_b = RaceTacticsService(db)
    _swap_athlete(svc_b, bob)
    with pytest.raises(NotFoundError):
        svc_b.get_session(alice_sid)
    with pytest.raises(NotFoundError):
        svc_b.delete_session(alice_sid)
