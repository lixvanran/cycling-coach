"""V0.8.0: ftp-predictor 真实集成 测试

测试范围:
1. 特征 20 维对齐 (跟 ftp-predictor 模型)
2. 加载真模型 + 预测
3. Conformal 区间 (P10/P50/P90)
4. 模型缺失降级 (mock fallback)
5. 端到端: /api/ml/predict/ftp 返真模型预测
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import numpy as np
import pytest


TMP = Path(tempfile.mkdtemp(prefix="cc_test_ftp_v080_"))
os.environ["M3_API_KEY"] = ""

# ftp-predictor 真实模型路径 (workspace/models/ftp_predictor/)
MODEL_DIR = Path("workspace/models/ftp_predictor")
# 找存在的版本
EXISTING_VERSIONS = [
    d.name for d in MODEL_DIR.iterdir()
    if d.is_dir() and (d / "best_model.joblib").exists()
] if MODEL_DIR.exists() else []


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module", autouse=True)
def _setup_module():
    """模块级 setup: 切到临时 workspace + 重建 engine + init_db + seed

    V0.8.0: workspace_dir 用实际 workspace (因为 model 文件在
    workspace/models/ftp_predictor/ 下, 不能在 temp 里)
    """
    from cycling_coach.config import config as cfg
    from cycling_coach.data.sqlite.database import Base
    from cycling_coach.data.sqlite import models  # noqa: F401
    from sqlalchemy import create_engine

    # 用项目的实际 workspace (因为 model 路径相对于此)
    actual_workspace = Path("workspace").resolve()
    cfg.settings.workspace_dir = str(actual_workspace)
    new_engine = create_engine(
        f"sqlite:///{TMP}/cycling_coach.sqlite",
        connect_args={"check_same_thread": False},
    )
    cfg.engine = new_engine
    Base.metadata.create_all(new_engine)

    from cycling_coach.data.sqlite.database import SessionLocal as _SL
    _SL.configure(bind=new_engine)

    from cycling_coach.data.sqlite.database import _auto_migrate, _ensure_indexes
    _auto_migrate()
    _ensure_indexes()

    # seed
    from cycling_coach.data.sqlite.database import SessionLocal
    from cycling_coach.data.sqlite.models import Athlete, Activity
    import json

    db = SessionLocal()
    try:
        a = Athlete(name="V080测试车手", ftp=270, max_hr=185, lthr=165, weight_kg=70)
        db.add(a)
        db.commit()
        db.refresh(a)

        # 14 天窗口的活动 (每天 1h 骑行, 共 14 个)
        today = datetime.now(timezone.utc).replace(tzinfo=None)
        for i in range(14):
            start = today - timedelta(days=14 - i, hours=2)
            # 模拟 zone 分布 (Coggan 7 区 + 5 区 HR)
            pz_7 = {"Z1": 600, "Z2": 1500, "Z3": 800, "Z4": 400, "Z5": 200, "Z6": 80, "Z7": 20}
            hz_5 = {"Z1": 400, "Z2": 1500, "Z3": 800, "Z4": 600, "Z5": 200}
            metrics = {
                "power_zones": pz_7,
                "hr_zones": hz_5,
                "power": {"kilojoules": 1800},
                "normalized_power": 220,
                "intensity_factor": 0.82,
                "tss": 95,
            }
            activity = Activity(
                athlete_id=a.id,
                source="fit",
                start_time=start,
                duration_s=3600,
                distance_m=35000,
                avg_power=215,
                avg_hr=152,
                metrics=metrics,
            )
            db.add(activity)
        db.commit()
    finally:
        db.close()

    # 清空 registry 缓存 (避免上轮测试的 stale handle)
    from cycling_coach.core.ml.registry import ModelRegistry
    ModelRegistry._cache.clear()

    yield
    if TMP.exists():
        shutil.rmtree(TMP, ignore_errors=True)


@pytest.fixture(scope="module")
def client():
    from cycling_coach.api.main import app
    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def db_session():
    from cycling_coach.data.sqlite.database import SessionLocal
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================
# 1) 特征 20 维对齐
# ============================================================

def test_feature_schema_20_dim():
    """V0.8.0: 12 维 → 20 维, 顺序对齐 ftp-predictor"""
    from cycling_coach.core.ml import FEATURE_SCHEMA, FEATURE_COLUMNS
    assert len(FEATURE_SCHEMA) == 20
    assert len(FEATURE_COLUMNS) == 20
    # 顺序必须跟 ftp-predictor 一致
    expected = [
        "distance", "moving_time", "average_heartrate",
        "HR Zone 1", "HR Zone 2", "HR Zone 3", "HR Zone 4", "HR Zone 5",
        "kilojoules",
        "Power Zone 1", "Power Zone 2", "Power Zone 3", "Power Zone 4",
        "Power Zone 5", "Power Zone 6", "Power Zone 7", "Power Zone 8",
        "Power Zone 9", "Power Zone 10", "Power Zone 11",
    ]
    assert FEATURE_COLUMNS == expected


def test_feature_schema_match_ftp_predictor():
    """如果 ftp-predictor 模型存在, FEATURE_COLUMNS 必须跟其 feature_cols 完全一致"""
    import joblib
    for v in EXISTING_VERSIONS:
        d = joblib.load(MODEL_DIR / v / "best_model.joblib")
        expected = d["feature_cols"]
        from cycling_coach.core.ml import FEATURE_COLUMNS
        assert FEATURE_COLUMNS == expected, (
            f"v{v}: FEATURE_COLUMNS != model.feature_cols"
        )


def test_build_feature_row_20_dim(db_session):
    """build_feature_row 必须返回 20 维, 顺序对齐 schema"""
    from cycling_coach.core.ml import build_feature_row
    from cycling_coach.data.sqlite.models import Athlete

    athlete = db_session.query(Athlete).first()
    assert athlete is not None
    values, columns = build_feature_row(db_session, athlete.id)
    assert len(values) == 20
    assert columns == list(range(20)) or len(columns) == 20  # 兼容 col 名
    # 至少要有非零值
    assert any(v > 0 for v in values), f"全是 0: {values}"


def test_build_feature_row_window_aggregated(db_session):
    """窗口聚合模式: 14d 窗口累加"""
    from cycling_coach.core.ml import build_feature_row
    from cycling_coach.core.ml.feature_pipe import FEATURE_COLUMNS
    from cycling_coach.data.sqlite.models import Athlete

    athlete = db_session.query(Athlete).first()
    values, columns = build_feature_row(db_session, athlete.id, window_days=14)
    assert len(values) == 20
    # 14 天 × 3600s = 50400s moving_time
    i_mt = FEATURE_COLUMNS.index("moving_time")
    assert values[i_mt] >= 14 * 3600 * 0.9  # 至少 90%


def test_build_feature_row_single_activity(db_session):
    """单活动模式: 用该活动 metrics"""
    from cycling_coach.core.ml import build_feature_row
    from cycling_coach.core.ml.feature_pipe import FEATURE_COLUMNS
    from cycling_coach.data.sqlite.models import Athlete, Activity

    athlete = db_session.query(Athlete).first()
    activity = (
        db_session.query(Activity)
        .filter(Activity.athlete_id == athlete.id)
        .order_by(Activity.start_time.desc())
        .first()
    )
    values, columns = build_feature_row(db_session, athlete.id, activity_id=activity.id)
    assert len(values) == 20


# ============================================================
# 2) 真模型加载 + 预测
# ============================================================

@pytest.mark.skipif(
    not EXISTING_VERSIONS,
    reason="ftp-predictor 模型未拉取, 跑 tools/sync_ftp_model.sh latest",
)
def test_load_real_model(db_session):
    """加载 ftp-predictor 真实模型"""
    from cycling_coach.core.ml.registry import ModelRegistry

    version = _register_real_model(db_session)

    # 加载
    handle = ModelRegistry.load("ftp_predictor")
    assert handle.model_format == "joblib"
    assert handle.metadata.get("cv_mae_mean") == 5.13 or handle.metadata.get("cv_mae_mean") is None
    # 跑一次预测
    X = np.zeros((1, 20), dtype=np.float32)
    X[0, 0] = 300000  # distance (m, 300km)
    X[0, 1] = 36000   # moving_time (s, 10h)
    X[0, 2] = 150     # average_heartrate
    X[0, 8] = 14000   # kilojoules
    X[0, 3] = 4000    # HR Zone 1
    X[0, 4] = 15000   # HR Zone 2
    X[0, 5] = 8000    # HR Zone 3
    X[0, 6] = 4000    # HR Zone 4
    X[0, 7] = 500     # HR Zone 5
    # Power Zone 1-11 一些值
    for i in range(11):
        X[0, 9 + i] = 500 + i * 100

    point = handle.predict(X)
    assert 50 < point < 400, f"FTP 预测值 {point}W 不在合理范围"


@pytest.mark.skipif(
    not EXISTING_VERSIONS,
    reason="ftp-predictor 模型未拉取",
)
def _register_real_model(db_session, version=None):
    """Helper: 注册 ftp-predictor 真模型到 MLModelMeta, 设为 active"""
    import joblib
    from cycling_coach.core.ml.registry import ModelRegistry
    from cycling_coach.data.sqlite.models import MLModelMeta
    from datetime import datetime as _dt

    if version is None:
        version = EXISTING_VERSIONS[0]
    # 清掉 + 注册
    db_session.query(MLModelMeta).filter(
        MLModelMeta.task_name == "ftp_predictor"
    ).delete()
    db_session.commit()
    meta = MLModelMeta(
        task_name="ftp_predictor",
        version=version,
        model_path=f"models/ftp_predictor/{version}/best_model.joblib",
        model_format="joblib",
        training_metrics={"cv_mae_mean": 5.13, "cv_r2_mean": 0.95},
        feature_columns=joblib.load(MODEL_DIR / version / "best_model.joblib")["feature_cols"],
        feature_schema={},
        is_active=True,
    )
    db_session.add(meta)
    db_session.commit()
    ModelRegistry._cache.clear()
    return version


def test_conformal_interval(db_session):
    """Conformal 校准区间 (P10/P50/P90)"""
    from cycling_coach.core.ml.registry import ModelRegistry

    _register_real_model(db_session)

    handle = ModelRegistry.load("ftp_predictor")
    assert handle.has_conformal(), "Conformal 应该已加载"

    X = np.zeros((1, 20), dtype=np.float32)
    X[0, 0] = 300000
    X[0, 1] = 36000
    X[0, 2] = 150
    X[0, 8] = 14000

    point, lower, upper = handle.predict_interval(X, coverage=0.8)
    # Conformal 区间特性: lower <= point <= upper, 区间宽 ~10-100W
    assert lower < point < upper, f"区间错: {lower} < {point} < {upper}"
    assert 10 < (upper - lower) < 200, f"区间宽 {upper - lower}W 不合理"


# ============================================================
# 3) 模型缺失降级 (mock fallback)
# ============================================================

def test_mock_fallback_when_no_model(db_session, client):
    """没注册模型时 → MockFTPModel 兜底"""
    from cycling_coach.data.sqlite.models import MLModelMeta
    from cycling_coach.core.ml.registry import ModelRegistry

    # 确保没有激活模型
    db_session.query(MLModelMeta).filter(
        MLModelMeta.task_name == "ftp_predictor",
        MLModelMeta.is_active.is_(True),
    ).update({"is_active": False})
    db_session.commit()
    ModelRegistry._cache.clear()

    r = client.post("/api/ml/predict/ftp", json={})
    assert r.status_code == 200, f"expected 200, got {r.status_code}: {r.text}"
    d = r.json()
    assert d["ok"] is True
    assert d["model_format"] == "mock"
    assert d["model_version"] == "mock-v0"
    assert 100 < d["predicted_ftp"] < 400
    assert d["lower_80"] < d["predicted_ftp"] < d["upper_80"]
    assert d["feature_count"] == 20
    assert d["model_has_conformal"] is False


def test_model_not_found_falls_back_to_mock(db_session, client):
    """ModelNotFoundError → 降级 mock (跟 V0.7.8 行为一致)"""
    from cycling_coach.data.sqlite.models import MLModelMeta
    from cycling_coach.core.ml.registry import ModelRegistry

    # 注册一个指向不存在路径的激活模型
    db_session.query(MLModelMeta).filter(
        MLModelMeta.task_name == "ftp_predictor",
        MLModelMeta.is_active.is_(True),
    ).update({"is_active": False})
    db_session.commit()
    ModelRegistry._cache.clear()

    meta = MLModelMeta(
        task_name="ftp_predictor",
        version="nonexistent",
        model_path="models/nonexistent/missing.joblib",
        model_format="joblib",
        feature_columns=[
            "distance", "moving_time", "average_heartrate",
            "HR Zone 1", "HR Zone 2", "HR Zone 3", "HR Zone 4", "HR Zone 5",
            "kilojoules",
            "Power Zone 1", "Power Zone 2", "Power Zone 3", "Power Zone 4",
            "Power Zone 5", "Power Zone 6", "Power Zone 7", "Power Zone 8",
            "Power Zone 9", "Power Zone 10", "Power Zone 11",
        ],
        is_active=True,
    )
    db_session.add(meta)
    db_session.commit()
    ModelRegistry._cache.clear()

    r = client.post("/api/ml/predict/ftp", json={})
    # 模型文件找不到, 应降级 mock (200)
    assert r.status_code == 200
    d = r.json()
    assert d["model_format"] == "mock"


# ============================================================
# 4) 端到端: predict 端点
# ============================================================

def test_predict_ftp_endpoint_returns_20_dim(client):
    """predict 端点返回 20 维特征计数"""
    r = client.post("/api/ml/predict/ftp", json={})
    assert r.status_code == 200
    d = r.json()
    assert d["feature_count"] == 20
    assert d["data_window"]  # 非空


@pytest.mark.skipif(
    not EXISTING_VERSIONS,
    reason="ftp-predictor 模型未拉取",
)
def test_predict_ftp_endpoint_with_real_model(db_session, client):
    """端到端: 激活真模型后, predict 端点用真模型 + Conformal"""
    from cycling_coach.core.ml.registry import ModelRegistry

    version = _register_real_model(db_session)

    r = client.post("/api/ml/predict/ftp", json={})
    assert r.status_code == 200
    d = r.json()
    # 真模型
    assert d["model_format"] == "joblib"
    assert d["model_version"] == version
    assert d["model_has_conformal"] is True
    assert d["feature_count"] == 20
    # 区间必须真 Conformal, 不是 mock 的 ±10W
    interval_width = d["upper_80"] - d["lower_80"]
    assert interval_width > 15, f"区间宽 {interval_width}W 太小, 可能不是 Conformal"
    # 真模型预测 (非 mock 250-258 范围)
    # ftp-predictor 训练分布: FTP 52-250, 当前值取决于输入
    assert 50 < d["predicted_ftp"] < 400


# ============================================================
# 5) 导出 CLI
# ============================================================

def test_export_features_cli_exists():
    """CLI 文件存在"""
    from pathlib import Path
    cli = Path("cycling_coach/cli/export_features.py")
    assert cli.exists()


def test_export_features_cli_imports():
    """CLI 可 import"""
    from cycling_coach.cli.export_features import export_features
    assert callable(export_features)
