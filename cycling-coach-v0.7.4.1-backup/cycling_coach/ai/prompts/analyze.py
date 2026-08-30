"""analyze_activity 工具的 prompt"""
ANALYZE_USER_PROMPT = """请基于以下训练数据,给出专业、简洁的分析报告。

## 关键指标
{metrics_block}

## 个体画像
- 姓名: {athlete_name}
- FTP: {ftp}W(估算: {ftp_estimated}W)
- 最大心率: {max_hr}bpm
- 本周已累计 TSS: {weekly_tss}

## 训练数据(分段)
{laps_block}

## 报告结构(请严格按此输出)
1. **一句话总评** — 用一句话给这次训练定性
2. **亮点** — 这次做得好的 2-3 点(必须引用具体数据)
3. **待改进** — 看到的问题 1-2 点(不夸大,不编造)
4. **下一步** — 给 1-2 条可执行的建议(明天 / 本周)

字数控制在 400 字以内。不要寒暄,直接开始。"""


def build_analyze_prompt(
    metrics: dict, athlete: dict, weekly_tss: int, laps_summary: str
) -> tuple[str, str]:
    """返回 (system, user)"""
    from .style import get_style_prompt
    m = metrics
    metrics_block = "\n".join([
        f"- 时长: {m.get('duration_min', '?')} 分钟",
        f"- 距离: {m.get('distance_km', '?')} km",
        f"- 平均功率: {m.get('avg_power', '?')} W",
        f"- 归一化功率 NP: {m.get('normalized_power', '?')} W",
        f"- 强度因子 IF: {m.get('intensity_factor', '?')}",
        f"- 训练压力 TSS: {m.get('tss', '?')}",
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
            ftp=athlete.get("ftp", "未知"),
            ftp_estimated=athlete.get("ftp_estimated", "未估算"),
            max_hr=athlete.get("max_hr", "未知"),
            weekly_tss=weekly_tss,
            laps_block=laps_summary or "(无分段数据)",
        ),
    )
