"""V0.9.0: readiness 分数的诚实性 — 别拿没有数据的维度凑分

## 这组测试在防什么

`generate_recommendations` 有一个"数据够不够"的门槛(7 次活动 / 7 天跨度),
我以为加上它就解决了"零数据用户拿到 82 分极佳"。

**没有。** 门槛只挡住了"完全没有数据", 挡不住"有活动、但某些维度算不出来"。
做了一次决定性实验: 8 次活动 / 7 天、零 HRV 记录、算不出 ACWR 的用户 ——
拿到 67 分"良好" + 阈值间歇处方, 其中

    hrv  20/30   status=insufficient_data 仍然给了 2/3 分
    acwr 25/25   **满分**, 等于宣称"负荷平衡完美";
                 而 ACWR 结构上需要 28 天 chronic, 7 天根本算不出来

**75% 的分数来自没有数据的维度**, 并且这个假分直接驱动了训练处方
(>=60 -> 2x20min 阈值间歇)。这比原来的零数据 bug 更隐蔽: 那批用户一眼能看出
不对, 这批用户**以为自己数据够了**, 反而更容易被骗。

修法: 维度内部区分"真实测量"和"兜底猜测" —— 只有真有数据的维度才进 breakdown,
分数按可用维度的满分归一化, 可用维度 <2 或缺训练负荷维度时返回 None。

## 最重要的一条: 不得给老用户改分

五个维度齐全时, 新旧算法必须**逐位一致**(权重和还是 100)。这是本组测试的
第一道关 —— 修诚实性很容易顺手把别人的分数也改了, 那是回归不是改进。
"""
from __future__ import annotations

import asyncio
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tests.conftest import use_temp_db
from tests.fit_fixtures import build_fit


# ---------------------------------------------------------------- fixtures

def _make_athlete():
    from cycling_coach.core.profile import store as profile_store
    from cycling_coach.data.sqlite.database import SessionLocal
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    return db, ath


