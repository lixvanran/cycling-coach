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
    """把 PMC 状态卡格式化成可读 block"""
    tsb = pmc.get("tsb", 0)
    ctl = pmc.get("ctl", 0)
    atl = pmc.get("atl", 0)
    ramp = pmc.get("ramp_rate", 0)
    label = pmc.get("status_label", "")
    tss_today = pmc.get("tss_today", 0)

    if tsb < -10:
        tsb_desc = "累积疲劳,建议恢复"
    elif tsb > 20:
        tsb_desc = "状态巅峰"
    elif tsb > 5:
        tsb_desc = "状态良好"
    else:
        tsb_desc = "平衡"

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
"""


def _format_acwr_block(acwr: dict) -> str:
    """V0.7.1: ACWR 急慢性负荷比 (Gabbett 2016)"""
    today = acwr.get("today") or {}
    if not today:
        return ""
    ratio = today.get("acwr", 0)
    acute = today.get("acute_avg", 0)
    chronic = today.get("chronic_avg", 0)
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
    return f"""## 最新 FTP 测试
- FTP: {ftp_info["ftp_w"]} W
- 测试日期: {ftp_info["test_date"] or "未测"}
- 协议: {ftp_info["method"]}
"""
