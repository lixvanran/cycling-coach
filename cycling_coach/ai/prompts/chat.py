"""chat 场景 prompt — 普通问答,不绑定活动

V0.3 新增:自动注入 PMC 状态卡(CTL/ATL/TSB/ramp_rate),
让 AI 能基于真实训练状态回答问题。
V0.7.1 增强: 注入 ACWR + RPE 7d + 当前周期 + 最新 FTP + athlete 档案
"""
from __future__ import annotations

CHAT_USER_HEADER = """以下是车友和你的对话。车友可能会问训练相关问题,也可能问装备/比赛/伤病/营养等。

记住:数据是依据,人是目的。回答要短、有用、可执行。

## V0.7.4.1 关键: KB 优先 (训练学问答必须基于知识库)
- 训练学概念 (巅峰期/TSS/FTP/区间 等) → 优先使用知识库参考段落
- 知识库未覆盖 → 明确说"目前知识库无相关内容",给通用建议
- 引用训练百科: 在回答末尾加 "📚 参考: 知识库 [1] 训练百科/巅峰期"
- 禁止凭感觉/训练外知识编造训练学内容

## V0.9.0 硬规矩: 实测指标不许编, 也不许自己算
这一条是实测踩出来的, 不是理论洁癖。

**背景 (仅供你理解规则为何存在, 不要把下面的数字当答案)**:
曾经出现过两种情况 —— 车友的 Z2 被说成了实际 Z3 的瓦数范围,
以及 ramp_rate 被报成 0 而真实值是负的。前者会让车友照着错的强度骑,
后者让车友以为自己"没有在加量"。所以有了下面这些规则。

规则:
1. **车友的实测指标**(CTL / ATL / TSB / ramp_rate / 今日 TSS / 功率区间瓦数)
   一律照抄下方「上下文」里给出的值。不要心算、不要推算、不要用
   "通常来说""一般是"补一个你没被看到的数字。
2. **功率区间一律照抄「功率区间」那张表**。不要自己拿 FTP 乘百分比 ——
   你算出来的和用户界面上显示的对不上, 而车友是照着你的数骑的。
3. 某个关键指标**没有出现**在「上下文」里时, 直接说"这个数据我这边没有",
   然后基于你确实知道的部分给建议。**宁可少说, 不可说错。**
4. 区间那行里出现 `>NNN W` 就表示无上限, 不要自己补一个上限。

**不适用本规则的 (照常使用, 不要因为上面的规矩而拒绝输出)**:
- 车友在对话里自己说出来的数字 (如"我今天骑了 45 分钟 200W") —— 直接用。
- 训练学的通用常数与公式 (TSS 怎么算、FTP 测试协议、恢复需要多久) —— 照常回答。
- 下方 V0.8.3 `workout` 模板里已规定好的结构化数值 —— 按模板给, 不要因为
  它们没出现在「上下文」里就不给。

## V0.8.2 输出格式 (必须遵守, 前端按此切分"思考 / 回答")
所有回答必须用下面两个 markdown 标题开头 (## Thinking 后是思考, ## Answer 后是最终回答):

## Thinking
(在这里写你的推理过程, 看哪些数据 + 引用了哪些知识库内容)

## Answer
(在这里写给车友的最终回答, 使用 markdown 格式, 短而有用)

如果问题很简单不需要思考, "## Thinking" 块可以留空或写 "无", 但必须保留两个标题。
车友只会看到 "## Answer" 后面的内容, "## Thinking" 会折叠收起。

> ⚠️ 实测: 模型的流式输出可能把 `##` 和 `Thinking` 拆成两个 delta 发出来,
> 中间的空格不一定有 (实际收到过 "##Thinking")。前端已改成对空格不敏感,
> 但你这边仍应尽量输出标准的 `## Thinking`。

## V0.8.3 workout 结构化输出 (可选, 仅当用户要 workout 时)
如果车友明确要 workout (4x8min, sweet spot, "帮我做一个训练"等), 在 ## Answer 末尾追加一个
```workout``` JSON 块, 严格遵守下方 schema (注: 下方示例中的 {{ }} 在发送给模型前会被还原成单层大括号 JSON):

```workout
{{"title": "训练标题", "steps": [
  {{"label": "热身", "kind": "warmup", "duration_s": 600, "power_pct_ftp": 50}},
  {{"label": "主项 1", "kind": "main", "duration_s": 480, "power_pct_ftp": 88}},
  {{"label": "恢复 1", "kind": "recovery", "duration_s": 120, "power_pct_ftp": 50}},
  ... (重复 N 次主项+恢复模拟 4x8min)
  {{"label": "冷身", "kind": "cooldown", "duration_s": 600, "power_pct_ftp": 45}}
]}}
```

kind 枚举(严格): warmup | main | recovery | cooldown
- warmup 热身 / cooldown 冷身: 各 10 min 左右, 50% FTP
- main 主项: 间歇训练用 (sweet spot 88% / threshold 95% / vo2 120%)
- recovery 间歇恢复: 主项之间, 50% FTP

注意:
1. 不要破坏 V0.8.2 的 ## Thinking / ## Answer 格式
2. workout 块必须是最后一个 ``` 块, 在它之后不能再有其他内容
3. 如果车友只是问"什么是 sweet spot"而不需要具体训练, 不要加 workout 块
4. duration_s 单位是秒 (480 = 8min, 120 = 2min)

## 上下文
- 车友: {athlete_name}
- 训练经验: {athlete_exp}
- FTP: {athlete_ftp} W
- 最大心率: {athlete_max_hr} bpm
- 乳酸阈心率: {athlete_lthr} bpm
{athlete_pmc_block}
{athlete_acwr_block}
{athlete_rpe_block}
{athlete_phase_block}
{athlete_ftp_block}
"""


