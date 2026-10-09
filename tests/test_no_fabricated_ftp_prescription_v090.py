"""V0.9.0-09: 训练处方绝不能按编造的 FTP 来开

## 独立审查端到端打穿的漏洞

`api/routers/phases.py` 里是:

    current_ftp = latest_ftp.ftp_w if latest_ftp else 250

一个**从没测过 FTP** 的用户打这个接口, 拿到:

    current_ftp: 250
    plan 里 7 个节点的 ftp_target 全部 = 250

也就是**一份按编造 FTP 开的完整比赛训练计划**, 而且那个 250
明晃晃写在 API 响应里。用户照着它训练, 每一天的强度都是错的。

同类还有 4 处, 其中 `race_prep.py` 是 **falsy-zero** 的反向版本:

    current_ctl = pcm.get("ctl", 60) or 60      # ctl=0 是 falsy -> 变成 60

以及 `erg.py` 的 `ftp: int = 250` —— 导出的骑行台课程
每一段瓦数都按 FTP 乘, 默认值 250 意味着导出一份强度全错的课。

## 为什么这条是 P0

前端显示"基于 FTP 250W"最多是**误导**。
后端这个是**直接生成处方** —— 差别是量级。

## 双向: 不许拦掉真实用户

没 FTP 要拒绝, 但**有 FTP 的用户必须一切照旧**。
"""
from __future__ import annotations


def _client_with_ftp(ftp=None, estimated=None):
    from tests.conftest import use_temp_db
    import uuid
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as ps
    from datetime import date, timedelta

    use_temp_db(f"v090_ftp_pres_{uuid.uuid4().hex[:6]}")
    db = SessionLocal()
    a = ps.get_or_create_athlete(db)
    a.ftp = ftp
    a.ftp_estimated = estimated
    db.commit()
    c = TestClient(app)
    race_date = (date.today() + timedelta(days=60)).isoformat()
    return c, race_date, a


def test_race_plan_refuses_without_ftp():
    """🔴 核心: 没测过 FTP 的用户不能拿到按 250 开的计划"""
    c, race_date, a = _client_with_ftp(ftp=None, estimated=None)
    r = c.get(f"/api/phases/race-plan?race_date={race_date}&race_name=T&distance=100")
    assert r.status_code == 400, (
        f"零 FTP 用户拿到 {r.status_code}, 响应里有编造的 FTP: {r.text[:200]}"
    )
    assert "250" not in r.text, "响应里仍然出现 250"
    assert "FTP" in r.text, "错误提示要说清缺的是什么"


def test_race_plan_still_works_with_real_ftp():
    """反向: 有真实 FTP 的用户必须照常拿到计划(别把正常人拦了)"""
    c, race_date, a = _client_with_ftp(ftp=300)
    r = c.get(f"/api/phases/race-plan?race_date={race_date}&race_name=T&distance=100")
    assert r.status_code == 200, f"有真实 FTP 却被拦了: {r.status_code} {r.text[:200]}"
    d = r.json()
    assert d.get("current_ftp") == 300, f"current_ftp={d.get('current_ftp')}, 应为 300"
    assert d.get("current_ftp_is_estimate") is False


def test_race_plan_marks_estimated_ftp():
    """只有估算值时: 可以出计划, 但必须标明是估算"""
    c, race_date, a = _client_with_ftp(ftp=None, estimated=280)
    r = c.get(f"/api/phases/race-plan?race_date={race_date}&race_name=T&distance=100")
    assert r.status_code == 200, f"有估算值应该能出计划: {r.text[:150]}"
    d = r.json()
    assert d.get("current_ftp_is_estimate") is True, (
        "用了估算 FTP 却不标明 —— 用户会以为那是实测值"
    )


def test_tsb_target_refuses_zero_ctl():
    """🔴 falsy-zero: 零训练用户拿到过 current_ctl=60 的完整减量计划"""
    c, race_date, a = _client_with_ftp(ftp=300)
    r = c.get(f"/api/race-prep/tsb-target?race_type=tt&race_date={race_date}")
    assert r.status_code == 400, (
        f"零训练用户拿到 {r.status_code} —— 会按 CTL=60 生成减量计划, "
        f"而他其实从没有过任何训练。响应: {r.text[:200]}"
    )


def test_erg_export_refuses_without_ftp():
    """🔴 导出骑行台课程: 没 FTP 就别导出一份强度全错的"""
    from cycling_coach.core.exporters.erg import export_erg
    try:
        export_erg("t", "d", [{"minutes": 60, "watts": 200}], ftp=None)
    except ValueError as e:
        assert "FTP" in str(e)
    else:
        raise AssertionError("ftp=None 竟然导出了课程 —— 强度全是错的")
