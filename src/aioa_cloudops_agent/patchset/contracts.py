"""Strict provider-neutral contracts for one bounded canonical PatchSet."""

from __future__ import annotations

import hashlib
import unicodedata
from datetime import datetime, timedelta
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.nz import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.redaction import contains_sensitive_material
from aioa_cloudops_agent.sandbox import RepositorySourceIdentity
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

PATCHSET_POLICY_VERSION = "W7A_BOUNDED_PATCHSET_V1"
PATCHSET_PROVENANCE = "actual_workspace_state:bounded_patchset_v1"


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError("PatchSet timestamps must be timezone-aware UTC")
    return value


class PatchOperation(StrEnum):
    """Filesystem operations derived from base and final tree state."""

    ADD = "ADD"
    MODIFY = "MODIFY"
    DELETE = "DELETE"


class PatchPolicyResult(StrEnum):
    """Closed result vocabulary for a canonical PatchSet."""

    PASS = "PASS"
    DENY = "DENY"


class FileContentIdentity(NonZeroContract):
    """Content and mode identity for one regular single-link file."""

    sha256: Sha256Digest
    size: int = Field(ge=0, le=16 * 1024 * 1024)
    mode: int = Field(ge=0, le=0o777)


class PatchFileChange(NonZeroContract):
    """One actual changed path with exact before and after identities."""

    path: str = Field(min_length=1, max_length=1024)
    operation: PatchOperation
    before: FileContentIdentity | None
    after: FileContentIdentity | None
    lines_added: int = Field(ge=0, le=300)
    lines_deleted: int = Field(ge=0, le=300)
    binary: Literal[False] = False

    @field_validator("path")
    @classmethod
    def validate_path(cls, value: str) -> str:
        candidate = PurePosixPath(value)
        if (
            value != unicodedata.normalize("NFC", value)
            or "\\" in value
            or candidate.is_absolute()
            or candidate.as_posix() != value
            or not candidate.parts
            or any(part in {"", ".", ".."} for part in candidate.parts)
        ):
            raise ValueError("PatchSet file path must be exact canonical relative POSIX text")
        return value

    @model_validator(mode="after")
    def validate_operation_shape(self) -> Self:
        if self.operation is PatchOperation.ADD:
            if self.before is not None or self.after is None:
                raise ValueError("ADD requires only an after identity")
        elif self.operation is PatchOperation.DELETE:
            if self.before is None or self.after is not None:
                raise ValueError("DELETE requires only a before identity")
        else:
            if self.before is None or self.after is None:
                raise ValueError("MODIFY requires before and after identities")
            if self.before == self.after:
                raise ValueError("MODIFY must change exact file identity")
            if self.before.mode != self.after.mode:
                raise ValueError("MODIFY cannot conceal a mode change")
        return self


class PatchTotals(NonZeroContract):
    """Deterministic bounded aggregate over the actual changed files."""

    files_changed: int = Field(ge=1, le=3)
    lines_added: int = Field(ge=0, le=300)
    lines_deleted: int = Field(ge=0, le=300)
    changed_lines: int = Field(ge=0, le=300)
    binary_change_count: Literal[0] = 0
    deletion_count: int = Field(ge=0, le=1)
    mass_delete: Literal[False] = False

    @model_validator(mode="after")
    def validate_line_total(self) -> Self:
        if self.changed_lines != self.lines_added + self.lines_deleted:
            raise ValueError("changed_lines must equal additions plus deletions")
        if self.deletion_count and self.lines_deleted > 150:
            raise ValueError("deletion exceeds the bounded mass-delete ceiling")
        return self


class PatchSecretScanSummary(NonZeroContract):
    """Value-free scan receipt bound to changed after-content identities."""

    scanner_version: Literal["NZ_PROVIDER_NEUTRAL_SECRET_SCAN_V1"] = (
        "NZ_PROVIDER_NEUTRAL_SECRET_SCAN_V1"
    )
    result: Literal[PatchPolicyResult.PASS] = PatchPolicyResult.PASS
    files_scanned: int = Field(ge=0, le=3)
    finding_count: Literal[0] = 0
    scanned_content_sha256: Sha256Digest
    secret_values_retained: Literal[False] = False
    receipt_sha256: Sha256Digest

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        payload = self.model_dump(mode="json", exclude={"receipt_sha256"})
        if self.receipt_sha256 != canonical_workspace_json_digest(payload):
            raise ValueError("secret scan receipt digest mismatch")
        return self


