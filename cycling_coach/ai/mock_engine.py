"""Mock 引擎 — V0.7.6 抽离

把 m3_client 里的 mock 业务逻辑 (KB 问答 + 活动分析 + 流式 yield) 搬到独立模块.
m3_client 只负责真实 LLM 调用, MockEngine 负责无 key 时的回退行为.
"""
from __future__ import annotations
import logging
import re
from typing import Any, Generator

logger = logging.getLogger(__name__)

_STOPWORDS = {
    "的", "了", "是", "在", "和", "与", "或", "及", "把", "给",
    "我", "你", "他", "她", "它", "这", "那", "吗", "啊", "呢",
    "吧", "什么", "怎么", "如何", "为什么", "多久",
}


def _extract_user_keywords(user: str) -> set:
    """从 user query 抽关键词 (中英文混合)"""
    kws: set = set()
    for w in re.findall(r"[A-Za-z][A-Za-z0-9_]+", user):
        if len(w) >= 2:
            kws.add(w.lower())
    for s in re.findall(r"[\u4e00-\u9fff]+", user):
        for ch in s:
            if ch not in _STOPWORDS:
                kws.add(ch)
        for i in range(len(s) - 1):
            g = s[i:i + 2]
            if g not in _STOPWORDS:
                kws.add(g)
    return kws or set(re.findall(r"\w+", user))


def _parse_kb_block_from_system(system: str) -> list[dict]:
    """从 system prompt 抽 '## 知识库参考' 块, 切成 retrieved[] 列表"""
    if not system or "知识库参考" not in system:
        return []
    m = re.search(r"## 知识库参考.+?(?=---|$)", system, re.DOTALL)
    if not m:
        return []
    out = []
    for cm in re.finditer(
        r"### \[\d+\] (.+?)\n来源: (.+?)\n.+?完整内容:\n(.+?)(?=\n### |\n---|$)",
        m.group(0), re.DOTALL,
    ):
        c = cm.group(3).strip()
        out.append({
            "title": cm.group(1).strip(),
            "path": cm.group(2).strip(),
            "content": c, "snippet": c[:200],
        })
    return out