def _import_rides(db, n_days: int, *, with_hrv: bool = False,
                  start: datetime | None = None) -> None:
    """导入 n_days 天的训练。用 ActivityService 走真实上传路径, 不直接插库。"""
    from cycling_coach.core.services.activity import ActivityService
    tmp = Path(tempfile.mkdtemp(prefix="cc_rh_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    base = start or (datetime.now(timezone.utc) - timedelta(days=n_days - 1))
    try:
        for i in range(n_days):
            p = tmp / f"r{i:02d}.fit"
            build_fit(
                p,
                duration_s=3600,
                avg_power=180,
                avg_hr=145,
                speed_mps=8.0,
                start=base + timedelta(days=i),
            )
            loop.run_until_complete(
                svc.upload(filename=p.name, file_bytes=p.read_bytes())
            )
    finally:
        loop.close()


@pytest.fixture(scope="module")
def fresh():
    use_temp_db("v090_readiness_honesty")
    from cycling_coach.data.sqlite.database import SessionLocal
    return SessionLocal()


@pytest.fixture(scope="module")
def short_history_athlete(fresh):
    """7 天历史: 过了活动数门槛, 但 HRV/ACWR/RPE 全都没有"""
    import cycling_coach.data.sqlite.models as models
    from cycling_coach.core.profile import store as profile_store
    db = fresh
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    _import_rides(db, 8)  # 8 天 -> span 7 天, 刚好过门槛
    # 确保 HRV/RPE 确实为空 —— 前提是 build_fit 不写这两个字段
    assert db.query(models.DailyMetric).filter(
        models.DailyMetric.hrv_ms.isnot(None)).count() == 0
    return ath.id


# ---------------------------------------------------------------- 核心: 不得改老用户的分

def test_full_data_score_unchanged(fresh):
    """五维齐全时, 新算法与旧算法**逐位一致** —— 修诚实性不能顺手改掉别人的分

    旧算法: total = sum(五个维度), 满分 100
    新算法: total / sum(可用维度满分) * 100, 五维齐全时分母就是 100
    """
    from cycling_coach.core.coaching.recommendations import (
        compute_readiness, readiness_coverage, READINESS_WEIGHTS)

    # 直接构造一个"全部可用"的 breakdown, 验证归一化在全维度时是恒等变换
    full = {"hrv": 30, "acwr": 25, "tsb": 20, "phase": 15, "rpe": 10}
    assert set(full) == set(READINESS_WEIGHTS)
    total = sum(full.values())
    max_total = sum(READINESS_WEIGHTS[k] for k in full)
    assert total == max_total == 100
    assert round(total / max_total * 100) == 100

    cov = readiness_coverage(full)
    assert cov["complete"] is True
    assert cov["n_available"] == 5


def test_normalization_only_over_available(fresh, short_history_athlete):
    """分数按**可用维度**归一化, 且缺失维度根本不出现在 breakdown 里"""
    from cycling_coach.core.coaching.recommendations import (
        compute_readiness, readiness_coverage)

    score, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)

    # 前提: 这些维度确实没数据
    assert "hrv" in cov["missing"], "实验前提失效: 居然有 HRV 数据了"
    assert "acwr" in cov["missing"], "实验前提失效: 居然有 ACWR 数据了"

    # 核心断言: 没数据的维度不能出现在 breakdown
    assert "hrv" not in bd
    assert "acwr" not in bd
    assert "rpe" not in bd

    # 训练负荷必须在(它是 readiness 的地基)
    assert "tsb" in bd

    if score is not None:
        # 分数只能由真实维度构成
        assert sum(bd.values()) == pytest.approx(
            score / 100 * sum(
                {"hrv": 30, "acwr": 25, "tsb": 20, "phase": 15, "rpe": 10}[k]
                for k in bd
            ), abs=0.5)


# ---------------------------------------------------------------- 回归防护: 旧的两个编造默认值

def test_no_full_marks_without_data(fresh, short_history_athlete):
    """没有 ACWR 数据时, 绝不能拿满分 25/25

    这是本组测试最核心的一条。旧代码 `acwr_val = today.get("acwr", 1.0)`
    在无数据时默认 1.0, 1.0 落在 0.8-1.3 甜区 -> **满分**。
    """
    from cycling_coach.core.coaching.recommendations import compute_readiness

    _score, bd = compute_readiness(fresh, short_history_athlete)
    assert bd.get("acwr") != 25, (
        "算不出 ACWR 却给了满分 25 —— 正是 V0.9.0 要修的编造默认值"
    )


def test_no_hrv_score_without_hrv_data(fresh, short_history_athlete):
    """没有 HRV 记录时不能给 20/30 —— "没测心率但我按三分之二算上了"是骗人"""
    from cycling_coach.core.coaching.recommendations import compute_readiness

    _score, bd = compute_readiness(fresh, short_history_athlete)
    assert "hrv" not in bd, "无 HRV 数据却给 HRV 打了分"


def test_no_neutral_rpe_score_without_rpe(fresh, short_history_athlete):
    """没有 RPE 记录时不能给 5/10 中性分"""
    from cycling_coach.core.coaching.recommendations import compute_readiness

    _score, bd = compute_readiness(fresh, short_history_athlete)
    assert "rpe" not in bd, "无 RPE 记录却给了中性分"


# ---------------------------------------------------------------- 分数可为 None

def test_returns_none_without_load_dimension():
    """缺训练负荷维度时必须返回 None, 而不是硬凑一个分

    不知道最近骑了多少, 就没有资格说今天该上什么强度。
    """
    from cycling_coach.core.coaching.recommendations import (
        compute_readiness, MIN_DIMENSIONS_FOR_READINESS,
        REQUIRED_READINESS_DIMENSION)
    assert REQUIRED_READINESS_DIMENSION == "tsb"
    # V0.9.0 第二轮: 2 -> 3。2 会放行"只有 TSB + phase"这种最单薄的组合。
    assert MIN_DIMENSIONS_FOR_READINESS == 3


def test_coverage_reports_what_is_missing():
    """coverage 必须说得清"这个分是基于哪几个维度算的" """
    from cycling_coach.core.coaching.recommendations import readiness_coverage

    cov = readiness_coverage({"tsb": 5, "phase": 12})
    assert cov["n_available"] == 2
    assert cov["n_total"] == 5
    assert cov["complete"] is False
    assert set(cov["available"]) == {"tsb", "phase"}
    assert set(cov["missing"]) == {"hrv", "acwr", "rpe"}
    # 标签是人能读的, 不是内部字段名
    assert "训练负荷" in cov["available_labels"]
    assert "HRV" in cov["missing_labels"]


def test_missing_guidance_is_actionable():
    """缺维度时要告诉用户**具体怎么做**, 不是"请升级设备"这种无解建议"""
    from cycling_coach.core.coaching.recommendations import _missing_dimension_guidance

    txt = _missing_dimension_guidance(["hrv", "acwr", "tsb", "rpe"])
    assert "心率带" in txt
    assert "28 天" in txt
    assert "RPE" in txt
    assert txt.strip() != ""


# ---------------------------------------------------------------- ACWR 参数 P0

# 起因: 8 周 / 45 次活动的 demo 用户, ACWR 维度居然还是 missing。
# 一开始以为"数据还不够", 查下去发现不是数据问题:
#
#     compute_acwr() 开头: `if len(daily_tss) < chronic_window: return []`
#     chronic_window = 28
#     而 compute_readiness 传的是 `get_acwr(db, days=7)`
#     → 最多取到 8 条 → **恒为真** → series 恒空 → today 恒 None
#
# ACWR 在 readiness 这条路径上**从来没算出来过, 对所有用户都一样**。
# 之所以长期没暴露, 恰恰因为 `get("acwr", 1.0)` 把"算不出来"
# 伪装成了"负荷平衡完美 25/25" —— 一个坏掉的功能被假数据盖住了。
#
# **假数据不只是撒谎, 它还会掩盖真 bug**: 只要默认值填得"合理",
# 没人会去查那个值到底是不是真的。


def test_acwr_window_param_is_actually_computable():
    """ACWR 的取数天数必须 >= 库的 chronic_window, 且不该靠人记这个数"""
    import inspect
    import cycling_coach.core.metrics.acwr as acwr_mod
    from cycling_coach.core.coaching.recommendations import (
        ACWR_CHRONIC_WINDOW_DAYS, MIN_TRAINING_HISTORY_DAYS_FOR_ACWR)

    chronic = inspect.signature(acwr_mod.compute_acwr).parameters["chronic_window"].default
    assert ACWR_CHRONIC_WINDOW_DAYS == chronic
    # 训练史守卫也要 >= 同一个窗口, 否则等于没守
    assert MIN_TRAINING_HISTORY_DAYS_FOR_ACWR >= chronic


def test_acwr_called_with_sufficient_window(fresh, monkeypatch, short_history_athlete):
    """行为测试: readiness 调 get_acwr 时传的 days 必须够 chronic 窗口

    这条早先写成了 `assert "days=7" not in 源码`, **失败**, 两个原因:

    1. 我为了解释这个 bug 在注释里写了 `days=7 最多只能取到 8 条` ——
       断言分不清代码和说明。后来改用 tokenize 剥注释, 但行列换算写反了,
       结果 `"days=7" not in src` **恒为真**。做变异测试把 days 退回 7 时,
       13 条测试照样全绿 —— 断言从来没生效过。
    2. 就算剥注释做对了, 它测的也是"源码长什么样", 不是"行为对不对"。

    教训: **参数传递要用行为测试盯, 不要 grep 源码。** 注释怎么写不该影响测试。
    """
    import cycling_coach.core.coaching.recommendations as mod

    seen: list[int] = []
    real = mod.get_acwr

    def spy(db, days=90):
        seen.append(days)
        return real(db, days=days)

    monkeypatch.setattr(mod, "get_acwr", spy)
    mod.compute_readiness(fresh, short_history_athlete)

    assert seen, "compute_readiness 根本没调 get_acwr"
    for d in seen:
        assert d >= 28, f"传给 get_acwr 的 days={d} < 28, ACWR 会恒定算不出来"


def test_acwr_excluded_when_history_is_padded_zeros(fresh, short_history_athlete):
    """训练史太短时 ACWR 必须**不计入**, 而不是拿补零序列算出一个数

    `compute_daily_tss()` 会把没有活动的日期补成 TSS=0, 所以序列长度恒等于
    days+1 —— `compute_acwr()` 那个 `len < 28` 的守卫**从来没真正检验过训练史**。

    我第一版守卫写成"最近 28 天至少骑过 7 天", 结果 8 天连续训练的新用户照样
    放行: chronic = 8 天 TSS / 28, acute = 7 天 / 7, 比值能到 3.5 落进 danger 区,
    等于对一个刚入门的人说"你严重过载了"。比例没错, 错的是分母里有 20 天
    是"还没开始骑"。现在要求**整个慢性窗口都被真实历史覆盖**。
    """
    from cycling_coach.core.coaching.recommendations import (
        compute_readiness, readiness_coverage)

    _score, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    # 8 天训练史 -> 必须排除 ACWR
    assert "acwr" in cov["missing"], (
        "训练史只有 8 天, ACWR 却算出来了 —— 那是拿补零序列算的"
    )
    assert "acwr" not in bd


def test_acwr_included_for_long_history(fresh):
    """反过来: 训练史够长时 ACWR 必须真的算出来 (上一轮只验了"不编造", 没验"能算")"""
    import asyncio
    import tempfile
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.coaching.recommendations import compute_readiness
    from tests.fit_fixtures import build_fit

    use_temp_db("v090_acwr_long_history")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()

    # 40 天训练史 —— 覆盖 28 天慢性窗口
    tmp = Path(tempfile.mkdtemp(prefix="cc_acwr_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    base = datetime.now(timezone.utc) - timedelta(days=45)
    try:
        for w in range(6):
            for d in (0, 2, 4):
                p = tmp / f"a{w}_{d}.fit"
                build_fit(p, duration_s=3600, avg_power=180, avg_hr=145,
                          speed_mps=8.0, start=base + timedelta(days=w * 7 + d))
                loop.run_until_complete(
                    svc.upload(filename=p.name, file_bytes=p.read_bytes()))
    finally:
        loop.close()

    _score, bd = compute_readiness(db, ath.id)
    assert "acwr" in bd, (
        "18 次训练 / 40 天历史, ACWR 仍算不出来 —— 参数或守卫又出问题了"
    )
# ---------------------------------------------------------------- ACWR 参数 P0

# 起因: 8 周 / 45 次活动的 demo 用户, ACWR 维度居然还是 missing。
# 一开始以为"数据还不够", 查下去发现不是数据问题:
#
#     compute_acwr() 开头: `if len(daily_tss) < chronic_window: return []`
#     chronic_window = 28
#     而 compute_readiness 传的是 `get_acwr(db, days=7)`
#     → 最多取到 8 条 → **恒为真** → series 恒空 → today 恒 None
#
# ACWR 在 readiness 这条路径上**从来没算出来过, 对所有用户都一样**。
# 之所以长期没暴露, 恰恰因为 `get("acwr", 1.0)` 把"算不出来"
# 伪装成了"负荷平衡完美 25/25" —— 一个坏掉的功能被假数据盖住了。
#
# **假数据不只是撒谎, 它还会掩盖真 bug**: 只要默认值填得"合理",
# 没人会去查那个值到底是不是真的。


def test_acwr_window_param_is_actually_computable():
    """ACWR 的取数天数必须 >= 库的 chronic_window, 且不该靠人记这个数"""
    import inspect
    import cycling_coach.core.metrics.acwr as acwr_mod
    from cycling_coach.core.coaching.recommendations import (
        ACWR_CHRONIC_WINDOW_DAYS, MIN_TRAINING_HISTORY_DAYS_FOR_ACWR)

    chronic = inspect.signature(acwr_mod.compute_acwr).parameters["chronic_window"].default
    assert ACWR_CHRONIC_WINDOW_DAYS == chronic
    # 训练史守卫也要 >= 同一个窗口, 否则等于没守
    assert MIN_TRAINING_HISTORY_DAYS_FOR_ACWR >= chronic


def test_acwr_called_with_sufficient_window(fresh, monkeypatch, short_history_athlete):
    """行为测试: readiness 调 get_acwr 时传的 days 必须够 chronic 窗口

    这条早先写成了 `assert "days=7" not in 源码`, **失败**, 两个原因:

    1. 我为了解释这个 bug 在注释里写了 `days=7 最多只能取到 8 条` ——
       断言分不清代码和说明。后来改用 tokenize 剥注释, 但行列换算写反了,
       结果 `"days=7" not in src` **恒为真**。做变异测试把 days 退回 7 时,
       13 条测试照样全绿 —— 断言从来没生效过。
    2. 就算剥注释做对了, 它测的也是"源码长什么样", 不是"行为对不对"。

    教训: **参数传递要用行为测试盯, 不要 grep 源码。** 注释怎么写不该影响测试。
    """
    import cycling_coach.core.coaching.recommendations as mod

    seen: list[int] = []
    real = mod.get_acwr

    def spy(db, days=90):
        seen.append(days)
        return real(db, days=days)

    monkeypatch.setattr(mod, "get_acwr", spy)
    mod.compute_readiness(fresh, short_history_athlete)

    assert seen, "compute_readiness 根本没调 get_acwr"
    for d in seen:
        assert d >= 28, f"传给 get_acwr 的 days={d} < 28, ACWR 会恒定算不出来"


def test_acwr_excluded_when_history_is_padded_zeros(fresh, short_history_athlete):
    """训练史太短时 ACWR 必须**不计入**, 而不是拿补零序列算出一个数

    `compute_daily_tss()` 会把没有活动的日期补成 TSS=0, 所以序列长度恒等于
    days+1 —— `compute_acwr()` 那个 `len < 28` 的守卫**从来没真正检验过训练史**。

    我第一版守卫写成"最近 28 天至少骑过 7 天", 结果 8 天连续训练的新用户照样
    放行: chronic = 8 天 TSS / 28, acute = 7 天 / 7, 比值能到 3.5 落进 danger 区,
    等于对一个刚入门的人说"你严重过载了"。比例没错, 错的是分母里有 20 天
    是"还没开始骑"。现在要求**整个慢性窗口都被真实历史覆盖**。
    """
    from cycling_coach.core.coaching.recommendations import (
        compute_readiness, readiness_coverage)

    _score, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    # 8 天训练史 -> 必须排除 ACWR
    assert "acwr" in cov["missing"], (
        "训练史只有 8 天, ACWR 却算出来了 —— 那是拿补零序列算的"
    )
    assert "acwr" not in bd


def test_acwr_included_for_long_history(fresh):
    """反过来: 训练史够长时 ACWR 必须真的算出来 (上一轮只验了"不编造", 没验"能算")"""
    import asyncio
    import tempfile
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.coaching.recommendations import compute_readiness
    from tests.fit_fixtures import build_fit

    use_temp_db("v090_acwr_long_history")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()

    # 40 天训练史 —— 覆盖 28 天慢性窗口
    tmp = Path(tempfile.mkdtemp(prefix="cc_acwr_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    base = datetime.now(timezone.utc) - timedelta(days=45)
    try:
        for w in range(6):
            for d in (0, 2, 4):
                p = tmp / f"a{w}_{d}.fit"
                build_fit(p, duration_s=3600, avg_power=180, avg_hr=145,
                          speed_mps=8.0, start=base + timedelta(days=w * 7 + d))
                loop.run_until_complete(
                    svc.upload(filename=p.name, file_bytes=p.read_bytes()))
    finally:
        loop.close()

    _score, bd = compute_readiness(db, ath.id)
    assert "acwr" in bd, (
        "18 次训练 / 40 天历史, ACWR 仍算不出来 —— 参数或守卫又出问题了"
    )
# ---------------------------------------------------------------- ACWR 参数 P0

# 起因: 8 周 / 45 次活动的 demo 用户, ACWR 维度居然还是 missing。
# 一开始以为"数据还不够", 查下去发现不是数据问题:
#
#     compute_acwr() 开头: `if len(daily_tss) < chronic_window: return []`
#     chronic_window = 28
#     而 compute_readiness 传的是 `get_acwr(db, days=7)`
#     → 最多取到 8 条 → **恒为真** → series 恒空 → today 恒 None
#
# ACWR 在 readiness 这条路径上**从来没算出来过, 对所有用户都一样**。
# 之所以长期没暴露, 恰恰因为 `get("acwr", 1.0)` 把"算不出来"
# 伪装成了"负荷平衡完美 25/25" —— 一个坏掉的功能被假数据盖住了。
#
# **假数据不只是撒谎, 它还会掩盖真 bug**: 只要默认值填得"合理",
# 没人会去查那个值到底是不是真的。


def test_acwr_window_param_is_actually_computable():
    """ACWR 的取数天数必须 >= 库的 chronic_window, 且不该靠人记这个数"""
    import inspect
    import cycling_coach.core.metrics.acwr as acwr_mod
    from cycling_coach.core.coaching.recommendations import (
        ACWR_CHRONIC_WINDOW_DAYS, MIN_TRAINING_HISTORY_DAYS_FOR_ACWR)

    chronic = inspect.signature(acwr_mod.compute_acwr).parameters["chronic_window"].default
    assert ACWR_CHRONIC_WINDOW_DAYS == chronic
    # 训练史守卫也要 >= 同一个窗口, 否则等于没守
    assert MIN_TRAINING_HISTORY_DAYS_FOR_ACWR >= chronic


def test_acwr_called_with_sufficient_window(fresh, monkeypatch, short_history_athlete):
    """行为测试: readiness 调 get_acwr 时传的 days 必须够 chronic 窗口

    这条早先写成了 `assert "days=7" not in 源码`, **失败**, 两个原因:

    1. 我为了解释这个 bug 在注释里写了 `days=7 最多只能取到 8 条` ——
       断言分不清代码和说明。后来改用 tokenize 剥注释, 但行列换算写反了,
       结果 `"days=7" not in src` **恒为真**。做变异测试把 days 退回 7 时,
       13 条测试照样全绿 —— 断言从来没生效过。
    2. 就算剥注释做对了, 它测的也是"源码长什么样", 不是"行为对不对"。

    教训: **参数传递要用行为测试盯, 不要 grep 源码。** 注释怎么写不该影响测试。
    """
    import cycling_coach.core.coaching.recommendations as mod

    seen: list[int] = []
    real = mod.get_acwr

    def spy(db, days=90):
        seen.append(days)
        return real(db, days=days)

    monkeypatch.setattr(mod, "get_acwr", spy)
    mod.compute_readiness(fresh, short_history_athlete)

    assert seen, "compute_readiness 根本没调 get_acwr"
    for d in seen:
        assert d >= 28, f"传给 get_acwr 的 days={d} < 28, ACWR 会恒定算不出来"


def test_acwr_excluded_when_history_is_padded_zeros(fresh, short_history_athlete):
    """训练史太短时 ACWR 必须**不计入**, 而不是拿补零序列算出一个数

    `compute_daily_tss()` 会把没有活动的日期补成 TSS=0, 所以序列长度恒等于
    days+1 —— `compute_acwr()` 那个 `len < 28` 的守卫**从来没真正检验过训练史**。

    我第一版守卫写成"最近 28 天至少骑过 7 天", 结果 8 天连续训练的新用户照样
    放行: chronic = 8 天 TSS / 28, acute = 7 天 / 7, 比值能到 3.5 落进 danger 区,
    等于对一个刚入门的人说"你严重过载了"。比例没错, 错的是分母里有 20 天
    是"还没开始骑"。现在要求**整个慢性窗口都被真实历史覆盖**。
    """
    from cycling_coach.core.coaching.recommendations import (
        compute_readiness, readiness_coverage)

    _score, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    # 8 天训练史 -> 必须排除 ACWR
    assert "acwr" in cov["missing"], (
        "训练史只有 8 天, ACWR 却算出来了 —— 那是拿补零序列算的"
    )
    assert "acwr" not in bd


def test_acwr_included_for_long_history(fresh):
    """反过来: 训练史够长时 ACWR 必须真的算出来 (上一轮只验了"不编造", 没验"能算")"""
    import asyncio
    import tempfile
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.coaching.recommendations import compute_readiness
    from tests.fit_fixtures import build_fit

    use_temp_db("v090_acwr_long_history")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()

    # 40 天训练史 —— 覆盖 28 天慢性窗口
    tmp = Path(tempfile.mkdtemp(prefix="cc_acwr_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    base = datetime.now(timezone.utc) - timedelta(days=45)
    try:
        for w in range(6):
            for d in (0, 2, 4):
                p = tmp / f"a{w}_{d}.fit"
                build_fit(p, duration_s=3600, avg_power=180, avg_hr=145,
                          speed_mps=8.0, start=base + timedelta(days=w * 7 + d))
                loop.run_until_complete(
                    svc.upload(filename=p.name, file_bytes=p.read_bytes()))
    finally:
        loop.close()

    _score, bd = compute_readiness(db, ath.id)
    assert "acwr" in bd, (
        "18 次训练 / 40 天历史, ACWR 仍算不出来 —— 参数或守卫又出问题了"
    )


# ---------------------------------------------------------------- Verifier 抓到的缺口

def test_returns_none_when_load_dimension_missing_even_if_two_others_present():
    """有 2 个维度但缺训练负荷维度时, 必须返回 None

    Verifier 独立做变异测试时发现: 把"缺训练负荷维度就返回 None"这个哨兵删掉,
    **我 12 条测试全绿**。原因很直接 —— 我原先那条
    `test_returns_none_without_load_dimension` 只断言了两个常量存在,
    **根本没测行为**。这是典型的"看起来有测试, 其实没测到东西"。

    这个场景必须专门构造: 要同时满足
      - 训练负荷维度**不可用** (今天没有 DailyMetric 行)
      - 可用维度数 **>= 2** (否则 MIN_DIMENSIONS 那个检查会先挡下来,
        哨兵删不删结果都一样, 测试就抓不住)
    所以需要 HRV 可用 + phase 总是可用 → 2 个维度, 但没有 tsb。
    此时只有哨兵能让结果变成 None。
    """
    import asyncio
    import tempfile
    from pathlib import Path
    from datetime import datetime, timedelta, timezone
    from cycling_coach.core.services.activity import ActivityService
    from cycling_coach.core.coaching.recommendations import (
        compute_readiness, readiness_coverage)
    from tests.fit_fixtures import build_fit

    use_temp_db("v090_no_load_dim")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()

    tmp = Path(tempfile.mkdtemp(prefix="cc_noload_"))
    svc = ActivityService(db)
    loop = asyncio.new_event_loop()
    base = datetime.now(timezone.utc) - timedelta(days=7)
    try:
        for i in range(8):
            p = tmp / f"a{i}.fit"
            build_fit(p, duration_s=3600, avg_power=180, avg_hr=145,
                      speed_mps=8.0, start=base + timedelta(days=i))
            loop.run_until_complete(
                svc.upload(filename=p.name, file_bytes=p.read_bytes()))
    finally:
        loop.close()

    # 造 HRV 数据, 让 hrv 维度可用
    from cycling_coach.data.sqlite.models import DailyMetric
    today = datetime.utcnow().date()
    # 导入 FIT 已经建好了 DailyMetric 行(unique(athlete_id, date)),
    # 所以这里是**更新**而不是插入 —— 插入会撞 UNIQUE 约束。
    for i in range(10):
        row = (
            db.query(DailyMetric)
            .filter(DailyMetric.athlete_id == ath.id,
                    DailyMetric.date == today - timedelta(days=i))
            .first()
        )
        if row is not None:
            row.hrv_ms = 60          # 让 hrv 维度可用
    # 造一个赛程, 让 phase 维度可用 (它现在要求"有负荷数据**或**有赛程")
    # —— 没有它的话这个场景只有 hrv 一个可用维度, MIN_DIMENSIONS 会先挡下来,
    # 哨兵删不删结果都一样, 测试就抓不住哨兵了。
    from cycling_coach.data.sqlite.models import TrainingPhase
    db.add(TrainingPhase(athlete_id=ath.id, phase_type="base", name="基础期",
                        start_date=today - timedelta(days=30),
                        end_date=today + timedelta(days=60)))
    db.commit()

    # 删掉今天那一行 → get_pmc_today 返回"无数据" → 训练负荷维度不可用
    db.query(DailyMetric).filter(
        DailyMetric.athlete_id == ath.id,
        DailyMetric.date == today,
    ).delete()
    db.commit()

    score, bd = compute_readiness(db, ath.id)
    cov = readiness_coverage(bd)

    # 前提检查: 确实有 >=2 个可用维度, 否则这个测试测不到哨兵
    assert cov["n_available"] >= 2, (
        f"实验前提失效: 只有 {cov['n_available']} 个可用维度, "
        "MIN_DIMENSIONS 检查会先挡下来, 哨兵删不删都一样"
    )
    assert "tsb" not in bd, "实验前提失效: 训练负荷维度还在"
    # 核心断言: 缺训练负荷维度 -> 不给分
    assert score is None, (
        f"缺训练负荷维度却给了 {score} 分 —— "
        "不知道最近骑了多少, 就没有资格说今天该上什么强度"
    )


# ================================================================ 第二轮 Verifier

def test_pure_load_row_with_rpe_only_does_not_earn_tsb_points():
    """🔴 P0-3: 休息日填了 RPE, 于是有 DailyMetric 行, 但零负荷数据
    旧代码 `status_label != "无数据"` 放行 → `float(row.tsb or 0)` = 0.0 →
    classify_status(0,0) → "平衡" → **满分 20/20** → 87 分"极佳"。
    路径普通用户走得到: 骑满一周、今天休息、填一次 RPE。

    注意 `models.py` 里 ctl/atl/tsb 都是 `default=0.0`, 所以 NULL 不会出现 ——
    **"没测"和"测出来是 0"在 schema 层就被抹平了**, 不能靠 IS NULL 区分。
    改用语义判据: CTL/ATL 是 TSS 的 EWMA, 有任何训练史就必然 > 0。
    """
    from datetime import datetime as _dt, timedelta as _td
    from cycling_coach.data.sqlite.models import DailyMetric
    from cycling_coach.core.pmc import get_pmc_today
    from cycling_coach.core.coaching.recommendations import compute_readiness

    use_temp_db("v090_rpe_only_today")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    today = _dt.utcnow().date()
    for i in range(10):
        row = DailyMetric(athlete_id=ath.id, date=today - _td(days=i), tss=50)
        if i == 0:
            row.rpe = 5          # 今天休息, 只填了 RPE
        else:
            row.ctl, row.atl, row.tsb, row.rpe = 40, 42, -2, 5
        db.add(row)
    db.commit()

    pmc = get_pmc_today(db, ath.id)
    # 旧哨兵会放行的地方
    assert pmc["status_label"] == "平衡"
    # 新判据必须说不
    assert pmc["has_load_data"] is False, (
        "只有 RPE 没有负荷的行, has_load_data 不该是 True"
    )

    _score, bd = compute_readiness(db, ath.id)
    assert "tsb" not in bd, "零负荷数据拿到了训练负荷分 (P0-3 没修好)"


def test_load_row_with_real_data_still_counts():
    """反向: 真的有 ctl/atl/tsb 时, has_load_data 必须为 True (别把正常用户也排除)"""
    from datetime import datetime as _dt, timedelta as _td
    from cycling_coach.data.sqlite.models import DailyMetric
    from cycling_coach.core.pmc import get_pmc_today

    use_temp_db("v090_real_load")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    db.add(DailyMetric(athlete_id=ath.id, date=_dt.utcnow().date(),
                       tss=50, ctl=40, atl=42, tsb=-2, rpe=5))
    db.commit()
    assert get_pmc_today(db, ath.id)["has_load_data"] is True


def test_tier_is_capped_when_coverage_incomplete(fresh):
    """🔴 P0-1: 归一化能凑出 100 分, 而 100 分会一路走到 vo2 档

    零 HRV / 零 ACWR 的用户被派去做 4-6x3min @ 110-120% FTP ——
    而 HRV 恰恰是抓"看着还行其实已经过载"的那个维度。

    注意把 MIN_DIMENSIONS 从 2 提到 3 **修不掉这个**:
    tsb 20 + phase 15 + rpe 10 = 45/45 同样是 100。病根是归一化本身。
    """
    import inspect
    from cycling_coach.core.coaching import recommendations as mod

    src = inspect.getsource(mod.generate_recommendations)
    assert "MAX_TIER_BY_COVERAGE" in src, "档位没有对覆盖度封顶"
    assert "tier_cap" in src

    # 封顶表本身: 3 维封 endurance, 4 维封 threshold, 5 维不封顶
    assert mod.MAX_TIER_BY_COVERAGE[3] == "endurance"
    assert mod.MAX_TIER_BY_COVERAGE[4] == "threshold"
    assert mod.MAX_TIER_BY_COVERAGE[5] is None
    # vo2 只能出现在"不封顶"那一档
    assert "vo2" not in mod.MAX_TIER_BY_COVERAGE.values()


def test_tier_cap_cannot_be_bypassed(fresh, short_history_athlete):
    """封顶必须真的生效, 不能只是源码里有那么一行"""
    from cycling_coach.core.coaching.recommendations import (
        generate_recommendations, readiness_coverage, compute_readiness,
        MAX_TIER_BY_COVERAGE, _TIER_ORDER)

    score, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    if score is None or cov["complete"]:
        return  # 该场景拿不到分数, 封顶无从谈起, 跳过

    rec = generate_recommendations(fresh, short_history_athlete)
    cap = MAX_TIER_BY_COVERAGE.get(cov["n_available"])
    if cap is not None:
        assert _TIER_ORDER.index(rec.recommended_workout_type) <= _TIER_ORDER.index(cap), (
            f"{cov['n_available']}/5 维却给出了 {rec.recommended_workout_type}"
        )
        # 覆盖度不完整时绝不允许出现"极佳"
        assert "极佳" not in rec.readiness_label, (
            f"覆盖度 {cov['n_available']}/5 却给了「极佳」"
        )


def test_cap_is_explained_to_user(fresh, short_history_athlete):
    """被封顶时必须告诉用户为什么, 否则看起来像系统在乱推荐 (Verifier: M9)"""
    from cycling_coach.core.coaching.recommendations import (
        generate_recommendations, compute_readiness, readiness_coverage,
        MAX_TIER_BY_COVERAGE, _TIER_ORDER)

    _s, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    rec = generate_recommendations(fresh, short_history_athlete)
    if rec.readiness_score is None:
        # 拿不到分数时, "数据不足" 那条本身就是解释, 不该要求覆盖度提示
        assert rec.recommendations, "数据不足时至少要告诉用户为什么"
        return
    cap = MAX_TIER_BY_COVERAGE.get(cov["n_available"])
    should_be_capped = (
        cap is not None
        and _TIER_ORDER.index(rec.recommended_workout_type) == _TIER_ORDER.index(cap)
        and not cov["complete"]
    )
    texts = [r.title + r.detail for r in rec.recommendations]
    if should_be_capped:
        assert any("下调" in t for t in texts), "被封顶却没告诉用户"
    # 无论封没封顶, 覆盖度不完整时都必须有覆盖度说明
    if not cov["complete"] and rec.recommendations:
        assert any("个维度" in t for t in texts), "覆盖度不完整却没有说明"


def test_coverage_rec_present_even_at_minimum_dimensions(fresh, short_history_athlete):
    """变异 M9: 删掉覆盖度提示 Recommendation 时必须红"""
    from cycling_coach.core.coaching.recommendations import generate_recommendations
    rec = generate_recommendations(fresh, short_history_athlete)
    if rec.readiness_score is None:
        return
    assert any("个维度" in r.title for r in rec.recommendations), (
        "覆盖度提示不见了 —— 用户会看到一个来路不明的分数"
    )


def test_min_dimensions_is_three(fresh, short_history_athlete):
    """门槛必须是 3。2 会放行"只有 TSB + phase"这种最单薄的组合"""
    from cycling_coach.core.coaching import recommendations as mod
    assert mod.MIN_DIMENSIONS_FOR_READINESS == 3
    # phase 无条件写入, 所以 3 维 = tsb + phase + 任意一项真实信号
    _score, bd = mod.compute_readiness(fresh, short_history_athlete)
    assert len(bd) < 3 or "tsb" in bd


# ================================================================ 第二轮 Verifier

def test_pure_load_row_with_rpe_only_does_not_earn_tsb_points():
    """🔴 P0-3: 休息日填了 RPE, 于是有 DailyMetric 行, 但零负荷数据
    旧代码 `status_label != "无数据"` 放行 → `float(row.tsb or 0)` = 0.0 →
    classify_status(0,0) → "平衡" → **满分 20/20** → 87 分"极佳"。
    路径普通用户走得到: 骑满一周、今天休息、填一次 RPE。

    注意 `models.py` 里 ctl/atl/tsb 都是 `default=0.0`, 所以 NULL 不会出现 ——
    **"没测"和"测出来是 0"在 schema 层就被抹平了**, 不能靠 IS NULL 区分。
    改用语义判据: CTL/ATL 是 TSS 的 EWMA, 有任何训练史就必然 > 0。
    """
    from datetime import datetime as _dt, timedelta as _td
    from cycling_coach.data.sqlite.models import DailyMetric
    from cycling_coach.core.pmc import get_pmc_today
    from cycling_coach.core.coaching.recommendations import compute_readiness

    use_temp_db("v090_rpe_only_today")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    today = _dt.utcnow().date()
    for i in range(10):
        row = DailyMetric(athlete_id=ath.id, date=today - _td(days=i), tss=50)
        if i == 0:
            row.rpe = 5          # 今天休息, 只填了 RPE
        else:
            row.ctl, row.atl, row.tsb, row.rpe = 40, 42, -2, 5
        db.add(row)
    db.commit()

    pmc = get_pmc_today(db, ath.id)
    # 旧哨兵会放行的地方
    assert pmc["status_label"] == "平衡"
    # 新判据必须说不
    assert pmc["has_load_data"] is False, (
        "只有 RPE 没有负荷的行, has_load_data 不该是 True"
    )

    _score, bd = compute_readiness(db, ath.id)
    assert "tsb" not in bd, "零负荷数据拿到了训练负荷分 (P0-3 没修好)"


def test_load_row_with_real_data_still_counts():
    """反向: 真的有 ctl/atl/tsb 时, has_load_data 必须为 True (别把正常用户也排除)"""
    from datetime import datetime as _dt, timedelta as _td
    from cycling_coach.data.sqlite.models import DailyMetric
    from cycling_coach.core.pmc import get_pmc_today

    use_temp_db("v090_real_load")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    db.add(DailyMetric(athlete_id=ath.id, date=_dt.utcnow().date(),
                       tss=50, ctl=40, atl=42, tsb=-2, rpe=5))
    db.commit()
    assert get_pmc_today(db, ath.id)["has_load_data"] is True


def test_tier_is_capped_when_coverage_incomplete(fresh):
    """🔴 P0-1: 归一化能凑出 100 分, 而 100 分会一路走到 vo2 档

    零 HRV / 零 ACWR 的用户被派去做 4-6x3min @ 110-120% FTP ——
    而 HRV 恰恰是抓"看着还行其实已经过载"的那个维度。

    注意把 MIN_DIMENSIONS 从 2 提到 3 **修不掉这个**:
    tsb 20 + phase 15 + rpe 10 = 45/45 同样是 100。病根是归一化本身。
    """
    import inspect
    from cycling_coach.core.coaching import recommendations as mod

    src = inspect.getsource(mod.generate_recommendations)
    assert "MAX_TIER_BY_COVERAGE" in src, "档位没有对覆盖度封顶"
    assert "tier_cap" in src

    # 封顶表本身: 3 维封 endurance, 4 维封 threshold, 5 维不封顶
    assert mod.MAX_TIER_BY_COVERAGE[3] == "endurance"
    assert mod.MAX_TIER_BY_COVERAGE[4] == "threshold"
    assert mod.MAX_TIER_BY_COVERAGE[5] is None
    # vo2 只能出现在"不封顶"那一档
    assert "vo2" not in mod.MAX_TIER_BY_COVERAGE.values()


def test_tier_cap_cannot_be_bypassed(fresh, short_history_athlete):
    """封顶必须真的生效, 不能只是源码里有那么一行"""
    from cycling_coach.core.coaching.recommendations import (
        generate_recommendations, readiness_coverage, compute_readiness,
        MAX_TIER_BY_COVERAGE, _TIER_ORDER)

    score, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    if score is None or cov["complete"]:
        return  # 该场景拿不到分数, 封顶无从谈起, 跳过

    rec = generate_recommendations(fresh, short_history_athlete)
    cap = MAX_TIER_BY_COVERAGE.get(cov["n_available"])
    if cap is not None:
        assert _TIER_ORDER.index(rec.recommended_workout_type) <= _TIER_ORDER.index(cap), (
            f"{cov['n_available']}/5 维却给出了 {rec.recommended_workout_type}"
        )
        # 覆盖度不完整时绝不允许出现"极佳"
        assert "极佳" not in rec.readiness_label, (
            f"覆盖度 {cov['n_available']}/5 却给了「极佳」"
        )


def test_cap_is_explained_to_user(fresh, short_history_athlete):
    """被封顶时必须告诉用户为什么, 否则看起来像系统在乱推荐 (Verifier: M9)"""
    from cycling_coach.core.coaching.recommendations import (
        generate_recommendations, compute_readiness, readiness_coverage,
        MAX_TIER_BY_COVERAGE, _TIER_ORDER)

    _s, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    rec = generate_recommendations(fresh, short_history_athlete)
    if rec.readiness_score is None:
        # 拿不到分数时, "数据不足" 那条本身就是解释, 不该要求覆盖度提示
        assert rec.recommendations, "数据不足时至少要告诉用户为什么"
        return
    cap = MAX_TIER_BY_COVERAGE.get(cov["n_available"])
    should_be_capped = (
        cap is not None
        and _TIER_ORDER.index(rec.recommended_workout_type) == _TIER_ORDER.index(cap)
        and not cov["complete"]
    )
    texts = [r.title + r.detail for r in rec.recommendations]
    if should_be_capped:
        assert any("下调" in t for t in texts), "被封顶却没告诉用户"
    # 无论封没封顶, 覆盖度不完整时都必须有覆盖度说明
    if not cov["complete"] and rec.recommendations:
        assert any("个维度" in t for t in texts), "覆盖度不完整却没有说明"


def test_coverage_rec_present_even_at_minimum_dimensions(fresh, short_history_athlete):
    """变异 M9: 删掉覆盖度提示 Recommendation 时必须红"""
    from cycling_coach.core.coaching.recommendations import generate_recommendations
    rec = generate_recommendations(fresh, short_history_athlete)
    if rec.readiness_score is None:
        return
    assert any("个维度" in r.title for r in rec.recommendations), (
        "覆盖度提示不见了 —— 用户会看到一个来路不明的分数"
    )


def test_min_dimensions_is_three(fresh, short_history_athlete):
    """门槛必须是 3。2 会放行"只有 TSB + phase"这种最单薄的组合"""
    from cycling_coach.core.coaching import recommendations as mod
    assert mod.MIN_DIMENSIONS_FOR_READINESS == 3
    # phase 无条件写入, 所以 3 维 = tsb + phase + 任意一项真实信号
    _score, bd = mod.compute_readiness(fresh, short_history_athlete)
    assert len(bd) < 3 or "tsb" in bd


# ================================================================ 第二轮 Verifier

def test_pure_load_row_with_rpe_only_does_not_earn_tsb_points():
    """🔴 P0-3: 休息日填了 RPE, 于是有 DailyMetric 行, 但零负荷数据
    旧代码 `status_label != "无数据"` 放行 → `float(row.tsb or 0)` = 0.0 →
    classify_status(0,0) → "平衡" → **满分 20/20** → 87 分"极佳"。
    路径普通用户走得到: 骑满一周、今天休息、填一次 RPE。

    注意 `models.py` 里 ctl/atl/tsb 都是 `default=0.0`, 所以 NULL 不会出现 ——
    **"没测"和"测出来是 0"在 schema 层就被抹平了**, 不能靠 IS NULL 区分。
    改用语义判据: CTL/ATL 是 TSS 的 EWMA, 有任何训练史就必然 > 0。
    """
    from datetime import datetime as _dt, timedelta as _td
    from cycling_coach.data.sqlite.models import DailyMetric
    from cycling_coach.core.pmc import get_pmc_today
    from cycling_coach.core.coaching.recommendations import compute_readiness

    use_temp_db("v090_rpe_only_today")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    today = _dt.utcnow().date()
    for i in range(10):
        row = DailyMetric(athlete_id=ath.id, date=today - _td(days=i), tss=50)
        if i == 0:
            row.rpe = 5          # 今天休息, 只填了 RPE
        else:
            row.ctl, row.atl, row.tsb, row.rpe = 40, 42, -2, 5
        db.add(row)
    db.commit()

    pmc = get_pmc_today(db, ath.id)
    # 旧哨兵会放行的地方
    assert pmc["status_label"] == "平衡"
    # 新判据必须说不
    assert pmc["has_load_data"] is False, (
        "只有 RPE 没有负荷的行, has_load_data 不该是 True"
    )

    _score, bd = compute_readiness(db, ath.id)
    assert "tsb" not in bd, "零负荷数据拿到了训练负荷分 (P0-3 没修好)"


def test_load_row_with_real_data_still_counts():
    """反向: 真的有 ctl/atl/tsb 时, has_load_data 必须为 True (别把正常用户也排除)"""
    from datetime import datetime as _dt, timedelta as _td
    from cycling_coach.data.sqlite.models import DailyMetric
    from cycling_coach.core.pmc import get_pmc_today

    use_temp_db("v090_real_load")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    db.add(DailyMetric(athlete_id=ath.id, date=_dt.utcnow().date(),
                       tss=50, ctl=40, atl=42, tsb=-2, rpe=5))
    db.commit()
    assert get_pmc_today(db, ath.id)["has_load_data"] is True


def test_tier_is_capped_when_coverage_incomplete(fresh):
    """🔴 P0-1: 归一化能凑出 100 分, 而 100 分会一路走到 vo2 档

    零 HRV / 零 ACWR 的用户被派去做 4-6x3min @ 110-120% FTP ——
    而 HRV 恰恰是抓"看着还行其实已经过载"的那个维度。

    注意把 MIN_DIMENSIONS 从 2 提到 3 **修不掉这个**:
    tsb 20 + phase 15 + rpe 10 = 45/45 同样是 100。病根是归一化本身。
    """
    import inspect
    from cycling_coach.core.coaching import recommendations as mod

    src = inspect.getsource(mod.generate_recommendations)
    assert "MAX_TIER_BY_COVERAGE" in src, "档位没有对覆盖度封顶"
    assert "tier_cap" in src

    # 封顶表本身: 3 维封 endurance, 4 维封 threshold, 5 维不封顶
    assert mod.MAX_TIER_BY_COVERAGE[3] == "endurance"
    assert mod.MAX_TIER_BY_COVERAGE[4] == "threshold"
    assert mod.MAX_TIER_BY_COVERAGE[5] is None
    # vo2 只能出现在"不封顶"那一档
    assert "vo2" not in mod.MAX_TIER_BY_COVERAGE.values()


def test_tier_cap_cannot_be_bypassed(fresh, short_history_athlete):
    """封顶必须真的生效, 不能只是源码里有那么一行"""
    from cycling_coach.core.coaching.recommendations import (
        generate_recommendations, readiness_coverage, compute_readiness,
        MAX_TIER_BY_COVERAGE, _TIER_ORDER)

    score, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    if score is None or cov["complete"]:
        return  # 该场景拿不到分数, 封顶无从谈起, 跳过

    rec = generate_recommendations(fresh, short_history_athlete)
    cap = MAX_TIER_BY_COVERAGE.get(cov["n_available"])
    if cap is not None:
        assert _TIER_ORDER.index(rec.recommended_workout_type) <= _TIER_ORDER.index(cap), (
            f"{cov['n_available']}/5 维却给出了 {rec.recommended_workout_type}"
        )
        # 覆盖度不完整时绝不允许出现"极佳"
        assert "极佳" not in rec.readiness_label, (
            f"覆盖度 {cov['n_available']}/5 却给了「极佳」"
        )


def test_cap_is_explained_to_user(fresh, short_history_athlete):
    """被封顶时必须告诉用户为什么, 否则看起来像系统在乱推荐 (Verifier: M9)"""
    from cycling_coach.core.coaching.recommendations import (
        generate_recommendations, compute_readiness, readiness_coverage,
        MAX_TIER_BY_COVERAGE, _TIER_ORDER)

    _s, bd = compute_readiness(fresh, short_history_athlete)
    cov = readiness_coverage(bd)
    rec = generate_recommendations(fresh, short_history_athlete)
    if rec.readiness_score is None:
        # 拿不到分数时, "数据不足" 那条本身就是解释, 不该要求覆盖度提示
        assert rec.recommendations, "数据不足时至少要告诉用户为什么"
        return
    cap = MAX_TIER_BY_COVERAGE.get(cov["n_available"])
    should_be_capped = (
        cap is not None
        and _TIER_ORDER.index(rec.recommended_workout_type) == _TIER_ORDER.index(cap)
        and not cov["complete"]
    )
    texts = [r.title + r.detail for r in rec.recommendations]
    if should_be_capped:
        assert any("下调" in t for t in texts), "被封顶却没告诉用户"
    # 无论封没封顶, 覆盖度不完整时都必须有覆盖度说明
    if not cov["complete"] and rec.recommendations:
        assert any("个维度" in t for t in texts), "覆盖度不完整却没有说明"


def test_coverage_rec_present_even_at_minimum_dimensions(fresh, short_history_athlete):
    """变异 M9: 删掉覆盖度提示 Recommendation 时必须红"""
    from cycling_coach.core.coaching.recommendations import generate_recommendations
    rec = generate_recommendations(fresh, short_history_athlete)
    if rec.readiness_score is None:
        return
    assert any("个维度" in r.title for r in rec.recommendations), (
        "覆盖度提示不见了 —— 用户会看到一个来路不明的分数"
    )


def test_min_dimensions_is_three(fresh, short_history_athlete):
    """门槛必须是 3。2 会放行"只有 TSB + phase"这种最单薄的组合"""
    from cycling_coach.core.coaching import recommendations as mod
    assert mod.MIN_DIMENSIONS_FOR_READINESS == 3
    # phase 无条件写入, 所以 3 维 = tsb + phase + 任意一项真实信号
    _score, bd = mod.compute_readiness(fresh, short_history_athlete)
    assert len(bd) < 3 or "tsb" in bd


@pytest.fixture(scope="module")
def empty_db():
    """一个**真的什么都没有**的库。

    注意不能用模块级的 `fresh` —— 里面已经被 short_history_athlete 导了 8 次训练,
    拿它测"零数据用户"会得到误导性的结果 (我第一版就踩了, 断言报的是
    "{'tsb': 5, 'phase': 12}" 而不是我以为的空库)。
    """
    use_temp_db("v090_readiness_empty")
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.core.profile import store as profile_store
    db = SessionLocal()
    ath = profile_store.get_or_create_athlete(db)
    ath.ftp = 250
    db.commit()
    return db


def test_zero_data_user_gets_no_score_at_all(empty_db):
    """零数据用户: breakdown 必须完全为空, 连 phase 都不能有

    Verifier 抓到的 M6 死代码根源: `phase` 原来**无条件**写入 breakdown,
    于是它成了唯一"永远算得出"的维度。零数据用户只靠 `derive_phase`
    返回的 base(低 CTL) 就拿到 12/15, 归一化后 **80 分** ——
    而"低 CTL"的原因是**根本没数据**。

    同时它让 `len(breakdown) < MIN_DIMENSIONS` 形同虚设:
    tsb 在的时候 len 恒 >= 2, 分支不可达。
    """
    from cycling_coach.core.coaching.recommendations import compute_readiness

    from cycling_coach.core.profile import store as profile_store
    aid = profile_store.get_or_create_athlete(empty_db).id
    score, bd = compute_readiness(empty_db, aid)
    assert score is None, f"零数据用户拿到 {score} 分"
    assert bd == {}, f"零数据用户却有 breakdown: {bd}"


def test_the_none_guards_actually_exist():
    """源码级: 两个 None 守卫必须真的在归一化**之前**

    这条是被一次假信号变异测试逼出来的 —— 我注入 M6(删守卫)时,
    守卫在 baseline 里**本来就不在**, 那次变异是空操作,
    "测试变红"是别的断言造成的。**变异测试的前提是 baseline 是好的。**
    """
    import inspect
    from cycling_coach.core.coaching import recommendations as mod

    src = inspect.getsource(mod.compute_readiness)
    # 守卫必须在归一化之前
    i_guard = src.find("REQUIRED_READINESS_DIMENSION not in breakdown")
    i_guard2 = src.find("len(breakdown) < MIN_DIMENSIONS_FOR_READINESS")
    i_norm = src.find("max_total = sum(")
    assert i_guard != -1, "训练负荷维度的守卫丢了"
    assert i_guard2 != -1, "维度数守卫丢了"
    assert i_norm != -1, "归一化那行不见了"
    assert i_guard < i_norm and i_guard2 < i_norm, (
        "守卫必须在归一化之前, 否则它们形同虚设"
    )


def test_phase_not_counted_without_load_or_race(empty_db):
    """没有负荷数据也没有赛程时, phase 维度必须不计入"""
    from cycling_coach.core.profile import store as profile_store
    from cycling_coach.core.coaching.recommendations import compute_readiness
    aid = profile_store.get_or_create_athlete(empty_db).id
    _score, bd = compute_readiness(empty_db, aid)
    assert "phase" not in bd, (
        "零数据零赛程却把 '基础期(低 CTL)' 当成真实阶段计入了 —— "
        "低 CTL 的原因是没数据, 不是真的低"
    )
