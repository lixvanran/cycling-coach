"""V0.8.0: multi-mind 集成 (orchestrator mode=workflow + chat) 测试

覆盖:
1. mode=workflow → orchestrator 调 multi-mind → 拿到结果
2. multi-mind 不可达 → 降级到 mode=rag (如果 fallback=True)
3. multi-mind 不可达 + fallback=False → [ERROR]
4. mode=chat → 不调 multi-mind, 直接 LLM
5. mode=rag (默认) → V0.7.x 行为不变
6. chat_messages 持久化 parent_id/node_path/score 正确
7. settings 配置 (multi_mind_url/pipeline/timeout/fallback)
8. coach.py ChatRequest 接受 mode 字段

不依赖真实 multi-mind 进程 — 用 monkeypatch 替代 httpx.AsyncClient
"""
from __future__ import annotations
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, ".")

# 测试前: 强制无 API key + 临时 workspace
TMP = Path(tempfile.mkdtemp(prefix="cc_test_v080_"))
os.environ["M3_API_KEY"] = ""
os.environ["WORKSPACE_DIR"] = str(TMP)
os.environ["MULTI_MIND_FALLBACK_TO_RAG"] = "true"


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module", autouse=True)
def _setup_module():
    """模块级 setup: 切到临时 workspace + init_db"""
    from cycling_coach.config import config as cfg
    from cycling_coach.data.sqlite.database import (
        init_db, engine, Base,
    )
    from cycling_coach.data.sqlite import models  # noqa: F401 register tables
    cfg.settings.workspace_dir = str(TMP)
    from sqlalchemy import create_engine
    new_engine = create_engine(
        f"sqlite:///{TMP}/cycling_coach.sqlite",
        connect_args={"check_same_thread": False},
    )
    cfg.engine = new_engine  # type: ignore[attr-defined]
    Base.metadata.create_all(new_engine)
    yield


@pytest.fixture()
def client():
    """FastAPI TestClient"""
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    return TestClient(app)


# ============================================================
# Mock multi-mind HTTP 响应
# ============================================================

class MockMultiMindResponse:
    """模拟 multi-mind 流式 SSE 响应"""

    def __init__(self, status_code: int = 200, frames: list[str] | None = None, raise_exc: Exception | None = None):
        self.status_code = status_code
        self.frames = frames or []
        self.raise_exc = raise_exc

    async def aiter_text(self):
        if self.raise_exc:
            raise self.raise_exc
        for f in self.frames:
            yield f


def make_fake_multi_mind_client(frames: list[str], status_code: int = 200, raise_exc: Exception | None = None):
    """生成 fake httpx.AsyncClient — 支持 `async with AsyncClient() as client` + client.stream(...)"""
    mock_response = MockMultiMindResponse(status_code=status_code, frames=frames, raise_exc=raise_exc)

    class FakeStream:
        async def __aenter__(self):
            return mock_response
        async def __aexit__(self, *args):
            return None

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass
        async def __aenter__(self):
            return self
        async def __aexit__(self, *args):
            return None
        def stream(self, method, url, **kwargs):
            return FakeStream()

    return FakeClient


# 6 个 stage 节点 (dict 形式, 给 _call_multi_mind_sync 直接用)
SAMPLE_NODES = [
    {"event": "node", "stage": "router", "status": "started", "pipeline": "insight_v2", "task_preview": "100km 公路赛"},
    {"event": "node", "stage": "router", "status": "done", "difficulty": "hard", "model": "test-model"},
    {"event": "node", "stage": "decomposer", "n_subtasks": 3, "subtasks": [{"id": "s1", "angle": "节奏", "task": "配速"}]},
    {"event": "node", "stage": "executor", "n_results": 3, "preview": ["激进建议"]},
    {"event": "node", "stage": "integrator_aggressive", "content_preview": "激进版: 开局套圈"},
    {"event": "node", "stage": "critic", "content_preview": "对比分析..."},
]