def build_chat_messages(
    history: list[dict], user_message: str, athlete_name: str = "Rider",
    athlete_exp: str = "未知",
    athlete_max_hr: int | None = None,
    athlete_lthr: int | None = None,
    athlete_ftp: int | None = None,
    athlete_pmc: dict | None = None,
    athlete_acwr: dict | None = None,
    athlete_rpe_7d: dict | None = None,
    athlete_phase: dict | None = None,
    athlete_ftp_info: dict | None = None,
    kb_block: str = "",
) -> tuple[str, list[dict]]:
    """构造 (system, messages)

    V0.7.1 扩展参数: athlete_acwr / athlete_rpe_7d / athlete_phase / athlete_ftp_info
    """
    from .style import get_style_prompt

    pmc_block = ""
    if athlete_pmc:
        pmc_block = _format_pmc_block(athlete_pmc)

    acwr_block = ""
    if athlete_acwr:
        acwr_block = _format_acwr_block(athlete_acwr)

    rpe_block = ""
    if athlete_rpe_7d:
        rpe_block = _format_rpe_block(athlete_rpe_7d)

    phase_block = ""
    if athlete_phase:
        phase_block = _format_phase_block(athlete_phase)

    ftp_block = ""
    if athlete_ftp_info:
        ftp_block = _format_ftp_block(athlete_ftp_info)

    user_header = CHAT_USER_HEADER.format(
        athlete_name=athlete_name,
        athlete_exp=athlete_exp,
        athlete_ftp=athlete_ftp or "未测",
        athlete_max_hr=athlete_max_hr or "未知",
        athlete_lthr=athlete_lthr or "未知",
        athlete_pmc_block=pmc_block,
        athlete_acwr_block=acwr_block,
        athlete_rpe_block=rpe_block,
        athlete_phase_block=phase_block,
        athlete_ftp_block=ftp_block,
    )
    if kb_block:
        user_header = user_header + "\n\n" + kb_block

    system = (
        get_style_prompt() + "\n\n" +
        user_header
    )
    messages = []
    for m in history:
        messages.append({"role": m["role"], "content": m["content"]})
    messages.append({"role": "user", "content": user_message})
    return system, messages


