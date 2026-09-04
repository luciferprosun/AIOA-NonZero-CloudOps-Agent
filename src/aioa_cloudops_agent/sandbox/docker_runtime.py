"""Bounded structured-argv access to one operator-owned rootless Docker socket."""

from __future__ import annotations

import os
import selectors
import time
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from aioa_cloudops_agent.agent.owned_process import OwnedProcess, OwnedProcessTimeout


class DockerCliFailure(RuntimeError):
    """Stable Docker control-plane failure without embedding command output."""

    def __init__(self, code: str, *, returncode: int | None = None) -> None:
        super().__init__(code)
        self.code = code
        self.returncode = returncode


@dataclass(frozen=True, slots=True)
class DockerCliResult:
    returncode: int
    stdout: bytes
    stderr: bytes
    duration_milliseconds: int
    output_truncated: bool


class DockerCli:
    """Execute only caller-owned Docker argv through a fixed rootless Unix socket."""

    def __init__(self, engine_path: str, *, operator_uid: int | None = None) -> None:
        uid = os.getuid() if operator_uid is None else operator_uid
        if uid <= 0:
            raise ValueError("rootless Docker requires a non-root operator")
        path = Path(engine_path)
        if not path.is_absolute() or path.as_posix() != engine_path:
            raise ValueError("Docker engine path must be canonical and absolute")
        self._engine_path = engine_path
        self._environment = {
            "DOCKER_HOST": f"unix:///run/user/{uid}/docker.sock",
            "LANG": "C.UTF-8",
            "PATH": "/usr/bin:/bin",
        }

    def run(
        self,
        argv: tuple[str, ...],
        *,
        stdin: bytes = b"",
        timeout_seconds: float = 30.0,
        output_limit: int = 128 * 1024,
    ) -> DockerCliResult:
        if (
            not argv
            or len(argv) > 96
            or sum(len(value) for value in argv) > 32 * 1024
            or any(not value or "\x00" in value or "\n" in value or "\r" in value for value in argv)
        ):
            raise ValueError("Docker argv must contain bounded non-empty elements")
        if not isinstance(stdin, bytes) or len(stdin) > 20 * 1024 * 1024:
            raise ValueError("Docker stdin exceeds the fixed bound")
        if timeout_seconds <= 0 or not 1024 <= output_limit <= 20 * 1024 * 1024:
            raise ValueError("Docker execution bounds are invalid")
        started = time.monotonic()
        process = OwnedProcess.spawn(
            (self._engine_path, *argv),
            cwd=Path("/"),
            environment=self._environment,
        )
        try:
            if stdin:
                process.stdin.write(stdin)
            process.stdin.close()
            stdout, stderr, truncated = self._drain(
                process,
                timeout_seconds=timeout_seconds,
                output_limit=output_limit,
            )
            try:
                returncode = process.wait(timeout=1.0)
            except OwnedProcessTimeout as error:
                raise DockerCliFailure("DOCKER_CLI_WAIT_TIMEOUT") from error
        except BaseException:
            if process.poll() is None:
                process.kill()
                with suppress(OwnedProcessTimeout):
                    process.wait(timeout=1.0)
            raise
        finally:
            for stream in (process.stdin, process.stdout, process.stderr):
                with suppress(OSError):
                    stream.close()
        duration = int((time.monotonic() - started) * 1000)
        return DockerCliResult(
            returncode=returncode,
            stdout=stdout,
            stderr=stderr,
            duration_milliseconds=duration,
            output_truncated=truncated,
        )

    @staticmethod
    def _drain(
        process: OwnedProcess,
        *,
        timeout_seconds: float,
        output_limit: int,
    ) -> tuple[bytes, bytes, bool]:
        selector = selectors.DefaultSelector()
        buffers: dict[str, bytearray] = {"stdout": bytearray(), "stderr": bytearray()}
        total_observed = 0
        truncated = False
        for name, stream in (("stdout", process.stdout), ("stderr", process.stderr)):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, data=name)
        deadline = time.monotonic() + timeout_seconds
        try:
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise DockerCliFailure("DOCKER_CLI_TIMEOUT")
                events = selector.select(min(0.1, remaining))
                if not events and process.poll() is not None:
                    events = [
                        (key, selectors.EVENT_READ) for key in tuple(selector.get_map().values())
                    ]
                for key, _ in events:
                    try:
                        chunk = os.read(key.fileobj.fileno(), 64 * 1024)
                    except BlockingIOError:
                        continue
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    available = max(0, output_limit - total_observed)
                    if available:
                        buffers[key.data].extend(chunk[:available])
                    total_observed += len(chunk)
                    if total_observed > output_limit:
                        truncated = True
        finally:
            selector.close()
        return bytes(buffers["stdout"]), bytes(buffers["stderr"]), truncated

    def checked(
        self,
        argv: tuple[str, ...],
        *,
        stdin: bytes = b"",
        timeout_seconds: float = 30.0,
        output_limit: int = 128 * 1024,
        failure_code: str,
    ) -> DockerCliResult:
        result = self.run(
            argv,
            stdin=stdin,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
        )
        if result.returncode != 0 or result.output_truncated:
            raise DockerCliFailure(failure_code, returncode=result.returncode)
        return result
