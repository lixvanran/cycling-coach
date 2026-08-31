"""V0.7.6: chat 持久化 + 思维树端点测试

覆盖:
1. POST /api/chat/sessions — 创建会话
2. POST /api/chat/sessions/{id}/messages + GET 同路径 — 增查消息
3. GET /api/chat/sessions — 列出会话
4. PATCH /api/chat/sessions/{id}/tree — 更新思维树
5. DELETE /api/chat/sessions/{id} — cascade 删 messages
6. M3Client mock 模式向后兼容 (V0.7.6 mock_engine 抽离验证)
"""
from __future__ import annotations
import os
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, ".")

# 测试前: 强制无 API key + 临时 workspace
TMP = Path(tempfile.mkdtemp(prefix="cc_test_v076_"))
os.environ["M3_API_KEY"] = ""
os.environ["WORKSPACE_DIR"] = str(TMP)


@pytest.fixture(scope="module", autouse=True)
def _setup_module():
    """模块级 setup: 切到临时 workspace + init_db 建表"""
    from cycling_coach.config import config as cfg
    from cycling_coach.data.sqlite.database import (
        init_db, engine, Base,
    )
    from cycling_coach.data.sqlite import models  # noqa: F401 register tables
    # 重新指向临时 workspace
    cfg.settings.workspace_dir = str(TMP)
    # 重建 engine (指向新 db file)
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    new_engine = create_engine(
        f"sqlite:///{TMP}/cycling_coach.sqlite",
        connect_args={"check_same_thread": False},
    )
    cfg.engine = new_engine  # type: ignore[attr-defined]
    Base.metadata.create_all(new_engine)
    yield
    # teardown: 不删 tmp, pytest tmp_path 自动收


@pytest.fixture()
def client():
    """FastAPI TestClient (每个 test 独立 session)"""
    from fastapi.testclient import TestClient
    from cycling_coach.api.main import app
    return TestClient(app)


class TestChatSessionsCRUD:
    def test_create_session(self, client):
        r = client.post("/api/chat/sessions", json={"title": "测试", "session_type": "general"})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["title"] == "测试"
        assert data["session_type"] == "general"
        assert data["status"] == "active"
        assert data["message_count"] == 0
        assert "id" in data and data["id"] > 0
        assert "created_at" in data

    def test_create_session_default(self, client):
        """不传 body 也能建 (title 默认 '新对话')"""
        r = client.post("/api/chat/sessions", json={})
        assert r.status_code == 200
        data = r.json()
        assert data["title"] == "新对话"
        assert data["session_type"] == "general"

    def test_create_session_invalid_type(self, client):
        """session_type 必须匹配 pattern"""
        r = client.post("/api/chat/sessions", json={"session_type": "hacker"})
        assert r.status_code == 422  # pydantic validation


class TestMessages:
    def _make_session(self, client) -> int:
        r = client.post("/api/chat/sessions", json={"title": "msg test"})
        return r.json()["id"]

    def test_add_and_get_messages(self, client):
        sid = self._make_session(client)
        # user msg
        r1 = client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={"role": "user", "content": "你好"},
        )
        assert r1.status_code == 200
        m1 = r1.json()
        assert m1["role"] == "user"
        assert m1["content"] == "你好"
        assert m1["parent_id"] is None
        # assistant msg with thinking + tokens
        r2 = client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={
                "role": "assistant", "content": "你好,我是教练",
                "thinking": "用户在打招呼,回应一下",
                "tokens_in": 5, "tokens_out": 8,
            },
        )
        assert r2.status_code == 200
        m2 = r2.json()
        assert m2["role"] == "assistant"
        assert m2["thinking"] == "用户在打招呼,回应一下"
        assert m2["tokens_in"] == 5
        assert m2["tokens_out"] == 8
        # get_messages 顺序
        r3 = client.get(f"/api/chat/sessions/{sid}/messages")
        assert r3.status_code == 200
        msgs = r3.json()
        assert len(msgs) == 2
        assert msgs[0]["content"] == "你好"
        assert msgs[1]["content"] == "你好,我是教练"

    def test_add_message_404(self, client):
        r = client.post(
            "/api/chat/sessions/99999/messages",
            json={"role": "user", "content": "x"},
        )
        assert r.status_code == 404

    def test_thought_tree_message(self, client):
        """思维树节点: parent_id / node_path / thought_kind / score"""
        sid = self._make_session(client)
        r1 = client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={"role": "user", "content": "主问题"},
        )
        root_id = r1.json()["id"]
        r2 = client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={
                "role": "agent_a", "content": "子问题 A",
                "parent_id": root_id, "node_path": "root.0",
                "thought_kind": "decompose", "score": 0.85,
            },
        )
        assert r2.status_code == 200
        m = r2.json()
        assert m["parent_id"] == root_id
        assert m["node_path"] == "root.0"
        assert m["thought_kind"] == "decompose"
        assert m["score"] == 0.85


