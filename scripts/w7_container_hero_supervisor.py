#!/usr/bin/env python3
"""Test-owned single-container supervisor for the W7 Render-start hero proof."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from scripts.w7_container_hero_client import run_proof

_START_COMMAND = "/usr/local/bin/aioa-render-start"
_LOG_LIMIT_BYTES = 32_768
_START_TIMEOUT_SECONDS = 45.0


def main() -> int:
    token = os.environ.get("AIOA_OPERATOR_TOKEN", "")
    if not token:
        return 2
    process: subprocess.Popen[bytes] | None = None
    result: dict[str, object] | None = None
    log_valid = False
    with tempfile.TemporaryFile(mode="w+b") as log:
        try:
            process = subprocess.Popen(
                [_START_COMMAND],
                env=dict(os.environ),
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            os.environ["AIOA_W7_SERVER_PID"] = str(process.pid)
            token_path = Path(os.environ.get("AIOA_LOCAL_API_TOKEN_PATH", ""))
            deadline = time.monotonic() + _START_TIMEOUT_SECONDS
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    break
                if token_path.is_absolute() and token_path.is_file():
                    break
                time.sleep(0.05)
            else:
                return 2
            result = run_proof()
        except Exception:
            result = None
        finally:
            if process is not None and process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
            if process is not None:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=5)
            log.flush()
            log.seek(0)
            output = log.read(_LOG_LIMIT_BYTES + 1)
            log_valid = len(output) <= _LOG_LIMIT_BYTES and token.encode() not in output
    if process is None or process.returncode != 0 or result is None or not log_valid:
        return 2
    print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