class PatchSetContext(NonZeroContract):
    """Caller-owned correlation and provenance for one deterministic evaluation."""

    patchset_id: Uuid7Identifier
    task_id: Uuid7Identifier
    operation_correlation_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    worker_run_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)


class PatchSet(NonZeroContract):
    """Canonical, actual-state PatchSet; it grants no apply or remote authority."""

    schema_version: Literal[1] = 1
    patchset_id: Uuid7Identifier
    task_id: Uuid7Identifier
    operation_correlation_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    worker_run_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    repository: RepositorySourceIdentity
    base_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    final_tree_sha256: Sha256Digest
    canonical_diff: str = Field(min_length=1, max_length=2 * 1024 * 1024)
    canonical_diff_sha256: Sha256Digest
    files: tuple[PatchFileChange, ...] = Field(min_length=1, max_length=3)
    totals: PatchTotals
    policy_version: Literal["W7A_BOUNDED_PATCHSET_V1"] = PATCHSET_POLICY_VERSION
    policy_result: Literal[PatchPolicyResult.PASS] = PatchPolicyResult.PASS
    secret_scan: PatchSecretScanSummary
    authority: Literal["DETERMINISTIC_SERVER_POLICY"] = "DETERMINISTIC_SERVER_POLICY"
    provenance: Literal["actual_workspace_state:bounded_patchset_v1"] = PATCHSET_PROVENANCE
    observed_at: datetime
    mutation_authority: Literal[False] = False
    github_authority: Literal[False] = False
    aws_authority: Literal[False] = False
    patchset_sha256: Sha256Digest

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @field_validator("canonical_diff")
    @classmethod
    def reject_sensitive_diff(cls, value: str) -> str:
        if contains_sensitive_material(value):
            raise ValueError("canonical diff contains credential-shaped material")
        return value

    @model_validator(mode="after")
    def validate_bindings(self) -> Self:
        if self.repository.source_commit is None or self.base_head != self.repository.source_commit:
            raise ValueError("base HEAD must match the exact repository source commit")
        if (
            self.canonical_diff_sha256
            != hashlib.sha256(self.canonical_diff.encode("utf-8")).hexdigest()
        ):
            raise ValueError("canonical diff digest mismatch")
        paths = tuple(change.path for change in self.files)
        if paths != tuple(sorted(set(paths))):
            raise ValueError("PatchSet files must be unique and canonically ordered")
        if self.totals.files_changed != len(self.files):
            raise ValueError("PatchSet file total mismatch")
        if self.totals.lines_added != sum(change.lines_added for change in self.files):
            raise ValueError("PatchSet added-line total mismatch")
        if self.totals.lines_deleted != sum(change.lines_deleted for change in self.files):
            raise ValueError("PatchSet deleted-line total mismatch")
        if self.totals.deletion_count != sum(
            change.operation is PatchOperation.DELETE for change in self.files
        ):
            raise ValueError("PatchSet deletion total mismatch")
        scanned_records = [
            {"path": change.path, "sha256": change.after.sha256}
            for change in self.files
            if change.after is not None
        ]
        if self.secret_scan.files_scanned != len(scanned_records) or (
            self.secret_scan.scanned_content_sha256
            != canonical_workspace_json_digest(scanned_records)
        ):
            raise ValueError("PatchSet secret scan is not bound to changed after-content")
        if self.patchset_sha256 != canonical_workspace_json_digest(self.content_payload()):
            raise ValueError("canonical PatchSet digest mismatch")
        return self

    def content_payload(self) -> dict[str, object]:
        """Return the complete canonical identity without its self-hash."""

        return self.model_dump(mode="json", exclude={"patchset_sha256"})


class PatchSetRecheckReceipt(NonZeroContract):
    """Independent exact-state recheck proving a policy decision is still current."""

    patchset_id: Uuid7Identifier
    patchset_sha256: Sha256Digest
    base_tree_sha256: Sha256Digest
    final_tree_sha256: Sha256Digest
    result: Literal[PatchPolicyResult.PASS] = PatchPolicyResult.PASS
    drift_detected: Literal[False] = False
    checked_at: datetime
    receipt_sha256: Sha256Digest

    @field_validator("checked_at")
    @classmethod
    def validate_checked_at(cls, value: datetime) -> datetime:
        return _utc(value)

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.receipt_sha256 != canonical_workspace_json_digest(
            self.model_dump(mode="json", exclude={"receipt_sha256"})
        ):
            raise ValueError("PatchSet recheck receipt digest mismatch")
        return self
