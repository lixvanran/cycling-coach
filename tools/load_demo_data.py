#!/usr/bin/env python3
"""装载演示训练数据 —— 8 周真实周期化 + 对应课表

## 为什么要这个

1. **用户刚装上时是空的**。空库状态下所有页面都是"暂无数据",
   用户无法判断这个软件到底好不好用。TP 装上就有示例。
2. **开发走查必须有真实数据**。空库只能验证"不崩", 验证不了
   "算得对不对""显示得清楚不清楚""慢不慢"。

## 造的是什么

8 周完整周期化, 不是一个随机堆:

    W1-W2  Base      耐力为主, 低强度为主
    W3-W4  Build     加入甜点 + 阈值
    W5     Recovery  大幅降量
    W6-W7  Build2    阈值 + VO2max
    W8     Taper      降量 + 少量强度 (赛前减量)

课表里刻意混入真实的不完美, 否则演示数据会骗人:
- 约 15% 的计划**没完成** (真实生活: 加班/下雨/生病)
- 约 8% 被**主动跳过**
- 完成的多在目标 TSS 的 85%~120% 之间, 少数严重偏离
- 有一周只练了 2 次 (现实里这种事真的发生)

## ⚠️ 它会写进真实数据库

用 `--force` 之外的任何方式运行前请确认你清楚后果。
建议先用一个空 workspace 试。
"""
from __future__ import annotations

import argparse
import logging

logger = logging.getLogger(__name__)
import asyncio
import os
import random
import sys
from datetime import date, datetime, timedelta, timezone
import logging
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

FTP = 280
LTHR = 168
# ⚠️ 用**正则**而不是前缀通配符 —— 因为 SQLite `LIKE` 和 Python
#   `str.startswith` 的通配符语义不同(`%` vs `*`), 想两边通用就得写两套,
#   而两套会悄悄失准:
#   我第一版写 `"w%d_d%"`(Python 格式串思维), 于是:
#     - LIKE 拿字面量 "%d" 去匹配 -> 什么都没删掉(force 静默失效)
#     - startswith("w%d_d%") -> 全 False(生成处 assert 应该炸,但它没被接上)
#   **静默失准比报错难查得多。**
#
# 改成正则, 只有一处定义, 两边都用 `re`:
#   对应生成: f"w{w+1}_d{day_idx}_{intent}.fit"  -> w1_d1_endurance.fit
#   用户的:   "2026-10-01_ride.fit" / "wahoo_ride.fit" -> 都不匹配
DEMO_FILE_RE = r"^w\d+_d\d+_"
DEMO_FILE_PREFIX = "w"   # 仅供 LIKE 粗筛, 精确判定用 DEMO_FILE_RE


def _is_demo_file(file_name: str | None) -> bool:
    """这条记录是不是 demo 生成的?"""
    import re as _re
    return bool(file_name and _re.match(DEMO_FILE_RE, file_name))
HR_MAX = 188
WEIGHT = 68.0

# ---------------------------------------------------------------- 周期化
# 显式引用课名, 不用模板索引 —— 第一版用 index 导致 8 周几乎全是耐力骑,
# 阈值课和间歇课一次都没出现, 周期化形同虚设。
# (时长, 功率系数) 由课型自带, 这里只决定"练什么 + 练几节"
WEEK_PLAN: list[list[tuple[str, float, float]]] = [
    #                     课名,          节数, 强度系数
    # W1-W2 Base: 耐力为主
    [("恢复骑", 1, 1.0), ("耐力骑", 1, 1.0), ("恢复骑", 1, 1.0),
     ("长耐力", 1, 0.95), ("恢复骑", 1, 1.0), ("耐力骑", 1, 0.9), ("长耐力", 1, 1.05)],
    [("恢复骑", 1, 1.0), ("耐力骑", 1, 1.0), ("甜点课", 1, 0.85),
     ("耐力骑", 1, 1.0), ("恢复骑", 1, 1.0), ("爬坡耐力", 1, 0.9), ("长耐力", 1, 1.0)],
    # W3-W4 Build: 加入阈值
    [("耐力骑", 1, 1.0), ("阈值课", 1, 0.95), ("恢复骑", 1, 1.0),
     ("甜点课", 1, 0.95), ("耐力骑", 1, 1.0), ("恢复骑", 1, 1.0), ("长耐力", 1, 1.0)],
    [("恢复骑", 1, 1.0), ("甜点课", 1, 1.0), ("耐力骑", 1, 1.0),
     ("阈值课", 1, 0.95), ("恢复骑", 1, 1.0), ("爬坡耐力", 1, 0.95), ("长耐力", 1, 1.0)],
    # W5 Recovery: 大幅降量
    [("恢复骑", 1, 0.85), ("恢复骑", 1, 0.85), ("耐力骑", 1, 0.8),
     ("恢复骑", 1, 0.85), ("恢复骑", 1, 0.85), ("恢复骑", 1, 0.8), ("耐力骑", 1, 0.85)],
    # W6-W7 Build2: 阈值 + VO2max + 冲刺
    [("耐力骑", 1, 1.0), ("阈值课", 1, 1.0), ("甜点课", 1, 1.0),
     ("VO2max 间歇", 1, 0.95), ("恢复骑", 1, 1.0), ("冲刺", 1, 0.9), ("长耐力", 1, 1.0)],
    [("恢复骑", 1, 1.0), ("阈值课", 1, 1.0), ("耐力骑", 1, 1.0),
     ("VO2max 间歇", 1, 1.0), ("恢复骑", 1, 1.0), ("冲刺", 1, 1.0), ("甜点课", 1, 1.0)],
    # W8 Taper: 赛前减量
    [("恢复骑", 1, 0.7), ("甜点课", 1, 0.6), ("耐力骑", 1, 0.7),
     ("恢复骑", 1, 0.6), ("阈值课", 1, 0.55), ("恢复骑", 1, 0.5), ("恢复骑", 1, 0.5)],
]