# 对应的 SSE 帧 (给 _call_multi_mind_sync 测试解析用)
_DONE_PAYLOAD = json.dumps({
    "event": "done",
    "final_output": "【激进版】开局套圈\n\n【保守版】节能跟车\n\n【对比】场景 A 选激进",
    "tokens": 1500,
    "latency_ms": 500,
    "stage_metrics": {},
}, ensure_ascii=False)
_DONE_FRAME = "data: [DONE] " + _DONE_PAYLOAD + "\n\n"
SAMPLE_FRAMES = (
    [f"data: [NODE] {json.dumps(n, ensure_ascii=False)}\n\n" for n in SAMPLE_NODES]
    + [_DONE_FRAME]
)


# ============================================================
# 1. Settings 配置测试
# ============================================================

class TestSettings:
    def test_multi_mind_defaults(self):
        from cycling_coach.config.config import Settings
        s = Settings()
        assert s.multi_mind_url == "http://127.0.0.1:8766"
        assert s.multi_mind_pipeline == "insight_v2"
        assert s.multi_mind_timeout == 5.0
        assert s.multi_mind_fallback_to_rag is True

    def test_settings_override_via_env(self, monkeypatch):
        monkeypatch.setenv("MULTI_MIND_URL", "http://my-mm:9999")
        monkeypatch.setenv("MULTI_MIND_PIPELINE", "bilateral")
        monkeypatch.setenv("MULTI_MIND_TIMEOUT", "10.5")
        monkeypatch.setenv("MULTI_MIND_FALLBACK_TO_RAG", "false")
        from cycling_coach.config.config import Settings
        s = Settings()
        assert s.multi_mind_url == "http://my-mm:9999"
        assert s.multi_mind_pipeline == "bilateral"
        assert s.multi_mind_timeout == 10.5
        assert s.multi_mind_fallback_to_rag is False


# ============================================================
# 2. ChatRequest 接受 mode 字段
# ============================================================

class TestChatRequest:
    def test_default_mode_is_rag(self):
        from cycling_coach.api.routers.coach import ChatRequest
        req = ChatRequest(message="hi")
        assert req.mode == "rag"
        assert req.session_id is None

    def test_workflow_mode(self):
        from cycling_coach.api.routers.coach import ChatRequest
        req = ChatRequest(message="100km 公路赛", mode="workflow", session_id=42)
        assert req.mode == "workflow"
        assert req.session_id == 42

    def test_invalid_mode_rejected(self):
        from cycling_coach.api.routers.coach import ChatRequest
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            ChatRequest(message="hi", mode="not_a_mode")


# ============================================================
# 3. mode=workflow → 调 multi-mind
# ============================================================

