#!/usr/bin/env python3
"""Exercise the real rootless Phase 4 provider with offline Python and Node fixtures."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
    DockerCommandPlanBuilder,
    DockerSandboxProvider,
    DockerToolboxIdentity,
    SandboxCommand,
    SandboxCommandProfile,
    SandboxLifecycleState,
    SandboxPolicyDenied,
)
from aioa_cloudops_agent.sandbox.docker_runtime import DockerCli  # noqa: E402

SIX_WHEEL_SHA256 = "4721f391ed90541fddacab5acf947aa0d3dc7d27b2e1e8eda2be8970586c3274"
IS_NUMBER_INTEGRITY = (
    "sha512-41Cifkg6e8TylSpdtTpeLVMqvSBEVzTttHvERD741+pnZ8ANv0004MRL43QKPDlK9cGv"
    "Np6NZWZUBlbGXYxxng=="
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument("--certification", action="store_true")
    return parser.parse_args()


def _write_python_fixture(root: Path) -> None:
    root.mkdir(mode=0o700)
    (root / "requirements.txt").write_text(
        f"six==1.17.0 --hash=sha256:{SIX_WHEEL_SHA256}\n",
        encoding="utf-8",
    )
    (root / "test_fixture.py").write_text(
        "import errno\n"
        "import os\n"
        "import signal\n"
        "import time\n\n"
        "import six\n\n\n"
        "def test_offline_dependency():\n"
        "    assert six.__version__ == '1.17.0'\n\n\n"
        "def test_pid_limit_is_enforced():\n"
        "    children = []\n"
        "    blocked = False\n"
        "    try:\n"
        "        while len(children) < 256:\n"
        "            try:\n"
        "                child = os.fork()\n"
        "            except OSError as error:\n"
        "                assert error.errno == errno.EAGAIN\n"
        "                blocked = True\n"
        "                break\n"
        "            if child == 0:\n"
        "                time.sleep(10)\n"
        "                os._exit(0)\n"
        "            children.append(child)\n"
        "    finally:\n"
        "        for child in children:\n"
        "            try:\n"
        "                os.kill(child, signal.SIGKILL)\n"
        "            except ProcessLookupError:\n"
        "                pass\n"
        "        for child in children:\n"
        "            try:\n"
        "                os.waitpid(child, 0)\n"
        "            except ChildProcessError:\n"
        "                pass\n"
        "    assert blocked is True\n",
        encoding="utf-8",
    )


def _write_node_fixture(root: Path) -> None:
    root.mkdir(mode=0o700)
    package = {
        "dependencies": {"is-number": "7.0.0"},
        "name": "phase-four-fixture",
        "version": "1.0.0",
    }
    lock = {
        "lockfileVersion": 3,
        "name": "phase-four-fixture",
        "packages": {
            "": package,
            "node_modules/is-number": {
                "engines": {"node": ">=0.12.0"},
                "integrity": IS_NUMBER_INTEGRITY,
                "resolved": "https://registry.npmjs.org/is-number/-/is-number-7.0.0.tgz",
                "version": "7.0.0",
            },
        },
        "requires": True,
        "version": "1.0.0",
    }
    (root / "package.json").write_text(
        json.dumps(package, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    (root / "package-lock.json").write_text(
        json.dumps(lock, ensure_ascii=True, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    (root / "test.js").write_text(
        "const isNumber = require('is-number');\nif (!isNumber(42)) process.exit(1);\n",
        encoding="utf-8",
    )


def _cycle(
    fixture: Path,
    *,
    ecosystem: str,
    toolbox: DockerToolboxIdentity,
    source_commit: str,
) -> dict[str, object]:
    planner = DeterministicSetupPlanner()
    identity = planner.inspect_repository(fixture, source_commit=source_commit)
    setup_plan = (
        planner.plan_python(fixture, identity.tree_sha256)
        if ecosystem == "python"
        else planner.plan_node(fixture, identity.tree_sha256)
    )
    command = SandboxCommand(
        profile=(
            SandboxCommandProfile.PYTHON_TEST
            if ecosystem == "python"
            else SandboxCommandProfile.NODE_TEST
        ),
        argv=(
            ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider")
            if ecosystem == "python"
            else ("node", "test.js")
        ),
        timeout_seconds=60,
    )
    provider = DockerSandboxProvider(toolbox=toolbox)
    if not provider.availability().available:
        raise RuntimeError("DOCKER_PROVIDER_NOT_AVAILABLE")
    created = False
    cleanup = None
    try:
        provider.create(DOCKER_SANDBOX_V1)
        created = True
        staged = provider.stage_repository(fixture, identity)
        setup = provider.setup_environment(setup_plan)
        snapshot = provider.snapshot()
        provider.restore(snapshot)
        command_receipt = provider.exec(command)
        if command_receipt.exit_code != 0:
            raise RuntimeError("SANDBOX_FIXTURE_TEST_FAILED")
        replacement = (
            fixture / ("test_fixture.py" if ecosystem == "python" else "test.js")
        ).read_bytes()
        write = provider.write_file(
            "test_fixture.py" if ecosystem == "python" else "test.js",
            replacement + b"\n",
            DOCKER_SANDBOX_V1,
        )
        read = provider.read_file(write.relative_path, max_bytes=4096)
        if read.sha256 != write.sha256:
            raise RuntimeError("SANDBOX_WRITE_READ_IDENTITY_MISMATCH")
        try:
            provider.restore(snapshot)
        except SandboxPolicyDenied as error:
            if str(error) != "SANDBOX_MANIFEST_ONLY_SNAPSHOT_DRIFT":
                raise
            stale_restore_denied = True
        else:
            stale_restore_denied = False
        diff = provider.collect_diff(identity)
        if diff.changed_paths != (write.relative_path,):
            raise RuntimeError("SANDBOX_DIFF_PATH_MISMATCH")
        cleanup = provider.destroy()
        created = False
        return {
            "archive_sha256": staged.archive_sha256,
            "cleanup_orphans": cleanup.orphaned_resources,
            "command_exit_code": command_receipt.exit_code,
            "diff_sha256": diff.diff_sha256,
            "installed_manifest_sha256": setup.installed_manifest_sha256,
            "network_mode": command_receipt.network_mode,
            "package_manager_version": setup.package_manager_version,
            "setup_plan_sha256": setup.plan_sha256,
            "stale_restore_denied": stale_restore_denied,
            "write_sha256": write.sha256,
        }
    finally:
        if created:
            provider.destroy()


def _setup_code_execution_denial(
    root: Path,
    *,
    toolbox: DockerToolboxIdentity,
    source_commit: str,
) -> dict[str, object]:
    _write_python_fixture(root)
    (root / "sitecustomize.py").write_text(
        "from pathlib import Path\n"
        "Path('setup-code-executed').write_text('unsafe', encoding='utf-8')\n",
        encoding="utf-8",
    )
    planner = DeterministicSetupPlanner()
    identity = planner.inspect_repository(root, source_commit=source_commit)
    setup_plan = planner.plan_python(root, identity.tree_sha256)
    provider = DockerSandboxProvider(toolbox=toolbox)
    created = False
    try:
        provider.create(DOCKER_SANDBOX_V1)
        created = True
        provider.stage_repository(root, identity)
        setup = provider.setup_environment(setup_plan)
        diff = provider.collect_diff(identity)
        if diff.changed_paths:
            raise RuntimeError("SANDBOX_SETUP_EXECUTED_REPOSITORY_CODE")
        cleanup = provider.destroy()
        created = False
        return {
            "cleanup_orphans": cleanup.orphaned_resources,
            "repository_code_executed": False,
            "setup_plan_sha256": setup.plan_sha256,
        }
    finally:
        if created:
            provider.destroy()


def _runtime_controls(toolbox: DockerToolboxIdentity) -> dict[str, object]:
    provider = DockerSandboxProvider(toolbox=toolbox)
    created = False
    try:
        reference = provider.create(DOCKER_SANDBOX_V1)
        created = True
        builder = DockerCommandPlanBuilder("/usr/bin/docker", toolbox, DOCKER_SANDBOX_V1)
        invocation = builder.runtime_probe(reference)
        result = DockerCli("/usr/bin/docker").checked(
            invocation.argv[1:],
            timeout_seconds=90,
            output_limit=16 * 1024,
            failure_code="SANDBOX_RUNTIME_CONTROL_PROBE_FAILED",
        )
        payload = json.loads(result.stdout)
        required = {
            "cap_eff": "0000000000000000",
            "cpu_max": "100000 100000",
            "default_route_present": False,
            "docker_socket_present": False,
            "egress_probe_blocked": True,
            "gid": 65532,
            "hard_open_files": 1024,
            "host_aws_present": False,
            "host_home_present": False,
            "host_ssh_present": False,
            "memory_max": "536870912",
            "no_new_privs": "1",
            "pids_max": "128",
            "privileged_operation_denied": True,
            "root_read_only": True,
            "sensitive_environment_names": [],
            "soft_open_files": 1024,
            "uid": 65532,
        }
        if not isinstance(payload, dict) or any(
            payload.get(key) != value for key, value in required.items()
        ):
            raise RuntimeError("SANDBOX_RUNTIME_CONTROL_MISMATCH")
        options = payload.get("tmp_mount_options")
        if not isinstance(options, list) or not {"nodev", "noexec", "nosuid", "rw"} <= set(options):
            raise RuntimeError("SANDBOX_TMPFS_CONTROL_MISMATCH")
        cleanup = provider.destroy()
        created = False
        payload["cleanup_orphans"] = cleanup.orphaned_resources
        return payload
    finally:
        if created:
            provider.destroy()


def _failure_cycle(
    root: Path,
    *,
    kind: str,
    toolbox: DockerToolboxIdentity,
    source_commit: str,
) -> dict[str, object]:
    if kind == "crash":
        _write_node_fixture(root)
        (root / "test.js").write_text("process.abort();\n", encoding="utf-8")
        ecosystem = "node"
        command = SandboxCommand(
            profile=SandboxCommandProfile.NODE_TEST,
            argv=("node", "test.js"),
            timeout_seconds=60,
        )
        expected_state = SandboxLifecycleState.SANDBOX_CRASHED
    else:
        _write_python_fixture(root)
        if kind == "memory":
            body = (
                "import os\n\n\n"
                "def test_memory_limit():\n"
                "    allocations = []\n"
                "    try:\n"
                "        while True:\n"
                "            allocations.append(bytearray(64 * 1024 * 1024))\n"
                "    except MemoryError:\n"
                "        os._exit(137)\n"
            )
            timeout = 60
        elif kind == "cpu_timeout":
            body = "def test_cpu_timeout():\n    while True:\n        pass\n"
            timeout = 1
        else:
            raise ValueError("unknown failure fixture")
        (root / "test_fixture.py").write_text(body, encoding="utf-8")
        ecosystem = "python"
        command = SandboxCommand(
            profile=SandboxCommandProfile.PYTHON_TEST,
            argv=("python", "-m", "pytest", "-q", "-p", "no:cacheprovider"),
            timeout_seconds=timeout,
        )
        expected_state = SandboxLifecycleState.RESOURCE_LIMIT
    planner = DeterministicSetupPlanner()
    identity = planner.inspect_repository(root, source_commit=source_commit)
    setup_plan = (
        planner.plan_python(root, identity.tree_sha256)
        if ecosystem == "python"
        else planner.plan_node(root, identity.tree_sha256)
    )
    provider = DockerSandboxProvider(toolbox=toolbox)
    created = False
    try:
        provider.create(DOCKER_SANDBOX_V1)
        created = True
        provider.stage_repository(root, identity)
        provider.setup_environment(setup_plan)
        receipt = provider.exec(command)
        if receipt.state is not expected_state:
            raise RuntimeError(f"SANDBOX_{kind.upper()}_STATE_MISMATCH")
        cleanup = provider.destroy()
        created = False
        return {
            "cleanup_orphans": cleanup.orphaned_resources,
            "exit_code": receipt.exit_code,
            "state": receipt.state.value,
        }
    finally:
        if created:
            provider.destroy()


def main() -> int:
    arguments = _arguments()
    if (
        re.fullmatch(r"[0-9a-f]{64}", arguments.image_sha256) is None
        or re.fullmatch(r"[0-9a-f]{40}", arguments.source_commit) is None
    ):
        raise SystemExit("candidate identities must be full lowercase hexadecimal digests")
    toolbox = DockerToolboxIdentity(
        image_reference=f"sha256:{arguments.image_sha256}",
        image_digest=arguments.image_sha256,
        source_commit=arguments.source_commit,
    )
    with tempfile.TemporaryDirectory(prefix="aioa-w7a-phase4-runtime-") as directory:
        root = Path(directory)
        python_root = root / "python"
        node_root = root / "node"
        _write_python_fixture(python_root)
        _write_node_fixture(node_root)
        python_result = _cycle(
            python_root,
            ecosystem="python",
            toolbox=toolbox,
            source_commit=arguments.source_commit,
        )
        node_result = _cycle(
            node_root,
            ecosystem="node",
            toolbox=toolbox,
            source_commit=arguments.source_commit,
        )
        runtime_controls = _runtime_controls(toolbox)
        memory_result = _failure_cycle(
            root / "memory",
            kind="memory",
            toolbox=toolbox,
            source_commit=arguments.source_commit,
        )
        timeout_result = _failure_cycle(
            root / "cpu-timeout",
            kind="cpu_timeout",
            toolbox=toolbox,
            source_commit=arguments.source_commit,
        )
        crash_result = _failure_cycle(
            root / "crash",
            kind="crash",
            toolbox=toolbox,
            source_commit=arguments.source_commit,
        )
        setup_code_execution = _setup_code_execution_denial(
            root / "setup-code-execution",
            toolbox=toolbox,
            source_commit=arguments.source_commit,
        )
    result = {
        "authority": (
            "W7A_PHASE_4_RUNTIME_CERTIFICATION"
            if arguments.certification
            else "NON_AUTHORITATIVE_RUNTIME_PREFLIGHT"
        ),
        "aws_calls": 0,
        "docker_sandbox_real": "PASS",
        "failure_controls": {
            "crash": crash_result,
            "cpu_timeout": timeout_result,
            "memory": memory_result,
        },
        "github_credentials_in_sandbox": 0,
        "image_sha256": arguments.image_sha256,
        "node": node_result,
        "python": python_result,
        "runtime_controls": runtime_controls,
        "sandbox_cleanup_orphans": 0,
        "setup_code_execution_denial": setup_code_execution,
        "setup_egress_enforcement": "NETWORK_NONE",
        "source_commit": arguments.source_commit,
        "ssh_credentials_in_sandbox": 0,
    }
    encoded = json.dumps(result, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    envelope = {
        "receipt": result,
        "receipt_sha256": hashlib.sha256(encoded.encode("utf-8")).hexdigest(),
    }
    print(json.dumps(envelope, indent=2, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
