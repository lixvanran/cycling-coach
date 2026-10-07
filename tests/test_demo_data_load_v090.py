"""V0.9.0: "先看示例"必须真的能跑通（API 路径）

## 这条路径是新用户的主入口

零数据第一屏就摆着「先看示例」按钮。它挂了 = 新用户第一眼就看到报错。

## 我在这条路径上踩了五次

1. `ActivityService` 硬绑"库里第一个车手" → 归属不一致
2. 占位车手只按名字 `"Rider"` 找 → 用户改过名就清不掉
3. 只清 3 张表就删车手 → 另外 10 张外键悬空
4. `db.expunge_all()` 把 session 里**所有**对象踢出去 → not bound
5. **删完对象再读它的属性** → DetachedInstanceError

## 最要命的一条: CLI 能过, API 500

第 4 次的 `expunge_all` 在 CLI 下完全正常 —— 因为 CLI 是新进程新 session,
里面没有别的对象。API 路径的 session 里已经加载过 athlete, 于是只有它挂。

> **"命令行跑通了"不等于修好了。** 所以这条测试打的是 API 端点,
> 不是函数。
"""
from __future__ import annotations


def test_demo_load_endpoint_succeeds_on_api_path():
    """🔴 端点级: 零数据 + 有占位车手 → 必须 200 且真有数据"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_demo_api")
    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from cycling_coach.api.main import app
    from cycling_coach.core.profile import store as ps
    from cycling_coach.data.sqlite.models import Activity, PlannedWorkout

    db = SessionLocal()
    # 造一个占位车手(并改掉名字 —— 原来只按 "Rider" 找占位, 改名就清不掉)
    a = ps.get_or_create_athlete(db)
    a.name = "张三"
    a.ftp = 250
    db.commit()
    rebind_engine(str(db.get_bind().url))

    r = TestClient(app).post("/api/demo/load",
                             json={"weeks": 8, "force": True})
    assert r.status_code == 200, f"示例数据载入失败: {r.text[:200]}"
    body = r.json()
    assert body["ok"] is True
    assert body["n_activities"] > 0, "说成功了但一条活动都没有"
    assert body["n_planned"] > 0
    assert body["athlete_name"] == "演示车手", "演示车手没建起来"

    # 活动必须挂在演示车手名下, 不是占位车手
    demo = db.query(ps.Athlete).filter(
        ps.Athlete.name == "演示车手").first()
    assert demo is not None
    assert demo.ftp == 280, f"演示车手 FTP={demo.ftp}"
    acts = db.query(Activity).filter(Activity.athlete_id == demo.id).count()
    assert acts == body["n_activities"], "活动数对不上"
    pw = db.query(PlannedWorkout).filter(
        PlannedWorkout.athlete_id == demo.id).count()
    assert pw == body["n_planned"]


def test_demo_load_keeps_users_own_data():
    """🔴 有数据的用户车手绝不能被当成"空车手"删掉"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_demo_keep")
    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from cycling_coach.api.main import app
    from cycling_coach.core.profile import store as ps
    from cycling_coach.data.sqlite.models import Activity
    from datetime import datetime

    db = SessionLocal()
    me = ps.get_or_create_athlete(db)
    me.name = "李四"
    me.ftp = 240
    db.commit()
    db.add(Activity(athlete_id=me.id, start_time=datetime(2026, 9, 1, 6, 0),
                    duration_s=3600, distance_m=20000, tss=80,
                    avg_power=180, max_power=400, avg_hr=140, max_hr=165,
                    source="fit"))   # NOT NULL, 我第一版漏了
    db.commit()
    my_id = me.id
    rebind_engine(str(db.get_bind().url))

    r = TestClient(app).post("/api/demo/load",
                             json={"weeks": 8, "force": True})
    assert r.status_code == 200, r.text[:200]

    still = db.query(ps.Athlete).get(my_id)
    assert still is not None, "有活动的用户车手被删了 —— 那是数据丢失"
    assert still.name == "李四"
    assert db.query(Activity).filter(Activity.athlete_id == my_id).count() == 1


def test_demo_load_is_repeatable():
    """🔴 连续点两次不能炸（用户会反复试）"""
    from tests.conftest import use_temp_db
    use_temp_db("v090_demo_twice")
    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from cycling_coach.api.main import app

    db = SessionLocal()
    rebind_engine(str(db.get_bind().url))
    c = TestClient(app)
    r1 = c.post("/api/demo/load", json={"weeks": 4, "force": True})
    assert r1.status_code == 200, r1.text[:200]
    r2 = c.post("/api/demo/load", json={"weeks": 4, "force": True})
    assert r2.status_code == 200, f"第二次挂了: {r2.text[:200]}"
    # 不该翻倍
    assert r2.json()["n_activities"] == r1.json()["n_activities"], (
        "重复载入让活动数翻倍了 —— force 应该是替换不是追加"
    )
