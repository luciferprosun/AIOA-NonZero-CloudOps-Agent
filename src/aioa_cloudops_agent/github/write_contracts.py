"""Strict Phase 8 contracts for one deterministic Git remote effect."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.execution import ExecutionRepositoryIdentity, normalize_branch
from aioa_cloudops_agent.nz import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

_COMMIT = frozenset("0123456789abcdef")


def _utc(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")
    return value


def _commit(name: str, value: str) -> str:
    if len(value) != 40 or any(character not in _COMMIT for character in value):
        raise ValueError(f"{name} must be one full lowercase Git object id")
    return value


class GitWriteDisposition(StrEnum):
    VERIFIED = "VERIFIED"
    DENIED = "DENIED"
    UNKNOWN = "UNKNOWN"


class GitPushAcknowledgement(StrEnum):
    ACKNOWLEDGED = "ACKNOWLEDGED"
    UNKNOWN = "UNKNOWN"


class GitRemoteObservation(NonZeroContract):
    """Independent read-only truth captured before any remote write."""

    repository: ExecutionRepositoryIdentity
    default_branch: str
    base_ref: str
    base_head: str
    target_branch: str
    target_head: str | None = None
    observed_at: datetime
    authority: Literal["INDEPENDENT_READ_ONLY_GIT"] = "INDEPENDENT_READ_ONLY_GIT"
    observation_sha256: Sha256Digest

    @field_validator("default_branch", "base_ref", "target_branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return normalize_branch(value)

    @field_validator("base_head")
    @classmethod
    def validate_base_head(cls, value: str) -> str:
        return _commit("base_head", value)

    @field_validator("target_head")
    @classmethod
    def validate_target_head(cls, value: str | None) -> str | None:
        return None if value is None else _commit("target_head", value)

    @field_validator("observed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc("observed_at", value)

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        material = self.model_dump(mode="json", exclude={"observation_sha256"})
        if self.observation_sha256 != canonical_workspace_json_digest(material):
            raise ValueError("remote observation digest mismatch")
        return self


class GitVerificationReceipt(NonZeroContract):
    """Credential-free verification of the exact materialized PatchSet."""

    capsule_sha256: Sha256Digest
    patchset_sha256: Sha256Digest
    workspace_tree_sha256: Sha256Digest
    repair_loop_receipt_sha256: Sha256Digest
    sandbox_receipt_sha256: Sha256Digest
    execution_evidence_sha256: Sha256Digest
    result: Literal["PASS"] = "PASS"
    network_mode: Literal["NONE"] = "NONE"
    github_credentials_present: Literal[0] = 0
    aws_credentials_present: Literal[0] = 0
    ssh_credentials_present: Literal[0] = 0
    verified_at: datetime
    receipt_sha256: Sha256Digest

    @field_validator("verified_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc("verified_at", value)

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        material = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != canonical_workspace_json_digest(material):
            raise ValueError("Git verification receipt digest mismatch")
        return self


class GitCommitIdentity(NonZeroContract):
    """Exact deterministic local commit prepared before effect ownership."""

    commit_sha: str
    tree_sha: str
    parent_sha: str
    message_sha256: Sha256Digest
    author_policy: Literal["AIOA_W7A_DETERMINISTIC_AUTHOR_V1"] = (
        "AIOA_W7A_DETERMINISTIC_AUTHOR_V1"
    )

    @field_validator("commit_sha", "tree_sha", "parent_sha")
    @classmethod
    def validate_object_id(cls, value: str, info: object) -> str:
        return _commit(getattr(info, "field_name", "object_id"), value)


class GitRemoteCommitReadback(NonZeroContract):
    """Independent post-write ref, commit and tree observation."""

    target_branch: str
    commit_sha: str
    tree_sha: str
    observed_at: datetime
    authority: Literal["INDEPENDENT_READ_ONLY_GIT"] = "INDEPENDENT_READ_ONLY_GIT"

    @field_validator("target_branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return normalize_branch(value)

    @field_validator("commit_sha", "tree_sha")
    @classmethod
    def validate_object_id(cls, value: str, info: object) -> str:
        return _commit(getattr(info, "field_name", "object_id"), value)

    @field_validator("observed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc("observed_at", value)


class GitEffectOwnership(NonZeroContract):
    """Durable at-most-once ownership persisted before the first push."""

    operation_id: Uuid7Identifier
    effect_id: Uuid7Identifier
    idempotency_key: str = Field(pattern=r"^github-write/[0-9a-f]{64}$")
    capsule_sha256: Sha256Digest
    approval_request_sha256: Sha256Digest
    approval_decision_sha256: Sha256Digest
    authority_receipt_sha256: Sha256Digest
    repository: ExecutionRepositoryIdentity
    base_ref: str
    base_head: str
    target_branch: str
    expected_commit: GitCommitIdentity
    verification_receipt_sha256: Sha256Digest
    claimed_at: datetime
    remote_write_started: Literal[False] = False
    ownership_sha256: Sha256Digest

    @field_validator("base_ref", "target_branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return normalize_branch(value)

    @field_validator("base_head")
    @classmethod
    def validate_base_head(cls, value: str) -> str:
        return _commit("base_head", value)

    @field_validator("claimed_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc("claimed_at", value)

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        expected_key = "github-write/" + hashlib.sha256(
            f"{self.operation_id}:{self.capsule_sha256}".encode("ascii")
        ).hexdigest()
        if self.idempotency_key != expected_key:
            raise ValueError("Git effect idempotency key mismatch")
        if self.expected_commit.parent_sha != self.base_head:
            raise ValueError("Git effect parent does not match approved base")
        material = self.model_dump(mode="json", exclude={"ownership_sha256"})
        if self.ownership_sha256 != canonical_workspace_json_digest(material):
            raise ValueError("Git effect ownership digest mismatch")
        return self


class GitRemoteWriteReceipt(NonZeroContract):
    """Success exists only after independent remote commit/tree readback."""

    operation_id: Uuid7Identifier
    effect_id: Uuid7Identifier
    ownership_sha256: Sha256Digest
    capsule_sha256: Sha256Digest
    repository: ExecutionRepositoryIdentity
    base_head: str
    target_branch: str
    expected_commit: GitCommitIdentity
    observed_commit_sha: str
    observed_tree_sha: str
    push_acknowledgement: GitPushAcknowledgement
    product_runtime_writes: Literal[1] = 1
    force_pushes: Literal[0] = 0
    tag_writes: Literal[0] = 0
    default_branch_writes: Literal[0] = 0
    merges: Literal[0] = 0
    verified_at: datetime
    receipt_sha256: Sha256Digest

    @field_validator("base_head", "observed_commit_sha", "observed_tree_sha")
    @classmethod
    def validate_object_id(cls, value: str, info: object) -> str:
        return _commit(getattr(info, "field_name", "object_id"), value)

    @field_validator("target_branch")
    @classmethod
    def validate_branch(cls, value: str) -> str:
        return normalize_branch(value)

    @field_validator("verified_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc("verified_at", value)

    @model_validator(mode="after")
    def validate_readback(self) -> Self:
        if (
            self.observed_commit_sha != self.expected_commit.commit_sha
            or self.observed_tree_sha != self.expected_commit.tree_sha
        ):
            raise ValueError("remote receipt does not prove the expected commit/tree")
        material = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != canonical_workspace_json_digest(material):
            raise ValueError("remote write receipt digest mismatch")
        return self


class GitReconciliationMarker(NonZeroContract):
    """Durable UNKNOWN state; it never authorizes a blind retry."""

    operation_id: Uuid7Identifier
    effect_id: Uuid7Identifier
    ownership_sha256: Sha256Digest
    expected_commit_sha: str
    expected_tree_sha: str
    observed_commit_sha: str | None = None
    observed_tree_sha: str | None = None
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,95}$")
    write_attempted: Literal[True] = True
    blind_retry_allowed: Literal[False] = False
    recorded_at: datetime
    marker_sha256: Sha256Digest

    @field_validator(
        "expected_commit_sha",
        "expected_tree_sha",
        "observed_commit_sha",
        "observed_tree_sha",
    )
    @classmethod
    def validate_object_id(cls, value: str | None, info: object) -> str | None:
        return None if value is None else _commit(getattr(info, "field_name", "object_id"), value)

    @field_validator("recorded_at")
    @classmethod
    def validate_time(cls, value: datetime) -> datetime:
        return _utc("recorded_at", value)

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        material = self.model_dump(mode="json", exclude={"marker_sha256"})
        if self.marker_sha256 != canonical_workspace_json_digest(material):
            raise ValueError("Git reconciliation marker digest mismatch")
        return self


class GitWriteActuationResult(NonZeroContract):
    """Closed result that distinguishes denial from an ambiguous remote effect."""

    disposition: GitWriteDisposition
    receipt: GitRemoteWriteReceipt | None = None
    reconciliation: GitReconciliationMarker | None = None
    failure_code: str | None = Field(default=None, pattern=r"^[A-Z][A-Z0-9_]{2,95}$")

    @model_validator(mode="after")
    def validate_shape(self) -> Self:
        if self.disposition is GitWriteDisposition.VERIFIED:
            if self.receipt is None or self.reconciliation is not None or self.failure_code is not None:
                raise ValueError("verified Git result requires only its receipt")
        elif self.disposition is GitWriteDisposition.UNKNOWN:
            if self.reconciliation is None or self.receipt is not None or self.failure_code is not None:
                raise ValueError("unknown Git result requires only reconciliation evidence")
        elif self.failure_code is None or self.receipt is not None or self.reconciliation is not None:
            raise ValueError("denied Git result requires only a failure code")
        return self