# 课型池 (name, intent, segments) —— 从 realistic_rides 复用
from realistic_rides import WORKOUT_LIBRARY  # noqa: E402

BY_NAME: dict[str, tuple[str, str, list]] = {
    name: (name, intent, segs) for name, intent, segs in WORKOUT_LIBRARY
}


def scaled(segs: list, factor: float) -> list:
    """按强度系数缩放功率 —— 恢复周用 0.7 就是全课功率 x0.7"""
    return [(m, max(55, int(w * factor))) for m, w in segs]


def build_week_rides(week_idx: int) -> list[tuple[str, str, list, float]]:
    """返回 [(课名, intent, segments, 强度系数)]"""
    out = []
    for name, sessions, factor in WEEK_PLAN[week_idx]:
        base = BY_NAME[name]
        for k in range(sessions):
            out.append((name, base[1], scaled(base[2], factor), factor))
    return out


def _clear_athlete_rows(db, athlete_id: int,
                        only_prefix: str | None = None) -> dict[str, int]:
    """删掉某个车手名下的**所有**记录(遍历所有外键引用表)。

    ## 🔴 V0.9.1 新增 `only_prefix`

    原来无条件清空该车手名下的一切。V0.8.3 之前这没问题 ——
    demo 数据挂在**专属的"演示车手"**下面, 删干净正合适。

    但 V0.9.1 让 demo **复用库里第一个车手**(为了修"数据不可见"这个 P0),
    于是同一句 `force` 会把**用户自己的真实训练**一起删光:

        已清除旧数据(车手 #1 'Rider'): 1 行 (activities:1)

    用户点一次"重新载入示例", 自己三个月的骑行就没了。
    这是最不可接受的一类 bug —— 不可逆, 而且完全无声。

    ## 怎么区分 demo 数据和真实数据

    demo 生成的 FIT 文件名是 `w{周}_d{日}_{类型}.fit`(`w1_d1_endurance.fit`),
    用户自己的文件是 Garmin/Strava 导出的名字。**文件名是我们唯一可靠的
    区分依据** —— 没有 "is_demo" 标记位, 加一个要改 schema 并回填历史数据,
    对这个规模的项目不划算。

    ⚠️ 代价: 如果用户把自己的文件恰好命名成 `w1_d1_xxx.fit`, 会被一起清掉。
    概率极低, 但**这是真实的取舍**, 不是"完美方案"。
    真正的修法是给 activities 加 `is_demo` 列 + 迁移, 应该排进后续版本。

    ## 为什么需要遍历全部

    有 13 张表外键引用 athletes: activities / daily_metrics / planned_workouts /
    training_phases / workouts / ftp_tests / chat_sessions / training_diary /
    ml_predictions / ml_model_meta / plan_ai_drafts / plan_periods /
    race_tactics_sessions。

    原来 --force 只删了前 3 张就 `db.delete(athlete)`, 剩下的外键悬空 →
    `NOT NULL constraint failed: activities.athlete_id`。

    **删车手失败会让整个"载入示例"失败** —— 用户点一下按钮看到的是报错,
    而不是数据。
    """
    from sqlalchemy import inspect as _inspect, text as _text
    insp = _inspect(db.bind)
    removed: dict[str, int] = {}
    for t in insp.get_table_names():
        if t == "athletes":
            continue
        cols = None
        for fk in insp.get_foreign_keys(t):
            if fk.get("referred_table") == "athletes":
                cols = fk.get("constrained_columns")
                break
        if not cols:
            continue
        col = cols[0]
        try:
            cols_names = [c["name"] for c in insp.get_columns(t)]
            # 🔴 只删 demo 自己生成的那些行(见上面的 only_prefix 说明)
            #
            # ⚠️ 认得出的表: 有 file_name 的(activities 等)按文件名过滤。
            #    **认不出的表**(planned_workouts 没有 file_name, 只有 title/
            #    intent —— 用户也能自己建同样的)一律**跳过**, 不删。
            #
            #    这是有意的保守选择: 宁可残留一些重复的计划课,
            #    也不能删掉用户自己排的课。残留是可修正的(重装库),
            #    误删是不可逆的。
            if only_prefix and "file_name" not in cols_names:
                continue
            if only_prefix:
                # 逐行判 regex 而不是靠 LIKE 粗筛 —— LIKE 会漏, 也会误伤。
                _rows = db.execute(
                    _text(f"SELECT rowid, file_name FROM {t} WHERE {col} = :aid"),
                    {"aid": athlete_id},
                ).fetchall()
                import re as _re
                _rx = _re.compile(DEMO_FILE_RE)
                _hit = [r[0] for r in _rows if r[1] and _rx.match(r[1])]
                if _hit:
                    _ids = ','.join(str(int(x)) for x in _hit)
                    # ⚠️ 删 activities 之前必须先清掉引用它的行, 否则
                    #   FOREIGN KEY constraint failed。
                    #   引用方: ml_predictions / planned_workouts /
                    #          training_diary / workouts
                    #
                    #   ⚠️⚠️ 第一版我写成 `WHERE {col} IN (SELECT rowid FROM {t} ...)`,
                    #   那个子查询查的是**当前表 t 自己的 rowid**,
                    #   而引用方表要的是 **activities.id** —— 两者不是一回事
                    #   (SQLite 里恰好常常相等, 于是"有时能跑",
                    #   但一旦 activities 有过删除, id 和 rowid 就错位了,
                    #   表现为**第二次 force 就 500**)。
                    #
                    #   正解: 显式用被删的 activities **id**, 不是 rowid。
                    _act_ids = [str(int(r[0])) for r in db.execute(
                        _text(f"SELECT id FROM {t} WHERE rowid IN ({_ids})")
                    ).fetchall()]
                    if _act_ids:
                        _alist = ','.join(_act_ids)
                        for _ft in insp.get_table_names():
                            for _fk in insp.get_foreign_keys(_ft):
                                if _fk.get("referred_table") != t:
                                    continue
                                for _fc in (_fk.get("constrained_columns") or []):
                                    try:
                                        db.execute(_text(
                                            f"UPDATE {_ft} SET {_fc} = NULL "
                                            f"WHERE {_fc} IN ({_alist})"
                                        ))
                                    except Exception:
                                        pass
                    db.execute(
                        _text(f"DELETE FROM {t} WHERE {col} = :aid "
                              f"AND rowid IN ({_ids})"),
                        {"aid": athlete_id},
                    )
                    removed[t] = len(_hit)
                continue
            n = db.execute(
                _text(f"SELECT COUNT(*) FROM {t} WHERE {col} = :aid"),
                {"aid": athlete_id},
            ).scalar() or 0
            if n:
                db.execute(_text(f"DELETE FROM {t} WHERE {col} = :aid"),
                           {"aid": athlete_id})
                removed[t] = n
        except Exception as e:
            # 🔴 V0.9.1: 原来是 `logger.debug`, 于是**删除失败完全不可见** ——
            #   函数返回 `{}`, 调用方打印"已清除旧数据: 0 行",
            #   看起来一切正常, 实际什么都没删。
            #   我为这个"静默的空操作"debug 了很久, 最后是手动把日志级别
            #   调到 DEBUG 才看到真因是 FOREIGN KEY constraint failed。
            #
            #   **凡是"结果决定成败"的分支, 异常必须可见。**
            #   这里删除失败会让 force 静默失效 -> 重复载入堆重复数据。
            logger.warning("清理 %s 失败: %s", t, e, exc_info=True)
            raise
    # ⚠️ 必须 commit + **expire_all**(不是 expunge_all):
    #   - expire_all: 只清属性缓存, 对象**仍然绑定**在 session 上 ✅
    #   - expunge_all: 把对象彻底踢出 session → 后面再用就报
    #     "Instance ... is not bound to a Session"
    #
    # 我第一版写的是 expunge_all, 结果 CLI 路径能过(新进程新 session,
    # 没别的对象), API 路径 500(那个 session 里已经加载过 athlete)。
    # **同一个函数, 两条路径, 一个通一个挂** —— 典型的"测了一条路就以为对了"。
    db.commit()
    db.expire_all()
    return removed


