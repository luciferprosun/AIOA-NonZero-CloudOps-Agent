"""Canonical W7A execution capsule and human-authority boundary."""

from .authority import (
    ExecutionAuthorityDenied,
    build_execution_approval_decision,
    require_execution_authority,
)
from .capsule import ExecutionCapsuleBuildRequest, build_execution_capsule
from .contracts import (
    EXECUTION_CAPSULE_AUTHORITY,
    EXECUTION_CAPSULE_PROVENANCE,
    EXECUTION_CAPSULE_SCHEMA_VERSION,
    EXECUTION_OPERATION_ORDER,
    TARGET_BRANCH_PREFIX,
    ExecutionApprovalDecision,
    ExecutionApprovalRequestBinding,
    ExecutionAuthorityReceipt,
    ExecutionCapsule,
    ExecutionCredentialClass,
    ExecutionCredentialPolicy,
    ExecutionOperation,
    ExecutionRepositoryIdentity,
    ExecutionSandboxBinding,
    ExecutionVerificationBinding,
    ExecutionVerificationEvent,
    hash_decision_nonce,
    normalize_branch,
)

__all__ = [
    "EXECUTION_CAPSULE_AUTHORITY",
    "EXECUTION_CAPSULE_PROVENANCE",
    "EXECUTION_CAPSULE_SCHEMA_VERSION",
    "EXECUTION_OPERATION_ORDER",
    "TARGET_BRANCH_PREFIX",
    "ExecutionApprovalDecision",
    "ExecutionApprovalRequestBinding",
    "ExecutionAuthorityDenied",
    "ExecutionAuthorityReceipt",
    "ExecutionCapsule",
    "ExecutionCapsuleBuildRequest",
    "ExecutionCredentialClass",
    "ExecutionCredentialPolicy",
    "ExecutionOperation",
    "ExecutionRepositoryIdentity",
    "ExecutionSandboxBinding",
    "ExecutionVerificationBinding",
    "ExecutionVerificationEvent",
    "build_execution_approval_decision",
    "build_execution_capsule",
    "hash_decision_nonce",
    "normalize_branch",
    "require_execution_authority",
]
