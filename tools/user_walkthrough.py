#!/usr/bin/env python3
"""使用者视角走查 —— 拿真实数据把一个用户会走的路走一遍

## 为什么要有这个

之前所有验证都是"接口返回 200"或"测试通过"。但用户不关心这些,
用户关心的是: 我打开这个软件, 能不能看懂我自己的训练?

所以这个脚本刻意**用使用者的眼光提问**, 而不是检查字段是否存在:

    打开 Dashboard → 今天该练什么? 说得清楚吗?
    看日历       → 计划 vs 实际对得上吗? 我练得够不够?
    看活动详情   → 数字合理吗? 我看得懂吗?
    看趋势       → 8 周训练有故事吗? 还是一堆线?
    看 AI        → 它知道我什么状态吗? 说的话有依据吗?

## 输出分两类

- **🔴 说谎/看不懂** —— 用户会被误导的, 必须修
- **🟡 不够好** —— 能用但难受, 记下来排优先级

每条都带具体数字, 不写"体验不好"这种没法行动的结论。
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(ROOT))

BASE = os.environ.get("WALK_BASE", "http://127.0.0.1:8795")
findings: list[tuple[str, str, str]] = []   # (级别, 位置, 描述)


def note(level: str, where: str, msg: str) -> None:
    findings.append((level, where, msg))
    icon = {"🔴": "🔴", "🟡": "🟡", "✅": "✅"}[level]
    print(f"  {icon} {where}: {msg}")


def api(path: str, timeout: int = 60) -> tuple[int, object, float]:
    """返回 (状态码, 解析后的 JSON, 耗时秒)"""
    t0 = time.time()
    try:
        req = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read()
            code = r.status
    except urllib.error.HTTPError as e:
        body, code = e.read(), e.code
    except Exception as e:
        return -1, {"error": str(e)}, time.time() - t0
    dt = time.time() - t0
    try:
        return code, json.loads(body), dt
    except Exception:
        return code, {"raw": body[:400].decode("utf-8", "ignore")}, dt


def head(title: str) -> None:
    print()
    print("=" * 70)
    print(f"  {title}")
    print("=" * 70)


# ====================================================================== 1
def walk_dashboard() -> None:
    head("1. 打开 Dashboard —— 用户第一眼看到什么")
    code, d, dt = api("/api/dashboard/overview")
    if code != 200:
        note("🔴", "Dashboard", f"HTTP {code}: {str(d)[:120]}")
        return
    print(f"  响应 {dt*1000:.0f}ms")
    if dt > 2.0:
        note("🟡", "Dashboard", f"首屏 {dt:.1f}s, 偏慢")
    elif dt > 1.0:
        note("🟡", "Dashboard", f"首屏 {dt:.2f}s, 勉强")

    # ⚠️ 不要靠"我猜它应该有这些字段"来判断。
    # 第一版这里硬编码了 today/recommendation/pmc/... 一串字段名,
    # 而 /api/dashboard/overview 实际返回的是
    # total_activities / total_distance_km / this_week / last_7_days,
    # 于是每次跑都报 6 条"缺字段"假黄。**走查脚本自己发假警报,
    # 用两次就没人信它了。**
    print(f"  顶层字段: {list(d.keys())}")
    tw = d.get("this_week") or {}
    print(f"  本周: {tw.get('activities')} 次 / {tw.get('distance_km')}km / {tw.get('tss')} TSS")
    if d.get("total_activities", 0) == 0:
        note("🟡", "Dashboard", "总训练数为 0, 但库里应该有数据")

    # readiness 单独看 (它在 /api/recommendations/today)
    code2, rec, _ = api("/api/recommendations/today")
    if code2 == 200:
        rs = rec.get("readiness_score")
        if rs is None:
            note("🟡", "今日建议",
                 "readiness_score 是 null —— 有 8 周数据还不给分, 要么数据没接上, 要么门禁过严")
        else:
            print(f"  今日 readiness = {rs} ({rec.get('readiness_label')}), "
                  f"建议 {rec.get('recommended_workout_type')} / 目标 TSS {rec.get('target_tss')}")
            if not rec.get("recommended_intensity"):
                note("🟡", "今日建议", "给了分数但没有训练强度建议文本")


# ====================================================================== 2
def walk_calendar() -> None:
    head("2. 看日历 —— 我练得够不够? 计划对得上吗?")
    code, d, _ = api("/api/calendar?year=2026&month=9")
    if code != 200:
        note("🔴", "日历", f"HTTP {code}")
        return
    st = d.get("stats", {})
    print(f"  9月: 计划 {st.get('planned_count')} / 完成 {st.get('done_count')} "
          f"/ 跳过 {st.get('skipped_count')} / 完成率 {st.get('completion_rate')}%")
    print(f"      实际训练 {st.get('actual_activities')} 次, "
          f"TSS 合计 {st.get('actual_tss_total')}, 时长 {st.get('actual_hours_total')}h")

    # 读接口已经算好的字段, 不要自己重算一遍再去"发现"它算得不对
    print(f"  完成率 {st.get('completion_rate')}% (排除跳过) | "
          f"履约率 {st.get('adherence_rate')}% (含跳过)")
    print(f"  负荷达成 {st.get('load_completion')}% "
          f"({st.get('completed_tss_total')}/{st.get('planned_tss_total')} TSS)")
    if st.get("load_completion") in (None, 0) and (st.get("planned_tss_total") or 0) > 0:
        note("🔴", "负荷达成", "有计划 TSS 但负荷达成率是 0 —— 用户无法判断练够了没")
    if (st.get("load_completion") or 0) > 200:
        note("🟡", "负荷达成", f"{st.get('load_completion')}% 偏高, 检查计划值是否偏低")

    pb = d.get("planned_by_day") or {}
    ab = d.get("actual_by_day") or {}
    print(f"  有计划的天数: {len(pb)} | 有实际训练的天数: {len(ab)}")


# ====================================================================== 3
def walk_activity() -> None:
    head("3. 打开一次训练详情 —— 数字合理吗?")
    code, lst, _ = api("/api/activities?limit=5")
    if code != 200:
        note("🔴", "活动列表", f"HTTP {code}")
        return
    acts = lst.get("activities") or []
    if not acts:
        note("🔴", "活动列表", "没有活动数据")
        return
    print(f"  共 {lst.get('total')} 次训练")
    a = acts[0]
    aid = a.get("id")
    print(f"  看最近一次: #{aid} {a.get('start_time','')[:16]} {a.get('duration_s')}s")

    for ep, label in [
        (f"/api/activities/{aid}", "详情"),
        (f"/api/activities/{aid}/power-zones-detailed?ftp=280", "功率分区"),
        (f"/api/activities/{aid}/wbal", "W'平衡"),
        (f"/api/activities/{aid}/decoupling", "解耦"),
        (f"/api/activities/{aid}/power-curve", "功率曲线"),
    ]:
        c, d, dt = api(ep)
        mark = "✅" if c == 200 else "🔴"
        extra = ""
        if dt > 2.0:
            extra = f"  (慢 {dt:.1f}s)"
            note("🟡", label, f"响应 {dt:.1f}s")
        if c == 200:
            keys = list(d.keys())[:6] if isinstance(d, dict) else type(d).__name__
            print(f"  {mark} {label:<10} {c} {dt*1000:.0f}ms  {keys}{extra}")
        else:
            note("🔴", label, f"HTTP {c} —— 这个页面用户点开就是报错/白屏")

    # 详情里的关键数字是否自洽
    c, det, _ = api(f"/api/activities/{aid}")
    if c == 200:
        m = det.get("metrics") or {}
        dur = det.get("duration_s") or 0
        ap = det.get("avg_power") or 0
        work_kj = (ap * dur) / 1000.0 if ap and dur else 0
        got_kj = m.get("total_kj")
        if not got_kj:
            # 活动详情的 metrics 里本来就不含 total_kj —— 它在
            # /power-zones-detailed 里。第一版这里报警, 属于脚本自己
            # 找错地方, 不是产品问题。改成去正确的端点取。
            c2, pz, _ = api(f"/api/activities/{aid}/power-zones-detailed?ftp=280")
            got_kj = pz.get("total_kj") if c2 == 200 else None
        if not got_kj:
            print("  (两个端点都没给 total_kj, 跳过做功交叉验证)")
        elif abs(got_kj - work_kj) / max(1, work_kj) > 0.08:
            note("🔴", "数据自洽",
                 f"总做功 {got_kj:.0f}kJ, 但 平均功率×时长 应为 {work_kj:.0f}kJ")
        else:
            print(f"  ✅ 做功自洽: {got_kj:.0f}kJ ≈ {ap}W x {dur//60}min = {work_kj:.0f}kJ")
        np_ = m.get("normalized_power")
        if np_ and ap and np_ < ap - 2:
            note("🔴", "数据自洽", f"NP={np_} < 平均功率={ap}, NP 不可能低于平均功率")


# ====================================================================== 4
def walk_trends() -> None:
    head("4. 看趋势 —— 8 周训练有故事吗?")
    for ep in ["/api/trends/volume?weeks=8",
               "/api/trends/metrics?weeks=8",
               "/api/trends/zones?weeks=8",
               "/api/trends/acwr",
               "/api/trends/overview?weeks=8"]:
        c, d, dt = api(ep)
        if c != 200:
            note("🔴", ep, f"HTTP {c}")
            continue
        note_txt = ""
        if isinstance(d, dict):
            for k in ("series", "data", "points", "values"):
                if isinstance(d.get(k), list) and d[k]:
                    note_txt = f"{k} {len(d[k])} 点"
                    break
            else:
                note_txt = f"keys={list(d.keys())[:6]}"
        print(f"  ✅ {ep:<34} {c} {dt*1000:>5.0f}ms  {note_txt}")
        if dt > 2.0:
            note("🟡", ep, f"响应 {dt:.1f}s")

    c, pmc, _ = api("/api/pmc/today")
    if c == 200:
        ctl, atl, tsb = pmc.get("ctl"), pmc.get("atl"), pmc.get("tsb")
        print(f"  PMC: CTL={ctl} ATL={atl} TSB={tsb} 状态={pmc.get('status')}")
        if ctl is None or atl is None or tsb is None:
            note("🔴", "PMC", "CTL/ATL/TSB 有 None —— 8 周数据下不应该缺")
        elif tsb is not None and atl is not None and abs((ctl - atl) - tsb) > 1.5:
            note("🔴", "PMC 自洽", f"TSB 应该 = CTL - ATL = {ctl-atl:.1f}, 但报的是 {tsb}")
        else:
            # 受训车手的 TSB 常见区间是 -30 ~ +30。
            # 第一版写"绝对值 < 100 就不合理", 结果减量周正常的 TSB=-2.6
            # 被报成异常。判据应该是"超出受训车手可能出现的范围"。
            if abs(tsb) > 60:
                note("🟡", "PMC",
                     f"TSB={tsb:.0f} 超出受训车手常见区间 (-30~+30), 检查计算")
            else:
                print(f"  ✅ TSB={tsb:.0f} 在正常区间内 (负值 = 训练负荷累积, 正值 = 恢复中)")


# ====================================================================== 5
def walk_ai() -> None:
    head("5. 问 AI —— 它知道我什么状态吗?")
    c, ctx, _ = api("/api/chat/sessions")
    if c == 200 and isinstance(ctx, dict):
        flat = json.dumps(ctx, ensure_ascii=False)
        for k in ("ctl", "atl", "tsb", "acwr", "ftp", "lthr"):
            if k not in flat.lower():
                note("🟡", "AI 上下文", f"上下文里找不到 {k} —— AI 拿不到这个, 就没法给个性化建议")
        print(f"  上下文 keys: {list(ctx.keys())[:10]}")
    else:
        print(f"  (无 /api/chat/context, HTTP {c})")

    # 真实问一句, 看它是不是在瞎说
    print("  提问: '我今天状态怎么样? 该练什么?' (真实调用, 约 10-30s)")
    try:
        sid = "walkthrough"
        # 第一步: 建/取会话
        rq = urllib.request.Request(
            BASE + "/api/chat/sessions",
            data=json.dumps({"title": "走查", "session_type": "general"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(rq, timeout=30) as r:
            sid = str(json.loads(r.read()).get("id", sid))
        # 第二步: 发消息
        req = urllib.request.Request(
            f"{BASE}/api/chat/sessions/{sid}/messages",
            data=json.dumps({
                "role": "user", "content": "我今天状态怎么样? 该练什么?"
            }).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=90) as r:
            d = json.loads(r.read())
        dt = time.time() - t0
        ans = (d.get("answer") or d.get("reply") or d.get("content") or "")
        print(f"  回答 ({dt:.1f}s): {ans[:300]}")
        if dt > 30:
            note("🟡", "AI 响应", f"{dt:.0f}s —— 用户会以为卡死了")
        if not ans.strip():
            note("🔴", "AI 回答", "返回空")
        elif ans.strip() == "我今天状态怎么样? 该练什么?":
            # 这个接口只是把用户消息存进去, 真正的推理在别的流程里。
            # 回显不等于 AI 回答了 —— 别把它算作"AI 已验证"。
            note("🟡", "AI 回答",
                 "返回的是原问题回显, 说明这一路径没有真正触发推理 —— "
                 "AI 推理链本次**未被验证**, 需要单独走真实对话流程")
        for leak in ("Traceback", "MOCK", "mock", "prompt", "system"):
            if leak in ans:
                note("🔴", "AI 输出", f"回答里泄漏了内部信息: {leak}")
    except Exception as e:
        note("🟡", "AI 提问", f"调用失败: {type(e).__name__}: {e}")


# ======================================================================
def main() -> int:
    print("使用者视角走查")
    print(f"目标: {BASE}")
    for fn in (walk_dashboard, walk_calendar, walk_activity,
               walk_trends, walk_ai):
        try:
            fn()
        except Exception as e:
            note("🔴", fn.__name__, f"走查脚本自身异常: {type(e).__name__}: {e}")

    print()
    print("=" * 70)
    red = [f for f in findings if f[0] == "🔴"]
    yel = [f for f in findings if f[0] == "🟡"]
    print(f"  🔴 会误导用户: {len(red)}    🟡 不够好: {len(yel)}")
    for lv, w, m in findings:
        print(f"    {lv} {w}: {m}")
    print("=" * 70)
    return 1 if red else 0


if __name__ == "__main__":
    sys.exit(main())
