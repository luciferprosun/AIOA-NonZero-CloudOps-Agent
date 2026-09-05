"""Validated Phase 5/6 fixtures shared by Phase 7 boundary tests."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from aioa_cloudops_agent.agent import WorkerTerminalStatus
from aioa_cloudops_agent.execution import (
    ExecutionCapsule,
    ExecutionCapsuleBuildRequest,
    build_execution_capsule,
    hash_decision_nonce,
)
from aioa_cloudops_agent.github import GitHubRepositoryIdentity
from aioa_cloudops_agent.patchset import BoundedPatchSetPolicy, PatchSetContext
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

NOW = datetime(2026, 9, 5, 8, 0, tzinfo=UTC)
BASE_HEAD = "d" * 40
RAW_NONCE = "phase7-exact-human-nonce-0001"


def uuid7(suffix: int) -> UUID:
    return UUID(f"01890f6c-3311-7abc-8f4a-6e4f7f0b{suffix:04x}")


def build_phase5_phase6_fixture(tmp_path: Path):
    base = tmp_path / "base"
    final = tmp_path / "final"
    base.mkdir(parents=True)
    final.mkdir(parents=True)
    (base / "solver.py").write_text("def add(a, b):\n    return a - b\n", encoding="utf-8")
    (final / "solver.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
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
        base_root=base,
        final_root=final,
        base_head=BASE_HEAD,
        context=context,
    )
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
            evidence_sha256=hashlib.sha256(stage.value.encode("ascii")).hexdigest(),
            sandbox_id=uuid7(20),
            exit_code=0,
        )
        for stage in stages
    )
    attempt = RepairAttemptReceipt(
        attempt_number=0,
        is_repair=False,
        worker_run_id=context.worker_run_id,
        worker_status=WorkerTerminalStatus.SUCCESS,
        worker_result_sha256="8" * 64,
        patchset_sha256=patchset.patchset_sha256,
        validation_steps=steps,
        outcome=ValidationOutcome.PASS,
    )
    values = {
        "run_id": context.run_id,
        "trace_id": context.trace_id,
        "task_id": context.task_id,
        "operation_correlation_id": context.operation_correlation_id,
        "workspace_id": context.workspace_id,
        "base_head": BASE_HEAD,
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
    loop = RepairLoopResult(
        **values,
        receipt_sha256=canonical_workspace_json_digest(provisional.content_payload()),
    )
    return patchset, loop


def build_capsule(tmp_path: Path) -> ExecutionCapsule:
    patchset, loop = build_phase5_phase6_fixture(tmp_path)
    request = ExecutionCapsuleBuildRequest(
        proposal_id=uuid7(8),
        operation_id=uuid7(9),
        attempt_id=uuid7(10),
        approval_request_id=uuid7(11),
        repository=GitHubRepositoryIdentity.create(
            "luciferprosun",
            "AIOA-NonZero-CloudOps-Agent",
        ),
        default_branch="main",
        base_ref="codex/w7a-agent-execution-slice",
        target_branch="codex/w7a-verified-pr-01890f6c",
        actor_session_id="operator-session-01",
        decision_nonce_sha256=hash_decision_nonce(RAW_NONCE),
        sandbox_id=uuid7(20),
        sandbox_policy_sha256="a" * 64,
        toolbox_image_sha256="7" * 64,
        sandbox_receipt_sha256="b" * 64,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=30),
    )
    return build_execution_capsule(request, patchset=patchset, repair_result=loop)
