"""Strict Phase 7 contracts joining verified code to later remote authority."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.nz import ApprovalDecision, Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.repair_loop import ValidationStage
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

EXECUTION_CAPSULE_SCHEMA_VERSION = 1
EXECUTION_CAPSULE_AUTHORITY = "AIOA_W7A_EXECUTION_CAPSULE_V1"
EXECUTION_CAPSULE_PROVENANCE = "verified_patchset:finite_repair_loop:execution_capsule_v1"
TARGET_BRANCH_PREFIX = "codex/w7a-verified-pr-"

_OWNER = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,37}[a-z0-9])?$")
_REPOSITORY = re.compile(r"^[a-z0-9](?:[a-z0-9._-]{0,98}[a-z0-9])?$")
_COMMIT = re.compile(r"^[0-9a-f]{40}$")
_BRANCH_ALLOWED = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")


def _utc(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")
    return value


def normalize_branch(value: object) -> str:
    """Reject ambiguous Git ref aliases and return one exact short branch name."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError("execution branch is not canonical")
    if value != unicodedata.normalize("NFC", value):
        raise ValueError("execution branch Unicode is ambiguous")
    forbidden = ("..", "@{", "\\", "//")
    if (
        _BRANCH_ALLOWED.fullmatch(value) is None
        or value.startswith(("-", ".", "/", "refs/"))
        or value.endswith(("/", ".", ".lock"))
        or any(marker in value for marker in forbidden)
        or any(part in {"", ".", ".."} or part.startswith(".") for part in value.split("/"))
    ):
        raise ValueError("execution branch is not canonical")
    return value


class ExecutionOperation(StrEnum):
    """Only operations a later deterministic actuator may request."""

    READ_PRECONDITION = "READ_PRECONDITION"
    CREATE_NONDEFAULT_FEATURE_REF = "CREATE_NONDEFAULT_FEATURE_REF"
    MATERIALIZE_EXACT_PATCHSET = "MATERIALIZE_EXACT_PATCHSET"
    CREATE_EXACT_COMMIT = "CREATE_EXACT_COMMIT"
    PERSIST_EFFECT_OWNERSHIP = "PERSIST_EFFECT_OWNERSHIP"
    PUSH_EXPECTED_FEATURE_REF_ONCE = "PUSH_EXPECTED_FEATURE_REF_ONCE"
    READBACK_REMOTE_REF_AND_COMMIT = "READBACK_REMOTE_REF_AND_COMMIT"
    CREATE_DRAFT_PR = "CREATE_DRAFT_PR"


EXECUTION_OPERATION_ORDER: tuple[ExecutionOperation, ...] = tuple(ExecutionOperation)


class ExecutionCredentialClass(StrEnum):
    NONE = "NONE"
    GITHUB_WRITE_ACTUATOR_ONLY = "GITHUB_WRITE_ACTUATOR_ONLY"


class ExecutionRepositoryIdentity(NonZeroContract):
    """Case-normalized GitHub namespace; arbitrary remotes are impossible."""

    host: Literal["github.com"] = "github.com"
    owner: str
    name: str
    canonical_url: str

    @field_validator("owner")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        if _OWNER.fullmatch(value) is None:
            raise ValueError("execution repository owner must be lowercase canonical text")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if _REPOSITORY.fullmatch(value) is None or value in {".", ".."}:
            raise ValueError("execution repository name must be lowercase canonical text")
        return value

    @model_validator(mode="after")
    def validate_url(self) -> Self:
        expected = f"https://github.com/{self.owner}/{self.name}"
        if self.canonical_url != expected:
            raise ValueError("execution repository URL does not match canonical identity")
        return self

    @classmethod
    def normalize(cls, owner: str, name: str) -> ExecutionRepositoryIdentity:
        normalized_owner = owner.casefold()
        normalized_name = name.casefold()
        return cls(
            owner=normalized_owner,
            name=normalized_name,
            canonical_url=f"https://github.com/{normalized_owner}/{normalized_name}",
        )


class ExecutionSandboxBinding(NonZeroContract):
    """Digest-only identity of the already isolated validation environment."""

    provider: Literal["docker"] = "docker"
    sandbox_id: Uuid7Identifier
    policy_sha256: Sha256Digest
    toolbox_image_sha256: Sha256Digest
    sandbox_receipt_sha256: Sha256Digest
    source_workspace_sha256: Sha256Digest
    run_as: Literal["65532:65532"] = "65532:65532"
    coding_network: Literal["NONE"] = "NONE"
    github_credentials_present: Literal[0] = 0
    aws_credentials_present: Literal[0] = 0
    ssh_credentials_present: Literal[0] = 0


