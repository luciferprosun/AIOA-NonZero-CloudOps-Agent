#!/usr/bin/env python3
"""Run the fixed workspace hero proof against a loopback server inside one container."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Final

_MAX_RESPONSE_BYTES: Final = 65_536
_SCENARIO: Final = "FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1"
_READINESS_TIMEOUT_SECONDS: Final = 45.0
_EXPECTED_TMP_ROOTS: Final = frozenset(
    {
        "aioa-durable-truth-workspace-hero",
        "aioa-durable-truth.json",
        "aioa-mock-inventory.json",
        "aioa-operator.token",
    }
)
_MAX_TMP_ENTRIES: Final = 512
_MAX_TMP_FILE_BYTES: Final = 2 * 1024 * 1024


class HeroClientFailure(RuntimeError):
    """One fixed container-hero proof failure."""


def _strict_json(raw: bytes) -> dict[str, object]:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for name, value in values:
            if name in result:
                raise ValueError("duplicate key")
            result[name] = value
        return result

    try:
        value = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _value: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, ValueError, json.JSONDecodeError) as error:
        raise HeroClientFailure("RESPONSE_INVALID") from error
    if not isinstance(value, dict):
        raise HeroClientFailure("RESPONSE_INVALID")
    return value


def _runtime_inputs() -> tuple[str, str, Path]:
    raw_port = os.environ.get("AIOA_PORT", "")
    token_path_value = os.environ.get("AIOA_LOCAL_API_TOKEN_PATH", "")
    if not raw_port.isascii() or not raw_port.isdigit():
        raise HeroClientFailure("RUNTIME_INPUT_INVALID")
    port = int(raw_port)
    token_path = Path(token_path_value)
    if not 1 <= port <= 65_535 or not token_path.is_absolute():
        raise HeroClientFailure("RUNTIME_INPUT_INVALID")
    try:
        metadata = token_path.stat()
        token = token_path.read_text(encoding="utf-8").rstrip("\n")
    except (OSError, UnicodeDecodeError) as error:
        raise HeroClientFailure("TOKEN_FILE_INVALID") from error
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or stat.S_IMODE(metadata.st_mode) != 0o600
        or not 32 <= len(token) <= 256
        or token != token.strip()
    ):
        raise HeroClientFailure("TOKEN_FILE_INVALID")
    return f"http://127.0.0.1:{port}", token, token_path


def _snapshot_tmp() -> dict[str, tuple[str, int, str]]:
    snapshot: dict[str, tuple[str, int, str]] = {}
    try:
        paths = sorted(Path("/tmp").rglob("*"))
        if len(paths) > _MAX_TMP_ENTRIES:
            raise HeroClientFailure("TMP_SNAPSHOT_INVALID")
        for path in paths:
            metadata = path.lstat()
            relative = path.relative_to("/tmp").as_posix()
            mode = stat.S_IMODE(metadata.st_mode)
            if stat.S_ISDIR(metadata.st_mode):
                snapshot[relative] = ("directory", mode, "")
            elif stat.S_ISREG(metadata.st_mode):
                if metadata.st_size > _MAX_TMP_FILE_BYTES:
                    raise HeroClientFailure("TMP_SNAPSHOT_INVALID")
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                snapshot[relative] = ("file", mode, digest)
            else:
                raise HeroClientFailure("TMP_SNAPSHOT_INVALID")
    except OSError as error:
        raise HeroClientFailure("TMP_SNAPSHOT_INVALID") from error
    return snapshot


def _unexpected_tmp_changes(
    before: dict[str, tuple[str, int, str]],
    after: dict[str, tuple[str, int, str]],
) -> tuple[str, ...]:
    changed = {
        path for path in set(before) | set(after) if before.get(path) != after.get(path)
    }
    return tuple(
        sorted(
            path
            for path in changed
            if Path(path).parts[0] not in _EXPECTED_TMP_ROOTS
        )
    )


def _server_process_path() -> Path:
    raw_pid = os.environ.get("AIOA_W7_SERVER_PID", "1")
    if not raw_pid.isascii() or not raw_pid.isdigit() or int(raw_pid) < 1:
        raise HeroClientFailure("SERVER_PID_INVALID")
    return Path("/proc") / raw_pid


def _request(
    base: str,
    token: str,
    method: str,
    path: str,
    body: dict[str, object] | None = None,
) -> tuple[int, dict[str, object]]:
    data = None
    headers = {"Accept": "application/json", "Authorization": f"Bearer {token}"}
    if body is not None:
        data = json.dumps(
            body,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        headers["Content-Type"] = "application/json"
        headers["X-AIOA-Intent"] = "judge-console-v1"
    request = urllib.request.Request(
        f"{base}{path}",
        data=data,
        headers=headers,
        method=method,
    )
    try:
        response = urllib.request.urlopen(request, timeout=10)
    except urllib.error.HTTPError as error:
        response = error
    try:
        payload = response.read(_MAX_RESPONSE_BYTES + 1)
        status = int(response.status)
    finally:
        response.close()
    if len(payload) > _MAX_RESPONSE_BYTES:
        raise HeroClientFailure("RESPONSE_INVALID")
    return status, _strict_json(payload)


def _result(status: int, payload: dict[str, object], expected: int) -> dict[str, object]:
    value = payload.get("result")
    if status != expected or payload.get("ok") is not True or not isinstance(value, dict):
        raise HeroClientFailure("HERO_TRANSITION_INVALID")
    return value


def _wait_for_runtime(
    base: str,
    token: str,
) -> tuple[dict[str, object], dict[str, object]]:
    deadline = time.monotonic() + _READINESS_TIMEOUT_SECONDS
    while time.monotonic() < deadline:
        try:
            health_status, health = _request(base, token, "GET", "/health")
            ready_status, ready = _request(base, token, "GET", "/ready")
        except (HeroClientFailure, OSError, urllib.error.URLError):
            time.sleep(0.1)
            continue
        if health_status == 200 and ready_status == 200:
            return health, ready
        time.sleep(0.1)
    raise HeroClientFailure("RUNTIME_NOT_READY")


def _start(base: str, token: str) -> dict[str, object]:
    return _result(
        *_request(
            base,
            token,
            "POST",
            "/api/workspace-demo/runs",
            {"scenario_id": _SCENARIO},
        ),
        201,
    )


def _approval_request(base: str, token: str, run_id: object) -> dict[str, object]:
    return _result(
        *_request(
            base,
            token,
            "POST",
            f"/api/workspace-demo/runs/{run_id}/approval-request",
            {},
        ),
        200,
    )


def _decision(
    base: str,
    token: str,
    view: dict[str, object],
    decision: str,
) -> dict[str, object]:
    card = view.get("approval_card")
    if not isinstance(card, dict):
        raise HeroClientFailure("APPROVAL_CARD_INVALID")
    return _result(
        *_request(
            base,
            token,
            "POST",
            f"/api/workspace-demo/runs/{view.get('run_id')}/decision",
            {
                "decision": decision,
                "request_fingerprint": card.get("request_fingerprint"),
            },
        ),
        200,
    )


def run_proof() -> dict[str, object]:
    """Complete approve/replay and fresh deny journeys over loopback only."""

    base, token, token_path = _runtime_inputs()
    health, ready = _wait_for_runtime(base, token)
    runtime = ready.get("runtime")
    if (
        health != {"mode": "mock", "service": "aioa-local-hitl", "status": "ok"}
        or ready.get("status") != "ready"
        or not isinstance(runtime, dict)
        or runtime.get("provider") != "mock"
        or runtime.get("aws_calls_allowed") is not False
        or runtime.get("external_network_allowed") is not False
        or runtime.get("real_cloud_mutations_enabled") is not False
    ):
        raise HeroClientFailure("RUNTIME_NOT_READY")
    before_tmp = _snapshot_tmp()

    approved_start = _start(base, token)
    approved_request = _approval_request(base, token, approved_start.get("run_id"))
    approved_decision = _decision(base, token, approved_request, "APPROVED")
    run_id = approved_decision.get("run_id")
    applied = _result(
        *_request(
            base,
            token,
            "POST",
            f"/api/workspace-demo/runs/{run_id}/resume",
            {"confirm_execution": True},
        ),
        200,
    )
    verified = _result(
        *_request(
            base,
            token,
            "POST",
            f"/api/workspace-demo/runs/{run_id}/verify-or-reconcile",
            {},
        ),
        200,
    )
    replayed = _result(
        *_request(
            base,
            token,
            "POST",
            f"/api/workspace-demo/runs/{run_id}/resume",
            {"confirm_execution": True},
        ),
        200,
    )
    refreshed = _result(
        *_request(base, token, "GET", f"/api/workspace-demo/runs/{run_id}"),
        200,
    )
    replay = replayed.get("replay")
    after = verified.get("after")
    if (
        approved_start.get("state") != "PATCH_PROPOSED"
        or approved_request.get("state") != "AWAITING_APPROVAL"
        or approved_decision.get("state") != "APPROVED"
        or applied.get("state") != "PATCH_APPLIED_UNVERIFIED"
        or applied.get("success_with_evidence") is not False
        or verified.get("state") != "SUCCESS_WITH_EVIDENCE"
        or verified.get("success_with_evidence") is not True
        or verified.get("workspace_mutation_count") != 1
        or refreshed != replayed
        or not isinstance(replay, dict)
        or replay.get("status") != "REPLAY_REJECTED_RECONCILED"
        or replay.get("patch_apply_count") != 1
        or replay.get("additional_mutation_delta") != 0
        or replay.get("additional_profile_executions") != 0
        or not isinstance(after, dict)
        or after.get("external_egress") != 0
        or after.get("aws_calls") != 0
    ):
        raise HeroClientFailure("APPROVE_REPLAY_PROOF_INVALID")

    denied_start = _start(base, token)
    denied_request = _approval_request(base, token, denied_start.get("run_id"))
    denied = _decision(base, token, denied_request, "DENIED")
    denied_status, denied_resume = _request(
        base,
        token,
        "POST",
        f"/api/workspace-demo/runs/{denied.get('run_id')}/resume",
        {"confirm_execution": True},
    )
    if (
        denied.get("state") != "DENIED_BY_HUMAN"
        or denied.get("workspace_mutation_count") != 0
        or denied.get("executor_receipt_present") is not False
        or denied.get("verification_receipt_present") is not False
        or denied_status != 403
        or denied_resume.get("ok") is not False
    ):
        raise HeroClientFailure("DENY_PROOF_INVALID")
    after_tmp = _snapshot_tmp()
    if _unexpected_tmp_changes(before_tmp, after_tmp):
        raise HeroClientFailure("UNEXPECTED_FILE_MUTATION")

    try:
        process_path = _server_process_path()
        server_environment = (process_path / "environ").read_bytes().split(b"\0")
    except OSError as error:
        raise HeroClientFailure("SERVER_ENVIRONMENT_UNAVAILABLE") from error
    bootstrap_secret_absent = not any(
        item.startswith(b"AIOA_OPERATOR_TOKEN=") for item in server_environment
    )
    if not bootstrap_secret_absent:
        raise HeroClientFailure("BOOTSTRAP_SECRET_PRESENT_IN_SERVER")
    try:
        argv = tuple(
            os.fsdecode(item)
            for item in (process_path / "cmdline").read_bytes().split(b"\0")
            if item
        )
    except OSError as error:
        raise HeroClientFailure("SERVER_ARGV_UNAVAILABLE") from error
    server_argv_exact = argv[1:] == ("-m", "aioa_cloudops_agent.portable_server")
    if not server_argv_exact or Path(argv[0]).name != "python":
        raise HeroClientFailure("SERVER_ARGV_INVALID")

    return {
        "approve": {
            "final_state": "SUCCESS_WITH_EVIDENCE",
            "patch_apply_count": 1,
            "replay_additional_mutations": 0,
            "replay_status": "REPLAY_REJECTED_RECONCILED",
        },
        "aws_calls": 0,
        "aws_mutations": 0,
        "bootstrap_secret_absent_from_server": True,
        "deny": {"final_state": "DENIED_BY_HUMAN", "mutation_count": 0},
        "external_network_connections": 0,
        "health": "PASS",
        "ready": "PASS",
        "server_argv_exact": True,
        "source_commit": os.environ.get("SOURCE_COMMIT", "unknown"),
        "status": "PASS",
        "token_file_mode": oct(stat.S_IMODE(token_path.stat().st_mode)),
        "unexpected_file_mutations": 0,
    }


def main() -> int:
    try:
        result = run_proof()
        code = 0
    except (HeroClientFailure, OSError, ValueError, urllib.error.URLError):
        result = {"reason": "W7_CONTAINER_HERO_PROOF_FAILED", "status": "FAIL"}
        code = 1
    print(json.dumps(result, allow_nan=False, indent=2, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
