#!/usr/bin/env python3
"""workout intent 词汇表一致性检查 —— V0.9.1

## 为什么需要这个

`intent` / `intensity` 这个字段在系统里同时出现在**五处**, 而它们
从来没有任何一处强制一致:

| 位置 | 原本用的值 |
|---|---|
| `data/sqlite/models.py` 注释说明的标准 | `recovery/endurance/tempo/threshold/vo2max/race` |
| 前端 `CalendarPage.INTENT_LABEL` | 同上(含 vo2max) |
| 前端 `DailyRecommendationCard.WORKOUT_META` | 含 **vo2** ← 不同 |
| `core/coaching/recommendations.py` `_TIER_ORDER` | 含 **vo2** ← 不同 |
| `tests/realistic_rides.py` `WORKOUT_LIBRARY` | 含 **vo2 / sweet_spot** ← 两个都不对 |

后果不是"页面报错", 而是**静默降级**:

- `INTENT_LABEL[p.intent]` 查不到 → 悬停提示显示 `甜点课 · undefined · 90min`
- `WORKOUT_META[...]` 查不到 → 静默 fallback 到 endurance,
  **把"高强度日"显示成"轻松日"** —— 这是安全性问题, 不是显示问题
- 任何"按 intent 匹配课程库"的查询 → 一条都匹配不上

三套拼法(`vo2max` / `vo2` / `sweet_spot`)混在一个库里, 意味着**按 intent 分组的
任何统计都会漏掉一部分**, 而漏掉的量取决于哪个拼法出现得多 —— 不可预测。

## 为什么写成脚本而不是 pytest

`apps/web` 是 TypeScript, 后端是 Python, 两边都要读。脚本能同时读两边,
而且能在 CI 里独立跑, 不需要起服务。

## 用法

    python tools/check_intent_vocab.py
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 权威定义。改这里之前先想清楚 —— 改这一行等于改全系统的契约。
CANONICAL_INTENTS = frozenset({
    "recovery", "endurance", "tempo", "threshold", "vo2max", "race",
})

# 推荐系统的"档位", 和训练意图不是一回事: "rest"=完全休息,
# "none"=数据不足不给建议。它们永远不会出现在 workouts.intensity 里。
REC_TIERS = frozenset({"rest", "none"})

# 只统计这些目录, 排除 dist/ 和前端 node_modules
SCAN = [
    ROOT / "cycling_coach",
    ROOT / "tools",
    ROOT / "tests",
]


def _norm(rel) -> str:
    try:
        return str(Path(rel).resolve().relative_to(ROOT.resolve())).replace("\\", "/")
    except Exception:
        return str(rel)


# ⚠️ 检查器自己会包含 "vo2"/"sweet_spot" 这些字面量(白名单配置),
#    必须排除 —— 否则它会永远报自己, 然后被人当成噪音忽略掉。
#    **一个永远红的检查等于没有检查。**
SELF = _norm(__file__) if "__file__" in globals() else ""

# 这些是"合法的非 intent 用法", 不算违规
ALLOW = {
    # acwr 的负荷区间名, 和训练意图无关 —— 同形异义, 容易误判
    ("cycling_coach/core/metrics/acwr.py", "sweet_spot"),
}


def collect_python() -> list[tuple[str, int, str, str]]:
    """从 Python 源码里抓 intent 相关字符串。"""
    hits = []
    for base in SCAN:
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            rel = _norm(p)
            if rel == SELF:
                continue          # 别扫自己
            try:
                src = p.read_text(encoding="utf-8")
            except Exception:
                continue
            for i, line in enumerate(src.splitlines(), 1):
                s = line.strip()
                if s.startswith("#") or s.startswith('"') or s.startswith("'"):
                    continue
                code = line.split("#")[0]
                for m in re.finditer(r'"([a-z0-9_]+)"', code):
                    val = m.group(1)
                    if val in CANONICAL_INTENTS:
                        continue
                    # 形近但不是 intent 的合法词
                    if any(val == a[1] and _norm(p) == a[0] for a in ALLOW):
                        continue
                    # 只关心那几个真正出问题的
                    if val in ("vo2", "sweet_spot", "vo2max_interval"):
                        hits.append((rel, i, val, s[:70]))
    return hits


def collect_frontend() -> dict[str, set[str]]:
    """从 TS 里抓 INTENT_LABEL / WORKOUT_META / _TIER_ORDER 的键。"""
    out: dict[str, set[str]] = {}
    files = [
        ("apps/web/src/pages/CalendarPage.tsx", "INTENT_LABEL"),
        ("apps/web/src/pages/CalendarPage.tsx", "INTENT_ICON"),
        ("apps/web/src/components/DailyRecommendationCard.tsx", "WORKOUT_META"),
    ]
    for rel, name in files:
        p = ROOT / rel
        if not p.exists():
            continue
        src = p.read_text(encoding="utf-8")
        # 对象可能写成单行或多行, 结尾可能是 "};" 或 "}"
        m = re.search(rf"{name}\s*:[^=]*=\s*\{{(.*?)\n\s*\}}", src, re.S)
        if not m:
            continue
        # 抓所有 `key:` 形式, 再排除嵌套的类型标注/字段名。
        #
        # 为什么不用花括号深度: INTENT_LABEL 和 WORKOUT_META 都是
        # **单行对象**, 而它们各自的值里又带嵌套对象
        # (`icon: Activity, color: "..."`), 按行算深度必然出错 ——
        # 我试过行级深度, 结果 INTENT_LABEL 只读到 1 个键。
        #
        # 排除法反而稳: 嵌套键名来自 TypeScript 的**值定义**,
        # 那是一份有限的、写死在 `WORKOUT_META` 声明里的字段集合,
        # 不可能和训练意图重名。
        NESTED_FIELD_KEYS = {
            # WORKOUT_META 的值结构
            "label", "icon", "color", "tssHint",
            # INTENT_ICON / INTENT_DEFAULT 的值结构
            "duration", "tss",
        }
        # ⚠️ 必须先去注释 —— 否则注释里一句 "见 models.py:135" 的
        #    `py:135` 会被当成一个键。注释会随代码演化, 误报会让人
        #    习惯性忽略这个检查。
        body = "\n".join(
            ln for ln in m.group(1).splitlines()
            if not ln.strip().startswith("//")
        )
        keys = set(re.findall(r'([a-zA-Z_][a-zA-Z0-9_]*)\s*:', body))
        keys -= NESTED_FIELD_KEYS
        out[f"{rel}:{name}"] = keys
    return out


def collect_python_lists() -> dict[str, set[str]]:
    """_TIER_ORDER 这类 Python 里的字符串列表。"""
    out: dict[str, set[str]] = {}
    for p in (ROOT / "cycling_coach").rglob("*.py"):
        rel = _norm(p)
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in tree.body:
            if isinstance(node, ast.Assign) and isinstance(node.value, ast.List):
                tgt = node.targets[0]
                name = getattr(tgt, "id", "") or getattr(tgt, "attr", "")
                if not name or "TIER" not in name.upper():
                    continue
                vals = {e.value for e in node.value.elts
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)}
                out[f"{rel}:{name}"] = vals
    return out


def main() -> int:
    print("检查 workout intent 词汇表是否全局一致")
    print(f"权威定义: {sorted(CANONICAL_INTENTS)}\n")

    bad = False

    # 1. 前端映射表
    for name, keys in collect_frontend().items():
        extra = keys - CANONICAL_INTENTS - REC_TIERS
        if extra:
            bad = True
            print(f"❌ {name}")
            print(f"   非标准键: {sorted(extra)}")
        else:
            print(f"✅ {name}: {len(keys)} 个键全部标准")

    # 2. Python 里的列表常量
    for name, vals in collect_python_lists().items():
        # "rest"/"none" 是**推荐档位**, 不是训练意图 —— 合法
        extra = vals - CANONICAL_INTENTS - REC_TIERS
        if extra:
            bad = True
            print(f"❌ {name}")
            print(f"   非标准值: {sorted(extra)}")
        else:
            print(f"✅ {name}: {sorted(vals)}")

    # 3. 源码里的形近拼法
    hits = collect_python()
    if hits:
        bad = True
        print("\n❌ Python 源码里出现非标准 intent 拼法:")
        for rel, line, val, text in hits:
            print(f"   {rel}:{line}  {val!r}   {text}")
        print("\n   注意区分同形异义:")
        print("     - acwr.py 的 sweet_spot 是**负荷区间**, 不是训练意图")
        print("     - workouts.py 的 tags 里的 vo2 是**搜索关键字**, 合法")
    else:
        print("✅ Python 源码无 vo2 / sweet_spot 作 intent 用法")

    if bad:
        print("\n❌ intent 词汇表不一致。")
        print("   后果是静默的: 查不到映射 → undefined, 或错误地 fallback 到 endurance")
        print("   —— 后者会把'高强度日'显示成'轻松日'。")
        return 1
    print("\n✅ intent 词汇表全局一致。")
    return 0


if __name__ == "__main__":
    sys.exit(main())