class TestWorkflowMode:
    def test_workflow_calls_multi_mind_and_streams(self, monkeypatch):
        """workflow mode: 调 multi-mind HTTP, 转发 SSE 帧"""
        from cycling_coach.ai import orchestrator
        from cycling_coach.config.config import settings

        # 替换 _call_multi_mind_sync 为受控的 mock
        fake_result = (SAMPLE_NODES, "【激进版】激进建议", 750, 750, None)
        monkeypatch.setattr(orchestrator, "_call_multi_mind_sync", lambda url, payload, timeout: fake_result)

        # 跑
        chunks = list(orchestrator.workflow_pipeline(
            history=[],
            user_message="100km 公路赛配速",
        ))

        # 验证: [SESSION] 帧
        joined = "".join(chunks)
        assert "[SESSION]" in joined, f"no [SESSION] frame: {joined[:200]}"
        # 验证: 透传 [NODE] 帧
        assert joined.count("[NODE]") >= len(SAMPLE_NODES), f"too few [NODE]: {joined.count('[NODE]')}"
        # 验证: [FINAL] 帧
        assert "[FINAL]" in joined
        # 验证: [DONE] 帧
        assert joined.endswith("data: [DONE]\n\n") or "[DONE]" in joined

    def test_workflow_persists_to_chat_messages(self, monkeypatch):
        """workflow mode: 每个 stage 持久化到 chat_messages"""
        from cycling_coach.ai import orchestrator
        from cycling_coach.data.sqlite.database import SessionLocal
        from cycling_coach.data.sqlite.models import ChatSession, ChatMessage

        fake_result = (SAMPLE_NODES, "最终建议", 500, 500, None)
        monkeypatch.setattr(orchestrator, "_call_multi_mind_sync", lambda url, payload, timeout: fake_result)

        # 跑 workflow
        chunks = list(orchestrator.workflow_pipeline(
            history=[],
            user_message="测试持久化",
        ))

        # 验证 DB
        with SessionLocal() as db:
            sessions = db.query(ChatSession).filter(ChatSession.session_type == "diffuse_thinking").all()
            assert len(sessions) >= 1, "no diffuse_thinking session"
            sess = sessions[-1]
            msgs = db.query(ChatMessage).filter(ChatMessage.session_id == sess.id).order_by(ChatMessage.id.asc()).all()
            # 至少要有 user + N 个 stage + final
            assert len(msgs) >= 2, f"too few messages: {len(msgs)}"
            # 第 1 条是 user
            assert msgs[0].role == "user"
            assert msgs[0].content == "测试持久化"
            # 至少有 1 条 assistant (final)
            assistant_msgs = [m for m in msgs if m.role == "assistant"]
            assert len(assistant_msgs) >= 1
            final = assistant_msgs[-1]
            assert final.content == "最终建议"
            assert final.thought_kind == "final"
            assert final.status == "selected"
            # 有 agent_a / agent_b 节点 (思维树)
            agent_msgs = [m for m in msgs if m.role in ("agent_a", "agent_b")]
            assert len(agent_msgs) >= 1
            # 验证 parent_id / node_path
            for am in agent_msgs:
                assert am.parent_id is not None
                assert am.node_path is not None
                assert am.node_path.startswith(f"{msgs[0].id}.")
            # 验证 session 完成
            assert sess.status == "completed"


# ============================================================
# 4. multi-mind 不可达 → 降级
# ============================================================

class TestFallback:
    def test_fallback_to_rag_on_connection_error(self, monkeypatch):
        """multi-mind 不可达 → fallback 到 rag"""
        from cycling_coach.ai import orchestrator

        # mock 调失败
        monkeypatch.setattr(
            orchestrator, "_call_multi_mind_sync",
            lambda url, payload, timeout: ([], "", None, None, "connect refused"),
        )
        # 确认 fallback 开启
        from cycling_coach.config.config import settings
        assert settings.multi_mind_fallback_to_rag is True

        chunks = list(orchestrator.workflow_pipeline(
            history=[],
            user_message="测试降级",
        ))
        joined = "".join(chunks)
        # 验证: 推了 [FALLBACK] 提示
        assert "[FALLBACK]" in joined, f"no [FALLBACK]: {joined[:200]}"
        # 验证: 降级后走 rag, 推 [SOURCES] / [DONE]
        assert "[DONE]" in joined

    def test_no_fallback_raises_error(self, monkeypatch):
        """fallback=False → [ERROR]"""
        from cycling_coach.ai import orchestrator
        from cycling_coach.config.config import settings

        # 临时关 fallback
        monkeypatch.setattr(settings, "multi_mind_fallback_to_rag", False)

        monkeypatch.setattr(
            orchestrator, "_call_multi_mind_sync",
            lambda url, payload, timeout: ([], "", None, None, "connect refused"),
        )

        chunks = list(orchestrator.workflow_pipeline(
            history=[],
            user_message="测试不降级",
        ))
        joined = "".join(chunks)
        assert "[ERROR]" in joined
        assert "connect refused" in joined
        # 没有 [DONE] (因为直接返回 error)
        # 至少 [ERROR] 存在


# ============================================================
# 5. mode=chat → 不调 multi-mind
# ============================================================

