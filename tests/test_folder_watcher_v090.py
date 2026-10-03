"""V0.9.0 Inbox folder watcher — 单元 + 集成测试

不依赖真实 FIT 文件, 覆盖:
- 平台路径推导
- 注册表读写 / dedup
- 文件稳定性检查
- _ingest_one 白名单 (扩展名 / 大小限制 / sha256 dedup)
- _parse_ext_settings
"""
from __future__ import annotations
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cycling_coach.core.sync.folder_watcher import (
    ProcessedRegistry,
    compute_sha256,
    default_inbox_dir,
    default_registry_path,
    pid_file_path,
    log_file_path,
    _platform_data_dir,
    _parse_ext_settings,
    wait_until_stable,
    _ingest_one,
)
from cycling_coach.core.sync.folder_watcher import IngestResult


# =============== 平台路径 ===============

class TestPlatformPaths:
    def test_platform_data_dir_returns_str(self):
        p = _platform_data_dir()
        assert isinstance(p, Path)
        # 包含 app 名称
        assert "cycling-coach" in str(p)

    def test_default_inbox_under_data_dir(self):
        inbox = default_inbox_dir()
        data = _platform_data_dir()
        assert str(inbox).startswith(str(data))
        assert inbox.name == "inbox"

    def test_default_registry_under_data_dir(self):
        reg = default_registry_path()
        data = _platform_data_dir()
        assert str(reg).startswith(str(data))
        assert reg.name == "processed.json"

    def test_pid_log_files_under_data_dir(self):
        for f in (pid_file_path(), log_file_path()):
            assert str(f).startswith(str(_platform_data_dir()))

    def test_env_override_inbox(self, monkeypatch, tmp_path):
        custom = tmp_path / "my-inbox"
        monkeypatch.setenv("CYCLING_COACH_INBOX", str(custom))
        assert default_inbox_dir() == custom.resolve()

    def test_env_xdg_data_home(self, monkeypatch, tmp_path):
        custom = tmp_path / "xdg-data"
        monkeypatch.setenv("XDG_DATA_HOME", str(custom))
        if not os.environ.get("APPDATA"):  # Windows 跳过
            p = _platform_data_dir()
            assert str(p).startswith(str(custom.resolve()))


# =============== sha256 + 稳定性 ===============

class TestHashAndStable:
    def test_compute_sha256(self, tmp_path):
        f = tmp_path / "test.fit"
        f.write_bytes(b"hello world")
        h = compute_sha256(f)
        assert len(h) == 64
        assert h == compute_sha256(f)  # 幂等

    def test_compute_sha256_different_content(self, tmp_path):
        a = tmp_path / "a"
        b = tmp_path / "b"
        a.write_bytes(b"foo")
        b.write_bytes(b"bar")
        assert compute_sha256(a) != compute_sha256(b)

    def test_wait_until_stable_immediate(self, tmp_path):
        f = tmp_path / "stable.fit"
        f.write_bytes(b"x" * 100)
        assert wait_until_stable(f, polls=2, interval_ms=10) is True

    def test_wait_until_stable_missing(self, tmp_path):
        f = tmp_path / "missing.fit"
        assert wait_until_stable(f, polls=2, interval_ms=200) is False


# =============== 注册表 ===============

class TestProcessedRegistry:
    def test_load_empty(self, tmp_path):
        reg = ProcessedRegistry(path=tmp_path / "reg.json")
        reg.load()
        assert reg._data == {}

    def test_save_and_load(self, tmp_path):
        path = tmp_path / "reg.json"
        reg = ProcessedRegistry(path=path)
        reg.mark_processed("abc123", "/path/to/file.fit")
        reg.save()
        assert path.exists()

        reg2 = ProcessedRegistry(path=path)
        reg2.load()
        assert reg2.is_processed("abc123")

    def test_is_processed_false(self, tmp_path):
        reg = ProcessedRegistry(path=tmp_path / "reg.json")
        reg.load()
        assert not reg.is_processed("not-in-reg")

    def test_save_only_when_dirty(self, tmp_path):
        path = tmp_path / "reg.json"
        reg = ProcessedRegistry(path=path)
        reg.save()
        assert not path.exists()  # 空 + 未 dirty → 不写
        reg.mark_processed("x", "/y")
        reg.save()
        assert path.exists()

    def test_cleanup_orphan(self, tmp_path):
        path = tmp_path / "reg.json"
        reg = ProcessedRegistry(path=path)
        reg.mark_processed("keep1", "/a")
        reg.mark_processed("orphan1", "/b")
        reg.mark_processed("orphan2", "/c")
        n = reg.cleanup_orphan({"keep1"})
        assert n == 2
        assert reg.is_processed("keep1")
        assert not reg.is_processed("orphan1")

    def test_corrupt_json_resets(self, tmp_path):
        path = tmp_path / "reg.json"
        path.write_text("not valid json {")
        reg = ProcessedRegistry(path=path)
        reg.load()
        assert reg._data == {}


