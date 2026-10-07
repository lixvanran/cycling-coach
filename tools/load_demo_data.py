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


def _clear_athlete_rows(db, athlete_id: int) -> dict[str, int]:
    """删掉某个车手名下的**所有**记录(遍历所有外键引用表)。

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
            n = db.execute(
                _text(f"SELECT COUNT(*) FROM {t} WHERE {col} = :aid"),
                {"aid": athlete_id},
            ).scalar() or 0
            if n:
                db.execute(_text(f"DELETE FROM {t} WHERE {col} = :aid"),
                           {"aid": athlete_id})
                removed[t] = n
        except Exception as e:
            logger.debug(f"跳过 {t}: {e}")
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


def _delete_athlete_hard(db, athlete_id: int) -> None:
    """删车手: 清掉所有引用行, 再删 athletes 本身。

    ## 这里踩了四次, 每次错法不同 —— 全记下来

    1. `db.delete(athlete)` → ORM 按 relationship 发
       `UPDATE activities SET athlete_id=NULL`, 而该列 NOT NULL → IntegrityError
    2. 改用原生 SQL 删行, 但 session 的 identity map 里还留着那个对象
       → 后续用它报 "has been deleted, or its row is otherwise not present"
    3. 为修 #2 用 `db.expunge_all()` → 把 session 里**所有**对象都踢出去
       → 报 "is not bound to a Session"
    4. 手动 `db.expunge(obj)` 遍历 identity_map → 还是 #2
       （expire_all 之后访问 obj.id 本身就可能抛异常, 遍历并不可靠）

    **最终解法: 让 ORM 自己同步 identity map**, 别手动摘:
        db.query(Athlete).filter(...).delete(synchronize_session="fetch")

    ## 更要命的: CLI 能过, API 500

    1-4 之间还藏着一个陷阱: **命令行跑通了不代表修好了**。
    CLI 是新进程新 session(里面没别的对象), API 路径的 session 里
    已经加载过 athlete, 于是只有 API 挂。

    所以这条路径我坚持用**浏览器点按钮**验, 而不是只跑脚本。
    """
    from cycling_coach.data.sqlite.models import Athlete as _Athlete

    _clear_athlete_rows(db, athlete_id)
    # synchronize_session="fetch" 让 ORM 把 identity map 里对应的对象清掉,
    # 否则后面任何一次属性访问都会报 "has been deleted"
    db.query(_Athlete).filter(_Athlete.id == athlete_id).delete(
        synchronize_session="fetch"
    )
    db.commit()

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
        old_a = db.query(Athlete).filter(Athlete.name == args.athlete).first()
        if old_a:
            _removed = _clear_athlete_rows(db, old_a.id)
            _delete_athlete_hard(db, old_a.id)
            print(f"已清除旧的演示数据: "
                  f"{sum(_removed.values())} 行 ({', '.join(f'{k}:{v}' for k, v in _removed.items())})")

        # V0.9.0: 同时清掉 ActivityService 自动建的占位 athlete。
        #
        # 背景: `ActivityService.__init__` 会调 get_or_create_athlete(),
        # 它"返回第 1 个 athlete, 没有就建一个叫 Rider(ftp=250)"。
        # 空库 + 点「先看示例」= 先建了 Rider(id=1), 再建 演示车手(id=2),
        # 于是 ActivityService 绑到 #1 而计划课挂在 #2 ——
        # 下面那道归属校验会直接抛 SystemExit, 用户看到"载入失败"。
        #
        # 原来的 --force 只删**同名**的演示车手, 清不掉这个占位。
        # 但占位的意思是"没有任何活动", 删掉它不会丢用户数据。
        # 保守起见只在那个 athlete 名下**一条活动都没有**时才删。
        # ⚠️ 原来这里按 **名字 == "Rider"** 找占位车手, 但用户可能:
        #   - 改过名字(设置页里填了真实姓名)
        #   - 装的是旧版本, 占位叫别的名字
        # 这时候占位清不掉 → ActivityService 绑到 #1、课表挂到 #2 →
        # 归属校验直接失败 → 用户点"先看示例"只看到"载入失败"。
        #
        # 判据应该是"这个车手名下什么都没有", 不是"它叫什么名字"。
        #
        # ⚠️ 而且**不能只查活动**: 有 13 张表外键引用 athletes
        # (daily_metrics / ftp_tests / training_phases / chat_sessions /
        #  training_diary / ml_predictions / ...)。我第一版只查了 activities
        # 和 training_phases, 结果删一个"看起来空"的车手时
        # FOREIGN KEY constraint failed —— 而**删车手失败会让整个载入失败**。
        #
        # 所以: 一次性扫全部引用表, 任何一张有行就不删。
        from sqlalchemy import inspect as _inspect
        _insp = _inspect(db.bind)
        _ref_tables = []
        for _t in _insp.get_table_names():
            for _fk in _insp.get_foreign_keys(_t):
                if _fk.get("referred_table") == "athletes":
                    _ref_tables.append((_t, _fk.get("constrained_columns")))
                    break

        for placeholder in db.query(Athlete).all():
            if placeholder.name == args.athlete:
                continue                       # 那是演示车手本身, 不能删
            _occupied = None
            for _t, _cols in _ref_tables:
                _col = _cols[0]
                try:
                    _n = db.execute(
                        __import__("sqlalchemy").text(
                            f"SELECT COUNT(*) FROM {_t} WHERE {_col} = :aid"
                        ), {"aid": placeholder.id}
                    ).scalar() or 0
                except Exception:
                    continue                    # 表不存在/列名不同 -> 跳过
                if _n:
                    _occupied = f"{_t}({_n})"
                    break
            if _occupied is None:
                # ⚠️ 名字要**先取出来**再删。
                # 删完之后对象已经不在 session 里(synchronize_session 把它摘掉了),
                # 这时再读 `placeholder.name` 就是 DetachedInstanceError。
                #
                # "先操作对象, 再打印它的属性" —— 顺序反了就炸。
                _pid, _pname = placeholder.id, placeholder.name
                _delete_athlete_hard(db, _pid)
                print(f"  已清除空车手 id={_pid} 名字={_pname!r} "
                      f"(活动/计划/课程/对话全空)")
            else:
                print(f"  保留车手 id={placeholder.id} 名字={placeholder.name!r} "
                      f"—— 名下有 {_occupied}, 不动它")

    a = db.query(Athlete).filter(Athlete.name == args.athlete).first()
    if a is None:
        a = Athlete(
            name=args.athlete, ftp=FTP, lthr=LTHR,
            max_hr=HR_MAX, weight_kg=WEIGHT,
        )
        db.add(a)
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

    out_dir = Path(os.environ["WORKSPACE_DIR"]) / "_demo_fits"
    out_dir.mkdir(parents=True, exist_ok=True)

    n_ride = n_plan = n_done = n_skip = n_miss = 0
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
            start_dt = datetime.combine(
                d, datetime.min.time(), tzinfo=timezone.utc
            ) + timedelta(hours=6)
            gt = build_profile_fit(
                path, actual_segs, start=start_dt, seed=w * 100 + day_idx,
                ftp=FTP, lthr=LTHR,
            )

            try:
                res = asyncio.run(svc.upload(path.name, path.read_bytes()))
            except Exception as e:
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
    _arow = db.query(Athlete).filter(Athlete.name == athlete_name).first()
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
    _demo_acts = db.execute(
        _sql_text("SELECT COUNT(*) FROM activities WHERE athlete_id = :aid"),
        {"aid": _aid}).scalar() or 0
    if _demo_acts != n_ride:
        raise SystemExit(
            f"❌ 归属校验失败: 演示车手 #{_aid} 名下只有 {_demo_acts} 条活动, "
            f"但我们生成了 {n_ride} 条 —— 说明活动挂到了别的车手上。"
        )
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
