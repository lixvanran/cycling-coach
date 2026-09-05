"""V0.8.0: Service 层单元测试 (不依赖 HTTP)

覆盖:
1. ActivityService: list / get / RPE / 异常路径
2. ChatService: session CRUD / message / 异常路径
3. FTPService: methods / estimate / record / 异常路径
4. MLService: 模型列表 (mock 降级)
5. KBService: categories / 异常路径
6. DiaryService: 模板 / upsert / 异常路径
7. AppError: 子类化 / to_dict / 状态码映射

跑法: cd backend && ../.venv/bin/python -m pytest tests/test_services_v080.py -v
"""
from __future__ import annotations
import os
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, ".")

# 测试前: 强制无 API key + 临时 workspace
TMP = Path(tempfile.mkdtemp(prefix="cc_test_services_v080_"))
os.environ["M3_API_KEY"] = ""
os.environ["WORKSPACE_DIR"] = str(TMP)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module", autouse=True)
def _setup_module():
    """模块级 setup: 切到临时 workspace + 重建 engine + init_db"""
    from cycling_coach.config import config as cfg
    from cycling_coach.data.sqlite.database import Base, SessionLocal
    from cycling_coach.data.sqlite import models  # noqa: F401
    from sqlalchemy import create_engine

    cfg.settings.workspace_dir = str(TMP)
    new_engine = create_engine(
        f"sqlite:///{TMP}/cycling_coach.sqlite",
        connect_args={"check_same_thread": False},
    )
    cfg.engine = new_engine
    Base.metadata.create_all(new_engine)
    SessionLocal.configure(bind=new_engine)
    yield


@pytest.fixture()
def db():
    """每个 test 一个 session, 用完关闭"""
    from cycling_coach.data.sqlite.database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def seed_athlete(db):
    """默认 athlete (V0.8.0 单用户 MVP)"""
    from cycling_coach.core.profile import store as profile_store
    return profile_store.get_or_create_athlete(db)


# ============================================================
# Exception 体系
# ============================================================

class TestAppError:
    def test_base_to_dict(self):
        from cycling_coach.core.exceptions import AppError
        e = AppError("oops", code="x", status=418, foo="bar")
        d = e.to_dict()
        assert d == {"ok": False, "code": "x", "message": "oops", "foo": "bar"}
        assert e.status == 418

    def test_subclass_status_mapping(self):
        from cycling_coach.core.exceptions import (
            NotFoundError, ValidationError, ConflictError,
            ForbiddenError, UnauthorizedError,
        )
        assert NotFoundError("x").status == 404
        assert ValidationError("x").status == 422
        assert ConflictError("x").status == 409
        assert ForbiddenError("x").status == 403
        assert UnauthorizedError("x").status == 401

    def test_subclass_code_mapping(self):
        from cycling_coach.core.exceptions import (
            NotFoundError, ValidationError, ConflictError,
            ForbiddenError, UnauthorizedError,
        )
        assert NotFoundError("x").code == "not_found"
        assert ValidationError("x").code == "validation_error"
        assert ConflictError("x").code == "conflict"
        assert ForbiddenError("x").code == "forbidden"
        assert UnauthorizedError("x").code == "unauthorized"

    def test_isinstance_app_error(self):
        from cycling_coach.core.exceptions import NotFoundError, AppError
        e = NotFoundError("not here")
        assert isinstance(e, AppError)
        assert "NotFoundError" in repr(e)


# ============================================================
# ActivityService
# ============================================================

