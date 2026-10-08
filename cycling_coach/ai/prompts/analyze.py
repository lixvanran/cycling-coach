"""analyze_activity 工具的 prompt"""
ANALYZE_USER_PROMPT = """请基于以下训练数据,给出专业、简洁的分析报告。

## 关键指标
{metrics_block}

## 个体画像
- 姓名: {athlete_name}
- FTP: {ftp}{est_ftp_note}
- 最大心率: {max_hr}bpm
- 本周已累计 TSS: {weekly_tss}

## 训练数据(分段)
{laps_block}

## 报告结构(请严格按此输出)
1. **一句话总评** — 用一句话给这次训练定性
2. **亮点** — 这次做得好的 2-3 点(必须引用具体数据)
3. **待改进** — 看到的问题 1-2 点(不夸大,不编造)
4. **下一步** — 给 1-2 条可执行的建议(明天 / 本周)

## 诚实性要求(不可违反)
- 如果某个指标标注了 ⚠️ 或显示"无数据", **必须在报告里如实说明它不可靠或缺失**,
  **不允许把它当成实测值引用, 更不允许基于它给出训练强度建议**。
- 可以说明"若采用估算值, 大致处于什么区间", 但必须标明是估算。

字数控制在 400 字以内。不要寒暄,直接开始。"""


def build_analyze_prompt(
    metrics: dict, athlete: dict, weekly_tss: int, laps_summary: str
) -> tuple[str, str]:
    """返回 (system, user)"""
    from .style import get_style_prompt
    m = metrics

    # 🔴 V0.9.0: 这两个标记原来是"只写不读"的死字段 ——
    # 后端老老实实记了 tss_uses_estimated_ftp, 但 prompt 里一个字都没提。
    #
    # 后果比界面不显示严重得多: prompt 下面写着"必须引用具体数据",
    # 于是 AI 会把**基于估算 FTP 算出来的 TSS 当成实测值引用**,
    # 再基于它给出训练建议。用户在完全不知情的情况下照着骑车。
    #
    # 估算值不是不能用 —— 是**用了必须让 AI 知道, 并让 AI 告诉用户**。
    est = m.get("tss_uses_estimated_ftp")
    ftp_used = m.get("ftp_used_for_tss")
    if est and ftp_used:
        tss_note = f"  ⚠️ **该 TSS 基于估算 FTP({ftp_used}W)计算, 不是实测值**"
    elif est:
        tss_note = "  ⚠️ **该 TSS 基于估算 FTP 计算, 不是实测值**"
    else:
        tss_note = ""
    tss_val = m.get("tss")
    tss_disp = tss_val if tss_val is not None else "无数据"

    metrics_block = "\n".join([
        f"- 时长: {m.get('duration_min', '?')} 分钟",
        f"- 距离: {m.get('distance_km', '?')} km",
        f"- 平均功率: {m.get('avg_power', '?')} W",
        f"- 归一化功率 NP: {m.get('normalized_power', '?')} W",
        f"- 强度因子 IF: {m.get('intensity_factor', '?')}",
        f"- 训练压力 TSS: {tss_disp}{tss_note}",
        f"- 效率因子 EF: {m.get('efficiency_factor', '?')}",
        f"- 变异性指数 VI: {m.get('variability_index', '?')}",
        f"- 平均心率: {m.get('avg_hr', '?')} bpm",
        f"- 心率漂移: {m.get('hr_drift', '?')} bpm",
        f"- 平均踏频: {m.get('avg_cadence', '?')} rpm",
        f"- 爬升: {m.get('elevation_gain', '?')} m",
    ])
    return (
        get_style_prompt(),
        ANALYZE_USER_PROMPT.format(
            metrics_block=metrics_block,
            athlete_name=athlete.get("name", "Rider"),
            ftp=f"{athlete['ftp']}W(实测)" if athlete.get("ftp") else "未设置(没有实测值)",
            est_ftp_note=(
                f", 估算 {athlete['ftp_estimated']}W" if athlete.get("ftp_estimated") else ""
            ),
            max_hr=athlete.get("max_hr", "未知"),
            weekly_tss=weekly_tss,
            laps_block=laps_summary or "(无分段数据)",
        ),
    )
