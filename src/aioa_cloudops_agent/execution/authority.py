"""Exact durable-human-authority validator for Phase 7 capsules."""

from __future__ import annotations

from collections.abc import Collection
from datetime import UTC, datetime, timedelta

from aioa_cloudops_agent.nz import ApprovalDecision
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

from .contracts import (
    ExecutionApprovalDecision,
    ExecutionAuthorityReceipt,
    ExecutionCapsule,
    hash_decision_nonce,
)


class ExecutionAuthorityDenied(ValueError):
    """Stable value-free denial; remote execution must not start."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def build_execution_approval_decision(
    capsule: ExecutionCapsule,
    *,
    decision: ApprovalDecision,
    actor_session_id: str,
    decision_nonce: str,
    decided_at: datetime,
) -> ExecutionApprovalDecision:
    """Create the durable decision while retaining only a nonce digest."""

    if not isinstance(capsule, ExecutionCapsule):
        raise TypeError("capsule must be ExecutionCapsule")
    values: dict[str, object] = {
        "request_id": capsule.approval_request.request_id,
        "capsule_sha256": capsule.capsule_sha256,
        "request_sha256": capsule.approval_request.request_sha256,
        "decision": decision,
        "actor_session_id": actor_session_id,
        "decision_nonce_sha256": hash_decision_nonce(decision_nonce),
        "decided_at": decided_at,
        "expires_at": capsule.approval_request.expires_at,
    }
    provisional = ExecutionApprovalDecision.model_construct(
        **values,
        decision_sha256="0" * 64,
    )
    return ExecutionApprovalDecision(
        **values,
        decision_sha256=canonical_workspace_json_digest(provisional.content_payload()),
    )


def require_execution_authority(
    capsule: ExecutionCapsule,
    decision: ExecutionApprovalDecision | None,
    *,
    validated_at: datetime | None = None,
    completed_operation_ids: Collection[str] = (),
) -> ExecutionAuthorityReceipt:
    """Validate every binding and replay guard before any actuator can run."""

    if not isinstance(capsule, ExecutionCapsule):
        raise ExecutionAuthorityDenied("EXECUTION_CAPSULE_INVALID")
    if decision is None:
        raise ExecutionAuthorityDenied("EXECUTION_HUMAN_APPROVAL_REQUIRED")
    if not isinstance(decision, ExecutionApprovalDecision):
        raise ExecutionAuthorityDenied("EXECUTION_APPROVAL_INVALID")
    now = validated_at or datetime.now(UTC)
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise ExecutionAuthorityDenied("EXECUTION_VALIDATION_TIME_INVALID")
    request = capsule.approval_request
    if now > request.expires_at or now > decision.expires_at:
        raise ExecutionAuthorityDenied("EXECUTION_APPROVAL_EXPIRED")
    if decision.decision is not ApprovalDecision.APPROVED:
        raise ExecutionAuthorityDenied("EXECUTION_DENIED_BY_HUMAN")
    bindings = (
        (decision.request_id, request.request_id),
        (decision.capsule_sha256, capsule.capsule_sha256),
        (decision.request_sha256, request.request_sha256),
        (decision.actor_session_id, request.actor_session_id),
        (decision.decision_nonce_sha256, request.decision_nonce_sha256),
        (decision.expires_at, request.expires_at),
    )
    if any(left != right for left, right in bindings):
        raise ExecutionAuthorityDenied("EXECUTION_APPROVAL_BINDING_MISMATCH")
    if str(capsule.operation_id) in set(completed_operation_ids):
        raise ExecutionAuthorityDenied("EXECUTION_OPERATION_REPLAY_DENIED")
    material: dict[str, object] = {
        "authority": "EXACT_DURABLE_HUMAN_APPROVAL",
        "capsule_sha256": capsule.capsule_sha256,
        "request_sha256": request.request_sha256,
        "decision_sha256": decision.decision_sha256,
        "operation_id": capsule.operation_id,
        "permitted_operations": capsule.allowed_operations,
        "validated_at": now,
        "granted": True,
        "remote_effect_completed": False,
    }
    provisional = ExecutionAuthorityReceipt.model_construct(
        **material,
        receipt_sha256="0" * 64,
    )
    return ExecutionAuthorityReceipt(
        **material,
        receipt_sha256=canonical_workspace_json_digest(
            provisional.model_dump(mode="json", exclude={"receipt_sha256"})
        ),
    )