class TestActivityService:
    def test_list_empty(self, db, seed_athlete):
        from cycling_coach.core.services.activity import ActivityService, ActivityFilters
        svc = ActivityService(db)
        result = svc.list_activities(ActivityFilters())
        assert result["total"] == 0
        assert result["activities"] == []
        assert result["aggregate"]["count"] == 0

    def test_get_not_found_raises(self, db, seed_athlete):
        from cycling_coach.core.services.activity import ActivityService
        from cycling_coach.core.exceptions import NotFoundError
        svc = ActivityService(db)
        with pytest.raises(NotFoundError) as exc_info:
            svc.get_activity(99999)
        assert exc_info.value.status == 404
        assert "99999" in exc_info.value.message

    def test_delete_not_found_raises(self, db, seed_athlete):
        from cycling_coach.core.services.activity import ActivityService
        from cycling_coach.core.exceptions import NotFoundError
        svc = ActivityService(db)
        with pytest.raises(NotFoundError):
            svc.delete_activity(99999)

    def test_rpe_validation_range(self, db, seed_athlete):
        """rpe > 10 应抛 ValidationError"""
        from cycling_coach.core.services.activity import ActivityService
        from cycling_coach.core.exceptions import ValidationError
        # 先建一个活动
        from cycling_coach.data.sqlite.models import Activity
        a = Activity(
            athlete_id=seed_athlete.id,
            source="fit", start_time=datetime.now(),
            duration_s=3600, file_name="test.fit",
        )
        db.add(a); db.commit(); db.refresh(a)
        svc = ActivityService(db)
        # rpe=11 越界
        with pytest.raises(ValidationError):
            svc.update_rpe(a.id, {"rpe": 11})
        # rpe=-1 越界
        with pytest.raises(ValidationError):
            svc.update_rpe(a.id, {"rpe": -1})
        # rpe="abc" 类型错
        with pytest.raises(ValidationError):
            svc.update_rpe(a.id, {"rpe": "abc"})

    def test_rpe_valid(self, db, seed_athlete):
        from cycling_coach.core.services.activity import ActivityService
        from cycling_coach.data.sqlite.models import Activity
        a = Activity(
            athlete_id=seed_athlete.id,
            source="fit", start_time=datetime.now(),
            duration_s=3600, file_name="t.fit",
        )
        db.add(a); db.commit(); db.refresh(a)
        svc = ActivityService(db)
        result = svc.update_rpe(a.id, {"rpe": 7, "rpe_note": "正常"})
        assert result["ok"] is True
        assert result["rpe"] == 7
        assert result["rpe_note"] == "正常"

    def test_invalid_date_format_raises(self, db, seed_athlete):
        from cycling_coach.core.services.activity import ActivityService, ActivityFilters
        from cycling_coach.core.exceptions import ValidationError
        svc = ActivityService(db)
        with pytest.raises(ValidationError):
            svc.list_activities(ActivityFilters(date_from="not-a-date"))


# ============================================================
# ChatService
# ============================================================

class TestChatService:
    def test_create_and_list_session(self, db, seed_athlete):
        from cycling_coach.core.services.chat import ChatService, CreateSessionRequest
        svc = ChatService(db)
        s = svc.create_session(CreateSessionRequest(title="测试", session_type="general"))
        assert s["title"] == "测试"
        assert s["session_type"] == "general"
        assert s["status"] == "active"
        assert s["message_count"] == 0
        assert "id" in s and s["id"] > 0

        listed = svc.list_sessions()
        assert len(listed) >= 1
        assert any(x["id"] == s["id"] for x in listed)

    def test_create_invalid_type_rejected(self, db, seed_athlete):
        """Pydantic 应在校验层就拒绝"""
        from cycling_coach.core.services.chat import CreateSessionRequest
        from pydantic import ValidationError as PydValidationError
        with pytest.raises(PydValidationError):
            CreateSessionRequest(session_type="hacker")

    def test_add_and_get_messages(self, db, seed_athlete):
        from cycling_coach.core.services.chat import (
            ChatService, CreateSessionRequest, AddMessageRequest,
        )
        from cycling_coach.core.exceptions import NotFoundError
        svc = ChatService(db)
        s = svc.create_session(CreateSessionRequest())
        sid = s["id"]

        m1 = svc.add_message(sid, AddMessageRequest(role="user", content="hi"))
        m2 = svc.add_message(sid, AddMessageRequest(
            role="assistant", content="hello", parent_id=m1["id"],
            node_path="root.0", thought_kind="explore", score=0.9,
        ))
        assert m1["role"] == "user"
        assert m1["parent_id"] is None
        assert m2["parent_id"] == m1["id"]
        assert m2["node_path"] == "root.0"
        assert m2["score"] == 0.9

        msgs = svc.get_messages(sid)
        assert len(msgs) == 2
        assert msgs[0]["content"] == "hi"
        assert msgs[1]["content"] == "hello"

    def test_get_messages_404(self, db, seed_athlete):
        from cycling_coach.core.services.chat import ChatService
        from cycling_coach.core.exceptions import NotFoundError
        svc = ChatService(db)
        with pytest.raises(NotFoundError):
            svc.get_messages(99999)

    def test_delete_session_cascades(self, db, seed_athlete):
        from cycling_coach.core.services.chat import (
            ChatService, CreateSessionRequest, AddMessageRequest,
        )
        from cycling_coach.data.sqlite.models import ChatMessage
        svc = ChatService(db)
        s = svc.create_session(CreateSessionRequest())
        sid = s["id"]
        svc.add_message(sid, AddMessageRequest(role="user", content="x"))
        # cascade
        svc.delete_session(sid)
        # message 也没了
        cnt = db.query(ChatMessage).filter(ChatMessage.session_id == sid).count()
        assert cnt == 0


