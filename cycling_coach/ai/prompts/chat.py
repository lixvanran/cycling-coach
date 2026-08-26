"""chat 场景 prompt — 普通问答,不绑定活动

V0.3 新增:自动注入 PMC 状态卡(CTL/ATL/TSB/ramp_rate),
让 AI 能基于真实训练状态回答问题。
"""
from __future__ import annotations

CHAT_USER_HEADER = """以下是车友和你的对话。车友可能会问训练相关问题,也可能问装备/比赛/伤病/营养等。

记住:数据是依据,人是目的。回答要短、有用、可执行。

## 上下文
- 车友: {athlete_name}
- 训练经验: 未知(如有 athlete 资料会附在 system prompt)
{athlete_pmc_block}
"""


def build_chat_messages(
    history: list[dict], user_message: str, athlete_name: str = "Rider",
    athlete_pmc: dict | None = None,
    kb_block: str = "",
) -> tuple[str, list[dict]]:
    """构造 (system, messages)

    history: [{"role": "user"/"assistant", "content": "..."}, ...]
    user_message: 当前用户输入
    athlete_pmc: 可选,来自 get_pmc_today(),{tsb, ctl, atl, ramp_rate, status_label, ...}
    kb_block: V0.5 RAG 检索到的知识库参考 (markdown)
    """
    from .style import get_style_prompt

    pmc_block = ""
    if athlete_pmc:
        pmc_block = _format_pmc_block(athlete_pmc)

    user_header = CHAT_USER_HEADER.format(
        athlete_name=athlete_name,
        athlete_pmc_block=pmc_block,
    )
    # V0.5: 拼接 RAG 知识库
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
    """把 PMC 状态卡格式化成可读 block"""
    tsb = pmc.get("tsb", 0)
    ctl = pmc.get("ctl", 0)
    atl = pmc.get("atl", 0)
    ramp = pmc.get("ramp_rate", 0)
    label = pmc.get("status_label", "")
    tss_today = pmc.get("tss_today", 0)

    # 状态语义
    if tsb < -10:
        tsb_desc = "累积疲劳,建议恢复"
    elif tsb > 20:
        tsb_desc = "状态巅峰"
    elif tsb > 5:
        tsb_desc = "状态良好"
    else:
        tsb_desc = "平衡"

    # ramp 语义
    if ramp > 7:
        ramp_desc = "提升较快,注意过训"
    elif ramp > 0:
        ramp_desc = "稳步提升中"
    elif ramp > -3:
        ramp_desc = "维持"
    else:
        ramp_desc = "减量中"

    return f"""## 今日训练状态(Performance Management Chart)
- 今日 TSB: **{tsb:+.1f}**({tsb_desc})
- CTL(慢性负荷,42天 EWMA): {ctl:.1f}
- ATL(急性负荷,7天 EWMA): {atl:.1f}
- 今日 TSS: {tss_today:.0f}
- 7 天趋势(ramp_rate): {ramp:+.2f} TSS/wk({ramp_desc})
- 综合状态: {label}

回答时**必须参考**这些数据,不要泛泛而谈。如果用户问"我现在状态怎么样"或"今天能训练吗",直接用上面的数字给出建议。"""
