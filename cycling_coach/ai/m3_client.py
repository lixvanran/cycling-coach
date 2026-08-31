"""MiniMax M3 / OpenAI 兼容客户端

参考 Photographer-Copilot 风格:
- 5 个错误子类 + 任务级中断
- Mock 模式 first-class
- 启动时验证 key
"""
from __future__ import annotations
import logging
import os
from typing import Optional
from dataclasses import dataclass

from openai import OpenAI, APIError, APIConnectionError, AuthenticationError, RateLimitError

from cycling_coach.config.config import settings

logger = logging.getLogger(__name__)


# === 错误分类 ===

class M3Error(Exception):
    """基础错误"""
    pass


class M3AuthError(M3Error):
    """401 / 403 — key 无效"""
    pass


class M3QuotaError(M3Error):
    """402 / 429 — 余额 / 限流"""
    pass


class M3ServerError(M3Error):
    """5xx — 服务端问题,可重试"""
    pass


class M3NetworkError(M3Error):
    """超时 / DNS / 连接错误"""
    pass


class M3BadResponseError(M3Error):
    """响应格式错误(无法解析)"""
    pass


# === 客户端 ===

@dataclass
class M3Message:
    role: str
    content: str


class M3Client:
    def __init__(self):
        self.api_key = settings.m3_api_key or ""
        self.base_url = settings.m3_base_url
        self.model = settings.m3_model
        self.is_mock = settings.is_mock
        # v0.1.1: minimax-m3 在 OpenRouter AtlasCloud provider 配错,自动降级到 m2.7
        # 用户改 .env 里的 M3_MODEL 就能覆盖
        self.fallback_model = "minimax/minimax-m2.7"
        if not self.is_mock:
            self._client = OpenAI(api_key=self.api_key, base_url=self.base_url)
            logger.info(f"M3 client 初始化: model={self.model}, base={self.base_url}")
        else:
            self._client = None
            logger.warning("M3_API_KEY 未配置,进入 mock 模式")

    def chat(
        self,
        system: str,
        user: str,
        *,
        temperature: float = 0.7,
        max_tokens: int = 1500,
        retrieved: list | None = None,
    ) -> str:
        """单次同步 chat — V0.1.2 加 fallback(主模型空响应 → fallback_model)
        
        V0.7.4.1: retrieved 用于 mock 模式 (无 key) 拼 KB 知识问答
        """
        if self.is_mock:
            return self._mock_response(user, retrieved=retrieved)
        # 1) 先用主模型
        try:
            resp = self._client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = self._extract_content(resp)
            if content.strip():
                return content
        except AuthenticationError as e:
            raise M3AuthError(f"M3 API key 无效或被拒绝 (401): {e}") from e
        except RateLimitError as e:
            raise M3QuotaError(f"M3 限流 / 余额不足 (429/402): {e}") from e
        except APIConnectionError as e:
            raise M3NetworkError(f"M3 网络错误: {e}") from e
        except APIError as e:
            status = getattr(e, "status_code", 500) or 500
            if 500 <= status < 600:
                raise M3ServerError(f"M3 服务端错误 ({status}): {e}") from e
            raise M3Error(f"M3 错误 ({status}): {e}") from e
        except Exception as e:
            raise M3Error(f"M3 未知错误: {e}") from e

        # 2) 主模型空响应 → fallback(同样错误处理)
        logger.warning(
            f"主模型 {self.model} 完全空响应,降级到 {self.fallback_model}"
        )
        try:
            resp = self._client.chat.completions.create(
                model=self.fallback_model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            return self._extract_content(resp)
        except Exception as e:
            raise M3Error(f"主模型 + fallback 都失败: {e}") from e

    def stream_chat(
        self,
        system: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 2000,
    ):
        """流式 chat — 逐 token yield 字符串

        v0.1.1:加 fallback — 如果主模型完全返回空(无任何 content),降级到 fallback_model
        """
        if self.is_mock:
            # mock 模式 (V0.7.4.1 改: 接受 KB 检索结果, 知识问答也能基于 KB 回答)
            # 注: stream_chat 自身不调 KB, 需 orchestrator 把 retrieved 传进来
            # 此处用消息里最后一条 user 提取
            last_user = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    last_user = m.get("content", "")
                    break
            # 尝试从 system prompt 抽取 KB 块 (orchestrator 注入的)
            # system 通常是 messages[0] (如果 list) 或者单独的 system 变量
            # 但此函数签名只有 messages, 我们从 messages 找 system
            kb_block = ""
            for m in messages:
                if m.get("role") == "system":
                    sb = m.get("content", "")
                    if "知识库参考" in sb:
                        # 抽出 [1] ... [2] ... 之间的内容
                        import re as _re
                        m1 = _re.search(r"## 知识库参考.+?(?=---|$)", sb, _re.DOTALL)
                        if m1:
                            kb_block = m1.group(0)
                    break
            # 抽出 KB chunk title/content (简化: 把 KB 块整个传过去)
            retrieved = []
            if kb_block:
                # 按 ### 切片
                import re as _re
                for chunk_match in _re.finditer(r"### \[\d+\] (.+?)\n来源: (.+?)\n.+?完整内容:\n(.+?)(?=\n### |\n---|$)", kb_block, _re.DOTALL):
                    title = chunk_match.group(1).strip()
                    path = chunk_match.group(2).strip()
                    content = chunk_match.group(3).strip()
                    retrieved.append({"title": title, "path": path, "content": content, "snippet": content[:200]})
            text = self._mock_response(last_user, retrieved=retrieved)
            for ch in text:
                yield ch
            return

        # 1) 先用主模型试 — 边 yield 边判断是否有 content
        got_real_content = False
        for chunk in self._stream(self.model, system, messages, temperature, max_tokens):
            # 区分 thinking 和真 content
            if chunk.startswith("[THINK]"):
                yield chunk
            else:
                got_real_content = True
                yield chunk
        if got_real_content:
            return

        # 2) 主模型空 — fallback
        logger.warning(
            f"主模型 {self.model} 完全空响应,降级到 {self.fallback_model}"
        )
        yield f"\n\n[系统提示:主模型 {self.model} 不可用,降级到 {self.fallback_model}]\n\n"
        yield from self._stream(self.fallback_model, system, messages, temperature, max_tokens)

    def _stream(self, model, system, messages, temperature, max_tokens):
        """流式调用 — 支持 reasoning model

        对于 minimax m3 / m2.7 这种 reasoning model,OpenRouter 把思考过程放在
        delta.reasoning,实际回答在 delta.content。
        优先用 reasoning(reasoning 和 reasoning_details 内容通常一样,只取一个避免重复)。
        """
        try:
            stream = self._client.chat.completions.create(
                model=model,
                messages=[{"role": "system", "content": system}, *messages],
                temperature=temperature,
                max_tokens=max_tokens,
                stream=True,
            )
            for chunk in stream:
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                if not delta:
                    continue
                # 1) 普通 content(优先)
                if delta.content:
                    yield delta.content
                    continue
                # 2) reasoning(只在没 content 时)
                reasoning = getattr(delta, "reasoning", None)
                if reasoning:
                    yield f"[THINK]{reasoning}[/THINK]"
                # 3) reasoning_details 数组(OpenRouter 格式)— 备选
                rd = getattr(delta, "reasoning_details", None)
                if rd and not reasoning:
                    for d in rd:
                        text = d.get("text") if isinstance(d, dict) else getattr(d, "text", None)
                        if text:
                            yield f"[THINK]{text}[/THINK]"
        except AuthenticationError as e:
            raise M3AuthError(f"M3 API key 无效 (401): {e}") from e
        except RateLimitError as e:
            raise M3QuotaError(f"M3 限流 / 余额不足: {e}") from e
        except APIConnectionError as e:
            raise M3NetworkError(f"M3 网络错误: {e}") from e
        except APIError as e:
            status = getattr(e, "status_code", 500) or 500
            if 500 <= status < 600:
                raise M3ServerError(f"M3 服务端错误 ({status}): {e}") from e
            raise M3Error(f"M3 错误 ({status}): {e}") from e
        except Exception as e:
            raise M3Error(f"M3 未知错误: {e}") from e

    def _extract_content(self, resp) -> str:
        """提取 response content;空响应时返回 '' 以触发 fallback"""
        try:
            content = resp.choices[0].message.content or ""
            return content
        except (AttributeError, IndexError, KeyError):
            return ""

    # ---------- mock (V0.7.4.1 修: KB-aware) ----------

    def _mock_response(self, user: str, retrieved: list | None = None) -> str:
        """V0.7.4.1: 无 key 时也用 KB 检索拼知识问答

        优先级:
        1. KB 检索有命中 → 用 KB 内容拼回答
        2. user 含 NP/IF/TSS 指标 → 走原训练报告模板
        """
        if retrieved:
            kb_text = self._format_kb_answer(user, retrieved)
            if kb_text:
                return kb_text
        return self._format_activity_report(user)

    def _format_kb_answer(self, user: str, retrieved: list) -> str:
        """V0.7.5.1: 抽取跟用户问题相关的句子 (避免堆砌无关内容, 牛头不对马嘴)"""
        import re
        if not retrieved:
            return ""
        # 1) 提取 user 关键词
        stopwords = {"的", "了", "是", "在", "和", "与", "或", "及", "把", "给", "我", "你", "他", "她", "它", "这", "那", "吗", "啊", "呢", "吧", "什么", "怎么", "如何", "为什么", "多久", "什么"}
        user_kws = set()
        for w in re.findall(r'[A-Za-z][A-Za-z0-9_]+', user):
            if len(w) >= 2:
                user_kws.add(w.lower())
        for s in re.findall(r'[\u4e00-\u9fff]+', user):
            # 加单字
            for ch in s:
                if ch not in stopwords:
                    user_kws.add(ch)
            # 2-gram
            for i in range(len(s) - 1):
                g = s[i:i+2]
                if g not in stopwords:
                    user_kws.add(g)
        if not user_kws:
            user_kws = set(re.findall(r'\w+', user))
        # 2) 给 retrieved 排序 + 计算每条相关性
        scored = []
        for i, r in enumerate(retrieved[:5]):
            content = r.get("content", "")
            if not content:
                continue
            # 计算关键词命中
            hits = sum(1 for kw in user_kws if kw in content)
            scored.append((hits, i, r))
        scored.sort(key=lambda x: (-x[0], x[1]))
        if not scored:
            return ""
        primary = scored[0][2]
        title = primary.get("title", "")
        content = primary.get("content", "")
        path = primary.get("path", "")
        # 3) 抽取 primary 里的相关句子 (按句号 / 换行 / 句号)
        if not content:
            return ""
        # 拆句
        sentences = re.split(r'(?<=[。！？!?\n])|(?<=[.!?]\s)', content)
        relevant = []
        for sent in sentences:
            sent = sent.strip()
            if not sent or len(sent) < 8:
                continue
            # 计算句子命中
            sent_hits = sum(1 for kw in user_kws if kw in sent)
            if sent_hits > 0:
                relevant.append((sent_hits, sent))
        relevant.sort(key=lambda x: -x[0])
        # 取 top 3-5 句
        if relevant:
            top_sents = [s for _, s in relevant[:5]]
            content_used = "\n\n".join(top_sents)
        else:
            # 没有任何命中, 取头 400 字符
            content_used = content[:400] + ("..." if len(content) > 400 else "")
        parts = [f"# {title}\n"]
        parts.append(f"**来源**: {path}\n")
        parts.append("\n## 核心内容\n")
        parts.append(content_used)
        if len(scored) > 1:
            parts.append("\n## 相关参考\n")
            for hits, i, c in scored[1:3]:
                ctitle = c.get("title", "")
                ccontent = c.get("content", "")[:200]
                if ccontent and ctitle:
                    parts.append(f"**{ctitle}**: {ccontent}...\n")
        parts.append(f"\n> 📚 本回答基于训练百科 (潘震教练) KB 检索, 命中 {len(scored)} 个相关片段, 已按问题关键词抽取相关句子.")
        parts.append("> 注: mock 模式 (无 M3_API_KEY). 配 key 后 LLM 会基于 KB 完整生成.")
        return "\n".join(parts)

    def _format_activity_report(self, user: str) -> str:
        """原训练报告模板 (单活动)"""
        import re
        m = re.search(r"NP[:=]\s*(\d+)", user)
        np_v = m.group(1) if m else "?"
        m = re.search(r"IF[:=]\s*([\d.]+)", user)
        if_v = m.group(1) if m else "?"
        m = re.search(r"TSS[:=]\s*(\d+)", user)
        tss_v = m.group(1) if m else "?"
        m = re.search(r"FTP[:=]\s*(\d+)", user)
        ftp_v = m.group(1) if m else "?"
        m = re.search(r"avg_power[:=]\s*(\d+)", user)
        avg_v = m.group(1) if m else "?"
        m = re.search(r"avg_hr[:=]\s*(\d+)", user)
        hr_v = m.group(1) if m else "?"
        m = re.search(r"duration_min[:=]\s*([\d.]+)", user)
        dur_v = m.group(1) if m else "?"

        # 简单判断强度 + 给建议
        try:
            if_num = float(if_v)
        except (ValueError, TypeError):
            if_num = 0.0
        try:
            tss_num = int(tss_v)
        except (ValueError, TypeError):
            tss_num = 0

        # 默认 rec(防止某分支没赋值,被 f-string 引用时报 UnboundLocalError)
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


_client: Optional[M3Client] = None


def get_m3() -> M3Client:
    global _client
    if _client is None:
        _client = M3Client()
    return _client