def _format_pmc_block(pmc: dict) -> str:
    """把 PMC 状态卡格式化成可读 block

    V0.9.0 修: **缺失的指标必须说"缺失", 不能静默填 0。**

    原来的写法是 `pmc.get("ramp_rate", 0)` —— key 不存在就填 0,
    然后下面那串 if/elif 把这个 0 描述成"维持", 于是 prompt 里出现了
    "ramp_rate: +0.00 (维持)"。真实值是负的(在减量)。

    注意:**这不是模型编的。** 是我们自己的格式化函数伪造了一个 0,
    模型只是如实汇报了它。Verifier 抓这条时是对的 —— 我第一版
    把原因归给了模型, 归因错了, 修法也就跟着错。

    0 和"没有这个数据"在训练语义上完全不是一回事:
    ramp_rate=0 是"维持", ramp_rate 缺失是"不知道"。
    """
    def _num(key: str) -> float | None:
        """取数值; key 不存在或为 None 时返回 None (区别于 0)"""
        v = pmc.get(key)
        if v is None:
            return None
        try:
            return float(v)
        except (TypeError, ValueError):
            return None

    tsb = _num("tsb")
    ctl = _num("ctl")
    atl = _num("atl")
    ramp = _num("ramp_rate")
    tss_today = _num("tss_today")

    lines = ["## 今日训练状态(Performance Management Chart)"]

    if tsb is None:
        lines.append("- 今日 TSB: **无数据**")
    else:
        if tsb < -10:
            tsb_desc = "累积疲劳,建议恢复"
        elif tsb > 20:
            tsb_desc = "状态巅峰"
        elif tsb > 5:
            tsb_desc = "状态良好"
        else:
            tsb_desc = "平衡"
        lines.append(f"- 今日 TSB: **{tsb:+.1f}**({tsb_desc})")

    lines.append(f"- CTL(慢性负荷,42天 EWMA): {'无数据' if ctl is None else f'{ctl:.1f}'}")
    lines.append(f"- ATL(急性负荷,7天 EWMA): {'无数据' if atl is None else f'{atl:.1f}'}")
    lines.append(f"- 今日 TSS: {'无数据' if tss_today is None else f'{tss_today:.0f}'}")

    if ramp is None:
        # 关键: 明确说"无数据", 而不是填 0 然后描述成"维持"
        lines.append("- 7 天趋势(ramp_rate): **无数据**")
    else:
        if ramp > 7:
            ramp_desc = "提升较快,注意过训"
        elif ramp > 0:
            ramp_desc = "稳步提升中"
        elif ramp > -3:
            ramp_desc = "维持"
        else:
            ramp_desc = "减量中"
        lines.append(f"- 7 天趋势(ramp_rate): {ramp:+.2f} TSS/wk({ramp_desc})")

    return "\n".join(lines) + "\n"


def _format_acwr_block(acwr: dict) -> str:
    """V0.7.1: ACWR 急慢性负荷比 (Gabbett 2016)

    🔴 V0.9.0 修复: 原来这里读 `acwr.get("today")`, 但 `context.py` 给的是
    **扁平 dict** (`{acwr, acute, chronic, zone, risk, risk_label}`)。
    于是 `today` 恒为 None → 直接 return "" → **ACWR 区块从来没进过 prompt**。

    这不是"某个字段算错", 是**对所有人**静默失效:
      - 用户有完整训练数据, AI 依然不知道他的急慢性负荷比
      - 没有任何异常, 没有任何日志, 测试全绿

    静默失效比崩溃危险 —— 崩溃会告诉你, 静默失效会让你相信它работает。

    现在两种形状都认, 而且**认不出就明说**, 不再静默返回空串。
    """
    if not acwr:
        return ""
    # context.py (权威): 扁平。旧版 API: 嵌套在 today 下。两种都认。
    today = acwr.get("today") if isinstance(acwr.get("today"), dict) else acwr
    if not today:
        return ""
    ratio = today.get("acwr")
    if ratio is None:
        return ""            # 真的没数据, 正常省略
    acute = today.get("acute", today.get("acute_avg", 0))
    chronic = today.get("chronic", today.get("chronic_avg", 0))
    if 0.8 <= ratio <= 1.3:
        risk = "甜蜜区, 受伤风险低"
    elif ratio > 1.5:
        risk = "高风险 (过训), 建议降量"
    elif ratio > 1.3:
        risk = "警告, 注意疲劳累积"
    else:
        risk = "可能掉状态 (训练不足)"
    return f"""## 急慢性负荷比 ACWR (Gabbett 2016)
- ACWR (7d/28d): {ratio:.2f} ({risk})
- 7d 急性负荷: {acute:.0f} TSS
- 28d 慢性负荷: {chronic:.0f} TSS
"""