class TestChatMode:
    def test_chat_does_not_call_multi_mind(self, monkeypatch):
        """chat mode: 直接 LLM, 不调 multi-mind"""
        from cycling_coach.ai import orchestrator

        called = []
        def spy(url, payload, timeout):
            called.append(url)
            return ([], "", None, None, "should not be called")

        monkeypatch.setattr(orchestrator, "_call_multi_mind_sync", spy)

        chunks = list(orchestrator.chat_pipeline(
            history=[],
            user_message="随便聊聊",
        ))
        joined = "".join(chunks)
        # multi-mind 没被调
        assert called == []
        # 有 [SESSION] + 文本 + [DONE]
        assert "[SESSION]" in joined
        assert "[DONE]" in joined

    def test_chat_persists_assistant(self, monkeypatch):
        """chat mode: 持久化 user + assistant (无思维树)"""
        from cycling_coach.ai import orchestrator
        from cycling_coach.data.sqlite.database import SessionLocal
        from cycling_coach.data.sqlite.models import ChatSession, ChatMessage

        chunks = list(orchestrator.chat_pipeline(
            history=[],
            user_message="普通聊天测试",
        ))
        joined = "".join(chunks)
        assert "[DONE]" in joined

        with SessionLocal() as db:
            sessions = db.query(ChatSession).filter(ChatSession.session_type == "general").all()
            assert len(sessions) >= 1
            sess = sessions[-1]
            msgs = db.query(ChatMessage).filter(ChatMessage.session_id == sess.id).order_by(ChatMessage.id).all()
            # user + assistant
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert msgs[0].content == "普通聊天测试"
            assert msgs[1].role == "assistant"
            assert msgs[1].parent_id == msgs[0].id
            assert msgs[1].thought_kind == "final"
            assert msgs[1].status == "selected"


# ============================================================
# 6. mode=rag 保持 V0.7.x 行为
# ============================================================

class TestRagMode:
    def test_rag_default_works(self, monkeypatch):
        """rag mode (默认): V0.7.x 行为不变"""
        from cycling_coach.ai import orchestrator

        called = []
        def spy(url, payload, timeout):
            called.append(url)
            return ([], "", None, None, "should not be called")

        monkeypatch.setattr(orchestrator, "_call_multi_mind_sync", spy)

        # stream_chat 默认 = rag
        chunks = list(orchestrator.stream_chat(
            history=[],
            user_message="RAG 测试",
            mode="rag",  # 显式
        ))
        joined = "".join(chunks)
        assert called == []  # 不调 multi-mind
        assert "[SESSION]" in joined
        assert "[DONE]" in joined
        # rag 模式推 [SOURCES] (即使没命中也是 OK)

    def test_stream_chat_default_is_rag(self):
        """stream_chat 不传 mode → 默认 rag"""
        from cycling_coach.ai.orchestrator import stream_chat
        import inspect
        sig = inspect.signature(stream_chat)
        assert sig.parameters["mode"].default == "rag"


# ============================================================
# 7. HTTP 端点测试
# ============================================================