class MockEngine:
    """无 M3 API key 时的回退引擎 — 纯字符串拼接, 离线可跑"""

    def stream_response(
        self, messages: list[dict], **_: Any
    ) -> Generator[str, None, None]:
        """字符级流式 yield"""
        last_user, system = "", ""
        for m in messages:
            if m.get("role") == "system":
                system = m.get("content", "")
            if m.get("role") == "user":
                last_user = m.get("content", "")
        retrieved = _parse_kb_block_from_system(system) if system else []
        text = (
            self.format_kb_answer(last_user, retrieved, athlete_ctx={})
            if retrieved
            else self.format_activity_report({"raw_query": last_user}, focus="auto")
        )
        for ch in text:
            yield ch

    def format_kb_answer(
        self, question: str, retrieved: list, athlete_ctx: dict
    ) -> str:
        """V0.7.5.1 抽相关句子版 (避免堆砌无关内容)"""
        if not retrieved:
            return ""
        user_kws = _extract_user_keywords(question)
        scored = []
        for i, r in enumerate(retrieved[:5]):
            content = r.get("content", "")
            if not content:
                continue
            hits = sum(1 for kw in user_kws if kw in content)
            scored.append((hits, i, r))
        scored.sort(key=lambda x: (-x[0], x[1]))
        if not scored:
            return ""
        primary = scored[0][2]
        title = primary.get("title", "")
        content = primary.get("content", "")
        path = primary.get("path", "")
        if not content:
            return ""
        # 按句号/换行切句, 按命中数排序取 top 5
        sentences = re.split(r"(?<=[。！？!?\n])|(?<=[.!?]\s)", content)
        relevant = []
        for sent in sentences:
            sent = sent.strip()
            if len(sent) < 8:
                continue
            sh = sum(1 for kw in user_kws if kw in sent)
            if sh > 0:
                relevant.append((sh, sent))
        relevant.sort(key=lambda x: -x[0])
        if relevant:
            content_used = "\n\n".join(s for _, s in relevant[:5])
        else:
            content_used = content[:400] + ("..." if len(content) > 400 else "")
        parts = [f"# {title}\n", f"**来源**: {path}\n", "\n## 核心内容\n", content_used]
        if len(scored) > 1:
            parts.append("\n## 相关参考\n")
            for _, _, c in scored[1:3]:
                ct, cc = c.get("title", ""), c.get("content", "")[:200]
                if cc and ct:
                    parts.append(f"**{ct}**: {cc}...\n")
        parts.append(
            f"\n> 📚 本回答基于训练百科 (潘震教练) KB 检索, "
            f"命中 {len(scored)} 个相关片段, 已按问题关键词抽取相关句子."
        )
        parts.append(
            "> 注: mock 模式 (无 M3_API_KEY). 配 key 后 LLM 会基于 KB 完整生成."
        )
        return "\n".join(parts)

    def format_activity_report(self, activity: dict, focus: str = "auto") -> str:
        """活动分析 mock — 抽 NP/IF/TSS 等字段, 给训练强度建议

        activity 可含 raw_query (从原 user 抽) 或直接字段 np/if/tss/ftp/avg_power/avg_hr/duration_min
        """
        user = activity.get("raw_query", "")
        if "np" in activity:
            user = (
                f"NP={activity.get('np')} IF={activity.get('if', '?')} "
                f"TSS={activity.get('tss', '?')} FTP={activity.get('ftp', '?')} "
                f"avg_power={activity.get('avg_power', '?')} "
                f"avg_hr={activity.get('avg_hr', '?')} "
                f"duration_min={activity.get('duration_min', '?')}"
            )

        def _find(pat):
            m = re.search(pat, user)
            return m.group(1) if m else "?"

        np_v = _find(r"NP[:=]\s*(\d+)")
        if_v = _find(r"IF[:=]\s*([\d.]+)")
        tss_v = _find(r"TSS[:=]\s*(\d+)")
        ftp_v = _find(r"FTP[:=]\s*(\d+)")
        avg_v = _find(r"avg_power[:=]\s*(\d+)")
        hr_v = _find(r"avg_hr[:=]\s*(\d+)")
        dur_v = _find(r"duration_min[:=]\s*([\d.]+)")
        try:
            if_num = float(if_v)
        except (ValueError, TypeError):
            if_num = 0.0
        rec = "注意观察身体反馈,数据不够时建议补一次 RAMP 测试或 20 分钟全力测试。"
        if if_num == 0:
            intensity = "未知"
        elif if_num < 0.55:
            intensity = "恢复区 / 主动恢复"
            rec = "今天适合做拉伸 + 泡沫轴,不要硬上强度。"
        elif if_num < 0.75:
            intensity = "耐力区 / Z2"
            rec = "Z2 训练是建立有氧基础的关键,继续保持。关注 HR drift,越小越好。"
        elif if_num < 0.90:
            intensity = "节奏区 / 阈值附近"
            rec = "这次强度不低,注意观察次日晨起静息心率。如果持续升高,减量。"
        elif if_num < 1.05:
            intensity = "阈值上 / Sweet Spot"
            rec = "一次扎实的阈值训练,确保赛后 24-48h 充分恢复。"
        else:
            intensity = "VO2max / 无氧"
            rec = "高强度,本周 TSS 累积要控制好。一次太拼不如一周稳扎。"

        return f"""# 训练分析报告(mock)

## 概览
这次训练强度属于 **{intensity}**。

- 时长: {dur_v} 分钟
- 平均功率: {avg_v} W
- 归一化功率 NP: {np_v} W
- 强度因子 IF: {if_v} (FTP {ftp_v}W)
- 训练压力 TSS: {tss_v}

## 教练点评

数据说话,这次训练看起来"中规中矩"。NP 与平均功率的差距反映了输出的稳定性,间歇训练 VI 通常会 > 1.05。

## 下一步建议

{rec}

> 注:这是 mock 模式的报告。请配置 .env 中的 M3_API_KEY 获取真实 AI 分析。
"""


_default_engine = None  # type: ignore[var-annotated]


def get_mock_engine() -> MockEngine:
    """模块级单例 — 避免重复构造"""
    global _default_engine
    if _default_engine is None:
        _default_engine = MockEngine()
    return _default_engine
