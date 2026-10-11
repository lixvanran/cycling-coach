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
    # 🔴 V0.9.1 期望值更新: 原来断言 athlete_name == "演示车手",
    # 隐含前提是"demo 会新建一个专属车手" —— 而那正是用户报的 P0:
    # demo 挂在 #2, 所有只读 API 只读 #1, 界面永远"零数据"。
    #
    # 现在 demo **复用库里第一个车手**(名字保持用户自己填的),
    # 所以:
    #   - 不该再新建第二个车手(下面断言库里只有一个)
    #   - 活动/课表必须落在这个车手名下 —— 那才是"界面看得见"
    assert body["athlete_name"] == "张三", (
        f"demo 应该复用第一个车手(张三), 实际是 {body['athlete_name']!r}"
    )

    # 库里只能有一个车手: 出现第二个就意味着"数据挂上去但界面读不到"
    assert db.query(ps.Athlete).count() == 1, (
        "载入 demo 后出现了第二个车手 —— "
        "数据会挂到它上面, 而界面读的是第一个"
    )
    demo = db.query(ps.Athlete).first()
    assert demo is not None
    # FTP 沿用用户的(250), 没被 demo 的 280 覆盖 —— 用户填的值优先
    assert demo.ftp == 250, f"用户自己的 FTP 被覆盖了: {demo.ftp}"
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
    # 🔴 V0.9.1 期望值更新: 原来这里断言"名下仍然只有 1 条"。
    #
    # 那条期望背后的隐含前提是"demo 数据挂在**另一个** athlete(#2)上" ——
    # 而那正是用户报的 P0: 数据写进去了, 所有只读 API 却只读 #1,
    # 界面永远显示"还没有训练数据"。
    #
    # V0.9.1 的修法是让 demo **复用库里第一个车手**, 于是:
    #     46 = 1 条用户真实 + 45 条 demo(8 周)
    #
    # 所以现在要断言的是**用户那条还在**(而不是"总数 == 1"),
    # 并且 demo 数据确实落在**同一个车手**下 —— 那才是"界面看得见"的含义。
    acts = db.query(Activity).filter(Activity.athlete_id == my_id).all()
    assert len(acts) > 1, (
        f"demo 数据没和用户数据落在同一个车手上 -> 界面看不到 "
        f"(当前 {len(acts)} 条)"
    )
    assert any(a.tss == 80 and a.distance_m == 20000 for a in acts), \
        "用户自己那条活动被 demo 载入弄丢了 —— 那是数据丢失"


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
    r1 = c.post("/api/demo/load", json={"weeks": 8, "force": True})
    assert r1.status_code == 200, r1.text[:200]
    r2 = c.post("/api/demo/load", json={"weeks": 8, "force": True})
    assert r2.status_code == 200, f"第二次挂了: {r2.text[:200]}"
    # 不该翻倍
    assert r2.json()["n_activities"] == r1.json()["n_activities"], (
        "重复载入让活动数翻倍了 —— force 应该是替换不是追加"
    )


# ═══════════════════════════════════════════════════════════════
# 🔴 V0.9.1 用户 Windows 真机实测发现的 P0: 点了"先看示例"之后
#    界面还是"零数据"。这里把根因和两个分支都钉死。
#
#    根因: demo 数据按名字新建"演示车手"(#2), 而所有只读 API 走
#    get_or_create_athlete() -> 永远返回库里第一个(#1)。
#    数据写进去了, 界面读的是另一个档案 —— 而且 HTTP 200, 静默失败。
#
#    真实触发链(所以不是边缘情况):
#      打开产品 -> 任何一次 API 调用建出占位车手 #1
#      -> 点"先看示例" -> 数据挂 #2 -> 界面显示"还没有训练数据"
# ═══════════════════════════════════════════════════════════════


