#!/usr/bin/env python3
"""Run the real Codex-worker -> PatchSet -> rootless-Docker Phase 6 proof."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import stat
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if SOURCE_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SOURCE_ROOT.as_posix())

from aioa_cloudops_agent.agent import (  # noqa: E402
    SubprocessJsonRpcTransport,
    WorkerTask,
    WorkerTerminalStatus,
    WorkerWorkspaceIdentity,
    digest_workspace_tree,
    run_codex_worker_task,
)
from aioa_cloudops_agent.nz import (  # noqa: E402
    generate_event_id,
    generate_run_id,
    generate_trace_id,
)
from aioa_cloudops_agent.repair_loop import (  # noqa: E402
    BoundedRepairLoopCoordinator,
    CandidateWorkspace,
    DockerValidationBackend,
    RepairLoopRequest,
    RepairLoopState,
)
from aioa_cloudops_agent.sandbox import (  # noqa: E402
    DOCKER_SANDBOX_V1,
    DeterministicSetupPlanner,
    DockerSandboxProvider,
    DockerToolboxIdentity,
    SandboxCommand,
    SandboxCommandProfile,
    SandboxLifecycleState,
)
from aioa_cloudops_agent.sandbox.docker_runtime import DockerCli  # noqa: E402
from aioa_cloudops_agent.workspace.contracts import (  # noqa: E402
    canonical_workspace_json_digest,
)

FIXTURE = ROOT / "demo" / "w7a_repair_loop_v1"
TARGETED_ARGV = (
    "python",
    "-m",
    "pytest",
    "-q",
    "-p",
    "no:cacheprovider",
    "test_solver.py",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-sha256", required=True)
    parser.add_argument("--toolbox-source-commit", required=True)
    parser.add_argument("--base-head", required=True)
    return parser.parse_args()


def _require_digest(value: str, length: int, label: str) -> str:
    if re.fullmatch(rf"[0-9a-f]{{{length}}}", value) is None:
        raise ValueError(f"{label}_INVALID")
    return value


def _initial_failure(
    base_root: Path,
    *,
    toolbox: DockerToolboxIdentity,
    base_head: str,
) -> dict[str, object]:
    planner = DeterministicSetupPlanner()
    identity = planner.inspect_repository(base_root, source_commit=base_head)
    setup = planner.plan_python(base_root, identity.tree_sha256)
    provider = DockerSandboxProvider(toolbox=toolbox)
    if not provider.availability().available:
        raise RuntimeError("PHASE6_DOCKER_UNAVAILABLE")
    created = False
    try:
        reference = provider.create(DOCKER_SANDBOX_V1)
        created = True
        provider.stage_repository(base_root, identity)
        setup_receipt = provider.setup_environment(setup)
        command = provider.exec(
            SandboxCommand(
                profile=SandboxCommandProfile.PYTHON_TEST,
                argv=TARGETED_ARGV,
                timeout_seconds=60,
            )
        )
        if (
            command.exit_code == 0
            or command.state is not SandboxLifecycleState.COMMAND_FAILED
            or command.network_mode != "NONE"
        ):
            raise RuntimeError("PHASE6_INITIAL_TEST_DID_NOT_FAIL_CLOSED")
        cleanup = provider.destroy()
        created = False
        return {
            "command_argv_sha256": command.argv_sha256,
            "command_state": command.state.value,
            "exit_code": command.exit_code,
            "network_mode": command.network_mode,
            "sandbox_id": str(reference.sandbox_id),
            "setup_plan_sha256": setup_receipt.plan_sha256,
            "cleanup_orphans": cleanup.orphaned_resources,
        }
    finally:
        if created:
            provider.destroy()


def _materialize_fixture(destination: Path) -> None:
    """Copy the trusted fixture with modes matching the sandbox atomic writer."""

    shutil.copytree(FIXTURE, destination)
    destination.chmod(0o700)
    for candidate in sorted(destination.rglob("*")):
        metadata = candidate.lstat()
        if stat.S_ISLNK(metadata.st_mode):
            raise RuntimeError("PHASE6_FIXTURE_LINK_DENIED")
        if stat.S_ISDIR(metadata.st_mode):
            candidate.chmod(0o700)
        elif stat.S_ISREG(metadata.st_mode) and metadata.st_nlink == 1:
            candidate.chmod(0o644)
        else:
            raise RuntimeError("PHASE6_FIXTURE_FILE_TYPE_DENIED")
    if any(path.lstat().st_uid != os.getuid() for path in destination.rglob("*")):
        raise RuntimeError("PHASE6_FIXTURE_OWNER_MISMATCH")


class _CompletedRealWorkerProducer:
    def __init__(
        self,
        *,
        root: Path,
        worker_run_id,
        worker_result,
    ) -> None:
        self._root = root
        self._worker_run_id = worker_run_id
        self._worker_result = worker_result
        self.calls = 0

    def produce(self, attempt_number: int, feedback_code: str | None) -> CandidateWorkspace:
        if attempt_number != 0 or feedback_code is not None or self.calls:
            raise RuntimeError("PHASE6_UNEXPECTED_REAL_WORKER_REPAIR_REQUEST")
        self.calls += 1
        return CandidateWorkspace(
            root=self._root,
            worker_run_id=self._worker_run_id,
            worker_result=self._worker_result,
        )


def _run(arguments: argparse.Namespace) -> dict[str, object]:
    image_sha256 = _require_digest(arguments.image_sha256, 64, "IMAGE_SHA256")
    toolbox_source = _require_digest(
        arguments.toolbox_source_commit,
        40,
        "TOOLBOX_SOURCE_COMMIT",
    )
    base_head = _require_digest(arguments.base_head, 40, "BASE_HEAD")
    toolbox = DockerToolboxIdentity(
        image_reference=f"sha256:{image_sha256}",
        image_digest=image_sha256,
        source_commit=toolbox_source,
    )
    with tempfile.TemporaryDirectory(prefix="aioa-w7a-phase6-") as temporary:
        parent = Path(temporary).resolve()
        base_root = parent / "base"
        candidate_root = parent / "candidate"
        _materialize_fixture(base_root)
        _materialize_fixture(candidate_root)

        initial = _initial_failure(base_root, toolbox=toolbox, base_head=base_head)
        run_id = generate_run_id()
        trace_id = generate_trace_id()
        worker_run_id = generate_event_id()
        workspace_id = generate_event_id()
        worker_task = WorkerTask(
            run_id=run_id,
            task_id=worker_run_id,
            workspace=WorkerWorkspaceIdentity(
                workspace_id=workspace_id,
                root_path=candidate_root.as_posix(),
                expected_base_digest=digest_workspace_tree(candidate_root),
            ),
            instruction=(
                "This is a private disposable coding fixture. Inspect solver.py and "
                "test_solver.py. Correct only the arithmetic implementation in solver.py so "
                "add(2, 3) returns 5. Do not modify the test or requirements. Do not run Python, "
                "pytest, unittest, Node, or any program in this editing workspace; AIOA will run "
                "all code and tests later in its offline Docker sandbox. Do not use network, Git, "
                "GitHub, AWS, credentials, or paths outside this workspace. Create no other file."
            ),
            timeout_seconds=240,
        )
        transport = SubprocessJsonRpcTransport()
        events, worker_result = run_codex_worker_task(worker_task, transport=transport)
        host_code_commands = tuple(
            command.command
            for command in worker_result.commands
            if any(
                marker in command.command.casefold()
                for marker in ("python", "pytest", "unittest", "node ", "npm ")
            )
        )
        if worker_result.status is not WorkerTerminalStatus.SUCCESS:
            raise RuntimeError("PHASE6_REAL_WORKER_FAILED")
        if host_code_commands:
            raise RuntimeError("PHASE6_HOST_CODE_EXECUTION_DENIED")

        request = RepairLoopRequest(
            run_id=run_id,
            trace_id=trace_id,
            task_id=generate_event_id(),
            operation_correlation_id=generate_event_id(),
            workspace_id=workspace_id,
            base_head=base_head,
        )
        producer = _CompletedRealWorkerProducer(
            root=candidate_root,
            worker_run_id=worker_run_id,
            worker_result=worker_result,
        )
        validator = DockerValidationBackend(
            base_root=base_root,
            toolbox=toolbox,
            targeted_test_path="test_solver.py",
        )
        loop = BoundedRepairLoopCoordinator().run(
            request=request,
            base_root=base_root,
            producer=producer,
            validator=validator,
        )
        if loop.status != "PASS" or loop.terminal_state is not RepairLoopState.FINAL_PATCH_READY:
            raise RuntimeError(
                loop.final_failure_code or f"PHASE6_REAL_LOOP_{loop.terminal_state.value}"
            )
        if loop.final_patchset is None:
            raise RuntimeError("PHASE6_FINAL_PATCHSET_MISSING")
        actual_files = tuple(change.path for change in loop.final_patchset.files)
        if actual_files != ("solver.py",):
            raise RuntimeError("PHASE6_ACTUAL_FILE_SET_MISMATCH")
        if "return left + right" not in (candidate_root / "solver.py").read_text(encoding="utf-8"):
            raise RuntimeError("PHASE6_FIX_NOT_SEMANTICALLY_CORRECT")
        sandbox_ids = {
            str(step.sandbox_id)
            for attempt in loop.attempts
            for step in attempt.validation_steps
            if step.sandbox_id is not None
        }
        docker = DockerCli("/usr/bin/docker")
        independent_orphans = 0
        for sandbox_id in sorted(sandbox_ids):
            name = f"aioa-w7a-{sandbox_id}"
            independent_orphans += int(docker.run(("container", "inspect", name)).returncode == 0)
            independent_orphans += int(docker.run(("volume", "inspect", name)).returncode == 0)
        if independent_orphans:
            raise RuntimeError("PHASE6_SANDBOX_ORPHANS_REMAIN")

        result = {
            "authority": "W7A_PHASE_6_REAL_LOCAL_E2E",
            "aws_calls": loop.aws_calls,
            "aws_mutations": loop.aws_mutations,
            "base_head": base_head,
            "coding_network": "NONE",
            "external_deployments": loop.external_deployments,
            "final_files": actual_files,
            "final_patchset_sha256": loop.final_patchset.patchset_sha256,
            "initial_targeted_test": initial,
            "loop_receipt_sha256": loop.receipt_sha256,
            "max_repair_attempts": loop.max_repair_attempts,
            "product_github_mutations": loop.product_github_mutations,
            "real_codex_worker": "PASS",
            "real_docker_sandbox": "PASS",
            "sandbox_cleanup_orphans": loop.sandbox_cleanup_orphans,
            "sandbox_independent_orphans": independent_orphans,
            "status": "PASS",
            "toolbox_image_sha256": image_sha256,
            "validation_stages": tuple(
                step.stage.value for step in loop.attempts[-1].validation_steps
            ),
            "worker_claim_authoritative": False,
            "worker_changed_file_claim_count": len(worker_result.changed_files),
            "worker_claim_matched_actual": worker_result.changed_files == actual_files,
            "worker_event_count": len(events),
            "worker_host_code_test_commands": len(host_code_commands),
            "worker_result_sha256": canonical_workspace_json_digest(
                worker_result.model_dump(mode="json")
            ),
            "worker_status": worker_result.status.value,
        }
        return {
            "receipt": result,
            "receipt_sha256": canonical_workspace_json_digest(result),
        }


def main() -> int:
    try:
        result = _run(_arguments())
    except Exception as error:
        rendered = str(error)
        failure_code = (
            rendered
            if re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", rendered)
            else "PHASE6_UNCLASSIFIED_FAILURE"
        )
        print(
            json.dumps(
                {
                    "failure_code": failure_code,
                    "failure_type": type(error).__name__,
                    "status": "FAIL",
                },
                ensure_ascii=True,
                separators=(",", ":"),
                sort_keys=True,
            )
        )
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=True, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
