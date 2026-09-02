"""Strict contracts for the W1 sealed read-only workspace boundary."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.domain import AuthorityGate
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.identifiers import Sha256Digest, Uuid7Identifier

_CANONICAL_PATH = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_SENSITIVE_NAMES = frozenset(
    {
        ".aws",
        ".env",
        ".git",
        ".ssh",
        "credentials",
        "id_ed25519",
        "id_rsa",
        "secret",
        "secrets",
    }
)


def normalize_workspace_relative_path(value: object) -> str:
    """Accept one canonical, visible, relative POSIX artifact name."""

    if not isinstance(value, str):
        raise ValueError("workspace artifact path must be text")
    if not value or value != value.strip():
        raise ValueError("workspace artifact path must be non-empty canonical text")
    if "\\" in value or any(unicodedata.category(char).startswith("C") for char in value):
        raise ValueError("workspace artifact path contains a forbidden character")
    if _CANONICAL_PATH.fullmatch(value) is None:
        raise ValueError("workspace artifact path is not canonical POSIX text")
    candidate = PurePosixPath(value)
    if candidate.is_absolute() or candidate.as_posix() != value:
        raise ValueError("workspace artifact path must be canonical and relative")
    if not candidate.parts:
        raise ValueError("workspace artifact path must not be empty")
    for part in candidate.parts:
        if part in {"", ".", ".."} or part.startswith("."):
            raise ValueError("workspace artifact path contains a forbidden segment")
        if len(part) > 128:
            raise ValueError("workspace artifact path segment is too long")
        if part.casefold() in _SENSITIVE_NAMES or PurePosixPath(part).stem.casefold() in _SENSITIVE_NAMES:
            raise ValueError("workspace artifact path is secret-sensitive")
    return value


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("observed_at must be a timezone-aware UTC datetime")
    return value


class WorkspaceArtifactType(StrEnum):
    """Closed public-safe artifact types supported by the W1 fixture."""

    JSON = "JSON"
    MARKDOWN = "MARKDOWN"
    SHELL_SCRIPT = "SHELL"
    TEXT = "TEXT"
    YAML = "YAML"


class WorkspaceOperation(StrEnum):
    """The complete W1 workspace authority surface."""

    INSPECT = "INSPECT"
    LIST = "LIST"
    READ = "READ"
    HASH = "HASH"


class WorkspacePolicyOutcome(StrEnum):
    """Fail-closed decision result for a requested workspace operation."""

    ALLOW = "ALLOW"
    DENY = "DENY"


class WorkspaceEvidenceOutcome(StrEnum):
    """Outcome retained in the in-memory read-only evidence timeline."""

    SUCCESS = "SUCCESS"
    DENIED = "DENIED"
    FAILURE = "FAILURE"


class WorkspaceRef(NonZeroContract):
    """Opaque identity for one server-created sealed workspace."""

    run_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    root_digest: Sha256Digest
    created_from_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_sealed_origin(self) -> Self:
        if self.root_digest != self.created_from_digest:
            raise ValueError("sealed workspace digest must match its fixture origin")
        return self


class WorkspaceArtifactRef(NonZeroContract):
    """Content-addressed identity for one allowlisted regular file."""

    relative_path: str
    type: WorkspaceArtifactType
    size: int = Field(ge=0, le=16 * 1024 * 1024)
    sha256: Sha256Digest
    nlink: int = Field(ge=1, le=1024)

    @field_validator("relative_path")
    @classmethod
    def validate_relative_path(cls, value: object) -> str:
        return normalize_workspace_relative_path(value)


class WorkspacePolicyDecision(NonZeroContract):
    """Explicit server-owned allow/deny decision without execution authority."""

    operation: WorkspaceOperation
    workspace_id: Uuid7Identifier
    artifact_path: str | None = None
    outcome: WorkspacePolicyOutcome
    reason_code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{2,95}$")
    reason: str = Field(min_length=1, max_length=256)
    authority: Literal[AuthorityGate.AUTO] = AuthorityGate.AUTO
    mutation_allowed: Literal[False] = False
    network_allowed: Literal[False] = False

    @field_validator("artifact_path")
    @classmethod
    def validate_artifact_path(cls, value: object) -> str | None:
        if value is None:
            return None
        return normalize_workspace_relative_path(value)

    @model_validator(mode="after")
    def validate_operation_shape(self) -> Self:
        if self.operation in {WorkspaceOperation.READ, WorkspaceOperation.HASH}:
            if self.outcome is WorkspacePolicyOutcome.ALLOW and self.artifact_path is None:
                raise ValueError("allowed artifact operation requires artifact_path")
        elif self.artifact_path is not None:
            raise ValueError("workspace-wide operation must not carry artifact_path")
        return self


class WorkspaceEvidenceReceipt(NonZeroContract):
    """Common provenance record for one bounded workspace observation."""

    event_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    operation: WorkspaceOperation
    outcome: WorkspaceEvidenceOutcome
    artifact: WorkspaceArtifactRef | None = None
    observed_size: int = Field(ge=0, le=16 * 1024 * 1024)
    sha256: Sha256Digest
    returned_bytes: int = Field(ge=0, le=16 * 1024 * 1024)
    truncated: bool
    provenance: Literal["sealed_fixture:workspace_render_incident_v1"]
    observed_at: datetime
    policy: WorkspacePolicyDecision

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_identity_binding(self) -> Self:
        if self.workspace_id != self.policy.workspace_id or self.operation is not self.policy.operation:
            raise ValueError("receipt identity must match its policy decision")
        if self.outcome is WorkspaceEvidenceOutcome.SUCCESS:
            if self.policy.outcome is not WorkspacePolicyOutcome.ALLOW:
                raise ValueError("successful receipt requires an allow decision")
        elif self.policy.outcome is not WorkspacePolicyOutcome.DENY:
            raise ValueError("non-success receipt requires a deny decision")
        if self.returned_bytes > self.observed_size:
            raise ValueError("returned bytes cannot exceed observed size")
        return self


class WorkspaceReadReceipt(WorkspaceEvidenceReceipt):
    """Receipt for a content read or an independent full-file hash."""

    operation: Literal[WorkspaceOperation.READ, WorkspaceOperation.HASH]
    artifact: WorkspaceArtifactRef

    @model_validator(mode="after")
    def validate_read_binding(self) -> Self:
        if self.sha256 != self.artifact.sha256 or self.observed_size != self.artifact.size:
            raise ValueError("read receipt must match the exact artifact identity")
        if self.operation is WorkspaceOperation.READ:
            if self.truncated is not (self.returned_bytes < self.observed_size):
                raise ValueError("read truncation metadata is inconsistent")
        elif self.returned_bytes != 0 or self.truncated:
            raise ValueError("hash receipt cannot claim returned or truncated content")
        return self


class WorkspaceListResult(NonZeroContract):
    """Deterministic capped artifact listing and its evidence receipt."""

    artifacts: tuple[WorkspaceArtifactRef, ...] = Field(max_length=64)
    receipt: WorkspaceEvidenceReceipt

    @model_validator(mode="after")
    def validate_listing(self) -> Self:
        if self.receipt.operation is not WorkspaceOperation.LIST:
            raise ValueError("list result requires a LIST receipt")
        paths = tuple(artifact.relative_path for artifact in self.artifacts)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("artifacts must be unique and canonically ordered")
        return self


class WorkspaceReadResult(NonZeroContract):
    """Bounded UTF-8 text plus an explicit truncation receipt."""

    text: str = Field(max_length=16 * 1024 * 1024)
    receipt: WorkspaceReadReceipt

    @model_validator(mode="after")
    def validate_text_size(self) -> Self:
        if len(self.text.encode("utf-8")) != self.receipt.returned_bytes:
            raise ValueError("read text byte length must match its receipt")
        return self


class WorkspaceHashResult(NonZeroContract):
    """Canonical SHA-256 result with an independently generated receipt."""

    sha256: Sha256Digest
    receipt: WorkspaceReadReceipt

    @model_validator(mode="after")
    def validate_digest(self) -> Self:
        if self.receipt.operation is not WorkspaceOperation.HASH:
            raise ValueError("hash result requires a HASH receipt")
        if self.sha256 != self.receipt.sha256:
            raise ValueError("hash result and receipt digest must match")
        return self


class WorkspaceObservation(NonZeroContract):
    """High-level bounded facts; artifact interpretation remains model work."""

    workspace: WorkspaceRef
    incident_id: Literal["render-runtime-start-127"]
    observed_symptoms: tuple[str, ...] = Field(min_length=1, max_length=8)
    allowed_artifacts: tuple[WorkspaceArtifactRef, ...] = Field(min_length=1, max_length=64)
    recommended_review_order: tuple[str, ...] = Field(min_length=1, max_length=64)
    receipt: WorkspaceEvidenceReceipt

    @model_validator(mode="after")
    def validate_observation(self) -> Self:
        if self.receipt.operation is not WorkspaceOperation.INSPECT:
            raise ValueError("workspace observation requires an INSPECT receipt")
        if self.workspace.workspace_id != self.receipt.workspace_id:
            raise ValueError("workspace observation identity mismatch")
        allowed = tuple(artifact.relative_path for artifact in self.allowed_artifacts)
        if allowed != tuple(sorted(set(allowed))):
            raise ValueError("observation artifacts must be canonically ordered")
        if set(self.recommended_review_order) != set(allowed):
            raise ValueError("review order must cover exactly the allowed artifacts")
        return self