def test_demo_data_is_visible_when_placeholder_athlete_exists():
    """🔴 回归: 占位车手已存在时, 点"先看示例"后界面必须能看到数据。

    这是用户报的核心 bug。之前只测过"数据库里有行",
    没测过"用户真的能在界面看到" —— 而后者才是坏的。
    """
    import datetime
    from tests.conftest import use_temp_db
    use_temp_db("v090_demo_visible")
    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from cycling_coach.api.main import app
    from cycling_coach.core.profile import store as ps
    from cycling_coach.data.sqlite.models import Activity, Athlete

    db = SessionLocal()
    rebind_engine(str(db.get_bind().url))
    a = ps.get_or_create_athlete(db)
    db.add(Activity(athlete_id=a.id, source="fit", file_name="我的真实骑行.fit",
                    start_time=datetime.datetime(2026, 10, 1, 8, 0),
                    duration_s=3600, distance_m=25000))
    db.commit()

    c = TestClient(app)
    r = c.post("/api/demo/load", json={"weeks": 2, "force": True})
    assert r.status_code == 200, r.text[:300]

    # 🔴 核心断言: 界面读的那个接口必须能看到 demo 数据
    total = c.get("/api/activities").json().get("total")
    assert total is not None and total > 0, (
        "点了'先看示例'但 /api/activities 仍是空 —— "
        "demo 数据写到了别的 athlete 上, 界面看不见"
    )

    # 只读侧和写入侧必须是同一个 athlete
    db2 = SessionLocal()
    rebind_engine(str(db2.get_bind().url))
    n_ath = db2.query(Athlete).count()
    assert n_ath == 1, (
        f"载入示例后出现了 {n_ath} 个 athlete —— demo 又新建了第二个车手, "
        "数据挂上去但界面读的是第一个"
    )


def test_demo_load_preserves_user_real_activities():
    """🔴 用户自己的真实训练不能被 demo 覆盖或清掉"""
    import datetime
    from tests.conftest import use_temp_db
    use_temp_db("v090_demo_preserve")
    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from cycling_coach.api.main import app
    from cycling_coach.core.profile import store as ps
    from cycling_coach.data.sqlite.models import Activity

    db = SessionLocal()
    rebind_engine(str(db.get_bind().url))
    a = ps.get_or_create_athlete(db)
    db.add(Activity(athlete_id=a.id, source="fit", file_name="我的真实骑行.fit",
                    start_time=datetime.datetime(2026, 10, 1, 8, 0),
                    duration_s=3600, distance_m=25000))
    db.commit()

    TestClient(app).post("/api/demo/load", json={"weeks": 2, "force": True})

    db2 = SessionLocal()
    rebind_engine(str(db2.get_bind().url))
    kept = [r.file_name for r in db2.query(Activity).all() if r.file_name]
    assert any("我的真实骑行" in (n or "") for n in kept), (
        f"用户的真实活动被 demo 载入弄丢了, 剩下: {kept}"
    )


def test_demo_load_does_not_report_409_after_writing():
    """🔴 回归: 不能"返回 409 说失败, 但数据其实写进去了"。

    这是 V0.9.1 引入的回归: 归属校验原本比较"车手名下活动总数",
    复用第一个车手后用户自己的数据会把它顶到不相等, 于是
    SystemExit -> HTTP 409, 而数据已经入库了 —— 状态自相矛盾。
    """
    import datetime
    from tests.conftest import use_temp_db
    use_temp_db("v090_demo_no409")
    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from cycling_coach.api.main import app
    from cycling_coach.core.profile import store as ps
    from cycling_coach.data.sqlite.models import Activity

    db = SessionLocal()
    rebind_engine(str(db.get_bind().url))
    a = ps.get_or_create_athlete(db)
    db.add(Activity(athlete_id=a.id, source="fit", file_name="我的真实骑行.fit",
                    start_time=datetime.datetime(2026, 10, 1, 8, 0),
                    duration_s=3600, distance_m=25000))
    db.commit()

    c = TestClient(app)
    r = c.post("/api/demo/load", json={"weeks": 2, "force": True})
    assert r.status_code == 200, (
        f"点了'先看示例'返回 {r.status_code} —— 用户会看到'载入失败', "
        "但数据库里其实已经有数据了"
    )
    assert c.get("/api/activities").json().get("total", 0) > 0
