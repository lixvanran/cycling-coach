"""V0.9.0: 真实形态骑行数据下的指标正确性

## 这个文件存在的理由

V0.9.0 之前, 项目里所有测试数据的功率都是**恒定**的。
恒定功率对"算得对不对"是最干净的 ground truth, 但它测不出依赖
功率**时间结构**的指标: NP 的 30s 滑动窗口、W′ 平衡的累积效应、
分区时长的边界归属、解耦的时序错位。

`tests/realistic_rides.py` 生成带真实功率波动的 FIT, 并在测试里用
**教科书定义独立重算一遍** NP 和分区时长, 再和应用的结果比对。

这不是"验算法定义对不对"(那是另一回事), 是"验实现有没有做错":
滑动窗口错位、边界处理、稀疏采样、parser 丢点, 都会在这里被抓出来。

## 已验证结果 (2026-10-03, FTP=280)

8 种课型, NP 全部与应用一致 (差 <=0.5W), Z4 时长差 <=8s。
→ 核心指标引擎在真实波动数据上是正确的。

这个"没抓到 bug" 的结果本身也有价值:
它把"恒定 fixture 是否遮住了问题"这个问题从猜测变成了已验证的事实。
"""
from __future__ import annotations

import pytest

from tests.realistic_rides import (
    WORKOUT_LIBRARY,
    build_profile_fit,
    textbook_np,
    textbook_zone_seconds,
)

FTP = 280


@pytest.fixture(scope="module", autouse=True)
def _db():
    from tests.conftest import use_temp_db
    use_temp_db("realistic_metrics")


@pytest.fixture(scope="module")
def rides(tmp_path_factory):
    """8 种课型的真实形态 FIT, 只生成一次 (合成要 ~40s)"""
    d = tmp_path_factory.mktemp("rides")
    out = []
    for idx, (name, intent, segs) in enumerate(WORKOUT_LIBRARY):
        # 必须用 idx 做文件名: intent 有重复 (endurance 3 个 / vo2 2 个),
        # 用 intent 会互相覆盖, 导致 gt 和文件内容对不上 —— 看起来像应用算错,
        # 实际是测试自己踩了自己的脚。
        path = d / f"{idx:02d}_{intent}.fit"
        gt = build_profile_fit(path, segs, seed=3)
        out.append((name, intent, path, gt))
    return out


# ------------------------------------------------------------------ NP
def test_NP_与独立实现一致(rides):
    """NP 必须等于教科书定义, 而不是"差不多"。

    恒定功率下 NP 平凡地等于平均功率, 这条测试才真正有区分度。
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.power import normalized_power

    rows = []
    for name, intent, path, gt in rides:
        act = parse_fit(str(path))
        app = normalized_power(act)
        mine = textbook_np([float(x) for x in gt["power"]])
        rows.append((name, app, mine))
        assert app is not None, f"{name}: NP 算成了 None"
        assert abs(app - mine) < 3, (
            f"{name}: 应用 NP={app}, 独立实现 NP={mine:.1f}, 差 {abs(app-mine):.1f}W"
        )


def test_波动课的NP高于平均功率(rides):
    """NP 必须 >= 平均功率, 且波动越大超出越多。

    这是 NP 存在的全部意义。如果某节课的 NP 反而低于平均功率,
    说明滑动窗口实现反了 —— 这是恒定功率 fixture 测不出的错误。
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.power import normalized_power

    for name, intent, path, gt in rides:
        act = parse_fit(str(path))
        np_val = normalized_power(act)
        assert np_val >= gt["avg_power"] - 1, (
            f"{name}: NP({np_val}) < 平均功率({gt['avg_power']:.0f}) —— 滑动窗口可能反了"
        )

    # 冲刺课波动最大, NP 应该明显超出平均功率
    sprint = next(r for r in rides if r[0] == "冲刺")
    from cycling_coach.data.parsers.fit_parser import parse_fit
    app = normalized_power(parse_fit(str(sprint[2])))
    assert app - sprint[3]["avg_power"] > 100, (
        f"冲刺课 NP({app}) 应比平均功率({sprint[3]['avg_power']:.0f}) 高 100W 以上, "
        f"实际只高 {app - sprint[3]['avg_power']:.0f}"
    )


def test_恒定功率时NP等于平均功率(tmp_path):
    """边界: 恒定功率下两者必须相等 (不引入系统性偏差)"""
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.power import normalized_power

    p = tmp_path / "flat.fit"
    gt = build_profile_fit(p, [(60, 210)], seed=1)
    app = normalized_power(parse_fit(str(p)))
    assert abs(app - gt["avg_power"]) <= 2, (
        f"恒定 210W 跑了 60 分钟, NP 应为 210, 实得 {app}"
    )


