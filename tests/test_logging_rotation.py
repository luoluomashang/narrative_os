"""
tests/test_logging_rotation.py — Phase 5-F3: 日志系统测试

验证日志文件时间戳命名、7 天轮转清理、correlation_id 注入。
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from narrative_os.infra.logging import (
    StructuredLogger,
    get_correlation_id,
    set_correlation_id,
)


# ------------------------------------------------------------------ #
# F3-1: 日志文件名含启动时间戳                                           #
# ------------------------------------------------------------------ #

def test_log_filename_contains_timestamp(tmp_path: Path):
    """DevServerManager 日志文件名包含启动时间戳。"""
    from narrative_os.infra.dev_server import DevServerManager

    with (
        patch("narrative_os.infra.dev_server.settings") as mock_settings,
        patch("narrative_os.infra.dev_server.atexit"),
    ):
        mock_settings.state_dir = str(tmp_path / "state")
        # 需要在临时目录中工作
        import os
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            mgr = DevServerManager()
            ts = mgr._launch_ts
            assert ts, "launch_ts 不应为空"
            # 检查日志文件存在且名字正确
            log_dir = tmp_path / "logs"
            backend_logs = list(log_dir.glob(f"backend_{ts}.log"))
            assert len(backend_logs) == 1
            frontend_logs = list(log_dir.glob(f"frontend_{ts}.log"))
            assert len(frontend_logs) == 1
        finally:
            mgr._close_logs()
            os.chdir(old_cwd)


# ------------------------------------------------------------------ #
# F3-2: 超过 7 天的日志被清理                                            #
# ------------------------------------------------------------------ #

def test_old_logs_cleaned_up(tmp_path: Path):
    """超过 max_days 天的日志文件被清理。"""
    from narrative_os.infra.dev_server import DevServerManager

    log_dir = tmp_path / "logs"
    log_dir.mkdir()

    # 创建一个"旧"日志文件（修改时间回拨 10 天）
    old_file = log_dir / "backend_20200101_000000.log"
    old_file.write_text("old log")
    old_mtime = time.time() - 10 * 86400
    import os
    os.utime(old_file, (old_mtime, old_mtime))

    # 创建一个"新"日志文件
    new_file = log_dir / "backend_29991231_235959.log"
    new_file.write_text("new log")

    with (
        patch("narrative_os.infra.dev_server.settings") as mock_settings,
        patch("narrative_os.infra.dev_server.atexit"),
    ):
        mock_settings.state_dir = str(tmp_path / "state")
        old_cwd = os.getcwd()
        os.chdir(tmp_path)
        try:
            mgr = DevServerManager()
        finally:
            mgr._close_logs()
            os.chdir(old_cwd)

    # 旧文件应被删除
    assert not old_file.exists(), "10 天前的日志应被清理"
    # 新文件应保留
    assert new_file.exists(), "新日志不应被清理"


# ------------------------------------------------------------------ #
# F3-3: JSONL 日志条目含 correlation_id                                 #
# ------------------------------------------------------------------ #

def test_correlation_id_in_jsonl(tmp_path: Path):
    """设置 correlation_id 后日志条目包含该字段。"""
    with patch("narrative_os.infra.logging.settings") as mock_settings:
        mock_settings.log_dir = str(tmp_path)
        lgr = StructuredLogger()
        lgr._log_dir = tmp_path

        cid = "test-cid-123"
        set_correlation_id(cid)
        lgr.info("test_event", extra_key="value")

        # 读取生成的 JSONL 文件
        jsonl_files = list(tmp_path.glob("narrative_*.jsonl"))
        assert len(jsonl_files) >= 1

        with jsonl_files[0].open() as f:
            for raw_line in f:
                entry = json.loads(raw_line)
                if entry.get("event") == "test_event":
                    assert entry["correlation_id"] == cid
                    assert entry["extra_key"] == "value"
                    break
            else:
                pytest.fail("未找到 test_event 日志条目")

        # 清除
        set_correlation_id("")


# ------------------------------------------------------------------ #
# F3-4: HTTP 响应头含 X-Correlation-ID                                 #
# ------------------------------------------------------------------ #

def test_api_response_has_correlation_header():
    """每个 HTTP 响应都应包含 X-Correlation-ID 头。"""
    from narrative_os.interface.api import app

    client = TestClient(app, raise_server_exceptions=False)

    # 使用一个简单的只读端点
    resp = client.get("/health")
    assert "X-Correlation-ID" in resp.headers
    cid = resp.headers["X-Correlation-ID"]
    assert len(cid) == 8  # uuid4 hex[:8]
