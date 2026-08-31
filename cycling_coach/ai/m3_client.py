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
from cycling_coach.ai.mock_engine import MockEngine, get_mock_engine

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
        # V0.7.5.7 A-2: 从 settings 读, 不再硬编码
        self.fallback_model = getattr(settings, "m3_fallback_model", "minimax/minimax-m2.7")
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
            # V0.7.6 抽离: 直接用 MockEngine 流式 yield
            # 把独立 system 参数塞到 messages 头部, MockEngine 才会抽到 KB 块
            msgs_for_mock = list(messages) if messages else []
            if system:
                msgs_for_mock = [{"role": "system", "content": system}, *msgs_for_mock]
            yield from get_mock_engine().stream_response(msgs_for_mock)
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

    # ---------- mock (V0.7.6 抽离 → cycling_coach.ai.mock_engine) ----------

    def _mock_response(self, user: str, retrieved: list | None = None) -> str:
        """V0.7.6 薄包装 — 委托给 MockEngine, 保持向后兼容签名

        优先级:
        1. KB 检索有命中 → 用 KB 内容拼回答
        2. user 含 NP/IF/TSS 指标 → 走原训练报告模板
        """
        engine = get_mock_engine()
        if retrieved:
            kb_text = engine.format_kb_answer(user, retrieved, athlete_ctx={})
            if kb_text:
                return kb_text
        return engine.format_activity_report({"raw_query": user}, focus="auto")


_client: Optional[M3Client] = None


def get_m3() -> M3Client:
    global _client
    if _client is None:
        _client = M3Client()
    return _client
