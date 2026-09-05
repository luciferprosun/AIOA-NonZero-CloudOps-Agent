"""Real local-Git fixtures for the Phase 8 actuator security tests."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from aioa_cloudops_agent.agent import WorkerTerminalStatus
from aioa_cloudops_agent.execution import (
    ExecutionCapsule,
    ExecutionCapsuleBuildRequest,
    build_execution_approval_decision,
    build_execution_capsule,
    hash_decision_nonce,
)
from aioa_cloudops_agent.github.contracts import GitHubRepositoryIdentity
from aioa_cloudops_agent.github.effect_repository import LocalFileGitEffectRepository
from aioa_cloudops_agent.github.repository_service import LocalBareGitRepositoryService
from aioa_cloudops_agent.github.write_actuator import (
    DeterministicGitHubWriteActuator,
    build_git_verification_receipt,
)
from aioa_cloudops_agent.github.write_contracts import GitVerificationReceipt
from aioa_cloudops_agent.nz import ApprovalDecision
from aioa_cloudops_agent.patchset import BoundedPatchSetPolicy, PatchSet, PatchSetContext
from aioa_cloudops_agent.repair_loop import (
    RepairAttemptReceipt,
    RepairLoopResult,
    RepairLoopResultStatus,
    RepairLoopState,
    ValidationOutcome,
    ValidationStage,
    ValidationStepReceipt,
)
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

NOW = datetime(2026, 9, 5, 10, 0, tzinfo=UTC)
RAW_NONCE = "phase8-exact-human-nonce-0001"
BASE_BRANCH = "codex/w7a-agent-execution-slice"
TARGET_BRANCH = "codex/w7a-verified-pr-01890f6c"


def uuid7(suffix: int) -> UUID:
    return UUID(f"01890f6c-4411-7abc-8f4a-6e4f7f0b{suffix:04x}")


def git(*arguments: str, cwd: Path) -> str:
    environment = {
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_AUTHOR_DATE": "@1788602400 +0000",
        "GIT_COMMITTER_DATE": "@1788602400 +0000",
        "HOME": cwd.as_posix(),
        "LANG": "C.UTF-8",
        "PATH": os.environ["PATH"],
    }
    completed = subprocess.run(
        ("git", *arguments),
        cwd=cwd,
        env=environment,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        timeout=20,
    )
    if completed.returncode != 0:
        raise AssertionError("fixture Git command failed")
    return completed.stdout.decode().strip()


def _repair_result(patchset: PatchSet) -> RepairLoopResult:
    stages = (
        ValidationStage.V0_PATCHSET_POLICY,
        ValidationStage.V1_FAST_STATIC,
        ValidationStage.V2_TARGETED_TESTS,
        ValidationStage.V4_SEMANTIC_REVIEW,
        ValidationStage.V5_SECRET_DETERMINISTIC_RECHECK,
        ValidationStage.V6_FINAL_GATES,
    )
    steps = tuple(
        ValidationStepReceipt(
            stage=stage,
            outcome=ValidationOutcome.PASS,
            evidence_sha256=hashlib.sha256(f"phase8:{stage.value}".encode()).hexdigest(),
            sandbox_id=uuid7(20),
            exit_code=0,
        )
        for stage in stages
    )
    attempt = RepairAttemptReceipt(
        attempt_number=0,
        is_repair=False,
        worker_run_id=patchset.worker_run_id,
        worker_status=WorkerTerminalStatus.SUCCESS,
        worker_result_sha256="8" * 64,
        patchset_sha256=patchset.patchset_sha256,
        validation_steps=steps,
        outcome=ValidationOutcome.PASS,
    )
    values = {
        "run_id": patchset.run_id,
        "trace_id": patchset.trace_id,
        "task_id": patchset.task_id,
        "operation_correlation_id": patchset.operation_correlation_id,
        "workspace_id": patchset.workspace_id,
        "base_head": patchset.base_head,
        "status": RepairLoopResultStatus.PASS,
        "terminal_state": RepairLoopState.FINAL_PATCH_READY,
        "state_history": (
            RepairLoopState.PROPOSED_PATCH,
            RepairLoopState.VALIDATING,
            RepairLoopState.VALIDATED,
            RepairLoopState.REVIEWING,
            RepairLoopState.REVIEW_PASS,
            RepairLoopState.FINAL_PATCH_READY,
        ),
        "attempts": (attempt,),
        "final_patchset": patchset,
        "each_repair_new_patchset_hash": True,
        "final_review_passed": True,
        "final_policy_recheck_passed": True,
        "final_secret_scan_passed": True,
        "sandbox_cleanup_orphans": 0,
    }
    provisional = RepairLoopResult.model_construct(**values, receipt_sha256="0" * 64)
    return RepairLoopResult(
        **values,
        receipt_sha256=canonical_workspace_json_digest(provisional.content_payload()),
    )


class PassingVerifier:
    def __init__(self, *, clock: datetime = NOW + timedelta(minutes=2)) -> None:
        self.clock = clock
        self.calls = 0

    def verify(
        self,
        *,
        workspace: Path,
        capsule: ExecutionCapsule,
        patchset: PatchSet,
    ) -> GitVerificationReceipt:
        self.calls += 1
        assert (workspace / "solver.py").read_text(encoding="utf-8") == (
            "def add(a, b):\n    return a + b\n"
        )
        return build_git_verification_receipt(
            capsule,
            patchset,
            verified_at=self.clock,
            execution_evidence_sha256=canonical_workspace_json_digest(
                {
                    "authority": "LOCAL_BARE_REMOTE_TEST_VERIFIER",
                    "patchset_sha256": patchset.patchset_sha256,
                }
            ),
        )


@dataclass
class Phase8Fixture:
    bare: Path
    base_root: Path
    final_root: Path
    base_head: str
    default_head: str
    patchset: PatchSet
    capsule: ExecutionCapsule
    service: LocalBareGitRepositoryService
    repository: LocalFileGitEffectRepository
    verifier: PassingVerifier
    actuator: DeterministicGitHubWriteActuator


def build_phase8_fixture(
    tmp_path: Path,
    *,
    approved: bool = True,
    expires_at: datetime = NOW + timedelta(days=1),
    remote_extra_files: int = 0,
) -> Phase8Fixture:
    tmp_path.mkdir(parents=True, exist_ok=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    git("init", "--initial-branch=main", cwd=seed)
    (seed / "solver.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    for index in range(remote_extra_files):
        path = seed / "unrelated" / f"file-{index:04d}.txt"
        path.parent.mkdir(exist_ok=True)
        path.write_text(f"unrelated {index}\n", encoding="utf-8")
    git("add", "-A", cwd=seed)
    git(
        "-c",
        "user.name=AIOA Fixture",
        "-c",
        "user.email=fixture@aioa.invalid",
        "commit",
        "--no-gpg-sign",
        "-m",
        "fixture base",
        cwd=seed,
    )
    base_head = git("rev-parse", "HEAD", cwd=seed)
    git("branch", BASE_BRANCH, base_head, cwd=seed)
    bare = tmp_path / "remote.git"
    git("clone", "--bare", seed.as_posix(), bare.as_posix(), cwd=tmp_path)

    base_root = tmp_path / "base"
    final_root = tmp_path / "final"
    base_root.mkdir()
    final_root.mkdir()
    (base_root / "solver.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    (final_root / "solver.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    context = PatchSetContext(
        patchset_id=uuid7(1),
        task_id=uuid7(2),
        operation_correlation_id=uuid7(3),
        run_id=uuid7(4),
        trace_id=uuid7(5),
        worker_run_id=uuid7(6),
        workspace_id=uuid7(7),
        observed_at=NOW,
    )
    patchset = BoundedPatchSetPolicy().evaluate(
        base_root=base_root,
        final_root=final_root,
        base_head=base_head,
        context=context,
    )
    capsule = build_execution_capsule(
        ExecutionCapsuleBuildRequest(
            proposal_id=uuid7(8),
            operation_id=uuid7(9),
            attempt_id=uuid7(10),
            approval_request_id=uuid7(11),
            repository=GitHubRepositoryIdentity.create(
                "luciferprosun",
                "AIOA-NonZero-CloudOps-Agent",
            ),
            default_branch="main",
            base_ref=BASE_BRANCH,
            target_branch=TARGET_BRANCH,
            actor_session_id="operator-session-01",
            decision_nonce_sha256=hash_decision_nonce(RAW_NONCE),
            sandbox_id=uuid7(20),
            sandbox_policy_sha256="a" * 64,
            toolbox_image_sha256="7" * 64,
            sandbox_receipt_sha256="b" * 64,
            created_at=NOW,
            expires_at=expires_at,
        ),
        patchset=patchset,
        repair_result=_repair_result(patchset),
    )
    state_path = tmp_path / "authority" / "github-effects.json"
    repository = LocalFileGitEffectRepository(state_path.resolve())
    if approved:
        repository.save_decision(
            build_execution_approval_decision(
                capsule,
                decision=ApprovalDecision.APPROVED,
                actor_session_id="operator-session-01",
                decision_nonce=RAW_NONCE,
                decided_at=NOW + timedelta(minutes=1),
            )
        )
    service = LocalBareGitRepositoryService(bare.resolve(), capsule.repository)
    verifier = PassingVerifier()
    actuator = DeterministicGitHubWriteActuator(
        service,
        repository,
        verifier,
        clock=lambda: NOW + timedelta(minutes=5),
        effect_id_factory=lambda: uuid7(30),
    )
    return Phase8Fixture(
        bare=bare,
        base_root=base_root,
        final_root=final_root,
        base_head=base_head,
        default_head=git("rev-parse", "refs/heads/main", cwd=bare),
        patchset=patchset,
        capsule=capsule,
        service=service,
        repository=repository,
        verifier=verifier,
        actuator=actuator,
    )