# ============================================================
# FTPService
# ============================================================

class TestFTPService:
    def test_methods(self, db, seed_athlete):
        from cycling_coach.core.services.ftp import FTPService
        svc = FTPService(db)
        m = svc.get_methods()
        assert "coggan_20min" in m["methods"]
        assert "auto" in m["methods"]

    def test_estimate_unknown_method(self, db, seed_athlete):
        from cycling_coach.core.services.ftp import FTPService, EstimateRequest
        from cycling_coach.core.exceptions import ValidationError
        svc = FTPService(db)
        with pytest.raises(ValidationError):
            svc.estimate_from_activity(EstimateRequest(activity_id=1, method="bogus"))

    def test_estimate_activity_not_found(self, db, seed_athlete):
        from cycling_coach.core.services.ftp import FTPService, EstimateRequest
        from cycling_coach.core.exceptions import NotFoundError
        svc = FTPService(db)
        with pytest.raises(NotFoundError):
            svc.estimate_from_activity(EstimateRequest(activity_id=99999))

    def test_record_validation(self, db, seed_athlete):
        from cycling_coach.core.services.ftp import FTPService, RecordFTPTest
        from cycling_coach.core.exceptions import ValidationError
        svc = FTPService(db)
        # ftp_w 越界
        with pytest.raises(ValidationError):
            svc.record_test(RecordFTPTest(test_date="2025-01-01", method="coggan_20min", ftp_w=10))
        # method 未知
        with pytest.raises(ValidationError):
            svc.record_test(RecordFTPTest(test_date="2025-01-01", method="nope", ftp_w=250))
        # 日期格式错
        with pytest.raises(ValidationError):
            svc.record_test(RecordFTPTest(test_date="not-a-date", method="coggan_20min", ftp_w=250))

    def test_record_and_history(self, db, seed_athlete):
        from cycling_coach.core.services.ftp import FTPService, RecordFTPTest
        from datetime import date, timedelta
        svc = FTPService(db)
        # 用近期日期 (默认 365 天窗口)
        recent = (date.today() - timedelta(days=30)).isoformat()
        t = svc.record_test(RecordFTPTest(
            test_date=recent, method="coggan_20min", ftp_w=260,
            confidence=0.85, weight_kg=70.0,
        ))
        assert t["ftp_w"] == 260
        assert t["w_per_kg"] == round(260 / 70.0, 2)
        assert t["method_label"] == "Coggan 20 分钟测试"

        hist = svc.list_history(days=365)
        assert len(hist) >= 1
        assert any(x["id"] == t["id"] for x in hist)

    def test_recommend_no_history(self, db, seed_athlete):
        from cycling_coach.core.services.ftp import FTPService
        svc = FTPService(db)
        # 测过的话, 删掉再测
        from cycling_coach.data.sqlite.models import FTPTest
        db.query(FTPTest).delete()
        db.commit()
        r = svc.recommend_next_test()
        assert r["should_test"] is True
        assert r["priority"] == "high"
        assert r["days_since"] is None


# ============================================================
# MLService
# ============================================================

class TestMLService:
    def test_list_models_empty(self, db, seed_athlete):
        from cycling_coach.core.services.ml import MLService
        svc = MLService(db)
        r = svc.list_models()
        assert r["ok"] is True
        assert r["models"] == []

    def test_register_and_activate(self, db, seed_athlete):
        from cycling_coach.core.services.ml import MLService, RegisterModelRequest, ActivateModelRequest
        svc = MLService(db)
        r = svc.register_model(RegisterModelRequest(
            task_name="ftp_predictor", version="v1-test",
            model_path="models/v1/model.joblib", model_format="joblib",
            is_active=False,
        ))
        assert r["ok"] is True
        assert r["is_active"] is False

        r2 = svc.activate_model(ActivateModelRequest(
            task_name="ftp_predictor", version="v1-test",
        ))
        assert r2["ok"] is True
        assert r2["activated"] == "ftp_predictor@v1-test"

    def test_activate_not_registered(self, db, seed_athlete):
        from cycling_coach.core.services.ml import MLService, ActivateModelRequest
        from cycling_coach.core.exceptions import NotFoundError
        svc = MLService(db)
        with pytest.raises(NotFoundError):
            svc.activate_model(ActivateModelRequest(task_name="bogus", version="v0"))


# ============================================================
# KBService
# ============================================================

