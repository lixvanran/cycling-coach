"""V0.9.0: AI 上下文完整性 —— 上下文缺一个字段, 模型就会编一个

## 实测踩出来的三个问题

用一个真实的 8 周训练库 (CTL 43.1 / ATL 45.7 / TSB -2.6 / FTP 280)
问 M3 "我今天状态怎么样? 该练什么?", 它这样答:

1. **Z2 功率区间说成 196-224W** —— 那是 70%-80% FTP, 实际是 Z3 节奏区。
   正确的 Z2 是 154-210W。**车友照着这个数骑, 以为是轻松恢复骑,
   实际一直在踩节奏区。**
2. **说 "ramp_rate+0.00, 维持期, 没有在加量也没有掉量"** ——
   当时上下文里压根没有 ramp_rate 这个字段, 真实值是 -3.46 (负荷在下降)。
   它编了一个, 而且说得非常笃定。
3. **上下文里压根没有 zones_w**, 提示词却写着"查 zones_w 表,
   不要自己乘百分比" —— 规则和它依赖的数据没同时到位, 那条规矩等于空文。

## 根因

不是模型笨, 是**我们没给它它要的东西**。
上下文里缺一个字段, 模型就用"听起来合理"的话把它补上 ——
而且补得比真值还像真的, 因为它符合常识。

AI 给错训练强度的代价比不给还大: 用户会照着骑。

## 本文件锁死

- AI 上下文里的 PMC 值必须和 /api/pmc/today 一致
- ramp_rate / status_label 必须在上下文里 (曾经缺席)
- 功率区间表必须在上下文里, 且与 core/metrics/power.py 同源
- 区间表必须真的进了 prompt (不只是存在于 context dict 里)
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest


@pytest.fixture(scope="module", autouse=True)
def _db():
    from tests.conftest import use_temp_db
    use_temp_db("ai_context")


def _seed(db):
    """造一个典型的训练中车手: PMC 有意义, FTP 已设定"""
    from cycling_coach.core.pmc import recompute_pmc
    from cycling_coach.data.sqlite.models import Activity, Athlete

    a = db.query(Athlete).first()
    if a is None:
        a = Athlete(name="上下文测试", ftp=280, lthr=168, max_hr=188, weight_kg=68.0)
        db.add(a)
        db.commit()
        db.refresh(a)

    base = datetime.now().date() - timedelta(days=42)
    for i in range(20):
        d = base + timedelta(days=i * 2)
        db.add(Activity(
            athlete_id=a.id, source="test", file_name=f"r{i}.fit",
            start_time=datetime.combine(d, datetime.min.time()) + timedelta(hours=6),
            duration_s=5400, distance_m=45000.0, avg_power=205,
            metrics={"tss": 60 + (i % 5) * 12},
        ))
    db.commit()
    recompute_pmc(db, a.id)
    db.commit()
    return a


# ======================================================================
def test_AI上下文的PMC与接口一致():
    """上下文里的数字必须和用户界面上看到的完全一致

    不一致 = 用户问 AI, AI 报一个数, 回头看界面是另一个数。
    那种不信任一次就永久建立。
    """
    from cycling_coach.core.coaching import context as C
    from cycling_coach.core.pmc import get_pmc_today
    from cycling_coach.data.sqlite import database as D

    db = D.SessionLocal()
    try:
        a = _seed(db)
        api = get_pmc_today(db, a.id)          # 接口给用户的
        ctx = C.build_pmc_context(db, a.id)   # AI 看到的
        for k in ("ctl", "atl", "tsb", "tss_today"):
            api_v = api.get(k) if isinstance(api, dict) else getattr(api, k, None)
            assert ctx.get(k) == api_v, (
                f"{k}: 接口报 {api_v}, AI 上下文却是 {ctx.get(k)} —— "
                f"AI 会照着错数字给建议"
            )
    finally:
        db.close()


def test_ramp_rate在上下文里():
    """曾经缺席 → 模型编了一个 +0.00

    实测原话: "ramp_rate+0.00: 维持期, 没有在加量也没有掉量",
    而真实值是负的 (减量周)。**它编得比真值还合理。**
    """
    from cycling_coach.core.coaching import context as C
    from cycling_coach.data.sqlite import database as D

    db = D.SessionLocal()
    try:
        a = _seed(db)
        ctx = C.build_pmc_context(db, a.id)
        assert "ramp_rate" in ctx, "ramp_rate 不在 AI 上下文里 → 模型会编一个"
        assert ctx["ramp_rate"] is not None, "ramp_rate 是 None"
        assert "status_label" in ctx, "status_label 缺失"
    finally:
        db.close()


def test_功率区间表在上下文里且数值正确():
    """曾经完全缺失 → 模型把 Z2 说成 Z3

    区间不能靠模型心算 —— 它算错过, 而且错得很像真的。
    """
    from cycling_coach.core.coaching.context import power_zone_ranges_w

    zones = power_zone_ranges_w(280)
    got = {z["zone"]: z for z in zones}
    assert len(zones) == 7, f"应该是 7 个区间, 实际 {len(zones)}"
    # Coggan 标准 @ FTP 280
    assert got["Z2"]["watts_from"] == 154 and got["Z2"]["watts_to"] == 210, (
        f"Z2 应为 154-210W, 实际 {got['Z2']['watts']} —— "
        f"这就是被说成 196-224W 的那个区间"
    )
    assert got["Z4"]["watts_from"] == 252 and got["Z4"]["watts_to"] == 294
    assert got["Z7"]["watts_to"] is None, "Z7 是无上限区, 不该编一个上限"


def test_区间表与指标模块同源():
    """区间边界必须只有一份定义, 不允许各处抄一份

    这条第一版是**无效测试**: 它 import 了 power_zones 却没用,
    只在测 context.py 自己的常量 —— 而"同源"恰恰是我要验的东西,
    却根本没和 power.py 比。断言全绿, 什么都没保证。

    现在的做法: 直接拿 COGGAN_7_ZONES 逐项比, 任何一边改了都会被抓住。
    """
    from cycling_coach.core.coaching.context import power_zone_ranges_w
    from cycling_coach.core.metrics.power import COGGAN_7_ZONES

    ftp = 280
    ctx_rows = power_zone_ranges_w(ftp)
    assert len(ctx_rows) == len(COGGAN_7_ZONES), (
        f"区间数量不一致: context {len(ctx_rows)} vs power {len(COGGAN_7_ZONES)}"
    )
    for src, got in zip(COGGAN_7_ZONES, ctx_rows):
        assert got["zone"] == src["code"]
        assert got["name_en"] == src["name"], (
            f"{src['code']} 英文名不一致: {got['name_en']} vs {src['name']}"
        )
        assert got["watts_from"] == round(ftp * src["lo"]), (
            f"{src['code']} 下界对不上 power.py: "
            f"{got['watts_from']} vs {round(ftp*src['lo'])}"
        )
        if src["code"] == "Z7":
            assert got["watts_to"] is None, "Z7 应为无上限"
        else:
            assert got["watts_to"] == round(ftp * src["hi"]), (
                f"{src['code']} 上界对不上 power.py: "
                f"{got['watts_to']} vs {round(ftp*src['hi'])}"
            )


def test_提示词规则指向模型真能看到的东西():
    """规则必须引用**渲染后 prompt 里真有的**东西, 而不是 Python 侧的标识符

    Verifier 抓到的: 我第一版规则里写"查数据里的 zones_w 表"和
    "区间 watts_to 为 null", 但 `zones_w` 是 dict key、`watts_to` 是字段名,
    **两者都从没进过 prompt** —— 模型无从按名解析, 抗编造规则直接打折。

    现在的规则措辞必须是 prompt 里真实出现的标题 (「上下文」「功率区间」)。
    """
    from cycling_coach.ai.prompts.chat import CHAT_USER_HEADER

    h = CHAT_USER_HEADER
    # 规则在
    assert "不许" in h or "禁止" in h, "提示词里没有'缺数据不许编'的硬规则"
    # 规则指向的东西也必须在 (这两个标题是 _format_* 真实渲染出来的)
    assert "功率区间" in h, "规则提到的『功率区间』标题不存在"
    assert "上下文" in CHAT_USER_HEADER, "规则提到的『上下文』标题不存在"
    # 不能再引用只存在于 Python 侧的标识符
    assert "zones_w" not in h, (
        "规则里又出现 zones_w —— 那是 Python dict key, 从没进过 prompt, "
        "模型按名解析不到"
    )
    assert "watts_to" not in h, "watts_to 是字段名, 从没进过 prompt"


def test_界面分区与AI区间真的一致():
    """真端到端: 造一条功率恰好落在 Z1/Z2 边界上的训练,
    用应用真正的 power_zones() 算, 断言分界和 power_zone_ranges_w 说的在同一处。

    这一条替换掉了原来的假版本 —— 那条自称"端到端", 实际在测试文件里
    又抄了第三份 Coggan 边界、从未调用过 power_zones。变异测试证明:
    把应用真正的 bins 改偏 1%, 那条测试连同其他 6 条一起全绿,
    **等于没有提供任何保证**。
    """
    import numpy as np

    from datetime import datetime

    from cycling_coach.core.coaching.context import power_zone_ranges_w
    from cycling_coach.core.metrics.power import power_zones
    from cycling_coach.data.parsers.schema import Activity, Sample

    ftp = 280
    zones = {z["zone"]: z for z in power_zone_ranges_w(ftp)}

    # 分别在 Z2 上下各取一个功率, 造一分钟的训练
    lo = zones["Z2"]["watts_from"] - 1     # 低于 Z2 下界 -> 应落 Z1
    hi = zones["Z2"]["watts_from"] + 1     # 高于 Z2 下界 -> 应落 Z2
    for power, want, label in ((lo, "Z1", "低于"), (hi, "Z2", "高于")):
        samples = [Sample(t_offset=i, power=power, hr=140, cadence=85)
                   for i in range(60)]
        act = Activity(source="test", start_time=datetime(2026, 1, 1),
                       duration_s=60, samples=samples)
        got = power_zones(act, ftp)
        assert got.get(want) == 60, (
            f"{label} Z2 下界({zones['Z2']['watts_from']}W)的 {power}W "
            f"应落在 {want} 60 秒, 实际 {got}"
        )


def test_区间随FTP缩放():
    """函数存在的意义就是随 FTP 缩放, 只测 FTP=280 等于没测入参

    变异测试: 让 power_zone_ranges_w 忽略入参恒返回 280 的结果,
    只测 280 的三个用例全绿。这条在那个变异下必红。
    """
    from cycling_coach.core.coaching.context import power_zone_ranges_w

    for ftp in (150, 200, 280, 305):
        zones = {z["zone"]: z for z in power_zone_ranges_w(ftp)}
        assert zones["Z2"]["watts_from"] == round(ftp * 0.55), (
            f"FTP={ftp}: Z2 下界应为 {round(ftp*0.55)}W, "
            f"实际 {zones['Z2']['watts_from']}W —— 函数没按入参缩放"
        )
        assert zones["Z2"]["watts_to"] == round(ftp * 0.75)
        assert zones["Z7"]["watts_to"] is None


def test_无上限判定跟着数据走():
    """原来靠硬编码区号 (code == "Z7") 判无上限。

    真正的语义是 power.py 里的哨兵值 hi=9.99。一旦加 Z8 或修正哨兵,
    硬编码那行会静默翻出假上限 (280*9.99=2797W) —— 正是要避免的事。
    """
    import inspect

    from cycling_coach.core.coaching import context as ctx_mod

    src = inspect.getsource(ctx_mod.power_zone_ranges_w)
    assert 'code == "Z7"' not in src, (
        "无上限判定还在硬编码区号, 应改成跟着数据走 (hi >= 9.99)"
    )
