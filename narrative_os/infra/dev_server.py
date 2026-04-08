"""
infra/dev_server.py — 一键开发服务器管理器

负责启动/停止 FastAPI 后端（uvicorn）和 Vue 前端（vite），
处理端口冲突、孤儿进程检测，以及 Ctrl+C 退出时的自动清理。
"""

from __future__ import annotations

import atexit
import json
import os
import platform
import signal
import socket
import subprocess
import sys
import time
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

import psutil

from narrative_os.infra.config import settings


class PortInUseError(Exception):
    """端口被占用且用户拒绝处理时抛出。"""


class DevServerManager:
    """管理后端和前端子进程的完整生命周期。"""

    def __init__(self) -> None:
        self._state_dir = Path(settings.state_dir)
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._pid_file = self._state_dir / "dev.pid"
        self._backend_proc: subprocess.Popen | None = None
        self._frontend_proc: subprocess.Popen | None = None
        # 日志目录
        self._log_dir = Path("logs")
        self._log_dir.mkdir(parents=True, exist_ok=True)
        self._launch_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._backend_log = open(  # noqa: SIM115
            self._log_dir / f"backend_{self._launch_ts}.log",
            "a", encoding="utf-8", buffering=1,
        )
        self._frontend_log = open(  # noqa: SIM115
            self._log_dir / f"frontend_{self._launch_ts}.log",
            "a", encoding="utf-8", buffering=1,
        )
        self._cleanup_old_logs()
        atexit.register(self._cleanup)
        atexit.register(self._close_logs)

    def _cleanup_old_logs(self, max_days: int = 7) -> None:
        """删除超过 max_days 天的日志文件。"""
        cutoff = time.time() - max_days * 86400
        for pattern in ("backend_*.log", "frontend_*.log"):
            for f in self._log_dir.glob(pattern):
                try:
                    if f.stat().st_mtime < cutoff:
                        f.unlink(missing_ok=True)
                except OSError:
                    pass

    def _close_logs(self) -> None:
        """关闭日志文件句柄。"""
        for f in (self._backend_log, self._frontend_log):
            try:
                f.close()
            except Exception:
                pass

    def _stream_logs(
        self,
        prefix: str,
        pipe: Any,
        log_file: Any,
    ) -> None:
        """
        后台线程：逐行读取子进程输出。
        - 全部写入对应日志文件（logs/backend.log / logs/frontend.log）
        - 仅 ERROR / WARNING / CRITICAL 行打印到终端
        prefix 示例： "[Backend]" / "[Frontend]"
        """
        _SHOW_KEYWORDS = ("error", "warning", "critical", "exception", "traceback", "attributeerror", "valueerror", "typeerror", "runtimeerror")
        try:
            for raw in iter(pipe.readline, b""):
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    line = repr(raw)
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_file.write(f"{ts}  {prefix}  {line}\n")
                # 只将错误/警告行输出到终端
                if any(kw in line.lower() for kw in _SHOW_KEYWORDS):
                    short_ts = ts[11:]  # HH:MM:SS
                    print(f"  {short_ts}  {prefix}  {line}", flush=True)
        except Exception:
            pass
        finally:
            try:
                pipe.close()
            except Exception:
                pass

    def _start_log_thread(self, prefix: str, proc: subprocess.Popen, log_file: Any) -> None:
        """为子进程启动一个守护日志线程。"""
        if proc.stdout is None:
            return
        t = threading.Thread(
            target=self._stream_logs,
            args=(prefix, proc.stdout, log_file),
            daemon=True,
        )
        t.start()

    # ------------------------------------------------------------------ #
    # 端口工具                                                              #
    # ------------------------------------------------------------------ #

    def _find_available_port(self, preferred: int, range_size: int = 20) -> int:
        """从 preferred 开始扫描，返回第一个可用端口（未被占用）。"""
        for port in range(preferred, preferred + range_size):
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                try:
                    s.bind(("127.0.0.1", port))
                    return port
                except OSError:
                    continue
        raise PortInUseError(
            f"无法在 {preferred}~{preferred + range_size - 1} 范围内找到可用端口"
        )

    def _check_port_owner(self, port: int) -> tuple[int, str] | None:
        """
        检查占用指定端口的进程。
        返回 (pid, process_name) 或 None（未被占用）。
        跨平台：Windows 和 Unix 均支持。
        """
        if platform.system() == "Windows":
            # Windows: 通过 netstat 解析
            try:
                result = subprocess.run(
                    ["netstat", "-ano"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                for line in result.stdout.splitlines():
                    # 格式: TCP  0.0.0.0:8000  ...  LISTENING  1234
                    if f":{port}" in line and "LISTENING" in line:
                        parts = line.strip().split()
                        pid = int(parts[-1])
                        try:
                            name = psutil.Process(pid).name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            name = "unknown"
                        return (pid, name)
            except (subprocess.TimeoutExpired, ValueError, IndexError):
                pass
        else:
            # Unix: 通过 psutil.net_connections()
            try:
                for conn in psutil.net_connections(kind="inet"):
                    if (
                        conn.laddr
                        and conn.laddr.port == port
                        and conn.status == psutil.CONN_LISTEN
                    ):
                        pid = conn.pid
                        if pid is None:
                            continue
                        try:
                            name = psutil.Process(pid).name()
                        except (psutil.NoSuchProcess, psutil.AccessDenied):
                            name = "unknown"
                        return (pid, name)
            except (psutil.AccessDenied, AttributeError):
                pass
        return None

    # ------------------------------------------------------------------ #
    # PID 文件                                                              #
    # ------------------------------------------------------------------ #

    def _read_pid_file(self) -> dict[str, Any] | None:
        """读取 PID 文件，返回 dict 或 None（文件不存在/损坏）。"""
        if not self._pid_file.exists():
            return None
        try:
            return json.loads(self._pid_file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _write_pid_file(self, data: dict[str, Any]) -> None:
        """将 PID 信息写入文件。"""
        self._pid_file.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _delete_pid_file(self) -> None:
        """删除 PID 文件（若存在）。"""
        if self._pid_file.exists():
            self._pid_file.unlink(missing_ok=True)

    # ------------------------------------------------------------------ #
    # 孤儿进程检测                                                          #
    # ------------------------------------------------------------------ #

    def _check_stale_pids(self) -> None:
        """
        检查 PID 文件中的孤儿进程。
        若发现存活进程占用目标端口，通过 Rich 或 input() 提示用户三选一：
          1 → 杀掉残留  2 → 中止启动  3 → 自动换端口（调用方处理）
        """
        data = self._read_pid_file()
        if not data:
            return

        stale_pids: list[tuple[int, int, str]] = []  # (pid, port, role)
        for role in ("backend", "frontend"):
            pid = data.get(f"{role}_pid")
            port = data.get(f"{role}_port")
            if pid and port and psutil.pid_exists(pid):
                owner = self._check_port_owner(port)
                if owner and owner[0] == pid:
                    stale_pids.append((pid, port, role))

        if not stale_pids:
            # 进程已不存在，清理残留 PID 文件
            self._delete_pid_file()
            return

        print(
            f"\n[警告] 检测到 {len(stale_pids)} 个残留进程（上次未正常退出）："
        )
        for pid, port, role in stale_pids:
            try:
                name = psutil.Process(pid).name()
            except psutil.NoSuchProcess:
                name = "unknown"
            print(f"  {role}: PID={pid} ({name}) 占用端口 {port}")

        print("\n请选择操作：")
        print("  1 - 杀掉残留进程并继续")
        print("  2 - 中止启动")
        print("  3 - 跳过（自动寻找新端口）")

        try:
            choice = input("请输入选择 [1/2/3]: ").strip()
        except (EOFError, KeyboardInterrupt):
            choice = "2"

        if choice == "1":
            for pid, port, role in stale_pids:
                try:
                    p = psutil.Process(pid)
                    p.terminate()
                    try:
                        p.wait(timeout=3)
                    except psutil.TimeoutExpired:
                        p.kill()
                    print(f"  已终止 {role} PID {pid}")
                except psutil.NoSuchProcess:
                    pass
            self._delete_pid_file()
        elif choice == "2":
            print("已中止。")
            sys.exit(0)
        else:
            # option 3: 调用方会用 _find_available_port 自动换端口
            self._delete_pid_file()

    # ------------------------------------------------------------------ #
    # 清理                                                                  #
    # ------------------------------------------------------------------ #

    def _cleanup(self) -> None:
        """
        终止所有子进程并等待端口释放。
        策略：SIGTERM → 3s 宽限 → SIGKILL。
        """
        procs: list[tuple[str, subprocess.Popen]] = []
        if self._backend_proc is not None:
            procs.append(("backend", self._backend_proc))
        if self._frontend_proc is not None:
            procs.append(("frontend", self._frontend_proc))

        if not procs:
            return

        print("\n正在清理开发服务器...")
        for role, proc in procs:
            if proc.poll() is None:  # 仍在运行
                try:
                    proc.terminate()
                except OSError:
                    pass

        # 等待 3s 宽限期
        deadline = time.time() + 3.0
        for role, proc in procs:
            remaining = max(0.0, deadline - time.time())
            try:
                proc.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                try:
                    proc.kill()
                    proc.wait(timeout=2)
                except OSError:
                    pass

        # 验证端口释放（最多等 5s）
        data = self._read_pid_file()
        if data:
            for role in ("backend", "frontend"):
                port = data.get(f"{role}_port")
                if port:
                    self._wait_port_free(port, max_wait=5)

        self._backend_proc = None
        self._frontend_proc = None
        self._delete_pid_file()
        print("清理完成。")

    def _wait_port_free(self, port: int, max_wait: float = 5.0) -> bool:
        """轮询直到端口释放或超时，返回是否成功。"""
        deadline = time.time() + max_wait
        while time.time() < deadline:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                try:
                    s.bind(("127.0.0.1", port))
                    return True
                except OSError:
                    time.sleep(0.3)
        return False

    def _kill_port(self, port: int) -> None:
        """
        强制释放端口。
        若为自身残留进程直接 kill；若为外部进程，需二次确认。
        """
        owner = self._check_port_owner(port)
        if owner is None:
            return
        pid, name = owner
        own_pid = os.getpid()

        if pid == own_pid or pid in {
            p.pid for p in (
                [self._backend_proc, self._frontend_proc]
                if self._backend_proc or self._frontend_proc
                else []
            )
        }:
            # 自身残留
            try:
                psutil.Process(pid).kill()
            except psutil.NoSuchProcess:
                pass
        else:
            print(f"端口 {port} 被外部进程占用：PID={pid}, 名称={name}")
            try:
                confirm = input("是否强制终止该进程？[y/N]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                confirm = "n"
            if confirm == "y":
                try:
                    psutil.Process(pid).kill()
                except psutil.NoSuchProcess:
                    pass
            else:
                raise PortInUseError(f"端口 {port} 被 {name}(PID={pid}) 占用，用户拒绝终止")

    # ------------------------------------------------------------------ #
    # 启动子进程                                                            #
    # ------------------------------------------------------------------ #

    def start_backend(self, host: str, port: int) -> subprocess.Popen:
        """启动 uvicorn 后端。"""
        cmd = [
            sys.executable, "-m", "uvicorn",
            "narrative_os.interface.api:app",
            "--host", host,
            "--port", str(port),
            "--reload",
        ]
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._backend_proc = proc
        self._start_log_thread("[Backend]", proc, self._backend_log)
        return proc

    def start_frontend(self, port: int, api_port: int) -> subprocess.Popen:
        """启动 vite 前端（在 narrative_os/frontend/ 目录下）。"""
        frontend_dir = Path(__file__).resolve().parents[2] / "frontend"
        env = os.environ.copy()
        env["VITE_API_PORT"] = str(api_port)
        cmd = ["pnpm", "dev", "--port", str(port)]
        if platform.system() == "Windows":
            cmd = ["pnpm.cmd", "dev", "--port", str(port)]
        proc = subprocess.Popen(
            cmd,
            cwd=str(frontend_dir),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        self._frontend_proc = proc
        self._start_log_thread("[Frontend]", proc, self._frontend_log)
        return proc

    def _poll_health(self, host: str, port: int, max_wait: float = 10.0) -> bool:
        """
        轮询 GET http://{host}:{port}/health，间隔 0.5s。
        成功返回 True，超时返回 False。
        """
        import urllib.request
        import urllib.error

        url = f"http://{host}:{port}/health"
        deadline = time.time() + max_wait
        while time.time() < deadline:
            try:
                with urllib.request.urlopen(url, timeout=1) as resp:  # noqa: S310
                    if resp.status == 200:
                        return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(0.5)
        return False

    # ------------------------------------------------------------------ #
    # 主入口                                                                #
    # ------------------------------------------------------------------ #

    def start_all(
        self,
        host: str = "127.0.0.1",
        api_port: int = 8000,
        frontend_port: int = 5173,
        api_only: bool = False,
        frontend_only: bool = False,
    ) -> None:
        """
        协调启动后端和/或前端。
        检查孤儿进程 → 寻找可用端口 → 启动进程 → 写 PID 文件 → 打印访问面板。
        """
        self._check_stale_pids()

        pid_data: dict[str, Any] = {}

        if not frontend_only:
            actual_api_port = self._find_available_port(api_port)
            if actual_api_port != api_port:
                print(f"[提示] 端口 {api_port} 已被占用，改用 {actual_api_port}")
            api_port = actual_api_port
            self.start_backend(host, api_port)
            pid_data["backend_pid"] = self._backend_proc.pid  # type: ignore[union-attr]
            pid_data["backend_port"] = api_port
            print(f"后端启动中... (PID {self._backend_proc.pid})")  # type: ignore[union-attr]

            # 等待后端健康检查通过再启动前端
            if not api_only:
                healthy = self._poll_health(host, api_port)
                if not healthy:
                    print("[警告] 后端健康检查超时，继续启动前端...")

        if not api_only:
            actual_frontend_port = self._find_available_port(frontend_port)
            if actual_frontend_port != frontend_port:
                print(f"[提示] 端口 {frontend_port} 已被占用，改用 {actual_frontend_port}")
            frontend_port = actual_frontend_port
            self.start_frontend(frontend_port, api_port)
            pid_data["frontend_pid"] = self._frontend_proc.pid  # type: ignore[union-attr]
            pid_data["frontend_port"] = frontend_port
            print(f"前端启动中... (PID {self._frontend_proc.pid})")  # type: ignore[union-attr]

        self._write_pid_file(pid_data)

        # 打印访问信息面板
        log_dir = Path("logs").resolve()
        print("\n" + "=" * 50)
        print("  Narrative OS — 开发服务已启动")
        print("=" * 50)
        if not frontend_only:
            print(f"  后端 API:  http://{host}:{api_port}")
            print(f"  API 文档:  http://{host}:{api_port}/docs")
        if not api_only:
            print(f"  前端 UI:   http://localhost:{frontend_port}")
        print(f"  后端日志:  {log_dir / 'backend.log'}")
        print(f"  前端日志:  {log_dir / 'frontend.log'}")
        print("  终端仅显示 ERROR/WARNING，详细日志见上方文件")
        print("  按 Ctrl+C 退出并自动清理")
        print("=" * 50 + "\n")

        # 注册信号处理
        def _sig_handler(signum, frame):
            self._cleanup()
            sys.exit(0)

        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