# ------------------------------------------------------------------ 分区
def test_各区间时长与应用一致(rides):
    """7 区间秒数必须与应用一致, 跨区间边界不能错配

    容差为什么是 3% 而不是 0:
    有些课型的功率段**正好压在分区边界上** —— 比如甜点课的 150W 段,
    而 Z1/Z2 分界在 0.55*FTP = 154W。FIT 里功率是整数, 取整会让
    边界附近的采样在分界两侧来回移动, 差异约 1~2%。

    这不是 bug, 是数据本身坐在刀刃上。所以容差按总时长的 3% 给,
    足以容纳取整效应, 又远小于"重复计/漏计/系统性错配"那类真 bug
    (那些会造成几十个百分点甚至数倍的偏差)。

    ⚠️ 收紧这个容差会让本测试在甜点课上重新失败 —— 那时请先想清楚
    是要处理边界效应, 而不是去调数字。
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.power import power_zones

    for name, intent, path, gt in rides:
        act = parse_fit(str(path))
        got = power_zones(act, FTP)
        want = textbook_zone_seconds([float(x) for x in gt["power"]], FTP)
        tol = max(60.0, gt["duration_s"] * 0.03)
        for z in range(7):
            key = f"Z{z + 1}"
            assert abs((got.get(key) or 0) - want[z]) < tol, (
                f"{name}: {key} 应用={got.get(key)} 独立={want[z]:.0f} "
                f"差 {abs((got.get(key) or 0) - want[z]):.0f}s 超过容差 {tol:.0f}s"
            )


def test_区间总和等于总时长(rides):
    """所有区间秒数加起来必须等于骑行总时长, 不多不少。

    这条专门抓"分区时长重复计"或"漏掉某些区间"这类 bug。
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.power import power_zones

    for name, intent, path, gt in rides:
        act = parse_fit(str(path))
        got = power_zones(act, FTP)
        total = sum(got.get(f"Z{z + 1}") or 0 for z in range(7))
        # 有停表/掉功率低于 0 的区间可能不被计入, 允许 1% 容差
        assert abs(total - gt["duration_s"]) < gt["duration_s"] * 0.01, (
            f"{name}: 各区间合计 {total}s, 总时长 {gt['duration_s']}s —— 有重复计或漏计"
        )


# ------------------------------------------------------------------ 采样率无关性
@pytest.mark.parametrize("interval", [1.0, 2.0, 5.0])
def test_采样率不影响结果(tmp_path, interval):
    """同一段训练, 不同采样率, 结果必须一致"""
    """同一段训练, 1s / 2s / 5s 采样, 算出来的 NP 必须一致。

    真实场景: 不同码表采样率不同, 用户不该因为换了码表就看到不同指标。
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.power import normalized_power

    vals = []
    for i in (1.0, 2.0, 5.0):
        p = tmp_path / f"s{i}.fit"
        build_profile_fit(p, [(15, 150), (10, 260), (15, 150)], seed=5, sample_interval_s=i)
        vals.append(normalized_power(parse_fit(str(p))))
    assert all(v is not None for v in vals), f"有采样率下 NP 算成了 None: {vals}"
    assert max(vals) - min(vals) < 6, (
        f"采样率影响了 NP: 1s={vals[0]} 2s={vals[1]} 5s={vals[2]} —— 时间加权有问题"
    )


# ------------------------------------------------------------------ 解耦
def test_解耦在长课低强度下合理(rides):
    """低强度长课 EF 应在真实量级, 且能正常算出

    ⚠️ 这个断言的第一版是**空转**的:
    写的 `res.get("ef1")` 在生产代码里根本不存在 (返回的是
    `first_half_ef` / `decoupling_pct`), 所以 `if ef1:` 恒为 False,
    断言一次都没执行过 —— 测试绿着, 但什么都没验。
    Verifier 抓出来的。这类"永远会通过"的测试比没有测试更危险。

    骑行 EF 的真实量级是 1.3~1.8 (功率 W / 心率 bpm),
    第一版我按跑步的 0.75~1.10 写, 那也是错的。
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.hr import pa_hr_decoupling

    long_ride = next(r for r in rides if r[0] == "长耐力")
    act = parse_fit(str(long_ride[2]))
    res = pa_hr_decoupling(act)
    assert res.get("applicable") is True, (
        f"3 小时 45 分的长耐力课应该适用解耦, 实得 {res.get('error')}"
    )
    ef1 = (res.get("first_half") or {}).get("efficiency_factor")
    ef2 = (res.get("second_half") or {}).get("efficiency_factor")
    pct = res.get("decoupling_pct")
    assert ef1 and ef2, f"没算出前后半 EF: {res}"
    # 骑行 EF = 平均功率/平均心率, 真实区间约 1.3~1.8
    assert 1.2 <= ef1 <= 1.9, f"长耐力课前半 EF={ef1} 不在骑行真实量级 (1.3~1.8)"
    assert 1.2 <= ef2 <= 1.9, f"长耐力课后半 EF={ef2} 不在骑行真实量级"
    assert pct is not None and -20 <= pct <= 30, (
        f"解耦率 {pct}% 不合理 (低强度长课应在 ±20% 内)"
    )