class TestListSessions:
    def test_list_empty(self, client):
        r = client.get("/api/chat/sessions")
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_list_count(self, client):
        # 建 2 个 diffuse_thinking session
        for i in range(2):
            r = client.post(
                "/api/chat/sessions",
                json={"title": f"list-{i}", "session_type": "diffuse_thinking"},
            )
            assert r.status_code == 200
        r = client.get("/api/chat/sessions?session_type=diffuse_thinking")
        assert r.status_code == 200
        rows = r.json()
        assert len(rows) >= 2
        for row in rows:
            assert row["session_type"] == "diffuse_thinking"

    def test_list_pagination(self, client):
        r = client.get("/api/chat/sessions?limit=2&offset=0")
        assert r.status_code == 200
        assert len(r.json()) <= 2


class TestTreeUpdate:
    def test_update_tree(self, client):
        # 1) 建会话
        r = client.post("/api/chat/sessions", json={"title": "tree test", "session_type": "diffuse_thinking"})
        sid = r.json()["id"]
        # 2) 加几个思维树节点
        root = client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={"role": "user", "content": "主问题"},
        ).json()
        n1 = client.post(
            f"/api/chat/sessions/{sid}/messages",
            json={"role": "agent_a", "content": "分支 A", "parent_id": root["id"], "node_path": "root.0", "thought_kind": "decompose", "score": 0.7},
        ).json()
        # 3) PATCH 树
        snapshot = {
            "root_id": root["id"],
            "nodes": [
                {"id": root["id"], "content": "主问题", "children": [n1["id"]]},
                {"id": n1["id"], "content": "分支 A", "children": [], "score": 0.7},
            ],
        }
        r = client.patch(
            f"/api/chat/sessions/{sid}/tree",
            json={"tree_snapshot": snapshot, "selected_node_id": n1["id"], "status": "completed"},
        )
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        # 4) 验证 list 里 status 变 completed
        r = client.get("/api/chat/sessions?session_type=diffuse_thinking")
        for s in r.json():
            if s["id"] == sid:
                assert s["status"] == "completed"
                break

    def test_update_tree_404(self, client):
        r = client.patch(
            "/api/chat/sessions/99999/tree",
            json={"tree_snapshot": {}, "selected_node_id": 1},
        )
        assert r.status_code == 404


class TestDeleteSession:
    def test_delete_cascades_messages(self, client):
        # 1) 建 session + 加 3 条消息
        r = client.post("/api/chat/sessions", json={"title": "to delete"})
        sid = r.json()["id"]
        for i in range(3):
            client.post(
                f"/api/chat/sessions/{sid}/messages",
                json={"role": "user", "content": f"msg-{i}"},
            )
        # 2) 确认有 3 条
        r = client.get(f"/api/chat/sessions/{sid}/messages")
        assert len(r.json()) == 3
        # 3) 删 session
        r = client.delete(f"/api/chat/sessions/{sid}")
        assert r.status_code == 200
        assert r.json()["ok"] is True
        # 4) 再查 messages 返 404
        r = client.get(f"/api/chat/sessions/{sid}/messages")
        assert r.status_code == 404
        # 5) 再删返 404
        r = client.delete(f"/api/chat/sessions/{sid}")
        assert r.status_code == 404


class TestMockEngineBackwardCompat:
    """V0.7.6 抽离验证: M3Client mock 模式仍能跑, 接口签名不变"""

    def test_m3_client_chat_mock(self):
        from cycling_coach.ai.m3_client import M3Client
        c = M3Client()
        # 在测试 setup 时 M3_API_KEY='', 但 M3Client 启动时已读了 settings
        # 强制设 is_mock=True 重测
        c.is_mock = True
        r = c.chat("你是一个教练", "NP=200 IF=0.85 TSS=80 FTP=250")
        assert "节奏区" in r

    def test_m3_client_stream_chat_mock(self):
        from cycling_coach.ai.m3_client import M3Client
        c = M3Client()
        c.is_mock = True
        chunks = list(c.stream_chat("你是教练", [{"role": "user", "content": "NP=250 IF=1.1 TSS=120 FTP=260"}]))
        text = "".join(chunks)
        assert len(text) > 50
        assert "VO2max" in text or "阈值" in text

    def test_mock_engine_module_api(self):
        """mock_engine 模块的 3 个接口 + 流式"""
        from cycling_coach.ai.mock_engine import MockEngine, get_mock_engine
        m = MockEngine()
        # 1) stream_response
        t1 = "".join(m.stream_response([{"role": "user", "content": "hello"}]))
        assert len(t1) > 0
        # 2) format_kb_answer
        assert m.format_kb_answer("q", [], {}) == ""
        r = m.format_kb_answer(
            "FTP",
            [{"title": "FTP", "path": "/k", "content": "FTP 是阈值. 测试.", "snippet": "..."}],
            {},
        )
        assert "FTP" in r
        # 3) format_activity_report
        r2 = m.format_activity_report({"raw_query": "NP=200 IF=0.85"})
        assert "节奏区" in r2
        # 4) 单例
        e1 = get_mock_engine()
        e2 = get_mock_engine()
        assert e1 is e2
