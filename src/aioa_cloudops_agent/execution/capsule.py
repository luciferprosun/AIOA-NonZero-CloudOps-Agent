"""Construction of one canonical Phase 7 execution capsule."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field

from aioa_cloudops_agent.github import GitHubRepositoryIdentity
from aioa_cloudops_agent.nz import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.patchset import PatchSet
from aioa_cloudops_agent.repair_loop import (
    RepairLoopResult,
    RepairLoopState,
    ValidationOutcome,
)
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

from .contracts import (
    EXECUTION_OPERATION_ORDER,
    ExecutionApprovalRequestBinding,
    ExecutionCapsule,
    ExecutionCredentialPolicy,
    ExecutionRepositoryIdentity,
    ExecutionSandboxBinding,
    ExecutionVerificationBinding,
    ExecutionVerificationEvent,
    normalize_branch,
)


class ExecutionCapsuleBuildRequest(NonZeroContract):
    proposal_id: Uuid7Identifier
    operation_id: Uuid7Identifier
    attempt_id: Uuid7Identifier
    approval_request_id: Uuid7Identifier
    repository: GitHubRepositoryIdentity
    default_branch: str
    base_ref: str
    target_branch: str
    actor_session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,127}$")
    decision_nonce_sha256: Sha256Digest
    sandbox_id: Uuid7Identifier
    sandbox_policy_sha256: Sha256Digest
    toolbox_image_sha256: Sha256Digest
    sandbox_receipt_sha256: Sha256Digest
    created_at: datetime
    expires_at: datetime


def build_execution_capsule(
    request: ExecutionCapsuleBuildRequest,
    *,
    patchset: PatchSet,
    repair_result: RepairLoopResult,
) -> ExecutionCapsule:
    """Bind actual PatchSet and complete final repair-loop evidence, granting nothing."""

    if not isinstance(request, ExecutionCapsuleBuildRequest):
        raise TypeError("request must be ExecutionCapsuleBuildRequest")
    if not isinstance(patchset, PatchSet) or not isinstance(repair_result, RepairLoopResult):
        raise TypeError("capsule inputs must be validated Phase 5/6 contracts")
    if (
        repair_result.status != "PASS"
        or repair_result.terminal_state is not RepairLoopState.FINAL_PATCH_READY
        or repair_result.final_patchset is None
        or repair_result.final_patchset.patchset_sha256 != patchset.patchset_sha256
    ):
        raise ValueError("execution capsule requires one final verified PatchSet")
    identities = (
        (patchset.run_id, repair_result.run_id),
        (patchset.trace_id, repair_result.trace_id),
        (patchset.task_id, repair_result.task_id),
        (patchset.operation_correlation_id, repair_result.operation_correlation_id),
        (patchset.workspace_id, repair_result.workspace_id),
        (patchset.base_head, repair_result.base_head),
    )
    if any(left != right for left, right in identities):
        raise ValueError("execution capsule inputs do not share one operation identity")
    final_attempt = repair_result.attempts[-1]
    if final_attempt.outcome is not ValidationOutcome.PASS:
        raise ValueError("execution capsule requires a passing terminal attempt")
    events = tuple(
        ExecutionVerificationEvent(
            sequence=index,
            stage=step.stage,
            outcome="PASS",
            evidence_sha256=step.evidence_sha256,
            network_mode=step.network_mode,
        )
        for index, step in enumerate(final_attempt.validation_steps)
    )
    verification = ExecutionVerificationBinding(
        repair_loop_receipt_sha256=repair_result.receipt_sha256,
        events=events,
        review_result="PASS" if repair_result.final_review_passed else "FAIL",
        policy_recheck="PASS" if repair_result.final_policy_recheck_passed else "FAIL",
        secret_scan="PASS" if repair_result.final_secret_scan_passed else "FAIL",
        cleanup_orphans=repair_result.sandbox_cleanup_orphans,
    )
    repository = ExecutionRepositoryIdentity.normalize(
        request.repository.owner,
        request.repository.name,
    )
    sandbox = ExecutionSandboxBinding(
        sandbox_id=request.sandbox_id,
        policy_sha256=request.sandbox_policy_sha256,
        toolbox_image_sha256=request.toolbox_image_sha256,
        sandbox_receipt_sha256=request.sandbox_receipt_sha256,
        source_workspace_sha256=patchset.final_tree_sha256,
    )
    approval = ExecutionApprovalRequestBinding(
        request_id=request.approval_request_id,
        actor_session_id=request.actor_session_id,
        decision_nonce_sha256=request.decision_nonce_sha256,
        requested_at=request.created_at,
        expires_at=request.expires_at,
        request_sha256="0" * 64,
    )
    material: dict[str, object] = {
        "run_id": patchset.run_id,
        "trace_id": patchset.trace_id,
        "task_id": patchset.task_id,
        "proposal_id": request.proposal_id,
        "operation_id": request.operation_id,
        "attempt_id": request.attempt_id,
        "repository": repository,
        "default_branch": normalize_branch(request.default_branch),
        "base_ref": normalize_branch(request.base_ref),
        "base_head": patchset.base_head,
        "target_branch": normalize_branch(request.target_branch),
        "patchset_sha256": patchset.patchset_sha256,
        "changed_files": tuple(change.path for change in patchset.files),
        "verification": verification,
        "sandbox": sandbox,
        "credential_policy": ExecutionCredentialPolicy(),
        "allowed_operations": EXECUTION_OPERATION_ORDER,
        "approval_request": approval,
        "created_at": request.created_at,
    }
    provisional = ExecutionCapsule.model_construct(**material, capsule_sha256="0" * 64)
    request_sha256 = canonical_workspace_json_digest(provisional.approval_payload())
    material["approval_request"] = approval.model_copy(
        update={"request_sha256": request_sha256}
    )
    provisional = ExecutionCapsule.model_construct(**material, capsule_sha256="0" * 64)
    return ExecutionCapsule(
        **material,
        capsule_sha256=canonical_workspace_json_digest(provisional.content_payload()),
    )