# =============== 扩展名解析 ===============

class TestParseExtensions:
    def test_default_extensions(self, monkeypatch):
        monkeypatch.setattr("cycling_coach.core.sync.folder_watcher.settings", MagicMock(inbox_extensions=".fit,.tcx,.csv"))
        assert _parse_ext_settings() == {".fit", ".tcx", ".csv"}

    def test_lowercase_normalization(self, monkeypatch):
        monkeypatch.setattr(
            "cycling_coach.core.sync.folder_watcher.settings",
            MagicMock(inbox_extensions=".FIT,.TCX"),
        )
        assert _parse_ext_settings() == {".fit", ".tcx"}

    def test_extra_spaces(self, monkeypatch):
        monkeypatch.setattr(
            "cycling_coach.core.sync.folder_watcher.settings",
            MagicMock(inbox_extensions=" .fit , .tcx , "),
        )
        assert _parse_ext_settings() == {".fit", ".tcx"}

    def test_empty_uses_default(self, monkeypatch):
        monkeypatch.setattr(
            "cycling_coach.core.sync.folder_watcher.settings",
            MagicMock(inbox_extensions=""),
        )
        assert _parse_ext_settings() == {".fit", ".tcx", ".csv"}


# =============== _ingest_one (用 mock 隔离 DB) ===============

class TestIngestOne:
    @pytest.mark.asyncio
    async def test_skipped_wrong_extension(self, tmp_path):
        f = tmp_path / "bad.txt"
        f.write_bytes(b"hello")
        reg = ProcessedRegistry(path=tmp_path / "reg.json")
        reg.load()
        result = await _ingest_one(f, registry=reg)
        assert result.status == "skipped"
        assert "扩展名" in result.detail

    @pytest.mark.asyncio
    async def test_skipped_too_large(self, tmp_path, monkeypatch):
        # 用 monkeypatch 把 max_file_mb 设到 0
        from cycling_coach.core.sync import folder_watcher
        monkeypatch.setattr(
            folder_watcher.settings, "inbox_max_file_mb", 0
        )
        monkeypatch.setattr(
            folder_watcher.settings, "inbox_extensions", ".fit,.tcx,.csv"
        )
        f = tmp_path / "big.fit"
        f.write_bytes(b"x" * 100)
        reg = ProcessedRegistry(path=tmp_path / "reg.json")
        reg.load()
        result = await _ingest_one(f, registry=reg)
        assert result.status == "skipped"
        assert "限制" in result.detail

    @pytest.mark.asyncio
    async def test_duplicate_via_registry(self, tmp_path, monkeypatch):
        from cycling_coach.core.sync import folder_watcher
        monkeypatch.setattr(
            folder_watcher.settings, "inbox_stable_polls", 1
        )
        monkeypatch.setattr(
            folder_watcher.settings, "inbox_poll_interval_ms", 10
        )
        monkeypatch.setattr(
            folder_watcher.settings, "inbox_max_file_mb", 50
        )
        monkeypatch.setattr(
            folder_watcher.settings, "inbox_extensions", ".fit,.tcx,.csv"
        )
        f = tmp_path / "dup.fit"
        f.write_bytes(b"abcd1234")
        reg = ProcessedRegistry(path=tmp_path / "reg.json")
        reg.load()
        # 预先标记为已处理
        sha = compute_sha256(f)
        reg.mark_processed(sha, str(f))

        result = await _ingest_one(f, registry=reg)
        assert result.status == "duplicate"
        assert result.sha256 == sha  # hash 字段带回了实际值
        assert "已处理" in result.detail or "跳过" in result.detail

    @pytest.mark.asyncio
    async def test_missing_file(self, tmp_path, monkeypatch):
        from cycling_coach.core.sync import folder_watcher
        monkeypatch.setattr(
            folder_watcher.settings, "inbox_extensions", ".fit,.tcx,.csv"
        )
        f = tmp_path / "nonexistent.fit"
        reg = ProcessedRegistry(path=tmp_path / "reg.json")
        reg.load()
        result = await _ingest_one(f, registry=reg)
        # wait_until_stable → 文件不存在 → False → failed
        assert result.status == "failed"


# =============== CLI dispatch smoke test ===============

class TestCLI:
    def test_help(self):
        from cycling_coach.cli.folder_watch import main
        with pytest.raises(SystemExit) as e:
            # 不带参数应要求 subcommand
            main()
        # argparse 失败也是 SystemExit(2) 或 0 (--help)
        assert e.value.code in (0, 2)