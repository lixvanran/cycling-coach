#!/usr/bin/env python
"""V0.9.0: 跨层契约形状检查

## 为什么需要这个脚本

2026-10-06 的三个 P0 里, **有两个**是同一类病:

| P0 | 后端 | 前端 |
|---|---|---|
| 周期化白屏 | 零数据返回 `dimensions: null` | 类型写 `dimensions: {...}`, 直接 `[k]` → TypeError |
| 阶段处方编数字 | 零数据返回 `0` (看起来合法) | 类型写 `number`, 照着渲染 |

共同点: **后端改了契约, 前端类型没跟上。**

tsc 抓不到跨语言的情况 —— 它只看 TypeScript 内部自洽。
所以这里从后端侧实际调用端点, 把"零数据时到底返回什么形状"记下来,
跟一个显式的契约表比对。

## 为什么不用 mock

因为今天三个 P0 全都是**静默失效**: 没异常, 没日志, 测试全绿。
唯一能暴露它们的方式是**真的去调那个端点, 看真的返回什么**。

## 怎么扩展

新增一个容易忘的端点时, 在 CONTRACT 里加一条:
- 零数据下必须为 None 的字段
- 零数据下**不允许**出现的"看起来合法的默认值"
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


# 端点 -> (零数据时必须为 None 的字段, 零数据时不允许出现的值)
#
# ⚠️ 维护提醒: 每次有人把某个字段"改成 None"以表达数据不足,
# 就要在这里登记。**没登记 = 没测 = 会静默退化。**
CONTRACT: dict[str, dict] = {
    "/api/race-prep/training-state": {
        # P0-1: 曾返回 dimensions: null 而前端当对象用 → 整页白屏
        "must_be_none": ["dimensions", "overall", "interpretation", "source"],
        "must_be_false": ["data_sufficient"],
        "forbid_literals": [],
    },
    "/api/phases/suggest": {
        # P0-3: 曾返回 0 —— 0 是"建议一周都不练", 看起来像一份具体处方
        "must_be_none": [
            "target_weekly_tss", "target_weekly_tss_range", "weeks_recommended",
        ],
        "must_be_false": ["data_sufficient"],
        "forbid_literals": [("target_weekly_tss", 0), ("weeks_recommended", 0)],
    },
    # 🔴 Verifier P2-A: 这个端点之前**不在表里** —— 而它恰好是问题最集中
    # 的那个: 上一轮 P0-2 的 500 在它上面, NEW P1-A 的假 ACWR 警告也在它上面。
    # 门禁漏了最该盯的地方。
    "/api/recommendations/today": {
        # 零数据时 readiness 必须是 None 而不是 0 或某个"看起来正常"的分数
        "must_be_none": ["readiness_score"],
        "must_be_false": [],
        "forbid_literals": [],
        # ⚠️ `target_tss` 故意**不**登记 —— 我第一版把它加进来, 脚本立刻报错。
        # 查过之后确认是**我登记错了, 不是实现错**:
        #   - 同一响应里 readiness_score=null + label="数据不足" 已经说清楚了
        #   - DailyRecommendationCard 用 `{hasScore && ...}` 守着, 零数据时
        #     那一整段根本不渲染, 用户看不到 "目标 TSS ~0"
        # 所以这个 0 不会误导任何人, 强行改成 None 反而是过度反应。
        #
        # **门禁也要有"故意不登记"的记录**, 否则下一个人会以为漏了。
        # 额外判据: 不能出现任何"ACWR 处方"字样。
        # P1-A 就是这么漏的: 8 天训练史拿到 "ACWR 危险区 3.50 / 立即减量 30-50%"。
        "forbid_substrings": [
            "ACWR 危险区", "立即减量", "伤病风险", "急慢性负荷比",
        ],
    },
    "/api/trust/self-check": {
        # 数据不足时不该有任何维度"可用"
        "must_be_none": [],
        "must_be_false": [],
        "forbid_literals": [],
        "predicate": lambda d: d.get("n_available", 0) == 0,
        "predicate_msg": "零数据用户 n_available 应为 0, 实际 %s",
    },
}


def main() -> int:
    from tests.conftest import use_temp_db
    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import SessionLocal, rebind_engine
    from cycling_coach.api.main import app

    failures: list[str] = []

    for name in (None, "contract_shape_check"):
        use_temp_db(name)
    db = SessionLocal()
    rebind_engine(str(db.get_bind().url))   # 必须绑空库, 否则读到脏数据
    client = TestClient(app)

    for endpoint, spec in CONTRACT.items():
        r = client.get(endpoint)
        if r.status_code != 200:
            failures.append(f"{endpoint} 零数据返回 HTTP {r.status_code} (应为 200)")
            continue
        body = r.json()

        # 🔴 Verifier P2-A: 原来写的是 `if body.get(field) is not None`,
        # 而**字段根本不存在时 .get() 也返回 None** —— 于是"字段被改名"
        # 这类最典型的跨层断裂, 这个专门抓断裂的脚本**一声不吭**。
        #
        # 实测: 把 `target_weekly_tss` 改名成 `target_tss` → 仍然报 ✅ 通过。
        #
        # 字段不存在不是"正确地是 None", 是"这个键没了"。两者必须分开。
        for field in spec.get("must_be_none", []):
            if field not in body:
                failures.append(
                    f"{endpoint}.{field} 字段不存在 —— 这不是'值为 None', "
                    f"是契约断了(字段可能被改名了)。"
                    f"现有键: {sorted(body)[:12]}"
                )
            elif body[field] is not None:
                failures.append(
                    f"{endpoint}.{field} = {body[field]!r}, 零数据时必须为 None"
                )
        for field in spec.get("must_be_false", []):
            # 原来字段缺失时 `None is not False` 会报错 —— 方向对, 但
            # 错误信息没说清是"缺失"还是"值不对"。分开报。
            if field not in body:
                failures.append(
                    f"{endpoint}.{field} 字段不存在 —— 契约断了(字段可能被改名了)"
                )
            elif body[field] is not False:
                failures.append(
                    f"{endpoint}.{field} = {body[field]!r}, 零数据时必须为 False"
                )
        # forbid_literals 保留: 当某个字段"合法存在但默认值不可接受"时用它。
        # 注意别和 must_be_none 登记同一个字段 —— 那会让同一个错误报两遍。
        for field, val in spec.get("forbid_literals", []):
            if field in body and body[field] == val:
                failures.append(
                    f"{endpoint}.{field} = {val!r} —— 这是'看起来合法的默认值', "
                    f"不是'缺失'"
                )
        # Verifier P2-A 补充: 逐条测试, 但要抓"字符串本身"级别的伪造。
        # 上面那些 must_be_none / forbid_literals 都是结构断言, 抓不到
        # "字段结构没变但内容是编的" —— P1-A 正是这种。
        for needle in spec.get("forbid_substrings", []):
            if needle in json.dumps(body, ensure_ascii=False):
                failures.append(
                    f"{endpoint} 响应里出现 {needle!r} —— "
                    f"数据不足时不该出现这类处方/警告"
                )
        pred = spec.get("predicate")
        if pred and not pred(body):
            failures.append(spec.get("predicate_msg", "predicate failed") % body.get("n_available"))

    if failures:
        print("❌ 契约形状检查失败:\n")
        for f in failures:
            print(f"   - {f}")
        print(
            "\n这些字段昨天还在返回编造的数字。修的时候记得同步:\n"
            "   后端返回 → 前端类型 → 前端渲染\n"
            "(今天三个 P0 有两个是只改了后端, 忘了另外两层)"
        )
        return 1

    print(f"✅ 契约形状检查通过 ({len(CONTRACT)} 个端点, 零数据场景)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
