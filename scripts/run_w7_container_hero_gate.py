#!/usr/bin/env python3
"""Certify the frozen W5 workspace hero inside one networkless OCI image."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Final

ROOT: Final = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aioa_cloudops_agent.persistence.local_integrity import (  # noqa: E402
    LocalIntegrityError,
    atomic_write_private_json,
)
from scripts.run_b5_container_gate import (  # noqa: E402
    ContainerGateError,
    _external_nonroot_proof,
    _resolve_engine,
    _safe_environment,
    inspect_image,
)

DEFAULT_OUTPUT: Final = ROOT / ".local" / "w7" / "container-hero-gate.json"
_CLIENT: Final = ROOT / "scripts" / "w7_container_hero_client.py"
_COMMIT: Final = re.compile(r"^[0-9a-f]{40}$")
_IMAGE: Final = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/@:+-]{0,255}$")
_SAFE_ENGINE_RUN_ARGS: Final = frozenset(
    {
        "--cgroups=disabled",
        "--log-driver=k8s-file",
    }
)
_SYNTHETIC_TOKEN: Final = "w7-container-hero-synthetic-" + ("t" * 48)
_START_COMMAND: Final = "/usr/local/bin/aioa-render-start"


def _run(
    command: Sequence[str],
    *,
    timeout: int,
    reason: str,
    input_text: str | None = None,
    stdout_limit: int = 2 * 1024 * 1024,
) -> subprocess.CompletedProcess[str]:
    try:
        result = subprocess.run(
            tuple(command),
            cwd=ROOT,
            env=_safe_environment(),
            input=input_text,
            capture_output=True,
            check=False,
            text=True,
            timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ContainerGateError(reason) from error
    if (
        result.returncode != 0
        or len(result.stdout.encode("utf-8")) > stdout_limit
        or len(result.stderr.encode("utf-8")) > 256 * 1024
        or _SYNTHETIC_TOKEN in result.stdout
        or _SYNTHETIC_TOKEN in result.stderr
    ):
        raise ContainerGateError(reason)
    return result


def _strict_json(raw: str, *, reason: str) -> dict[str, object]:
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
    except (TypeError, ValueError, json.JSONDecodeError) as error:
        raise ContainerGateError(reason) from error
    if not isinstance(value, dict):
        raise ContainerGateError(reason)
    return value


def _engine_args(values: Sequence[str]) -> tuple[str, ...]:
    if len(values) != len(set(values)) or any(
        value not in _SAFE_ENGINE_RUN_ARGS for value in values
    ):
        raise ContainerGateError("CONTAINER_ENGINE_RUN_ARGUMENT_UNSAFE")
    return tuple(values)


def _container_run_command(
    engine: str,
    image: str,
    name: str,
    extra_args: Sequence[str],
    user_override: str | None,
) -> tuple[str, ...]:
    if user_override not in (None, "0:0"):
        raise ContainerGateError("CONTAINER_ENGINE_USER_OVERRIDE_UNSAFE")
    command = [
        engine,
        "run",
        "--detach",
        "--name",
        name,
        "--network",
        "none",
        "--read-only",
        "--tmpfs",
        "/tmp:rw,nosuid,nodev,noexec,size=64m",
        "--cap-drop",
        "ALL",
        "--security-opt",
        "no-new-privileges",
        "--env",
        "AWS_EC2_METADATA_DISABLED=true",
        "--env",
        "PYTHONNOUSERSITE=1",
        "--env",
        "AIOA_HOST=127.0.0.1",
        "--env",
        "AIOA_LOCAL_API_TOKEN_PATH=/tmp/aioa-operator.token",
        "--env",
        "AIOA_LOCAL_HITL_STATE_PATH=/tmp/aioa-durable-truth.json",
        "--env",
        "AIOA_LOCAL_INVENTORY_PATH=/tmp/aioa-mock-inventory.json",
        "--env",
        f"AIOA_OPERATOR_TOKEN={_SYNTHETIC_TOKEN}",
        *_engine_args(extra_args),
    ]
    if user_override is not None:
        command.extend(("--user", user_override))
    command.extend((image, _START_COMMAND))
    return tuple(command)


def _client_command(engine: str, name: str, user_override: str | None) -> tuple[str, ...]:
    command = [engine, "exec", "--interactive"]
    if user_override is not None:
        command.extend(("--user", user_override))
    command.extend((name, "python", "-"))
    return tuple(command)


def validate_hero_result(
    value: Mapping[str, object],
    expected_source_commit: str,
) -> dict[str, object]:
    """Validate and reduce the secret-free in-container proof."""

    approve = value.get("approve")
    deny = value.get("deny")
    if (
        set(value)
        != {
            "approve",
            "aws_calls",
            "aws_mutations",
            "bootstrap_secret_absent_from_server",
            "deny",
            "external_network_connections",
            "health",
            "ready",
            "server_argv_exact",
            "source_commit",
            "status",
            "token_file_mode",
            "unexpected_file_mutations",
        }
        or value.get("status") != "PASS"
        or value.get("health") != "PASS"
        or value.get("ready") != "PASS"
        or value.get("source_commit") != expected_source_commit
        or value.get("token_file_mode") != "0o600"
        or value.get("bootstrap_secret_absent_from_server") is not True
        or value.get("server_argv_exact") is not True
        or value.get("aws_calls") != 0
        or value.get("aws_mutations") != 0
        or value.get("external_network_connections") != 0
        or value.get("unexpected_file_mutations") != 0
        or approve
        != {
            "final_state": "SUCCESS_WITH_EVIDENCE",
            "patch_apply_count": 1,
            "replay_additional_mutations": 0,
            "replay_status": "REPLAY_REJECTED_RECONCILED",
        }
        or deny != {"final_state": "DENIED_BY_HUMAN", "mutation_count": 0}
    ):
        raise ContainerGateError("W7_CONTAINER_HERO_RESULT_INVALID")
    return dict(value)


def build_gate_receipt(
    *,
    image_reference: str,
    image_contract: Mapping[str, object],
    nonroot_proof: Mapping[str, object],
    hero: Mapping[str, object],
    engine_user_override: str | None,
) -> dict[str, object]:
    material: dict[str, object] = {
        "aws_calls": 0,
        "aws_mutations": 0,
        "container_start_command": _START_COMMAND,
        "credential_environment_inherited": False,
        "engine_user_override": engine_user_override,
        "external_deployments": 0,
        "external_network_connections": 0,
        "hero": dict(hero),
        "image": {"reference": image_reference, **dict(image_contract)},
        "nonroot_proof": {"mode": "BOUND_EXTERNAL_OCI_RUNTIME", **dict(nonroot_proof)},
        "receipt_type": "AIOA_W7_CONTAINER_WORKSPACE_HERO_GATE",
        "remote_pushes": 0,
        "runtime_hardening": {
            "capabilities_dropped": "ALL",
            "host_ports_published": 0,
            "network": "none",
            "no_new_privileges": True,
            "read_only_rootfs": True,
            "shared_mounts": 0,
            "tmpfs": "/tmp:rw,nosuid,nodev,noexec,size=64m",
        },
        "schema_version": 1,
        "status": "PASS",
    }
    canonical = json.dumps(
        material,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {**material, "receipt_sha256": hashlib.sha256(canonical).hexdigest()}


def _write_receipt(path: Path, receipt: Mapping[str, object]) -> None:
    resolved = path.resolve(strict=False)
    private_root = (ROOT / ".local").resolve(strict=False)
    if not resolved.is_relative_to(private_root):
        raise ContainerGateError("W7_CONTAINER_HERO_OUTPUT_OUTSIDE_PRIVATE_ROOT")
    if path.is_symlink() or any(
        parent.is_symlink() for parent in path.parents if parent.exists()
    ):
        raise ContainerGateError("W7_CONTAINER_HERO_OUTPUT_SYMLINK_FORBIDDEN")
    try:
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(path.parent, 0o700)
        atomic_write_private_json(path, dict(receipt))
    except (LocalIntegrityError, OSError, TypeError, ValueError) as error:
        raise ContainerGateError("W7_CONTAINER_HERO_OUTPUT_UNAVAILABLE") from error


def _cleanup(engine: str, name: str) -> bool:
    try:
        result = subprocess.run(
            (engine, "rm", "--force", name),
            cwd=ROOT,
            env=_safe_environment(),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return result.returncode == 0


def _arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--engine")
    parser.add_argument("--image", required=True)
    parser.add_argument("--expected-source-commit", required=True)
    parser.add_argument("--nonroot-receipt", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--engine-run-arg", action="append", default=[])
    parser.add_argument("--user-override")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _arguments(argv)
    name = f"aioa-w7-hero-{os.getpid()}-{uuid.uuid4().hex[:8]}"
    engine: str | None = None
    started = False
    cleanup_passed = True
    try:
        if _COMMIT.fullmatch(args.expected_source_commit) is None:
            raise ContainerGateError("CONTAINER_SOURCE_COMMIT_INVALID")
        if _IMAGE.fullmatch(args.image) is None:
            raise ContainerGateError("CONTAINER_IMAGE_REFERENCE_INVALID")
        if not _CLIENT.is_file() or _CLIENT.is_symlink():
            raise ContainerGateError("W7_CONTAINER_HERO_CLIENT_INVALID")
        engine = _resolve_engine(args.engine)
        image_contract = inspect_image(engine, args.image, args.expected_source_commit)
        nonroot_proof = _external_nonroot_proof(
            args.nonroot_receipt,
            image_contract,
            args.expected_source_commit,
        )
        _run(
            _container_run_command(
                engine,
                args.image,
                name,
                args.engine_run_arg,
                args.user_override,
            ),
            timeout=60,
            reason="W7_CONTAINER_HERO_START_FAILED",
            stdout_limit=16 * 1024,
        )
        started = True
        client_source = _CLIENT.read_text(encoding="utf-8")
        client = _run(
            _client_command(engine, name, args.user_override),
            timeout=180,
            reason="W7_CONTAINER_HERO_CLIENT_FAILED",
            input_text=client_source,
        )
        hero = validate_hero_result(
            _strict_json(client.stdout, reason="W7_CONTAINER_HERO_RESULT_INVALID"),
            args.expected_source_commit,
        )
        cleanup_passed = _cleanup(engine, name)
        started = False
        if not cleanup_passed:
            raise ContainerGateError("W7_CONTAINER_HERO_CLEANUP_FAILED")
        receipt = build_gate_receipt(
            image_reference=args.image,
            image_contract=image_contract,
            nonroot_proof=nonroot_proof,
            hero=hero,
            engine_user_override=args.user_override,
        )
        _write_receipt(args.output, receipt)
        print(json.dumps(receipt, indent=2, sort_keys=True))
        return 0
    except (ContainerGateError, OSError, UnicodeDecodeError) as error:
        reason = (
            error.reason
            if isinstance(error, ContainerGateError)
            else "W7_CONTAINER_HERO_GATE_UNAVAILABLE"
        )
        print(
            json.dumps(
                {
                    "aws_mutations": 0,
                    "external_deployments": 0,
                    "reason": reason,
                    "remote_pushes": 0,
                    "status": "FAIL",
                },
                sort_keys=True,
            )
        )
        return 1
    finally:
        if started and engine is not None:
            cleanup_passed = _cleanup(engine, name)
        if not cleanup_passed:
            print("W7 container hero cleanup failed", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
