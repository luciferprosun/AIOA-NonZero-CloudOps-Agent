"""Fixed, server-owned ``render_start_contract_v1`` runtime verifier."""

from __future__ import annotations

import json
import os
import signal
import socket
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final, Literal, Protocol

from aioa_cloudops_agent.nz.contracts import NonZeroContract

from .contracts import W2_VERIFICATION_PROFILE_ID

_PORTABLE_MODULE: Final = "aioa_cloudops_agent.portable_server"
_PORTABLE_ARGV: Final = ("-m", _PORTABLE_MODULE)
_LOOPBACK_HOST: Final = "127.0.0.1"
_PROBE_TIMEOUT_SECONDS: Final = 30.0
_HTTP_TIMEOUT_SECONDS: Final = 1.0
_LOG_LIMIT_BYTES: Final = 16_384
_EGRESS_AUDIT_ENV: Final = "AIOA_W4_EGRESS_AUDIT_PATH"


class TrustedRenderStartProfileFailure(RuntimeError):
    """A normalized profile failure that never contains token or host-private data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TrustedRenderStartProfileResult(NonZeroContract):
    """Bounded normalized proof returned by the fixed trusted probe."""

    verification_profile_id: Literal["render_start_contract_v1"] = (
        W2_VERIFICATION_PROFILE_ID
    )
    missing_token_fails_closed: Literal[True] = True
    token_mode_0600: Literal[True] = True
    bootstrap_secret_absent: Literal[True] = True
    child_argv_exact: Literal[True] = True
    health_passed: Literal[True] = True
    readiness_passed: Literal[True] = True
    external_egress_count: Literal[0] = 0
    aws_call_count: Literal[0] = 0
    workspace_code_executions: Literal[0] = 0
    arbitrary_command_executions: Literal[0] = 0
    process_executions: Literal[1] = 1

class TrustedRenderStartProfile(Protocol):
    """Server-selected profile dependency; its API takes no model-controlled values."""

    def run(self) -> TrustedRenderStartProfileResult: ...


class RenderStartContractV1Profile:
    """Run one fixed portable-server child under loopback-only observation."""

    def run(self) -> TrustedRenderStartProfileResult:
        with tempfile.TemporaryDirectory(prefix="aioa-w4-render-profile-") as directory:
            root = Path(directory)
            root.chmod(0o700)
            token_path = root / "operator.token"
            missing_path = root / "missing-token-probe"
            if not self._missing_token_fails_closed(missing_path):
                raise TrustedRenderStartProfileFailure("MISSING_TOKEN_PROBE_FAILED")

            port = self._free_loopback_port()
            synthetic_token = "w4-" + "synthetic-bootstrap-" + ("x" * 48)
            environment = self._fixed_environment(root, token_path, port)
            environment["AIOA_OPERATOR_TOKEN"] = synthetic_token
            child_environment = self._bootstrap(environment)
            token_metadata = token_path.stat()
            token_mode_0600 = (
                stat.S_ISREG(token_metadata.st_mode)
                and token_metadata.st_uid == os.getuid()
                and token_metadata.st_nlink == 1
                and stat.S_IMODE(token_metadata.st_mode) == 0o600
                and token_path.read_text(encoding="utf-8") == f"{synthetic_token}\n"
            )
            if not token_mode_0600:
                raise TrustedRenderStartProfileFailure("TOKEN_FILE_MODE_PROOF_FAILED")
            if "AIOA_OPERATOR_TOKEN" in child_environment:
                raise TrustedRenderStartProfileFailure("BOOTSTRAP_SECRET_ENV_REMOVE_FAILED")

            process: subprocess.Popen[bytes] | None = None
            health: dict[str, object] | None = None
            ready: dict[str, object] | None = None
            timed_out = False
            with (
                tempfile.TemporaryFile(mode="w+b") as stdout_file,
                tempfile.TemporaryFile(mode="w+b") as stderr_file,
            ):
                try:
                    process = subprocess.Popen(
                        [sys.executable, *_PORTABLE_ARGV],
                        cwd=root,
                        env=child_environment,
                        stdin=subprocess.DEVNULL,
                        stdout=stdout_file,
                        stderr=stderr_file,
                        start_new_session=True,
                    )
                    health, ready = self._wait_for_runtime(process, port)
                    bootstrap_secret_absent, child_argv_exact = self._inspect_child(process)
                except TimeoutError:
                    timed_out = True
                    raise TrustedRenderStartProfileFailure("RUNTIME_PROBE_TIMEOUT") from None
                except (OSError, ValueError, urllib.error.URLError) as error:
                    raise TrustedRenderStartProfileFailure("RUNTIME_PROBE_UNAVAILABLE") from error
                finally:
                    if process is not None:
                        self._stop(process)
                    stdout = self._bounded_log(stdout_file)
                    stderr = self._bounded_log(stderr_file)
                    if not timed_out and synthetic_token.encode() in stdout + stderr:
                        raise TrustedRenderStartProfileFailure("RUNTIME_PROBE_SECRET_LEAK")

            if process is None or process.returncode != 0:
                raise TrustedRenderStartProfileFailure("RUNTIME_PROBE_CHILD_FAILED")
            if not bootstrap_secret_absent:
                raise TrustedRenderStartProfileFailure("BOOTSTRAP_SECRET_PRESENT_IN_CHILD")
            if not child_argv_exact:
                raise TrustedRenderStartProfileFailure("PORTABLE_CHILD_ARGV_MISMATCH")
            if not self._health_passes(health):
                raise TrustedRenderStartProfileFailure("RUNTIME_HEALTH_MISMATCH")
            if not self._ready_passes(ready):
                raise TrustedRenderStartProfileFailure("RUNTIME_READINESS_MISMATCH")
            audit_path = root / "external-egress.audit"
            if audit_path.exists() and audit_path.read_bytes():
                raise TrustedRenderStartProfileFailure("RUNTIME_EXTERNAL_EGRESS_ATTEMPT")
            return TrustedRenderStartProfileResult()

    @staticmethod
    def _missing_token_fails_closed(token_path: Path) -> bool:
        environment = {"AIOA_LOCAL_API_TOKEN_PATH": str(token_path)}
        try:
            RenderStartContractV1Profile._bootstrap(environment)
        except TrustedRenderStartProfileFailure as error:
            return error.code == "BOOTSTRAP_TOKEN_MISSING" and not token_path.exists()
        return False

    @staticmethod
    def _bootstrap(environment: dict[str, str]) -> dict[str, str]:
        child = dict(environment)
        token = child.pop("AIOA_OPERATOR_TOKEN", "")
        token_path_value = child.get("AIOA_LOCAL_API_TOKEN_PATH", "")
        if not token:
            raise TrustedRenderStartProfileFailure("BOOTSTRAP_TOKEN_MISSING")
        if not token_path_value:
            raise TrustedRenderStartProfileFailure("BOOTSTRAP_TOKEN_PATH_MISSING")
        token_path = Path(token_path_value)
        flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(token_path, flags, 0o600)
        try:
            payload = f"{token}\n".encode()
            offset = 0
            while offset < len(payload):
                written = os.write(descriptor, payload[offset:])
                if written <= 0:
                    raise OSError("token write made no progress")
                offset += written
            os.fchmod(descriptor, 0o600)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)
        return child

    @staticmethod
    def _free_loopback_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind((_LOOPBACK_HOST, 0))
            return int(probe.getsockname()[1])

    @staticmethod
    def _fixed_environment(root: Path, token_path: Path, port: int) -> dict[str, str]:
        source_root = Path(__file__).resolve().parents[2]
        probe_site = Path(__file__).resolve().with_name("_probe_site")
        return {
            "AIOA_ALLOWED_EGRESS": "none",
            "AIOA_AWS_INTEGRATION_ENABLED": "false",
            "AIOA_HOST": _LOOPBACK_HOST,
            "AIOA_LOCAL_API_TOKEN_PATH": str(token_path),
            "AIOA_LOCAL_HITL_STATE_PATH": str(root / "durable-truth.json"),
            "AIOA_LOCAL_INVENTORY_PATH": str(root / "mock-inventory.json"),
            "AIOA_MODEL_PROVIDER": "mock",
            "AIOA_PORT": str(port),
            "AIOA_RUNTIME_MODE": "portable",
            _EGRESS_AUDIT_ENV: str(root / "external-egress.audit"),
            "PATH": f"{Path(sys.executable).parent}:{os.defpath}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": os.pathsep.join((str(probe_site), str(source_root))),
        }

    @staticmethod
    def _wait_for_runtime(
        process: subprocess.Popen[bytes],
        port: int,
    ) -> tuple[dict[str, object], dict[str, object]]:
        deadline = time.monotonic() + _PROBE_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise OSError("trusted runtime exited before readiness")
            try:
                health = RenderStartContractV1Profile._request_json(port, "/health")
                ready = RenderStartContractV1Profile._request_json(port, "/ready")
            except (OSError, TimeoutError, urllib.error.URLError):
                time.sleep(0.05)
                continue
            return health, ready
        raise TimeoutError("trusted runtime probe exceeded its fixed deadline")

    @staticmethod
    def _request_json(port: int, path: str) -> dict[str, object]:
        with urllib.request.urlopen(
            f"http://{_LOOPBACK_HOST}:{port}{path}",
            timeout=_HTTP_TIMEOUT_SECONDS,
        ) as response:
            if response.status != 200:
                raise ValueError("trusted runtime endpoint status mismatch")
            value = json.loads(response.read(16_385))
        if not isinstance(value, dict):
            raise ValueError("trusted runtime endpoint payload is not an object")
        return value

    @staticmethod
    def _inspect_child(process: subprocess.Popen[bytes]) -> tuple[bool, bool]:
        environment = Path(f"/proc/{process.pid}/environ").read_bytes().split(b"\0")
        bootstrap_absent = not any(
            item.startswith(b"AIOA_OPERATOR_TOKEN=") for item in environment
        )
        argv = tuple(
            os.fsdecode(item)
            for item in Path(f"/proc/{process.pid}/cmdline").read_bytes().split(b"\0")
            if item
        )
        return bootstrap_absent, argv[1:] == _PORTABLE_ARGV

    @staticmethod
    def _stop(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)

    @staticmethod
    def _bounded_log(handle) -> bytes:
        handle.flush()
        handle.seek(0)
        return handle.read(_LOG_LIMIT_BYTES + 1)

    @staticmethod
    def _health_passes(value: dict[str, object] | None) -> bool:
        return value == {"mode": "mock", "service": "aioa-local-hitl", "status": "ok"}

    @staticmethod
    def _ready_passes(value: dict[str, object] | None) -> bool:
        if not isinstance(value, dict) or value.get("status") != "ready":
            return False
        runtime = value.get("runtime")
        return isinstance(runtime, dict) and runtime.get("runtime_mode") == "portable" and (
            runtime.get("provider") == "mock"
            and runtime.get("aws_calls_allowed") is False
            and runtime.get("external_network_allowed") is False
            and runtime.get("real_cloud_mutations_enabled") is False
        )
