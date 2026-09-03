"""Strict contracts for the sealed workspace evidence and inert proposal boundary."""

from __future__ import annotations

import difflib
import hashlib
import json
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

W2_TARGET_PATH = "render.yaml"
W2_FIELD_PATH = "services[0].dockerCommand"
W2_AFTER_VALUE = "/usr/local/bin/aioa-render-start"
W2_DIFF_FROM = "a/render.yaml"
W2_DIFF_TO = "b/render.yaml"
W2_VERIFICATION_PROFILE_ID = "render_start_contract_v1"
W2_ROLLBACK_STRATEGY = (
    "Restore the exact render.yaml before bytes bound by target_before_sha256; "
    "re-run render_start_contract_v1 before any deployment."
)
W2_BEFORE_BLOCK = (
    "    dockerCommand: >-\n"
    "      /bin/sh -eu -c 'umask 077; test -n \"${AIOA_OPERATOR_TOKEN:-}\" || { "
    "printf \"%s\\n\" \"operator bootstrap missing\" >&2; exit 2; }; printf \"%s\\n\" "
    "\"$AIOA_OPERATOR_TOKEN\" > \"$AIOA_LOCAL_API_TOKEN_PATH\"; chmod 0600 "
    "\"$AIOA_LOCAL_API_TOKEN_PATH\"; unset AIOA_OPERATOR_TOKEN; exec python -m "
    "aioa_cloudops_agent.portable_server'\n"
)
W2_AFTER_LINE = f"    dockerCommand: {W2_AFTER_VALUE}\n"