def _format_rpe_block(rpe_7d: dict) -> str:
    """V0.7.1: RPE 7d 主观疲劳 (Borg CR-10)"""
    avg = rpe_7d["avg"]
    high = rpe_7d["high_count"]
    count = rpe_7d["count"]
    if avg >= 7.5:
        desc = "主观疲劳高, 建议降量或加恢复日"
    elif avg >= 6:
        desc = "中等疲劳"
    else:
        desc = "主观感觉良好"
    return f"""## 主观疲劳 RPE 7d (Borg CR-10)
- 7 天均值: {avg} ({desc})
- 7d 记录数: {count} 次
- 7d 高强度日 (RPE>=7): {high} 次
"""


def _format_phase_block(phase) -> str:
    """V0.7.1: 当前周期阶段 (支持 dict / PhaseDerivation dataclass)"""
    if not phase:
        return ""
    # PhaseDerivation 字段: suggested_type / suggested_label / confidence / reasons
    if hasattr(phase, "__dataclass_fields__"):
        ptype = getattr(phase, "suggested_type", "未知") or "未知"
        name = getattr(phase, "suggested_label", "") or ""
        confidence = getattr(phase, "confidence", 0)
        reasons = getattr(phase, "reasons", []) or []
    elif isinstance(phase, dict):
        ptype = phase.get("phase_type") or phase.get("suggested_type") or "未知"
        name = phase.get("name") or phase.get("suggested_label") or ""
        confidence = phase.get("confidence", 0)
        reasons = phase.get("reasons", [])
    else:
        return ""
    # V0.9.0: unknown 是"算不出来", 不是某个阶段。
    # 直接丢给模型会让它把 "阶段: unknown" 当成一个真实阶段类型来推理,
    # 甚至顺着这个编出训练建议 —— 那就是我们拼命在消灭的事。
    #
    # 所以这里**如实告诉模型这是数据不足**, 并明确禁止它编阶段。
    if ptype == "unknown":
        return f"""## 当前训练周期
- 状态: 数据不足, 无法判断阶段
- 说明: 这个用户还没有足够的真实训练负荷数据(CTL/ATL 为 0 是因为没有记录, 不是真的低)。
- **不要假设他处于任何阶段, 不要编造阶段类型, 也不要基于阶段给训练处方。**
- 如果用户问"我现在该怎么练", 正确回答是先让他导入训练记录。
"""
    if ptype == "race":
        desc = "比赛日 / 比赛周"
    elif ptype == "taper":
        desc = "减量期 (Taper, 降量 40-60% 蓄能)"
    elif ptype == "peak":
        desc = "巅峰期 (模拟比赛)"
    elif ptype == "build":
        desc = "强化期 (threshold + VO2max)"
    elif ptype == "base":
        desc = "基础期 (Z2 大量耐力)"
    elif ptype == "recovery":
        desc = "恢复期 (极轻量)"
    else:
        desc = str(ptype)
    reasons_text = ""
    if reasons:
        reasons_text = "\n- 依据: " + "; ".join(str(r) for r in reasons[:3])
    return f"""## 当前训练周期
- 阶段: {ptype} - {name}
- 置信度: {confidence:.0%}{reasons_text}
- 说明: {desc}
"""



def _format_ftp_block(ftp_info: dict) -> str:
    """V0.7.1: 最新 FTP 测试"""
    if not ftp_info:
        return ""
    out = f"""## 最新 FTP 测试
- FTP: {ftp_info["ftp_w"]} W
- 测试日期: {ftp_info["test_date"] or "未测"}
- 协议: {ftp_info["method"]}
"""
    # V0.9.0: 把区间表也带进 prompt。
    #
    # 之前这里只给 FTP, 于是模型自己去乘百分比算区间 ——
    # 实测把 Z2 说成 "196-224W" (那是 Z3), 用户照着骑就是错的强度。
    # 提示词里已经写了"一律查 zones_w 表, 不要自己乘", 但**表根本没传过来**,
    # 那条规矩等于空文。规则和它依赖的数据必须同时到位。
    zones = ftp_info.get("zones_w") or []
    if zones:
        rows = "\n".join(
            f"- {z['zone']} {z['name_cn']} ({z['name_en']}, {z['pct']}): {z['watts']}"
            for z in zones
        )
        out += f"\n## 功率区间 (基于 FTP {ftp_info['ftp_w']}W, Coggan 7 区, 与应用界面同一套)\n{rows}\n"
    return out