class TestKBService:
    def test_categories_empty(self, db, seed_athlete):
        from cycling_coach.core.services.kb import KBService
        svc = KBService(db)
        r = svc.list_categories()
        assert r["total"] == 0
        assert r["categories"] == []

    def test_stats(self, db, seed_athlete):
        from cycling_coach.core.services.kb import KBService
        svc = KBService(db)
        s = svc.stats()
        assert s["categories"] == 0
        assert s["documents"] == 0

    def test_get_document_404(self, db, seed_athlete):
        from cycling_coach.core.services.kb import KBService
        from cycling_coach.core.exceptions import NotFoundError
        svc = KBService(db)
        with pytest.raises(NotFoundError):
            svc.get_document(99999)

    def test_get_by_path_404(self, db, seed_athlete):
        from cycling_coach.core.services.kb import KBService
        from cycling_coach.core.exceptions import NotFoundError
        svc = KBService(db)
        with pytest.raises(NotFoundError):
            svc.get_document_by_path("不存在的路径")


# ============================================================
# DiaryService
# ============================================================

class TestDiaryService:
    def test_template(self, db, seed_athlete):
        from cycling_coach.core.services.diary import DiaryService
        svc = DiaryService(db)
        t = svc.get_template()
        assert t["title"] == "训练日记模板"
        assert any(f["key"] == "training_feel" for f in t["fields"])
        assert "prompts" in t
        assert "daily_factors" in t

    def test_upsert_and_get(self, db, seed_athlete):
        from cycling_coach.core.services.diary import DiaryService, DiaryIn
        svc = DiaryService(db)
        d = date.today()
        r = svc.upsert(DiaryIn(
            date=d, training_feel=4, mood=4, sleep_h=7.5,
            sleep_quality=4, content="状态不错",
        ))
        assert r["ok"] is True
        assert r["item"]["training_feel"] == 4

        g = svc.get_by_date(d.isoformat())
        assert g["exists"] is True
        assert g["item"]["content"] == "状态不错"

    def test_upsert_partial_update(self, db, seed_athlete):
        """partial update 不应清空已有字段"""
        from cycling_coach.core.services.diary import DiaryService, DiaryIn
        svc = DiaryService(db)
        d = date.today()
        svc.upsert(DiaryIn(date=d, training_feel=3, mood=5, content="原始笔记"))
        # 只更新 mood, training_feel/content 保留
        svc.upsert(DiaryIn(date=d, mood=2))
        g = svc.get_by_date(d.isoformat())
        # mood=2 是更新的, training_feel/content 仍存在
        assert g["item"]["mood"] == 2
        assert g["item"]["content"] == "原始笔记"

    def test_invalid_date_format(self, db, seed_athlete):
        from cycling_coach.core.services.diary import DiaryService
        from cycling_coach.core.exceptions import ValidationError
        svc = DiaryService(db)
        with pytest.raises(ValidationError):
            svc.get_by_date("not-a-date")

    def test_delete_not_found(self, db, seed_athlete):
        from cycling_coach.core.services.diary import DiaryService
        from cycling_coach.core.exceptions import NotFoundError
        svc = DiaryService(db)
        with pytest.raises(NotFoundError):
            svc.delete_by_date("2020-01-01")


# ============================================================
# Services Bundle
# ============================================================

class TestServicesBundle:
    def test_bundle_includes_all_services(self, db, seed_athlete):
        """Services bundle 包含 8 个 service"""
        from cycling_coach.api.dependencies import Services
        bundle = Services(db)
        assert bundle.activity is not None
        assert bundle.chat is not None
        assert bundle.ftp is not None
        assert bundle.kb is not None
        assert bundle.training is not None
        assert bundle.ml is not None
        assert bundle.race_tactics is not None
        assert bundle.diary is not None


# ============================================================
# Exception handler (FastAPI 集成)
# ============================================================

class TestAppErrorHandler:
    def test_handler_registration(self):
        """AppError handler 应注册到 FastAPI app"""
        from fastapi.testclient import TestClient
        from cycling_coach.api.main import app

        # 加一个临时端点测异常 handler
        from cycling_coach.core.exceptions import NotFoundError

        @app.get("/_test_notfound")
        def _raise_notfound():
            raise NotFoundError("test 404", resource="test")

        c = TestClient(app)
        r = c.get("/_test_notfound")
        assert r.status_code == 404
        body = r.json()
        assert body["ok"] is False
        assert body["code"] == "not_found"
        assert body["message"] == "test 404"
        assert body["resource"] == "test"
