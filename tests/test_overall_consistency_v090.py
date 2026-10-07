"""V0.9.0: 综合分必须等于界面上那五个分项的加权和

## 这条为什么值得单独存在

7cf2df9 修了一个真实 bug: `overall` 用**未舍入**的局部变量算, 而返回给
前端的对象里存的是 `round(x, 1)`。于是 App 显示的总分, 和它自己显示的
五个分项**加不起来**。

我修了, 但三次变异都没杀掉它, 最后标了"未经变异证明"并撤回了测试。
Verifier 独立复审确认:

    INPUTS: ctl=0.1 atl=0.0 tsb=-40.0 ramp_rate=-10.0

              fitness  fatigue   form  rhythm  recovery  overall  parts-sum
    PRE  4746234    0.2     100   10.0   40.0       60     37.0      37.1  ← 对不上
    POST ef5b485    0.2     100   10.0   40.0       60     37.1      37.1

## 为什么随机 fixture 撞不上

舍入差异的上限是 `0.05 * 0.30 = 0.015`。要让 round 的结果翻转, 加权和的
小数点后第二位必须恰好落在 `.x5` 下方 0.015 以内 —— **这个 bug 的可观测
窗口只有 0.015 宽**。

所以必须**显式构造边界输入**, 不能靠造训练数据碰运气。

## 为什么用 stub 而不是真造数据

真造数据要导入 FIT, 慢且会随 fixture 的功率/时长漂移。
这里被测的纯粹是"用哪些值算 overall", 所以直接 stub 掉数据源,
把判定变成**纯函数级的**, 稳定且快。
"""
from __future__ import annotations

# ⚠️ 关于"今天"的时间基准
#
# `get_pmc_today()` 用的是 `date.today()`(**本地时区**), 而这些测试原来用
# `datetime.utcnow().date()`(UTC)。**两者跨 UTC 日界时会差一天** ——
# 于是"今天的 DailyMetric"查不到, has_load_data 变 False, 测试在
# 凌晨(本地)跑红、白天跑绿。
#
# 我为此白查了三轮: 以为是测试污染、以为是全量顺序、以为是自己引入的
# 回归。真相比那都简单: **测试和生产代码对"今天"的定义不一致。**
#
# 教训: 断言涉及"今天"时, 必须用**被测代码同一个**日期来源,
# 不能想当然用 utcnow —— 那个是常见的直觉, 但生产代码不是那么写的。


from datetime import date, datetime, timedelta


def _fake_db_no_activities():
    """最小 db 替身: query(Activity).filter(...).all() 返回空列表"""
    class _Q:
        def filter(self, *a, **k):
            return self

        def all(self):
            return []

        def first(self):
            return None

    class _DB:
        def query(self, *a, **k):
            return _Q()

    return _DB()


# Verifier 给的边界输入 + 几个邻域值, 覆盖 .x5 两侧
BOUNDARY_CASES = [
    # (ctl, atl, tsb, ramp_rate, 期望 overall, 期望分项和)
    (0.1, 0.0, -40.0, -10.0, 37.1, 37.1),   # 经典边界: 修复前 37.0
    (0.1, 0.0, -40.0, -9.5, None, None),    # 邻域, 随回归一起算
    (0.3, 0.0, -40.0, -10.0, None, None),
    (0.0, 0.0, -40.0, -10.0, None, None),
    (0.1, 0.5, -40.0, -10.0, None, None),
]


def _compute(ctl, atl, tsb, ramp, monkeypatch):
    from cycling_coach.core.metrics import race_prep as RP

    monkeypatch.setattr(RP, "get_pmc_today", lambda db, aid: {
        "ctl": ctl, "atl": atl, "tsb": tsb, "ramp_rate": ramp,
        "has_load_data": True, "tss_today": 0,
        "status": "ok", "status_label": "", "status_color": "",
        "date": date.today(),
    })
    return RP.compute_training_state(_fake_db_no_activities(), 1)


def test_overall_equals_shown_parts_at_boundary(monkeypatch):
    """🔴 核心: 边界输入下, 总分必须等于分项加权和"""
    ctl, atl, tsb, ramp, exp_overall, exp_sum = BOUNDARY_CASES[0]

    st = _compute(ctl, atl, tsb, ramp, monkeypatch)
    assert st is not None

    parts_sum = round(
        st.fitness * 0.30 + st.fatigue * 0.20 + st.form * 0.20
        + st.rhythm * 0.15 + st.recovery * 0.15, 1
    )
    assert st.overall == parts_sum, (
        f"总分 {st.overall} 和界面上显示的五个分项(加权 {parts_sum})对不上。"
        f"用户看雷达图会发现分项加不起来。\n"
        f"  fitness={st.fitness} fatigue={st.fatigue} form={st.form} "
        f"rhythm={st.rhythm} recovery={st.recovery}"
    )


def test_overall_equals_shown_parts_across_neighbourhood(monkeypatch):
    """边界邻域也要成立 —— 不是只有那一个点对

    防止"把 overall 硬编码成某个值"这种假修法蒙混过关。
    """
    for ctl, atl, tsb, ramp, _, _ in BOUNDARY_CASES:
        st = _compute(ctl, atl, tsb, ramp, monkeypatch)
        parts_sum = round(
            st.fitness * 0.30 + st.fatigue * 0.20 + st.form * 0.20
            + st.rhythm * 0.15 + st.recovery * 0.15, 1
        )
        assert st.overall == parts_sum, (
            f"ctl={ctl} tsb={tsb} ramp={ramp}: "
            f"overall={st.overall} != 分项和 {parts_sum}"
        )


def test_parts_are_stored_rounded_not_raw(monkeypatch):
    """🔴 存进对象的分项必须已经舍入

    这是 bug 的另一半: 就算 overall 算对了, 如果对象里存的是未舍入值,
    界面渲染出来的数字还是会对不上用户自己算的。
    """
    for ctl, atl, tsb, ramp, _, _ in BOUNDARY_CASES:
        st = _compute(ctl, atl, tsb, ramp, monkeypatch)
        for name in ("fitness", "fatigue", "form", "rhythm", "recovery"):
            v = getattr(st, name)
            assert round(v, 1) == v, (
                f"{name}={v!r} 存的是未舍入值, 界面渲染出来会和对不上的数"
            )


def test_fixture_premise_is_real(monkeypatch):
    """前提自检: 这组输入确实落在敏感窗口里

    如果哪天 ctl 的含义变了导致这组数据不再敏感, 这条会提醒我
    **换一组输入**, 而不是让测试继续假绿。
    """
    st = _compute(0.1, 0.0, -40.0, -10.0, monkeypatch)

    # 关键前提: 这组输入的 fitness **必须真的有舍入差异**。
    # ctl=0.1 < 20 → 走 `fitness = ctl * 1.5` 分支 → 0.15000000000000002
    # 舍入后是 0.2 —— 差 0.05, 正好是这次 bug 的可观测窗口。
    #
    # 第一版我把这里写成了 `abs(round(st.fitness,1) - raw_fitness) < 1e-9`,
    # 也就是"拿已舍入的值减未舍入的值", 那当然差 0.05, 恒假。
    # 正确写法: 对象里存的应该**等于** round(原始值)。
    raw_fitness = max(0, 0.1 * 1.5)          # ctl < 20 → 线性分支
    assert round(raw_fitness, 1) != raw_fitness, (
        "前提失效: 这组输入的 fitness 不再有舍入差异, 测试会变假绿"
    )
    assert st.fitness == round(raw_fitness, 1), (
        f"对象里存的 {st.fitness} 不是 round({raw_fitness}, 1)"
    )
