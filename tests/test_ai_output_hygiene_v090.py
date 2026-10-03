"""V0.9.0: AI 流输出的用户可见性测试

## 为什么有这个文件

审计发现 3 个"内部实现泄漏到用户界面"的问题:
1. `m3_client` 把 `[THINK]xxx[/THINK]` 原文 yield 出去, 而前端只认 markdown
   的 `## Thinking` 标题 → "随便聊聊" tab 里用户看到一串裸思维链 token
2. 主模型空响应时, 把 `[系统提示:主模型 X 不可用,降级到 Y]` 直接 yield 给用户
3. FIT 缺 session 汇总时静默回算, watcher 报"导入成功"但数据是空的

2 和 3 是"骗用户", 1 是"脏用户眼睛"。都属于稳定性/体验问题, 不属于功能缺失。

## 测试策略

用假的流式源替代真实 LLM (CI 不能依赖网络), 断言**产出内容**里
不出现不该出现的标记。
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, ".")


# ================================================================
# 1. 思维链不混进正文
# ================================================================

class _FakeStream:
    """替换 M3Client._stream, 返回预设 chunk 序列"""

    def __init__(self, chunks):
        self._chunks = chunks

    def __call__(self, model, system, messages, temperature, max_tokens):
        yield from self._chunks


class TestThinkingNotLeakedIntoAnswer:
    def test_think_tags_become_think_frames_not_raw_text(self, monkeypatch):
        """[THINK] 内容应包成 [THINK] <内容> 帧, 而不是裸 [THINK]xxx[/THINK] 泄漏

        修复前: 产出的 text 里含 "[/THINK]" 闭合标记, 前端会当正文显示
        修复后: 闭合标记被剥掉, 内容包在 [THINK] 帧里由前端分流到思维树
        """
        from cycling_coach.ai.m3_client import M3Client

        client = M3Client()
        client.is_mock = False
        monkeypatch.setattr(
            client, "_stream",
            _FakeStream([
                "[THINK]用户问 FTP 怎么提高",
                "[THINK]，需要先确认基础。",
                "先测 FTP。",
            ]),
        )

        out = list(client.stream_chat(system="s", messages=[{"role": "user", "content": "q"}]))

        answer = "".join(c for c in out if not c.startswith("[THINK]"))
        think = "".join(c[len("[THINK]"):] for c in out if c.startswith("[THINK]"))

        assert "[/THINK]" not in answer, (
            f"正文里不该出现 [/THINK] 闭合标记: {answer[:120]!r}"
        )
        assert "[/THINK]" not in think, (
            f"think 帧里不该保留闭合标记: {think[:120]!r}"
        )
        assert "先测 FTP" in answer, f"正文应保留实际回答: {answer!r}"
        assert "用户问 FTP" in think, f"思维内容应保留: {think!r}"

    def test_fallback_message_not_yielded_to_user(self, monkeypatch):
        """主模型空响应时不该把降级提示 yield 给用户

        修复前: 用户会看到 "[系统提示:主模型 X 不可用,降级到 Y]"
        修复后: 只写日志, 用户只看到 fallback 模型的回答
        """
        from cycling_coach.ai.m3_client import M3Client

        client = M3Client()
        client.is_mock = False
        calls = []

        def fake_stream(model, system, messages, temperature, max_tokens):
            calls.append(model)
            if len(calls) == 1:
                return iter(())          # 主模型完全空
            yield "fallback 的正常回答"

        monkeypatch.setattr(client, "_stream", fake_stream)

        out = list(client.stream_chat(system="s", messages=[{"role": "user", "content": "q"}]))
        text = "".join(out)

        assert "系统提示" not in text, f"降级提示不该出现在用户输出: {text[:150]!r}"
        assert "不可用" not in text, f"降级提示不该出现在用户输出: {text[:150]!r}"
        assert "降级" not in text, f"降级提示不该出现在用户输出: {text[:150]!r}"
        assert "fallback 的正常回答" in text, f"fallback 回答应正常输出: {text!r}"
        assert len(calls) == 2, f"应该调了主模型 + fallback, 实际 {len(calls)} 次"


# ================================================================
# 2. 前端能把 think 帧分流
# ================================================================

class TestFrontendThinkRouting:
    def test_api_ts_parses_think_frame(self):
        """apps/web/src/lib/api.ts 必须把 [THINK] 帧解析成 think 事件

        这是纯静态检查 —— 断言源码里有对应分支。
        (前端没有单测框架, 用源码断言防止回归)
        """
        src = Path("apps/web/src/lib/api.ts").read_text(encoding="utf-8")
        assert 'line.startsWith("[THINK]")' in src, (
            "api.ts 缺少 [THINK] 帧解析分支 — "
            "思维链会被当成正文显示给用户"
        )
        assert 'type: "think"' in src, "api.ts 缺少 think 事件类型"

    def test_chatpage_routes_think_to_thinking_field(self):
        """ChatPage 必须把 think 事件写进 thinking 字段而不是 content"""
        src = Path("apps/web/src/pages/ChatPage.tsx").read_text(encoding="utf-8")
        assert 'evt.type === "think"' in src, (
            "ChatPage 缺少 think 事件处理 — 思维链会显示在正文气泡里"
        )
        assert "thinking: fullThink" in src, (
            "ChatPage 应把 think 内容写进 thinking 字段"
        )

    def test_generator_type_includes_think(self):
        """chatStreamV2 的返回类型联合要包含 think"""
        src = Path("apps/web/src/lib/api.ts").read_text(encoding="utf-8")
        assert '"think"' in src, "chatStreamV2 类型定义应包含 think"


# ================================================================
# 3. 缺 session 的 FIT 必须显式告知, 不能静默
# ================================================================

class TestReconstructedDataIsSurfaced:
    @pytest.fixture(autouse=True)
    def _tmpdb(self):
        from tests.conftest import use_temp_db
        use_temp_db("reconstructed_test")
        yield

    def test_parser_marks_reconstructed(self, tmp_path):
        """parser 的 raw_meta 要标 reconstructed=True"""
        from cycling_coach.data.parsers.fit_parser import FitParser
        from tests.fit_fixtures import build_fit

        p = tmp_path / "nosess.fit"
        build_fit(p, duration_s=1200, avg_power=190, with_session=False, with_lap=False)

        a = FitParser().parse_file(p)

        assert (a.raw_meta or {}).get("reconstructed") is True, (
            "缺 session 的 FIT 应标记 reconstructed=True, 让上层能提示用户"
        )

    def test_full_session_not_marked_reconstructed(self, tmp_path):
        from cycling_coach.data.parsers.fit_parser import FitParser
        from tests.fit_fixtures import build_fit

        p = tmp_path / "withsess.fit"
        build_fit(p, duration_s=1200, avg_power=190)

        a = FitParser().parse_file(p)

        assert not (a.raw_meta or {}).get("reconstructed"), (
            "正常带 session 的 FIT 不该标 reconstructed"
        )

    def test_upload_response_carries_warning(self, tmp_path):
        """ingest 的返回值要带 warning, 让前端能提示用户"""
        import asyncio

        from tests.conftest import use_temp_db
        use_temp_db("reconstructed_upload")

        from cycling_coach.core.services.activity import ActivityService
        from cycling_coach.data.sqlite.database import SessionLocal
        from cycling_coach.core.profile import store as profile_store
        from tests.fit_fixtures import build_fit

        db = SessionLocal()
        athlete = profile_store.get_or_create_athlete(db)
        athlete.ftp = 250
        db.commit()

        p = tmp_path / "nosess_up.fit"
        build_fit(p, duration_s=1800, avg_power=200, with_session=False, with_lap=False)

        svc = ActivityService(db)
        loop = asyncio.new_event_loop()
        try:
            res = loop.run_until_complete(
                svc.upload(filename="nosess_up.fit", file_bytes=p.read_bytes())
            )
        finally:
            loop.close()

        assert res.get("reconstructed") is True, (
            f"ingest 返回值应标 reconstructed=True: {res}"
        )
        assert res.get("warning"), (
            f"ingest 返回值应带 warning 让前端提示用户: {res}"
        )
        db.close()