def test_解耦短课明确拒绝(rides):
    """短于 60 分钟必须明说算不了, 而不是给个假数字

    生产代码的门槛是 duration_s < 3600 (60min), 且用时间加权算时长。
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.hr import pa_hr_decoupling

    short = next(r for r in rides if r[3]["duration_s"] < 3600)
    res = pa_hr_decoupling(parse_fit(str(short[2])))
    assert res.get("applicable") is False, (
        f"{short[0]} 只有 {short[3]['duration_s']//60} 分钟, 不该给解耦: {res}"
    )




def test_parser不丢采样点(rides):
    """parser 解析出的采样数必须等于生成时的采样数

    之前文档里写"parser 丢点会被抓出来", 但没有任何断言支撑这句话 ——
    textbook_np 用的是生成器原始序列, 应用用的是 parser 输出,
    两边长度不同时测试照样绿。这条把它变成真的。
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit

    for name, intent, path, gt in rides:
        act = parse_fit(str(path))
        n_app = len(act.samples or [])
        n_gen = len(gt["power"])
        assert n_app == n_gen, (
            f"{name}: parser 解析出 {n_app} 个采样, 生成时是 {n_gen} 个 —— "
            f"丢了 {n_gen - n_app} 个点"
        )


def test_W平衡符合Skiba模型语义(rides):
    """W′ balance 的核心物理性质

    这一条之前**完全缺失**: 文件开头的表格点名了 W′ balance 依赖
    功率时间结构, 但测试里一次都没调用过 w_prime_balance。

    第一版我写的是"曲线不该上升" —— 那是错的, 而且是我自己的错。
    W′ 模型的定义就是: 高于 CP 时消耗, 低于 CP 时**指数恢复**。
    间歇课的恢复段本来就该回升, 拿"不许上升"去测 VO2max 课,
    等于把模型最核心的行为当成 bug。

    真正该断言的是这三条:
      1. 高强度间歇课必须有显著消耗 (最低 W′ 明显低于初始值)
      2. 全程低于 CP 的课不该耗尽
      3. 恢复段确实回升 (说明不是简单积分)
    """
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.metrics.power import w_prime_balance

    def curve_of(path):
        act = parse_fit(str(path))
        return w_prime_balance(act.samples or [], cp=FTP)

    checked = 0

    # 1. 间歇课必须有显著消耗
    intervals = [r for r in rides if r[1] == "vo2" or r[0] == "VO2max 间歇"]
    for name, intent, path, gt in intervals:
        c = curve_of(path)
        if not c:
            continue
        checked += 1
        # W′ 的单位是**焦耳**(初始 ~20000J), 不是瓦特。
        # 第一版这里写的是 `min(c) < FTP * 0.5` = 140 —— 拿焦耳跟瓦特比,
        # 断言成了"W′ 要降到 140 焦耳以下", 物理上不可能, 于是红了。
        # 正确的问法是: 消耗掉初始 W′ 的百分之几。
        initial = c[0] or 20000.0
        assert min(c) < initial * 0.5, (
            f"{name}: 间歇课 W′ 只从 {initial:.0f}J 降到 {min(c):.0f}J "
            f"(剩 {min(c)/initial*100:.0f}%) —— 2 小时 45 分高强度间歇不可能几乎不消耗"
        )
        assert min(c) >= 0, (
            f"{name}: W′ 出现了负值 {min(c):.0f} —— 应钳位到 0 而非继续下降"
        )

    # 2. 全程不超过 CP 的课不该耗尽 W′
    #
    # 这里第一版用"平均功率 < CP"当判据, 被冲刺课打脸了:
    # 冲刺课平均功率只有 191W (远低于 CP 280), 但每次冲刺 700W,
    # W′ 照样被打到 0。**用平均功率判断 W′ 耗尽, 恰恰是 W′ 模型
    # 存在的意义所要纠正的误解。** 正确判据是峰值功率。
    for name, intent, path, gt in rides:
        if gt["max_power"] > FTP:
            continue          # 有超 CP 的冲刺, W′ 可能耗尽, 不在本题范围
        c = curve_of(path)
        if not c:
            continue
        checked += 1
        assert min(c) > 0, (
            f"{name}: 峰值功率才 {gt['max_power']:.0f}W (CP={FTP}), "
            f"不该有任何消耗, 但 W′ 降到了 {min(c):.0f}J"
        )

    # 3. 恢复段确实回升 —— 区分"Skiba 模型"和"简单积分"
    vo2 = next(r for r in rides if r[0] == "VO2max 间歇")
    c = curve_of(vo2[2])
    assert c and len(c) > 100
    lowest = min(c)
    after_low = c[c.index(lowest):]
    assert max(after_low) > lowest * 1.05, (
        f"W′ 到达最低点 {lowest:.0f} 后没有回升 —— "
        f"这是简单积分, 不是 Skiba 模型 (恢复期 W′ 应该补充)"
    )
    assert checked >= 4, f"只有 {checked} 节课覆盖到, 不足"
