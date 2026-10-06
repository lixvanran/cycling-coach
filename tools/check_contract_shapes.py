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

        for field in spec.get("must_be_none", []):
            if body.get(field) is not None:
                failures.append(
                    f"{endpoint}.{field} = {body.get(field)!r}, 零数据时必须为 None"
                )
        for field in spec.get("must_be_false", []):
            if body.get(field) is not False:
                failures.append(
                    f"{endpoint}.{field} = {body.get(field)!r}, 零数据时必须为 False"
                )
        for field, val in spec.get("forbid_literals", []):
            if body.get(field) == val:
                failures.append(
                    f"{endpoint}.{field} = {val!r} —— 这是'看起来合法的默认值', "
                    f"不是'缺失'"
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