def load_demo_data(weeks: int = 8, end: str | None = None,
                   athlete_name: str = "演示车手",
                   force: bool = False, no_plans: bool = False,
                   workspace: str | None = None) -> dict:
    """装载 8 周演示训练数据, 返回统计信息

    V0.9.0: 从 main() 抽成独立函数。原来逻辑整个埋在 main() 里,
    耦合 argparse 和 print, 于是"零数据用户点『先看示例』"这个按钮
    **无处可调** —— 前端要么写死 shell 命令, 要么只能做成死链。
    现在 CLI 和 HTTP 端点共用这个函数, 行为不会分叉。
    """
    class _A:
        pass
    args = _A()
    args.weeks, args.end, args.athlete = weeks, end, athlete_name
    args.force, args.no_plans, args.workspace = force, no_plans, workspace

    if args.workspace:
        os.environ["WORKSPACE_DIR"] = args.workspace
    os.environ.setdefault("M3_API_KEY", "")

    rng = random.Random(20261003)
    end = date.fromisoformat(args.end) if args.end else date.today()
    start = end - timedelta(days=args.weeks * 7 - 1)
    # 对齐到周一
    start -= timedelta(days=start.weekday())

    from cycling_coach.data.sqlite import database as D
    from cycling_coach.data.sqlite.models import Activity, Athlete, PlannedWorkout
    from cycling_coach.data.parsers.fit_parser import parse_fit
    from cycling_coach.core.services.activity import ActivityService

    D.init_db()
    db = D.SessionLocal()

    # ---- 车手 ----
    # ⚠️ 顺序很重要: 必须先建好车手, 再建 ActivityService。
    # ActivityService.__init__ 会调 get_or_create_athlete(), 而它是
    # "返回第 1 个 athlete, 没有就建一个叫 Rider(ftp=250)"。
    # 原来的写法先建 service, 结果 service 绑到了自动创建的 Rider 上,
    # 而 planned_workouts 挂在真正的演示车手上 ——
    # 45 条活动归 athlete 1, 51 个计划课归 athlete 2, 两边互相看不见,
    # 而且 TSS 是按 FTP=250 而不是 280 算的。
    if args.force:
        from cycling_coach.data.sqlite.models import (
            Activity, DailyMetric, PlannedWorkout,
        )
        # 🔴 V0.9.1: 原来是 `Athlete.name == args.athlete`("演示车手")。
        # 但 V0.9.1 之后 demo **复用库里第一个车手**, 它的名字是用户自己的
        # ("Rider" / 真实姓名) —— 这个条件**永远匹配不到**。
        #
        # 后果: 点两次"先看示例"(第二次 force=false):
        #   - 旧数据没被清掉
        #   - 新生成的 FIT 因为 SHA256 相同被去重, 一条都插不进去
        #   - 但生成循环仍然把 n_ride 记成满额
        #   -> 归属校验(新增条数 < 生成条数)失败 -> SystemExit -> HTTP 409
        #   -> 用户看到"载入失败", 而数据其实早就有了
        #
        # force 的语义是"重来一遍", 所以就该清**第一个车手**名下
        # 这次要重建的东西 —— 和写入侧同一个口径。
        _target = db.query(Athlete).first()
        if _target is not None:
            _removed = _clear_athlete_rows(db, _target.id,
                                            only_prefix=DEMO_FILE_PREFIX)
            print(f"已清除旧数据(车手 #{_target.id} {_target.name!r}): "
                  f"{sum(_removed.values())} 行 "
                  f"({', '.join(f'{k}:{v}' for k, v in _removed.items())})")

        # 🔴 V0.9.1: 整个"清除空占位车手"的循环被**删掉了**。
        #
        # 它存在的唯一目的是: 别让库里出现第二个车手(ActivityService 绑 #1、
        # 计划课挂 #2, 归属校验直接失败)。而 V0.9.1 的修法是
        # **让 demo 复用库里第一个车手**, 从根上就不存在"第二个"。
        #
        # 留着它的后果更糟 —— 它会把**正在用的那个车手**也当成占位删掉:
        #   BrokenPipeError: [Errno 32] Broken pipe  @ load_demo_data.py:310
        #   (删掉 #1 之后 session 还握着它, 后面任何操作都炸,
        #    而用户只看到"载入失败")
        #
        # 教训: **修根因之后要回头删掉为老根因打的补丁**。
        # 留着它不但没用, 还会制造新 bug —— 这正是"逐处打补丁"的代价。
    # 🔴 V0.9.1 (用户在 Windows 真机测出来的 P0): 原来这里是
    #     a = db.query(Athlete).filter(Athlete.name == args.athlete).first()
    #     if a is None: a = Athlete(name="演示车手", ...)
    #
    # 也就是"**库里没有叫演示车手的就新建一个**"。而只读侧
    # `get_or_create_athlete()` 永远返回 `db.query(Athlete).first()`(#1)。
    #
    # 真实场景(用户实测复现):
    #     1. 打开产品 -> 任何一次 API 调用建出占位车手 Rider (#1)
    #     2. 点"先看示例" -> 这里新建演示车手 (#2), 数据挂 #2
    #     3. 界面所有页面读 #1 -> **显示"还没有训练数据"**
    #     4. 而且 HTTP 200, 不报任何错 —— 静默失败
    #
    # **这不是边缘情况**: Dashboard 加载本来就会建占位车手,
    # 所以每个新用户点"先看示例"都会踩到。
    #
    # 修法: 复用库里**第一个** athlete(和只读侧同一个),
    # 不再新建第二个。只在它名下完全空的时候写数据。
    a = db.query(Athlete).first()
    # 示例数据会不会和用户自己的训练混在一起? 前端要据此提示
    _mixed_with_existing = False
    if a is None:
        a = Athlete(
            name=args.athlete, ftp=FTP, lthr=LTHR,
            max_hr=HR_MAX, weight_kg=WEIGHT,
        )
        db.add(a)
        db.commit()
        db.refresh(a)
    else:
        # 复用已有的第一个车手: 名字保持用户自己填的(可能是真实姓名),
        # 但补上 demo 需要的 FTP 等参数, 否则强度区间算不出来。
        _existing_acts = db.query(Activity).filter(
            Activity.athlete_id == a.id).count()
        _mixed_with_existing = _existing_acts > 0
        if _mixed_with_existing:
            print(f"⚠️ 车手 {a.name!r} 名下已有 {_existing_acts} 条训练, "
                  f"示例数据会**混进同一个档案**。")
        if a.ftp is None:
            a.ftp = FTP
        if a.lthr is None:
            a.lthr = LTHR
        if a.max_hr is None:
            a.max_hr = HR_MAX
        if a.weight_kg is None:
            a.weight_kg = WEIGHT
        db.commit()
        db.refresh(a)
    print(f"车手: {a.name}  FTP={a.ftp}  LTHR={a.lthr}")

    # 显式指定车手 —— ActivityService 默认绑库里第一个,
    # 库里有多余车手时必然错绑(这正是载入失败的根因)
    svc = ActivityService(db, athlete_id=a.id)
    if svc.athlete.id != a.id:
        # 静默继续下去就是"活动归 A、课表归 B", 直接失败
        raise SystemExit(
            f"归属不一致: ActivityService 绑到了 athlete "
            f"#{svc.athlete.id}({svc.athlete.name}, ftp={svc.athlete.ftp}), "
            f"但计划课会挂在 #{a.id}({a.name}, ftp={a.ftp})。\n"
            f"库里已有别的 athlete 占着 id={svc.athlete.id}。"
            f"请用 --force 重建, 或先清空该 workspace。"
        )

    # 入库前的基线 —— 最后的归属校验靠它算"这次新增了多少条"。
    # 🔴 V0.9.1: 必须在这里取, 即任何写入之前。
    #
    # ⚠️ `_sql_text` 的 import 原本写在函数更下面(校验段),
    #    这里先用了它 -> UnboundLocalError。这正是用户 Windows 报告里
    #    `/api/insights/weekly` 踩过的那一类错误, 我在同一个文件里又踩了一次。
    #    教训: **函数里所有 import 一律提到最前面**, 别按使用顺序随手放。
    from sqlalchemy import text as _sql_text
    _acts_before = db.execute(
        _sql_text("SELECT COUNT(*) FROM activities WHERE athlete_id = :aid"),
        {"aid": a.id}).scalar() or 0

    out_dir = Path(os.environ["WORKSPACE_DIR"]) / "_demo_fits"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_ride = n_plan = n_done = n_skip = n_miss = 0
    n_fail = 0
    _failures: list[str] = []
    tss_planned = tss_actual = 0

    from realistic_rides import build_profile_fit

    for w in range(args.weeks):
        week_start = start + timedelta(days=w * 7)
        rides = build_week_rides(w)
        # 第 3 周刻意来一次"只练了 2 次" —— 现实里真会发生
        if w == 2:
            rides = rides[:2]

        for day_idx, (name, intent, segs, factor) in enumerate(rides):
            d = week_start + timedelta(days=day_idx)
            if d > end:
                continue
            # 达成情况: 15% 没做, 8% 主动跳过
            roll = rng.random()
            planned = not args.no_plans
            if roll < 0.08:
                status = "skipped"
            elif roll < 0.23:
                status = "missed"
            else:
                status = "done"

            # ---- 先算这节课该有多少 TSS (用恒定功率快速估算做目标值) ----
            avg_w = sum(w_ * m for m, w_ in segs) / sum(m for m, _ in segs)
            hours = sum(m for m, _ in segs) / 60.0
            # TSS = 小时 x (平均功率/FTP)^2 x 100
            # 第一版误用 x60, 导致"实际/计划"算出 194% —— 目标值偏小 40%,
            # 任何达成都显示成超额完成, 这种错会直接让 compliance 失去意义。
            tss_target = max(20, int(hours * (avg_w / FTP) ** 2 * 100))

            planned_id = None
            if planned:
                pw = PlannedWorkout(
                    athlete_id=a.id, scheduled_date=d, title=name, intent=intent,
                    duration_target_min=int(hours * 60), tss_target=tss_target,
                    status=("skipped" if status == "skipped" else "planned"),
                )
                db.add(pw)
                db.commit()
                db.refresh(pw)
                planned_id = pw.id
                n_plan += 1
                tss_planned += tss_target
                if status == "skipped":
                    n_skip += 1

            if status == "skipped":
                continue

            # ---- 完成的部分: 实际功率在目标的 85%~120% ----
            if status == "missed":
                perf = rng.uniform(0.55, 0.8)
            else:
                perf = rng.uniform(0.85, 1.15)
            # perf 表达的是"实际 TSS 达到目标的多少", 必须作用在 TSS 上。
            # TSS ∝ 功率², 所以功率要乘 sqrt(perf)。
            # 第一版直接乘功率, 结果实际/目标 TSS 中位数 1.46 ——
            # 演示数据自己就把负荷达成率报成 139%, 用户看到的全是"超额完成"。
            k = perf ** 0.5
            actual_segs = [(m, max(55, int(w_ * k))) for m, w_ in segs]

            path = out_dir / f"w{w+1}_d{day_idx}_{intent}.fit"
            # 断言常量没和真实命名脱节 —— force 删除逻辑依赖它。
            # 一旦脱节就是"静默删不掉"或"静默删太多", 所以当场炸。
            assert _is_demo_file(path.name), (
                f"实际文件名 {path.name!r} 没匹配 DEMO_FILE_RE "
                f"({DEMO_FILE_RE!r}) —— 删除旧 demo 数据的逻辑会失准"
            )
            start_dt = datetime.combine(
                d, datetime.min.time(), tzinfo=timezone.utc
            ) + timedelta(hours=6)
            gt = build_profile_fit(
                path, actual_segs, start=start_dt, seed=w * 100 + day_idx,
                # V0.9.1: 采样率 2s 而不是默认的 1s。
                #
                # 慢的根源在这里 —— 造一条 1.5h 的 FIT 要 10 秒(每秒一个采样点,
                # 5400 条 fitparse 记录), 8 周 40 条就是 6 分钟; 而这个测试
                # 文件调了 4 次(第 3 个测试跑两遍), **单文件 24 分钟**,
                # 全量套件因此要 1 小时 44 分起。
                #
                # 实测降采样对统计特征无损(同一条课):
                #     1s: 4200 点 avg=130.0 std=14.8
                #     2s: 2100 点 avg=130.0 std=14.9
                #     5s:  840 点 avg=130.0 std=14.8
                # 功率是缓变信号, 2s 采样不丢任何统计特征, 速度快 2.4 倍。
                #
                # 只改 demo 生成的采样率, **不动 realistic_rides 的默认值** ——
                # 那些是测试夹具, 保持 1s 才不降低其他测试的真实性。
                sample_interval_s=2.0,
                ftp=FTP, lthr=LTHR,
            )

            try:
                # 批量导入: 关掉逐条 PMC 重算, 最后统一算一次。
                # 既快(O(n^2) -> O(n)), 也避免 PMC 内部异常把事务搞脏。
                res = asyncio.run(svc.upload(path.name, path.read_bytes(),
                                            recompute_pmc_eagerly=False))
            except Exception as e:
                # ⚠️ 失败原因必须留住。之前只 print 一行, 汇总时 n_ride 对不上
                # 只能报"生成 45 条但库里 0 条" —— **不说哪条失败、为什么失败**,
                # 排查时等于瞎猜。
                n_fail += 1
                _failures.append(f"第{w+1}周/{name}/{intent}: "
                                 f"{type(e).__name__}: {str(e)[:150]}")
                print(f"  ! 第{w+1}周 {name} 导入失败: {type(e).__name__}: {e}")
                db.rollback()
                continue
            act_id = res.get("id") if isinstance(res, dict) else getattr(res, "id", None)
            n_ride += 1
            act_tss = 0
            act = db.query(Activity).filter(Activity.id == act_id).first()
            if act:
                act_tss = (act.metrics or {}).get("tss") or 0
                tss_actual += act_tss
            if planned_id and act_id:
                pw = db.get(PlannedWorkout, planned_id)
                # "missed" = 计划了但没完成 (拖延/半途而废), 不能标成 done,
                # 否则完成率永远是 100%, 演示数据反而在骗人。
                pw.status = "done" if status == "done" else "missed"
                if status == "done":
                    pw.actual_activity_id = act_id
                    pw.completed_at = act.start_time
                    db.commit()
                    n_done += 1
                else:
                    db.commit()
                    n_miss += 1
            print(f"  W{w+1} {d} {name:<12} {intent:<10} "
                  f"功率{gt['avg_power']:>3.0f}W  {gt['duration_s']//60:>3}min  "
                  f"TSS {act_tss:>5.0f}/{tss_target:<4} {status}")

    # 关掉逐条 PMC 重算之后, 必须在收尾**统一算一次** ——
    # 否则示例数据的 PMC / 体能曲线是空的, 用户看到 0/5 维度却以为 App 坏了。
    #
    # ⚠️🔴 V0.9.1: `_aid` 在这里用, 但它在下面 ~490 行才被赋值 ——
    #   UnboundLocalError: cannot access local variable '_aid'
    #   而且它被 try/except Exception 吞掉了, 只打印一行 WARN,
    #   **表面上"载入成功", 实际上 PMC 曲线是空的** ——
    #   用户看到"体能 0/5 维度", 以为 App 坏了。
    #
    #   静默吞异常 + 变量顺序错误 = 双重掩盖。这类地方要一起看。
    if n_ride:
        try:
            from cycling_coach.core.pmc import recompute_pmc as _rpmc
            _athlete_id = db.query(Athlete).first().id
            _days = _rpmc(db, _athlete_id)
            print(f"  PMC 已重算 {_days} 天")
        except Exception as _e:
            print(f"  ⚠️ PMC 重算失败(不影响训练数据本身): {_e}")

    db.close()
    print()
    print("=" * 56)
    print(f"训练记录 {n_ride} 条 | 计划课 {n_plan} 条")
    print(f"  完成 {n_done} | 未完成 {n_miss} | 主动跳过 {n_skip}")
    print(f"计划 TSS 合计 {tss_planned:.0f} | 实际 TSS 合计 {tss_actual:.0f} "
          f"({tss_actual/tss_planned*100 if tss_planned else 0:.0f}%)")
    print(f"数据目录: {os.environ['WORKSPACE_DIR']}")

    # 交付前自检: 活动和课表必须挂在同一个车手上
    #
    # ⚠️ 这里不能读 `a.id` —— ORM 对象在前面某次 commit() 之后已经 detached,
    # 读属性会 DetachedInstanceError。**这个 bug 只有真跑才暴露**,
    # 静态看完全正常(它原本就存在, 只是以前 return 0 用不到这些字段)。
    # 所以重新查一次数据库拿值, 不碰已 detach 的对象。
    from cycling_coach.data.sqlite.models import Activity as _Act
    # 🔴 V0.9.1: 原来是按名字查 `Athlete.name == athlete_name`("演示车手")。
    # 但 V0.9.1 之后 demo **复用库里第一个车手**, 它的名字可能是用户自己的
    # 真实姓名 —— 于是这里查到 None, `_aid` 变成 None,
    # 后面所有校验都作用在 NULL 上, 静默失效。
    #
    # 和写入侧保持同一个口径: **第一个车手**。
    _arow = db.query(Athlete).first()
    _aid = _arow.id if _arow else None
    _aname = _arow.name if _arow else athlete_name
    _aftp = _arow.ftp if _arow else None
    from sqlalchemy import text as _sql_text
    # ⚠️ 原来查的是 **全库** 的 athlete_id, 于是校验语义变成了
    # "库里所有活动必须属于同一个车手"。
    #
    # 但"用户自己有 5 条训练 + 点先看示例加了 45 条演示数据"是完全合法的,
    # 这时候 acts_ath = {1, 2}、plan_ath = {2} → 报"归属校验失败" → 载入失败。
    #
    # 校验真正要抓的是: **这次生成的演示数据自己内部**别错绑
    # (演示活动挂用户车手、演示课表挂演示车手)。
    # 所以只查演示车手名下的记录。
    acts_ath = {r[0] for r in db.execute(
        _sql_text("SELECT DISTINCT athlete_id FROM activities WHERE athlete_id = :aid"),
        {"aid": _aid}).fetchall()}
    plan_ath = {r[0] for r in db.execute(
        _sql_text("SELECT DISTINCT athlete_id FROM planned_workouts WHERE athlete_id = :aid"),
        {"aid": _aid}).fetchall()}
    if not args.no_plans and acts_ath and plan_ath and acts_ath != plan_ath:
        raise SystemExit(
            f"❌ 归属校验失败: 演示活动在 athlete {acts_ath}, "
            f"演示课表在 {plan_ath}。这种数据看起来正常但用起来全错, 宁可构建失败。"
        )
    # 收窄范围之后上面那条几乎不可能触发, 所以补一条**真的能触发**的:
    # 演示车手名下的活动数必须等于我们生成的数。
    #
    # 这才是那个校验真正想抓的 —— "活动挂错车手"最常见的形态不是
    # 活动落在两个车手上, 而是**一条都没落到演示车手上**。
    # 🔴 V0.9.1: 复用第一个车手之后, 这个校验的**语义必须跟着改**。
    #
    # 原来 `_demo_acts` 查的是"这个车手名下所有活动", 于是隐含假设
    # "他名下只有演示数据"。V0.9.1 之后 demo 复用用户第一个车手,
    # 用户可能已经有自己的训练 —— 于是:
    #     用户 1 条 + demo 12 条 = 13 != n_ride(12)
    # 校验失败 → SystemExit → HTTP 409, **但数据其实已经写进去了**。
    # 用户看到"载入失败", 数据库里却有 13 条, 状态自相矛盾。
    #
    # 修法: 记录**入库前**该车手的活动数, 校验增量。
    # 这样校验真正想抓的东西("这次生成的演示数据一条都没落到
    # 正确的车手上")依然能抓到, 又不受用户既有数据干扰。
    _demo_acts = db.execute(
        _sql_text("SELECT COUNT(*) FROM activities WHERE athlete_id = :aid"),
        {"aid": _aid}).scalar() or 0
    if _demo_acts - _acts_before < n_ride - n_fail:
        _why = (f"\n\n失败明细(前 5 条):\n    " + "\n    ".join(_failures[:5])
                if _failures else
                "\n\n⚠️ 没有任何一条报了失败, 但入库数对不上 —— "
                "那就是 upload 内部静默吞掉了异常(比如 recompute_pmc 失败后 "
                "session 进入 PendingRollback 状态, 后续 commit 全部作废)。")
        raise SystemExit(
            f"❌ 归属校验失败: 演示车手 #{_aid} 名下这次只新增了 "
            f"{_demo_acts - _acts_before} 条活动, "
            f"但我们生成了 {n_ride} 条(失败 {n_fail} 条)。{_why}\n\n"
            f"最可能的原因: **这次没加 --force, 而库里已经有同一批示例数据**。\n"
            f"   (demo 的 FIT 用固定随机种子生成, 每次内容完全一样 → SHA256 相同\n"
            f"    → 被上传去重逻辑挡掉, 一条都插不进去)\n"
            f"   重新载入请加 --force。"
        )
    if _failures:
        print(f"⚠️ 有 {n_fail} 条训练导入失败(已跳过), 其余 {n_ride} 条成功")
    print(f"归属校验: 活动与课表均在 athlete {acts_ath or plan_ath} ✅")
    print("=" * 56)
    # ⚠️ commit() 之后 `a` 会 detach, 再读属性会 DetachedInstanceError。
    # 这个 bug 只有真跑才暴露 —— 静态看完全正常。
    # 所以在 commit 前就把值取出来, 提交后只用局部变量。
    return {
        "athlete_id": _aid,
        "athlete_name": _aname,
        "ftp": _aftp,
        "n_activities": n_ride,
        "n_planned": n_plan,
        # 🔴 V0.9.1: 复用第一个车手后, 示例数据可能和用户自己的训练
        # 混在同一个档案里。**这件事必须让前端知道** ——
        # 用户有权知道自己的档案里被塞进了 12 条不是自己骑的训练。
        "mixed_with_existing": _mixed_with_existing,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="装载 8 周演示训练数据")
    ap.add_argument("--weeks", type=int, default=8)
    ap.add_argument("--end", type=str, default=None, help="最后一天 YYYY-MM-DD, 默认今天")
    ap.add_argument("--athlete", type=str, default="演示车手")
    ap.add_argument("--workspace", type=str, default=None)
    ap.add_argument("--no-plans", action="store_true", help="只造训练记录, 不造课表")
    ap.add_argument("--force", action="store_true",
                    help="先删掉已有的演示车手及其数据, 再重新生成 (不加就是复用现有数据)")
    a = ap.parse_args()
    load_demo_data(weeks=a.weeks, end=a.end, athlete_name=a.athlete,
                   force=a.force, no_plans=a.no_plans, workspace=a.workspace)
    return 0


if __name__ == "__main__":
    sys.exit(main())