class TestChatEndpoint:
    def test_chat_endpoint_mode_rag(self, client):
        """POST /api/coach/chat mode=rag (默认)"""
        r = client.post("/api/coach/chat", json={"message": "测试 RAG 端点", "mode": "rag"})
        assert r.status_code == 200
        assert "text/event-stream" in r.headers["content-type"]
        body = r.text
        assert "[DONE]" in body

    def test_chat_endpoint_mode_chat(self, client):
        """POST /api/coach/chat mode=chat"""
        r = client.post("/api/coach/chat", json={"message": "测试 chat 端点", "mode": "chat"})
        assert r.status_code == 200
        body = r.text
        assert "[DONE]" in body

    def test_chat_endpoint_mode_workflow_with_fallback(self, client, monkeypatch):
        """POST /api/coach/chat mode=workflow + multi-mind 不可达 → 降级"""
        from cycling_coach.ai import orchestrator

        monkeypatch.setattr(
            orchestrator, "_call_multi_mind_sync",
            lambda url, payload, timeout: ([], "", None, None, "test error"),
        )
        # fallback 默认 True
        r = client.post("/api/coach/chat", json={"message": "测试 workflow 端点", "mode": "workflow"})
        assert r.status_code == 200
        body = r.text
        # 降级时推 [FALLBACK] + 走 rag 完成
        assert "[FALLBACK]" in body
        assert "[DONE]" in body

    def test_chat_endpoint_mode_workflow_success(self, client, monkeypatch):
        """POST /api/coach/chat mode=workflow + multi-mind 成功"""
        from cycling_coach.ai import orchestrator

        fake_nodes = [
            {"event": "node", "stage": "router", "status": "done", "difficulty": "hard", "model": "test"},
            {"event": "node", "stage": "decomposer", "n_subtasks": 3, "subtasks": []},
        ]
        monkeypatch.setattr(
            orchestrator, "_call_multi_mind_sync",
            lambda url, payload, timeout: (fake_nodes, "**多心智建议**: 选激进", 100, 200, None),
        )
        r = client.post("/api/coach/chat", json={"message": "100km 配速", "mode": "workflow"})
        assert r.status_code == 200
        body = r.text
        assert "[NODE]" in body
        assert "[FINAL]" in body
        assert "[DONE]" in body
        assert "多心智建议" in body

    def test_chat_endpoint_invalid_mode(self, client):
        """POST /api/coach/chat 错 mode → 422"""
        r = client.post("/api/coach/chat", json={"message": "x", "mode": "wrong"})
        assert r.status_code == 422

    def test_chat_endpoint_with_session_id(self, client, monkeypatch):
        """POST /api/coach/chat 传 session_id → 持久化到该 session"""
        from cycling_coach.ai import orchestrator
        from cycling_coach.data.sqlite.database import SessionLocal
        from cycling_coach.data.sqlite.models import ChatSession

        # 先建一个 session
        with SessionLocal() as db:
            sess = ChatSession(athlete_id=1, title="预建 session", session_type="general")
            db.add(sess)
            db.commit()
            sid = sess.id

        # 调 chat
        r = client.post("/api/coach/chat", json={"message": "用现有 session", "mode": "chat", "session_id": sid})
        assert r.status_code == 200
        body = r.text
        assert "[DONE]" in body

        # 验证消息挂到该 session 下
        with SessionLocal() as db:
            from cycling_coach.data.sqlite.models import ChatMessage
            msgs = db.query(ChatMessage).filter(ChatMessage.session_id == sid).all()
            assert len(msgs) == 2
            assert msgs[0].role == "user"
            assert msgs[0].content == "用现有 session"


# ============================================================
# 8. _call_multi_mind_sync 内部测试 (monkeypatch httpx)
# ============================================================

class TestCallMultiMindSync:
    def test_call_parses_sse_frames(self, monkeypatch):
        """_call_multi_mind_sync: 正确解析 SSE [NODE] / [DONE]"""
        from cycling_coach.ai import orchestrator
        import httpx

        # mock httpx.AsyncClient
        FakeClient = make_fake_multi_mind_client(SAMPLE_FRAMES)
        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

        nodes, final, t_in, t_out, err = orchestrator._call_multi_mind_sync(
            "http://fake/run", {"task": "x"}, 5.0
        )
        assert err is None
        assert len(nodes) == len(SAMPLE_NODES)
        assert "激进版" in final
        assert t_in == 750
        assert t_out == 750

    def test_call_handles_connection_error(self, monkeypatch):
        """_call_multi_mind_sync: 连接失败返 error_msg"""
        from cycling_coach.ai import orchestrator
        import httpx

        # 触发 ConnectError
        FakeClient = make_fake_multi_mind_client([], raise_exc=httpx.ConnectError("refused"))
        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

        nodes, final, t_in, t_out, err = orchestrator._call_multi_mind_sync(
            "http://fake/run", {"task": "x"}, 5.0
        )
        assert err is not None
        assert "connect" in err.lower()
        assert nodes == []
        assert final == ""

    def test_call_handles_http_error(self, monkeypatch):
        """_call_multi_mind_sync: HTTP 500"""
        from cycling_coach.ai import orchestrator
        import httpx

        # 触发非 200
        FakeClient = make_fake_multi_mind_client([], status_code=500)
        monkeypatch.setattr(httpx, "AsyncClient", FakeClient)

        nodes, final, t_in, t_out, err = orchestrator._call_multi_mind_sync(
            "http://fake/run", {"task": "x"}, 5.0
        )
        assert err is not None
        assert "500" in err