class ExecutionVerificationEvent(NonZeroContract):
    sequence: int = Field(ge=0, le=5)
    stage: ValidationStage
    outcome: Literal["PASS"] = "PASS"
    evidence_sha256: Sha256Digest
    network_mode: Literal["NONE"] = "NONE"


_EXPECTED_VALIDATION_STAGES = (
    ValidationStage.V0_PATCHSET_POLICY,
    ValidationStage.V1_FAST_STATIC,
    ValidationStage.V2_TARGETED_TESTS,
    ValidationStage.V4_SEMANTIC_REVIEW,
    ValidationStage.V5_SECRET_DETERMINISTIC_RECHECK,
    ValidationStage.V6_FINAL_GATES,
)


class ExecutionVerificationBinding(NonZeroContract):
    """Ordered terminal Phase 6 evidence; prose cannot stand in for receipts."""

    repair_loop_receipt_sha256: Sha256Digest
    events: tuple[ExecutionVerificationEvent, ...] = Field(min_length=6, max_length=6)
    review_result: Literal["PASS"] = "PASS"
    policy_recheck: Literal["PASS"] = "PASS"
    secret_scan: Literal["PASS"] = "PASS"
    cleanup_orphans: Literal[0] = 0

    @model_validator(mode="after")
    def validate_event_order(self) -> Self:
        if tuple(event.sequence for event in self.events) != tuple(range(6)):
            raise ValueError("verification events must be contiguous and ordered")
        if tuple(event.stage for event in self.events) != _EXPECTED_VALIDATION_STAGES:
            raise ValueError("verification events do not match the fixed V0-V6 ladder")
        if len({event.evidence_sha256 for event in self.events}) != len(self.events):
            raise ValueError("verification event receipts must be unique")
        return self


class ExecutionCredentialPolicy(NonZeroContract):
    worker: Literal[ExecutionCredentialClass.NONE] = ExecutionCredentialClass.NONE
    sandbox: Literal[ExecutionCredentialClass.NONE] = ExecutionCredentialClass.NONE
    test_process: Literal[ExecutionCredentialClass.NONE] = ExecutionCredentialClass.NONE
    actuator: Literal[ExecutionCredentialClass.GITHUB_WRITE_ACTUATOR_ONLY] = (
        ExecutionCredentialClass.GITHUB_WRITE_ACTUATOR_ONLY
    )
    token_values_retained: Literal[False] = False


class ExecutionApprovalRequestBinding(NonZeroContract):
    """Exact request identity; absence of its later decision grants nothing."""

    request_id: Uuid7Identifier
    actor_session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,127}$")
    decision_nonce_sha256: Sha256Digest
    requested_at: datetime
    expires_at: datetime
    request_sha256: Sha256Digest
    human_decision_present: Literal[False] = False

    @field_validator("requested_at", "expires_at")
    @classmethod
    def validate_time(cls, value: datetime, info: object) -> datetime:
        return _utc(getattr(info, "field_name", "timestamp"), value)

    @model_validator(mode="after")
    def validate_window(self) -> Self:
        if self.expires_at <= self.requested_at:
            raise ValueError("execution approval request must expire after creation")
        return self


