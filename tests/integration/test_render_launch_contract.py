from __future__ import annotations

import json
import os
import shlex
import signal
import socket
import stat
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
BLUEPRINT_PATH = ROOT / "render.yaml"
DOCKERFILE_PATH = ROOT / "Dockerfile"


def _service() -> dict[str, Any]:
    blueprint = yaml.safe_load(BLUEPRINT_PATH.read_text(encoding="utf-8"))
    assert isinstance(blueprint, dict)
    services = blueprint.get("services")
    assert isinstance(services, list) and len(services) == 1
    service = services[0]
    assert isinstance(service, dict)
    return service


def _free_loopback_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def _environment(service: dict[str, Any], workspace: Path, port: int) -> dict[str, str]:
    env_vars = service.get("envVars")
    assert isinstance(env_vars, list)
    environment = {
        item["key"]: str(item["value"])
        for item in env_vars
        if isinstance(item, dict) and "key" in item and "value" in item
    }
    environment.update(
        {
            "AIOA_HOST": "127.0.0.1",
            "AIOA_PORT": str(port),
            "AIOA_LOCAL_API_TOKEN_PATH": str(workspace / "operator.token"),
            "AIOA_LOCAL_HITL_STATE_PATH": str(workspace / "durable-truth.json"),
            "AIOA_LOCAL_INVENTORY_PATH": str(workspace / "mock-inventory.json"),
            "PATH": f"{Path(sys.executable).parent}:{os.defpath}",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONNOUSERSITE": "1",
            "PYTHONPATH": str(ROOT / "src"),
        }
    )
    return environment


def _request_json(port: int, path: str) -> dict[str, Any]:
    with urllib.request.urlopen(
        f"http://127.0.0.1:{port}{path}", timeout=1
    ) as response:
        assert response.status == 200
        value = json.loads(response.read())
    assert isinstance(value, dict)
    return value


def _wait_until_ready(
    process: subprocess.Popen[str], port: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    deadline = time.monotonic() + 60
    while time.monotonic() < deadline:
        assert process.poll() is None
        try:
            health = _request_json(port, "/health")
            ready = _request_json(port, "/ready")
        except (OSError, TimeoutError, urllib.error.URLError):
            time.sleep(0.05)
            continue
        return health, ready
    raise AssertionError("Render bootstrap process did not become ready")


def _stop(process: subprocess.Popen[str]) -> tuple[str, str]:
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        return process.communicate(timeout=10)
    except subprocess.TimeoutExpired:
        os.killpg(process.pid, signal.SIGKILL)
        return process.communicate(timeout=5)


def test_render_docker_command_securely_bootstraps_canonical_server(
    tmp_path: Path,
) -> None:
    service = _service()
    command = service.get("dockerCommand")
    assert isinstance(command, str)
    dockerfile = DOCKERFILE_PATH.read_text(encoding="utf-8")
    assert 'CMD ["python", "-m", "aioa_cloudops_agent.portable_server"]' in dockerfile
    assert "ENTRYPOINT" not in dockerfile

    port = _free_loopback_port()
    environment = _environment(service, tmp_path, port)
    token = "render-" + "bootstrap-" + ("t" * 48)
    environment["AIOA_OPERATOR_TOKEN"] = token
    process = subprocess.Popen(
        shlex.split(command),
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    stdout = ""
    stderr = ""
    try:
        health, ready = _wait_until_ready(process, port)
        token_path = Path(environment["AIOA_LOCAL_API_TOKEN_PATH"])
        metadata = token_path.stat()
        assert stat.S_ISREG(metadata.st_mode)
        assert stat.S_IMODE(metadata.st_mode) == 0o600
        assert token_path.read_text(encoding="utf-8") == f"{token}\n"

        child_environment = Path(f"/proc/{process.pid}/environ").read_bytes().split(b"\0")
        assert not any(
            item.startswith(b"AIOA_OPERATOR_TOKEN=") for item in child_environment
        )
        argv = [
            os.fsdecode(item)
            for item in Path(f"/proc/{process.pid}/cmdline").read_bytes().split(b"\0")
            if item
        ]
        assert argv[1:] == ["-m", "aioa_cloudops_agent.portable_server"]
        assert health == {"mode": "mock", "service": "aioa-local-hitl", "status": "ok"}
        assert ready["status"] == "ready"
        assert ready["runtime"]["runtime_mode"] == "portable"
        assert ready["runtime"]["provider"] == "mock"
        assert ready["runtime"]["aws_calls_allowed"] is False
        assert ready["runtime"]["external_network_allowed"] is False
        assert ready["runtime"]["real_cloud_mutations_enabled"] is False
    finally:
        stdout, stderr = _stop(process)
    assert process.returncode == 0
    assert token not in stdout
    assert token not in stderr


def test_render_docker_command_fails_closed_without_operator_token(
    tmp_path: Path,
) -> None:
    service = _service()
    command = service.get("dockerCommand")
    assert isinstance(command, str)
    environment = _environment(service, tmp_path, _free_loopback_port())
    environment.pop("AIOA_OPERATOR_TOKEN", None)

    result = subprocess.run(
        shlex.split(command),
        cwd=ROOT,
        env=environment,
        capture_output=True,
        check=False,
        text=True,
        timeout=5,
    )

    assert result.returncode == 2
    assert not Path(environment["AIOA_LOCAL_API_TOKEN_PATH"]).exists()
    assert result.stdout == ""
    assert result.stderr == "AIOA operator token missing\n"
