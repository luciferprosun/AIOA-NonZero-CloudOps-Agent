"""Minimal POSIX process primitive for one exact structured-argv child."""

from __future__ import annotations

import os
import signal
import time
from contextlib import suppress
from pathlib import Path
from typing import BinaryIO


class OwnedProcessTimeout(RuntimeError):
    """The exact child did not exit inside its bounded shutdown window."""


class OwnedProcess:
    """POSIX structured-argv child with owned pipes and a new session."""

    def __init__(
        self,
        pid: int,
        stdin: BinaryIO,
        stdout: BinaryIO,
        stderr: BinaryIO,
    ) -> None:
        self.pid = pid
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self._returncode: int | None = None

    @classmethod
    def spawn(
        cls,
        argv: tuple[str, ...],
        *,
        cwd: Path,
        environment: dict[str, str],
    ) -> OwnedProcess:
        """Spawn through `env --chdir` without a shell or command-string parsing."""

        descriptors = (
            os.pipe2(os.O_CLOEXEC),
            os.pipe2(os.O_CLOEXEC),
            os.pipe2(os.O_CLOEXEC),
        )
        stdin_read, stdin_write = descriptors[0]
        stdout_read, stdout_write = descriptors[1]
        stderr_read, stderr_write = descriptors[2]
        all_descriptors = tuple(item for pair in descriptors for item in pair)
        actions: list[tuple[int, ...]] = [
            (os.POSIX_SPAWN_DUP2, stdin_read, 0),
            (os.POSIX_SPAWN_DUP2, stdout_write, 1),
            (os.POSIX_SPAWN_DUP2, stderr_write, 2),
        ]
        actions.extend((os.POSIX_SPAWN_CLOSE, descriptor) for descriptor in all_descriptors)
        spawn_argv = ("env", "--chdir", cwd.as_posix(), *argv)
        try:
            pid = os.posix_spawnp(
                "env",
                spawn_argv,
                environment,
                file_actions=actions,
                setsid=True,
                setsigmask=(),
            )
        except BaseException:
            for descriptor in all_descriptors:
                with suppress(OSError):
                    os.close(descriptor)
            raise
        for descriptor in (stdin_read, stdout_write, stderr_write):
            os.close(descriptor)
        return cls(
            pid,
            os.fdopen(stdin_write, "wb", buffering=0),
            os.fdopen(stdout_read, "rb", buffering=0),
            os.fdopen(stderr_read, "rb", buffering=0),
        )

    def poll(self) -> int | None:
        """Observe the exact child without waiting for unrelated processes."""

        if self._returncode is not None:
            return self._returncode
        try:
            observed_pid, status = os.waitpid(self.pid, os.WNOHANG)
        except ChildProcessError:
            return self._returncode
        if observed_pid == 0:
            return None
        self._returncode = os.waitstatus_to_exitcode(status)
        return self._returncode

    def wait(self, *, timeout: float) -> int:
        """Wait only for this child and enforce the caller's deadline."""

        deadline = time.monotonic() + timeout
        while True:
            result = self.poll()
            if result is not None:
                return result
            if time.monotonic() >= deadline:
                raise OwnedProcessTimeout("owned process shutdown timed out")
            time.sleep(min(0.01, max(0.0, deadline - time.monotonic())))

    def send_signal(self, selected_signal: signal.Signals) -> None:
        """Signal only the exact child; the transport verifies its process group."""

        os.kill(self.pid, selected_signal)

    def kill(self) -> None:
        self.send_signal(signal.SIGKILL)

