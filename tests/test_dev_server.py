"""
tests/test_dev_server.py — 阶段 0：DevServerManager 单元测试
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import psutil
import pytest

from narrative_os.infra.dev_server import DevServerManager, PortInUseError


# ------------------------------------------------------------------ #
# 辅助工具                                                              #
# ------------------------------------------------------------------ #

def _bind_port(port: int) -> socket.socket:
    """绑定端口，阻止其它进程使用，返回 socket（由测试负责关闭）。"""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", port))
    s.listen(1)
    return s


# ------------------------------------------------------------------ #
# 测试 1 — 端口空闲时直接返回                                            #
# ------------------------------------------------------------------ #

def test_find_available_port_free(tmp_path):
    """空闲端口 preferred 时直接返回 preferred。"""
    manager = DevServerManager.__new__(DevServerManager)
    manager._state_dir = tmp_path
    manager._pid_file = tmp_path / "dev.pid"
    manager._backend_proc = None
    manager._frontend_proc = None

    # 找一个基本空闲的端口（使用高端口号降低冲突概率）
    preferred = 19877
    # 确保端口确实空闲
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            s.bind(("127.0.0.1", preferred))
            available = True
        except OSError:
            available = False

    if available:
        result = manager._find_available_port(preferred)
        assert result == preferred


# ------------------------------------------------------------------ #
# 测试 2 — preferred 端口被占用时递增                                    #
# ------------------------------------------------------------------ #

def test_find_available_port_occupied(tmp_path):
    """preferred 端口被占用时返回 preferred + 1。"""
    manager = DevServerManager.__new__(DevServerManager)
    manager._state_dir = tmp_path
    manager._pid_file = tmp_path / "dev.pid"
    manager._backend_proc = None
    manager._frontend_proc = None

    preferred = 19901
    sock = _bind_port(preferred)
    try:
        result = manager._find_available_port(preferred, range_size=5)
        assert result > preferred
        assert result < preferred + 5
    finally:
        sock.close()


# ------------------------------------------------------------------ #
# 测试 3 — 无进程占用端口时返回 None                                     #
# ------------------------------------------------------------------ #

def test_check_port_owner_none(tmp_path):
    """未被占用的端口应返回 None。"""
    manager = DevServerManager.__new__(DevServerManager)
    manager._state_dir = tmp_path
    manager._pid_file = tmp_path / "dev.pid"
    manager._backend_proc = None
    manager._frontend_proc = None

    # 使用高端口号降低冲突概率，且不绑定
    result = manager._check_port_owner(19999)
    assert result is None


# ------------------------------------------------------------------ #
# 测试 4 — PID 文件读写                                                  #
# ------------------------------------------------------------------ #

def test_write_read_pid_file(tmp_path):
    """写入 PID 文件后应能正确读取。"""
    manager = DevServerManager.__new__(DevServerManager)
    manager._state_dir = tmp_path
    manager._pid_file = tmp_path / "dev.pid"
    manager._backend_proc = None
    manager._frontend_proc = None

    data = {"backend_pid": 12345, "backend_port": 8000, "frontend_pid": 9999, "frontend_port": 5173}
    manager._write_pid_file(data)
    result = manager._read_pid_file()

    assert result == data


# ------------------------------------------------------------------ #
# 测试 5 — cleanup 调用 terminate 和 kill                               #
# ------------------------------------------------------------------ #

def test_cleanup_terminates_procs(tmp_path):
    """_cleanup() 应先调用 terminate，超时后调用 kill。"""
    manager = DevServerManager.__new__(DevServerManager)
    manager._state_dir = tmp_path
    manager._pid_file = tmp_path / "dev.pid"

    # 模拟 backend 进程（terminate 后 wait 超时，需要 kill）
    mock_backend = MagicMock(spec=subprocess.Popen)
    mock_backend.poll.return_value = None  # 仍在运行
    mock_backend.wait.side_effect = [subprocess.TimeoutExpired(cmd="test", timeout=3), None]

    # 模拟 frontend 进程（terminate 后正常退出）
    mock_frontend = MagicMock(spec=subprocess.Popen)
    mock_frontend.poll.return_value = None
    mock_frontend.wait.return_value = 0

    manager._backend_proc = mock_backend
    manager._frontend_proc = mock_frontend

    # _wait_port_free / _read_pid_file mock（避免真实 I/O）
    manager._read_pid_file = MagicMock(return_value=None)
    manager._delete_pid_file = MagicMock()

    manager._cleanup()

    mock_backend.terminate.assert_called_once()
    mock_backend.kill.assert_called_once()
    mock_frontend.terminate.assert_called_once()


# ------------------------------------------------------------------ #
# 测试 6 — 孤儿 PID 文件：进程不存在时自动清理                            #
# ------------------------------------------------------------------ #

def test_stale_pid_file_detection(tmp_path):
    """PID 文件中的进程不存在时，_check_stale_pids() 应自动清理文件。"""
    manager = DevServerManager.__new__(DevServerManager)
    manager._state_dir = tmp_path
    manager._pid_file = tmp_path / "dev.pid"
    manager._backend_proc = None
    manager._frontend_proc = None

    # 写入一个必然不存在的高 PID
    data = {
        "backend_pid": 2**22 - 1,   # 极大的 PID，几乎不可能存在
        "backend_port": 8001,
        "frontend_pid": 2**22 - 2,
        "frontend_port": 5174,
    }
    manager._write_pid_file(data)

    with patch("psutil.pid_exists", return_value=False):
        manager._check_stale_pids()

    # PID 文件应已被清理
    assert not manager._pid_file.exists()


# ------------------------------------------------------------------ #
# 测试 7 — find_available_port 在整个范围都被占用时抛出异常              #
# ------------------------------------------------------------------ #

def test_find_available_port_raises_when_range_full(tmp_path):
    """整个扫描范围都被占用时应抛出 PortInUseError。"""
    manager = DevServerManager.__new__(DevServerManager)
    manager._state_dir = tmp_path
    manager._pid_file = tmp_path / "dev.pid"
    manager._backend_proc = None
    manager._frontend_proc = None

    with patch("socket.socket") as mock_socket_cls:
        mock_sock = MagicMock()
        mock_sock.__enter__ = MagicMock(return_value=mock_sock)
        mock_sock.__exit__ = MagicMock(return_value=False)
        mock_sock.bind.side_effect = OSError("Address in use")
        mock_socket_cls.return_value = mock_sock

        with pytest.raises(PortInUseError):
            manager._find_available_port(20000, range_size=3)
