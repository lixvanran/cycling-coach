#!/usr/bin/env python
"""V0.9.0: 零数据 / 真实数据 双跑差分扫描器

## 为什么要有这个工具

2026-10-06, Verifier 指出我的"诚实性扫描器"有个结构性局限:

> 它的 class A 只找**打分函数** —— 而我那 6 个 P0/P1 里, 5 个是
> 契约变更 / 新值类型 / dict 形状不一致, **没有一个是正则能看出来的**。

然后它给了个建议(我称之为 item B):

> 对每个"下判断"的函数分别用**零数据**和**真实数据**跑一遍,
> **diff 两个输出** —— 数值上的差异就是候选清单。

## 这个工具做什么

1. 造两个**结构完全相同、只有训练数据不同**的库
   - 空库
   - 有 8 周真实 FIT 训练的库(走完整 upload 路径, 不是塞假数据)
2. 逐个 GET 端点各打一次
3. diff 两个响应, 输出三类线索:

   | 类别 | 含义 |
   |---|---|
   | `ZERO_ONLY` | 零数据时才有 —— 通常是守卫/错误分支, 要看是不是 500 |
   | `FAKE_ZERO` | **零数据时这个字段是 0** —— 最危险, 0 看起来像真实测量值 |
   | `MISSING` | 真实数据时有, 零数据时整个字段消失 —— 前端可能没守卫 |

## 为什么 `FAKE_ZERO` 最危险

`None` 让人停下来问, `0` 让人直接照着骑车。
V0.9.0 修掉的 bug 里有 10 个都是这一株。

## 用法

    python tools/scan_data_honesty.py            # 扫描
    python tools/scan_data_honesty.py --verbose  # 打印完整响应

退出码: 发现可疑项返回 1, 干净返回 0 —— 可以直接挂 CI。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# 这些字段的 0 对用户是有意义的(数量、偏移、页码), 不算 FAKE_ZERO
COUNT_OK = {"count", "total", "offset", "limit", "page", "n_available",
            "n_total", "size", "days", "weeks", "n_activities", "span_days",
            "n_planned", "index", "chunk", "batch", "version", "id",
            # 累计量: 用户确实骑了 0 公里 / 0 TSS, 那个 0 是**诚实的**。
            # 不排除的话工具会变成噪声源 —— 宁可漏报也不要天天误报。
            "total_tss", "total_duration_s", "total_distance_m",
            "total_distance_km", "total_duration_h", "avg_weekly_tss",
            "avg_daily_tss", "tts", "active_days", "days_active"}


def _is_fake_zero(path: str, val) -> bool:
    """判断这个 0 是不是'看起来像真实测量值的 0'"""
    if val != 0 and val != 0.0:
        return False
    key = path.rsplit(".", 1)[-1].lower()
    if key in COUNT_OK:
        return False
    # 指标/分数类字段名 —— 出现 0 就是在骗人
    metric_kw = ("ctl", "atl", "tsb", "score", "power", "hrv", "acwr",
                 "ramp", "overall", "fitness", "fatigue", "form", "rhythm",
                 "recovery", "tss", "duration", "calories", "distance",
                 "rpe", "if_", "np", "vam", "wbal", "work", "load")
    return any(k in key for k in metric_kw)


def _diff(zero, real, path="") -> dict:
    """递归 diff 两个响应, 返回三类线索"""
    out = {"ZERO_ONLY": [], "REAL_ONLY": [], "FAKE_ZERO": [], "DIFFERS": []}

    if type(zero) is not type(real):
        out["DIFFERS"].append(f"{path or '<root>'}: 类型不同 "
                              f"{type(zero).__name__} vs {type(real).__name__}")
        return out

    if isinstance(zero, dict):
        for k in zero:
            if k not in real:
                out["ZERO_ONLY"].append(f"{path}.{k}")
            else:
                for t, items in _diff(zero[k], real[k], f"{path}.{k}").items():
                    out[t].extend(items)
        for k in real:
            if k not in zero:
                out["REAL_ONLY"].append(f"{path}.{k}")
    elif isinstance(zero, list):
        if len(zero) != len(real):
            out["DIFFERS"].append(f"{path}: 长度 {len(zero)} vs {len(real)}")
        elif zero and isinstance(zero[0], dict):
            for t, items in _diff(zero[0], real[0], f"{path}[0]").items():
                out[t].extend(items)
    else:
        if zero == real:
            return out
        # 布尔值不是"假的 0": False 就是一个诚实的"没有负荷数据"。
        # 以前这条扫描把 has_load_data 报成 FAKE_ZERO, 于是真问题(target_tss=0)
        # 被淹没在噪声里 —— **扫描器报假警, 就是在削弱它的可信度**。
        if isinstance(zero, bool) or isinstance(real, bool):
            out["DIFFERS"].append(f"{path}: {zero} vs {real}")
        elif _is_fake_zero(path, zero):
            out["FAKE_ZERO"].append(f"{path} = 0 (真实数据: {real})")
        else:
            out["DIFFERS"].append(f"{path}: {zero} vs {real}")
    return out


def _build_dbs():
    """造两个结构相同的库: 空库 / 有 8 周真实训练"""
    from tests.conftest import use_temp_db
    from cycling_coach.data.sqlite.database import SessionLocal as _SL
    from cycling_coach.core.profile import store as ps
    from cycling_coach.core.services.activity import ActivityService
    from tests.fit_fixtures import build_fit

    use_temp_db("scan_empty")
    from cycling_coach.data.sqlite.database import SessionLocal
    db_e = SessionLocal()
    a = ps.get_or_create_athlete(db_e)
    a.ftp = 250
    db_e.commit()

    use_temp_db("scan_real")
    from cycling_coach.data.sqlite.database import SessionLocal as SL2
    db_r = SL2()
    b = ps.get_or_create_athlete(db_r)
    b.ftp = 250
    db_r.commit()

    tmp = Path(tempfile.mkdtemp(prefix="cc_scan_"))
    svc = ActivityService(db_r)
    loop = asyncio.new_event_loop()
    n = 0
    try:
        for w in range(8):
            for d in range(0, 7, 2):
                p = tmp / f"a{n}.fit"
                build_fit(p, duration_s=3600, avg_power=200, avg_hr=150,
                          speed_mps=8.5,
                          start=datetime(2026, 8, 3, 6, 0) + timedelta(days=w * 7 + d))
                loop.run_until_complete(
                    svc.upload(filename=p.name, file_bytes=p.read_bytes()))
                n += 1
    finally:
        loop.close()
    return db_e, a.id, db_r, b.id, n


def _get_json(client, path: str):
    """只处理 JSON 响应。

    ⚠️ 第一版这里直接 `r.json()`, 于是 `/api/reports/weekly` 返回
    合法 PDF (`%PDF-1.4\n%\x93...`) 时抛 UnicodeDecodeError,
    被我误报成 "ZERO_CRASH"。

    **第一版扫描器自己就是个假阳性源。** 教训: 工具也要先验证自己。
    """
    try:
        r = client.get(path)
    except Exception as e:
        return None, r"EXC", f"{type(e).__name__}: {e}"
    if r.status_code >= 500:
        return None, r.status_code, r.text[:120]
    ctype = r.headers.get("content-type", "")
    if "json" not in ctype:
        return None, None, f"(跳过: {ctype})"     # PDF/文件类, 不 diff
    try:
        return r.json(), None, None
    except Exception as e:
        return None, "BAD_JSON", str(e)[:80]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    from fastapi.testclient import TestClient
    from cycling_coach.data.sqlite.database import rebind_engine
    from cycling_coach.api.main import app

    db_e, aid_e, db_r, aid_r, n_acts = _build_dbs()
    print(f"已构造: 空库 + {n_acts} 次真实训练")

    spec = TestClient(app).get("/openapi.json").json()
    skip = ("docs", "openapi", "redoc", "static", "strava")
    paths = [p for p, m in spec["paths"].items()
             if "get" in m and "{" not in p
             and not any(s in p for s in skip)]

    findings = []
    skipped = 0
    for p in paths:
        rebind_engine(str(db_e.get_bind().url))
        j0, e0, note0 = _get_json(TestClient(app, raise_server_exceptions=False), p)

        rebind_engine(str(db_r.get_bind().url))
        j1, e1, note1 = _get_json(TestClient(app, raise_server_exceptions=False), p)

        if note0 and note0.startswith("(跳过"):
            skipped += 1
            continue
        if e0:
            findings.append(("ZERO_" + str(e0), p, note0))
        if e1:
            findings.append(("REAL_" + str(e1), p, note1))
        if j0 is None or j1 is None:
            continue

        d = _diff(j0, j1)
        for item in d["FAKE_ZERO"]:
            findings.append(("FAKE_ZERO", p, item))
        if args.verbose:
            for cat in ("ZERO_ONLY", "REAL_ONLY", "DIFFERS"):
                for item in d[cat][:5]:
                    findings.append((cat, p, item))

    # ── 报告 ──
    if not findings:
        print(f"\n✅ 扫了 {len(paths)} 个端点 (跳过 {skipped} 个非 JSON), 没发现编造数据或 500")
        return 0

    order = {"FAKE_ZERO": 0, "ZERO_500": 1, "REAL_500": 2, "ZERO_CRASH": 3,
             "REAL_CRASH": 4}
    findings.sort(key=lambda x: order.get(x[0], 9))

    buckets: dict[str, list] = {}
    for cat, path, detail in findings:
        buckets.setdefault(cat, []).append((path, detail))

    print(f"\n扫了 {len(paths)} 个端点 (跳过 {skipped} 个非 JSON), 发现 {len(findings)} 项:\n")
    for cat, items in sorted(buckets.items(),
                             key=lambda kv: order.get(kv[0], 9)):
        print(f"── {cat} ({len(items)}) {'← 最危险' if cat == 'FAKE_ZERO' else ''}")
        for path, detail in items[:20]:
            print(f"   {path}")
            print(f"      {detail}")
        print()

    print("FAKE_ZERO = 零数据时这个指标是 0。")
    print("0 看起来像真实测量值, 但它其实是'没有记录' —— 用户会照着它骑车。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