class ExecutionCapsule(NonZeroContract):
    """Immutable authorization envelope; it is deliberately not an executor."""

    schema_version: Literal[1] = EXECUTION_CAPSULE_SCHEMA_VERSION
    authority: Literal["AIOA_W7A_EXECUTION_CAPSULE_V1"] = EXECUTION_CAPSULE_AUTHORITY
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    task_id: Uuid7Identifier
    proposal_id: Uuid7Identifier
    operation_id: Uuid7Identifier
    attempt_id: Uuid7Identifier
    repository: ExecutionRepositoryIdentity
    default_branch: str
    base_ref: str
    base_head: str
    target_branch: str
    patchset_sha256: Sha256Digest
    changed_files: tuple[str, ...] = Field(min_length=1, max_length=3)
    verification: ExecutionVerificationBinding
    sandbox: ExecutionSandboxBinding
    credential_policy: ExecutionCredentialPolicy = Field(
        default_factory=ExecutionCredentialPolicy
    )
    allowed_operations: tuple[ExecutionOperation, ...] = EXECUTION_OPERATION_ORDER
    approval_request: ExecutionApprovalRequestBinding
    created_at: datetime
    provenance: Literal[
        "verified_patchset:finite_repair_loop:execution_capsule_v1"
    ] = EXECUTION_CAPSULE_PROVENANCE
    mutation_authority: Literal[False] = False
    github_authority: Literal[False] = False
    aws_authority: Literal[False] = False
    execution_engine: Literal[False] = False
    capsule_sha256: Sha256Digest

    @field_validator("created_at")
    @classmethod
    def validate_created_at(cls, value: datetime) -> datetime:
        return _utc("created_at", value)

    @field_validator("default_branch", "base_ref", "target_branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return normalize_branch(value)

    @field_validator("base_head")
    @classmethod
    def validate_base_head(cls, value: str) -> str:
        if _COMMIT.fullmatch(value) is None:
            raise ValueError("execution base HEAD must be a full lowercase SHA")
        return value

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.target_branch.casefold() == self.default_branch.casefold():
            raise ValueError("execution target must not be the default branch")
        if not self.target_branch.startswith(TARGET_BRANCH_PREFIX):
            raise ValueError("execution target is outside the AIOA-owned namespace")
        if self.base_ref == self.target_branch:
            raise ValueError("execution base and target branch must differ")
        if self.changed_files != tuple(sorted(set(self.changed_files))):
            raise ValueError("execution changed files must be unique and sorted")
        if self.allowed_operations != EXECUTION_OPERATION_ORDER:
            raise ValueError("execution operation set/order is not the closed contract")
        if self.created_at != self.approval_request.requested_at:
            raise ValueError("capsule and approval request timestamps must match")
        expected_request = canonical_workspace_json_digest(self.approval_payload())
        if self.approval_request.request_sha256 != expected_request:
            raise ValueError("execution approval request does not bind capsule authority facts")
        if self.capsule_sha256 != canonical_workspace_json_digest(self.content_payload()):
            raise ValueError("execution capsule digest does not match canonical content")
        return self

    def approval_payload(self) -> dict[str, object]:
        return {
            "actor_session_id": self.approval_request.actor_session_id,
            "allowed_operations": [item.value for item in self.allowed_operations],
            "attempt_id": str(self.attempt_id),
            "base_head": self.base_head,
            "base_ref": self.base_ref,
            "changed_files": list(self.changed_files),
            "decision_nonce_sha256": self.approval_request.decision_nonce_sha256,
            "expires_at": self.approval_request.expires_at.isoformat(),
            "operation_id": str(self.operation_id),
            "patchset_sha256": self.patchset_sha256,
            "proposal_id": str(self.proposal_id),
            "repository": self.repository.model_dump(mode="json"),
            "request_id": str(self.approval_request.request_id),
            "requested_at": self.approval_request.requested_at.isoformat(),
            "run_id": str(self.run_id),
            "sandbox": self.sandbox.model_dump(mode="json"),
            "target_branch": self.target_branch,
            "task_id": str(self.task_id),
            "trace_id": str(self.trace_id),
            "verification": self.verification.model_dump(mode="json"),
        }

    def content_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"capsule_sha256"})

    @property
    def authorizes_execution(self) -> Literal[False]:
        return False


class ExecutionApprovalDecision(NonZeroContract):
    """Separate exact human decision; raw nonce and credentials are never retained."""

    request_id: Uuid7Identifier
    capsule_sha256: Sha256Digest
    request_sha256: Sha256Digest
    decision: ApprovalDecision
    actor_session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._:@/-]{2,127}$")
    decision_nonce_sha256: Sha256Digest
    decided_at: datetime
    expires_at: datetime
    decision_sha256: Sha256Digest

    @field_validator("decided_at", "expires_at")
    @classmethod
    def validate_time(cls, value: datetime, info: object) -> datetime:
        return _utc(getattr(info, "field_name", "timestamp"), value)

    @model_validator(mode="after")
    def validate_decision(self) -> Self:
        if self.decided_at > self.expires_at:
            raise ValueError("execution approval decision is already expired")
        if self.decision_sha256 != canonical_workspace_json_digest(self.content_payload()):
            raise ValueError("execution approval decision digest mismatch")
        return self

    def content_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"decision_sha256"})


class ExecutionAuthorityReceipt(NonZeroContract):
    """Short-lived proof of validation, not remote-effect success."""

    authority: Literal["EXACT_DURABLE_HUMAN_APPROVAL"] = "EXACT_DURABLE_HUMAN_APPROVAL"
    capsule_sha256: Sha256Digest
    request_sha256: Sha256Digest
    decision_sha256: Sha256Digest
    operation_id: Uuid7Identifier
    permitted_operations: tuple[ExecutionOperation, ...]
    validated_at: datetime
    granted: Literal[True] = True
    remote_effect_completed: Literal[False] = False
    receipt_sha256: Sha256Digest

    @field_validator("validated_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc("validated_at", value)

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.permitted_operations != EXECUTION_OPERATION_ORDER:
            raise ValueError("authority receipt operations are not canonical")
        material = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != canonical_workspace_json_digest(material):
            raise ValueError("execution authority receipt digest mismatch")
        return self


def hash_decision_nonce(value: str) -> str:
    if not isinstance(value, str) or not 16 <= len(value) <= 256:
        raise ValueError("execution decision nonce must be bounded")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
