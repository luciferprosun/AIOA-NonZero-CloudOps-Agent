#!/usr/bin/env python3
"""Run the truthful W7A Phase 4 offline/Docker-availability proof."""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import sys
import tempfile
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if SOURCE_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SOURCE_ROOT.as_posix())

from aioa_cloudops_agent.sandbox import (  # noqa: E402
    DOCKER_SANDBOX_V1,
    DeterministicSetupPlanner,
    DockerSandboxProvider,
    SandboxUnavailable,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-commit", required=True)
    return parser.parse_args()


def _inventory_digest() -> str:
    inventory = sorted(
        (distribution.metadata.get("Name", "UNKNOWN").casefold(), distribution.version)
        for distribution in importlib.metadata.distributions()
    )
    encoded = json.dumps(inventory, ensure_ascii=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _write_python_fixture(root: Path) -> None:
    root.mkdir(mode=0o700)
    (root / "requirements.txt").write_text(
        f"phase-four-fixture==1.0.0 --hash=sha256:{'a' * 64}\n",
        encoding="utf-8",
    )
    (root / "test_fixture.py").write_text(
        "def test_fixture():\n    assert True\n",
        encoding="utf-8",
    )


def _write_node_fixture(root: Path) -> None:
    root.mkdir(mode=0o700)
    package = {"name": "phase-four-fixture", "version": "1.0.0"}
    lock = {
        "name": "phase-four-fixture",
        "version": "1.0.0",
        "lockfileVersion": 3,
        "requires": True,
        "packages": {"": package},
    }
    (root / "package.json").write_text(json.dumps(package, sort_keys=True), encoding="utf-8")
    (root / "package-lock.json").write_text(json.dumps(lock, sort_keys=True), encoding="utf-8")
    (root / "test.js").write_text("process.exit(0);\n", encoding="utf-8")


def main() -> int:
    arguments = _arguments()
    before_inventory = _inventory_digest()
    planner = DeterministicSetupPlanner()
    provider = DockerSandboxProvider()
    availability = provider.availability()
    with tempfile.TemporaryDirectory(prefix="aioa-w7a-phase4-") as directory:
        root = Path(directory)
        python_root = root / "python"
        node_root = root / "node"
        _write_python_fixture(python_root)
        _write_node_fixture(node_root)
        python_identity = planner.inspect_repository(
            python_root,
            source_commit=arguments.source_commit,
        )
        node_identity = planner.inspect_repository(
            node_root,
            source_commit=arguments.source_commit,
        )
        python_plan = planner.plan_python(python_root, python_identity.tree_sha256)
        node_plan = planner.plan_node(node_root, node_identity.tree_sha256)

        blocker = "NONE"
        try:
            provider.create(DOCKER_SANDBOX_V1)
        except SandboxUnavailable as error:
            blocker = str(error)
        if blocker == "NONE":
            raise RuntimeError("PHASE_4_UNCERTIFIED_RUNTIME_UNEXPECTEDLY_EXECUTED")

    after_inventory = _inventory_digest()
    if before_inventory != after_inventory:
        raise RuntimeError("HOST_PYTHON_PACKAGE_INVENTORY_CHANGED")
    result = {
        "aws_calls": 0,
        "aws_credentials_in_sandbox": 0,
        "coding_offline_network_proof": "BLOCKED_DOCKER",
        "docker_availability": availability.status,
        "docker_runtime_started": False,
        "github_credentials_in_sandbox": 0,
        "host_package_installs": 0,
        "host_python_inventory_stable": True,
        "node_plan_argv": list(node_plan.argv),
        "node_plan_sha256": node_plan.plan_sha256,
        "node_runtime_setup": "BLOCKED_DOCKER",
        "phase_4_result": "PARTIAL_DOCKER_UNAVAILABLE",
        "provider_blocker": blocker,
        "python_plan_argv": list(python_plan.argv),
        "python_plan_sha256": python_plan.plan_sha256,
        "python_runtime_setup": "BLOCKED_DOCKER",
        "sandbox_resources_created": 0,
        "ssh_credentials_in_sandbox": 0,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