def canonical_workspace_json_digest(payload: object) -> str:
    """Hash canonical JSON used only for workspace evidence/proposal identity."""

    encoded = json.dumps(
        payload,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def canonical_workspace_unified_diff(before_text: str, after_text: str) -> str:
    """Render the stable UI preview; this rendering is not the patch identity."""

    return "".join(
        difflib.unified_diff(
            before_text.splitlines(keepends=True),
            after_text.splitlines(keepends=True),
            fromfile=W2_DIFF_FROM,
            tofile=W2_DIFF_TO,
            lineterm="\n",
        )
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


class WorkspaceRemediationKind(StrEnum):
    """The single server-known remediation supported by W2."""

    USE_FIXED_RENDER_START_EXECUTABLE = "USE_FIXED_RENDER_START_EXECUTABLE"


class WorkspacePatchProposalOutcome(StrEnum):
    """Closed W2 outcome taxonomy; every non-ready outcome fails closed."""

    PROPOSAL_READY = "PROPOSAL_READY"
    UNSUPPORTED_REMEDIATION = "UNSUPPORTED_REMEDIATION"
    STALE_WORKSPACE = "STALE_WORKSPACE"
    STALE_EVIDENCE = "STALE_EVIDENCE"
    BASE_DIGEST_MISMATCH = "BASE_DIGEST_MISMATCH"
    TARGET_DIGEST_MISMATCH = "TARGET_DIGEST_MISMATCH"
    SUPPORTING_ARTIFACT_MISMATCH = "SUPPORTING_ARTIFACT_MISMATCH"
    AMBIGUOUS_TARGET = "AMBIGUOUS_TARGET"
    POLICY_DENIED = "POLICY_DENIED"
    VALIDATION_FAILURE = "VALIDATION_FAILURE"


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


class WorkspacePatchTarget(NonZeroContract):
    """Exact sealed artifact and before identity targeted by the inert proposal."""

    relative_path: Literal["render.yaml"] = W2_TARGET_PATH
    artifact: WorkspaceArtifactRef
    before_sha256: Sha256Digest

    @model_validator(mode="after")
    def validate_target_binding(self) -> Self:
        if self.artifact.relative_path != self.relative_path:
            raise ValueError("patch target artifact path does not match target path")
        if self.artifact.sha256 != self.before_sha256:
            raise ValueError("patch target before digest does not match artifact identity")
        return self


class WorkspacePatchChange(NonZeroContract):
    """Closed field-level replacement; it cannot carry arbitrary file content or diff text."""

    remediation_kind: Literal[
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE
    ] = WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE
    target_path: Literal["render.yaml"] = W2_TARGET_PATH
    field_path: Literal["services[0].dockerCommand"] = W2_FIELD_PATH
    expected_before_block_sha256: Sha256Digest
    replacement_value: Literal["/usr/local/bin/aioa-render-start"] = W2_AFTER_VALUE

    def canonical_payload(self) -> dict[str, object]:
        """Return stable structured change data with no UI rendering."""

        return {
            "expected_before_block_sha256": self.expected_before_block_sha256,
            "field_path": self.field_path,
            "remediation_kind": self.remediation_kind.value,
            "replacement_value": self.replacement_value,
            "target_path": self.target_path,
        }


class WorkspacePatchPreview(NonZeroContract):
    """Canonical before/after bytes and a deterministic server-rendered unified diff."""

    target_path: Literal["render.yaml"] = W2_TARGET_PATH
    before_text: str = Field(max_length=32 * 1024)
    after_text: str = Field(max_length=32 * 1024)
    before_sha256: Sha256Digest
    after_sha256: Sha256Digest
    unified_diff: str = Field(min_length=1, max_length=64 * 1024)
    diff_from: Literal["a/render.yaml"] = W2_DIFF_FROM
    diff_to: Literal["b/render.yaml"] = W2_DIFF_TO
    line_endings: Literal["LF"] = "LF"
    change: WorkspacePatchChange
    patch_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_canonical_preview(self) -> Self:
        if "\r" in self.before_text or "\r" in self.after_text or "\r" in self.unified_diff:
            raise ValueError("patch preview permits canonical LF line endings only")
        if not self.before_text.endswith("\n") or not self.after_text.endswith("\n"):
            raise ValueError("patch preview texts must end with LF")
        before_digest = hashlib.sha256(self.before_text.encode("utf-8")).hexdigest()
        after_digest = hashlib.sha256(self.after_text.encode("utf-8")).hexdigest()
        if self.before_sha256 != before_digest or self.after_sha256 != after_digest:
            raise ValueError("patch preview content digest mismatch")
        if self.before_text.count(W2_BEFORE_BLOCK) != 1:
            raise ValueError("patch preview before text lacks the exact canonical target")
        expected_after = self.before_text.replace(W2_BEFORE_BLOCK, W2_AFTER_LINE, 1)
        if self.after_text != expected_after:
            raise ValueError("patch preview changes bytes outside the canonical replacement")
        if self.after_text.count(W2_AFTER_LINE) != 1:
            raise ValueError("patch preview after text lacks the exact startup executable")
        if self.change.expected_before_block_sha256 != hashlib.sha256(
            W2_BEFORE_BLOCK.encode("utf-8")
        ).hexdigest():
            raise ValueError("structured change does not bind the exact before block")
        if self.unified_diff != canonical_workspace_unified_diff(
            self.before_text,
            self.after_text,
        ):
            raise ValueError("unified diff is not the canonical server rendering")
        if self.patch_digest != self.canonical_patch_digest():
            raise ValueError("patch digest does not match canonical structured content")
        return self

    def canonical_patch_payload(self) -> dict[str, object]:
        """Return the patch identity independent of UI/diff whitespace."""

        return {
            "after_sha256": self.after_sha256,
            "before_sha256": self.before_sha256,
            "change": self.change.canonical_payload(),
            "schema_version": 1,
            "target_path": self.target_path,
        }

    def canonical_patch_digest(self) -> str:
        return canonical_workspace_json_digest(self.canonical_patch_payload())


class WorkspaceProposalEvidenceRef(NonZeroContract):
    """Exact W1 receipt/artifact identity supporting one W2 proposal."""

    event_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
    operation: Literal[
        WorkspaceOperation.INSPECT,
        WorkspaceOperation.READ,
        WorkspaceOperation.HASH,
    ]
    artifact_path: str | None = None
    artifact_sha256: Sha256Digest
    receipt_sha256: Sha256Digest

    @field_validator("artifact_path")
    @classmethod
    def validate_evidence_artifact_path(cls, value: object) -> str | None:
        if value is None:
            return None
        return normalize_workspace_relative_path(value)

    @model_validator(mode="after")
    def validate_evidence_shape(self) -> Self:
        if self.operation is WorkspaceOperation.INSPECT:
            if self.artifact_path is not None:
                raise ValueError("inspection evidence cannot name one artifact")
        elif self.artifact_path is None:
            raise ValueError("read/hash evidence must name its exact artifact")
        return self


class WorkspacePatchProposal(NonZeroContract):
    """Durable-ready, evidence-bound patch proposal with no apply authority."""

    outcome: Literal[WorkspacePatchProposalOutcome.PROPOSAL_READY] = (
        WorkspacePatchProposalOutcome.PROPOSAL_READY
    )
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: Literal["workspace_render_incident_v1"]
    root_digest: Sha256Digest
    base_root_digest: Sha256Digest
    target_path: Literal["render.yaml"] = W2_TARGET_PATH
    target_before_sha256: Sha256Digest
    remediation_kind: Literal[
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE
    ] = WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE
    canonical_after_sha256: Sha256Digest
    patch_digest: Sha256Digest
    evidence_digest: Sha256Digest
    evidence_references: tuple[WorkspaceProposalEvidenceRef, ...] = Field(
        min_length=5,
        max_length=8,
    )
    supporting_start_script_sha256: Sha256Digest
    expected_runtime_contract_sha256: Sha256Digest
    verification_profile_id: Literal["render_start_contract_v1"] = (
        W2_VERIFICATION_PROFILE_ID
    )
    risk_class: Literal[AuthorityGate.PLAN_AND_CONFIRM] = AuthorityGate.PLAN_AND_CONFIRM
    rollback_strategy: Literal[
        "Restore the exact render.yaml before bytes bound by target_before_sha256; re-run render_start_contract_v1 before any deployment."
    ] = W2_ROLLBACK_STRATEGY
    diagnosis_evidence_paths: tuple[str, ...]
    target: WorkspacePatchTarget
    change: WorkspacePatchChange
    preview: WorkspacePatchPreview
    created_at: datetime
    expires_at: datetime
    proposal_digest: Sha256Digest
    version: Literal[1] = 1
    authorizes_execution: Literal[False] = False
    apply_authority_granted: Literal[False] = False
    mutation_allowed: Literal[False] = False
    process_execution_allowed: Literal[False] = False
    network_allowed: Literal[False] = False

    @field_validator("created_at", "expires_at")
    @classmethod
    def validate_proposal_timestamp(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_proposal_binding(self) -> Self:
        if self.expires_at <= self.created_at:
            raise ValueError("proposal expiry must follow creation")
        if self.root_digest != self.base_root_digest:
            raise ValueError("proposal root and base root digests must match")
        if (
            self.target_path != self.target.relative_path
            or self.target_before_sha256 != self.target.before_sha256
            or self.target_before_sha256 != self.preview.before_sha256
        ):
            raise ValueError("proposal target identity is inconsistent")
        if self.remediation_kind is not self.change.remediation_kind:
            raise ValueError("proposal remediation kind is inconsistent")
        if self.change != self.preview.change:
            raise ValueError("proposal change and preview change must match")
        if (
            self.canonical_after_sha256 != self.preview.after_sha256
            or self.patch_digest != self.preview.patch_digest
        ):
            raise ValueError("proposal patch identity is inconsistent")
        refs = self.evidence_references
        if len({ref.receipt_sha256 for ref in refs}) != len(refs):
            raise ValueError("proposal evidence references must be unique")
        if any(
            ref.run_id != self.run_id
            or ref.trace_id != self.trace_id
            or ref.workspace_id != self.workspace_id
            or ref.fixture_version != self.fixture_version
            for ref in refs
        ):
            raise ValueError("proposal evidence identity does not match the workspace")
        if self.evidence_digest != canonical_workspace_json_digest(
            [ref.model_dump(mode="json") for ref in refs]
        ):
            raise ValueError("proposal evidence digest mismatch")
        by_path = {ref.artifact_path: ref.artifact_sha256 for ref in refs}
        if by_path.get("scripts/render_start.sh") != self.supporting_start_script_sha256:
            raise ValueError("proposal does not bind the startup script evidence")
        if (
            by_path.get("expected_runtime_contract.json")
            != self.expected_runtime_contract_sha256
        ):
            raise ValueError("proposal does not bind the runtime contract evidence")
        expected_paths = (
            "deployment.log",
            "expected_runtime_contract.json",
            "render.yaml",
            "scripts/render_start.sh",
        )
        if self.diagnosis_evidence_paths != expected_paths:
            raise ValueError("proposal diagnosis paths must be exact and canonical")
        if self.proposal_digest != canonical_workspace_json_digest(self.content_payload()):
            raise ValueError("proposal digest does not match canonical bound content")
        return self

    def content_payload(self) -> dict[str, object]:
        """Return durable proposal identity without model text or UI rendering."""

        return {
            "base_root_digest": self.base_root_digest,
            "canonical_after_sha256": self.canonical_after_sha256,
            "diagnosis_evidence_paths": list(self.diagnosis_evidence_paths),
            "evidence_digest": self.evidence_digest,
            "expected_runtime_contract_sha256": self.expected_runtime_contract_sha256,
            "fixture_version": self.fixture_version,
            "patch_digest": self.patch_digest,
            "remediation_kind": self.remediation_kind.value,
            "risk_class": self.risk_class.value,
            "rollback_strategy": self.rollback_strategy,
            "root_digest": self.root_digest,
            "run_id": str(self.run_id),
            "schema_version": self.version,
            "supporting_start_script_sha256": self.supporting_start_script_sha256,
            "target_before_sha256": self.target_before_sha256,
            "target_path": self.target_path,
            "trace_id": str(self.trace_id),
            "verification_profile_id": self.verification_profile_id,
            "workspace_id": str(self.workspace_id),
        }
