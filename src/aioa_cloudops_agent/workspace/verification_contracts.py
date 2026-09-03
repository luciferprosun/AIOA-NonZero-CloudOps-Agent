"""Strict W4 contracts for independent workspace verification and recovery."""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.identifiers import Sha256Digest, Uuid7Identifier

from .contracts import (
    W2_TARGET_PATH,
    W2_VERIFICATION_PROFILE_ID,
    canonical_workspace_json_digest,
    normalize_workspace_relative_path,
)


def _utc(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")
    return value


class WorkspaceVerificationDisposition(StrEnum):
    """Closed independent-verification outcomes."""

    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    DEPENDENCY_UNAVAILABLE = "DEPENDENCY_UNAVAILABLE"


class WorkspaceVerificationCheckStatus(StrEnum):
    """Truthful result of one deterministic server-owned check."""

    PASS = "PASS"
    FAIL = "FAIL"
    NOT_RUN = "NOT_RUN"
    UNAVAILABLE = "UNAVAILABLE"


class WorkspaceVerificationCheckCode(StrEnum):
    """Canonical check order for ``render_start_contract_v1``."""

    PROPOSAL_BINDING = "PROPOSAL_BINDING"
    APPROVAL_BINDING = "APPROVAL_BINDING"
    WORKSPACE_PROVENANCE = "WORKSPACE_PROVENANCE"
    EXACT_CHANGED_PATH_SET = "EXACT_CHANGED_PATH_SET"
    TARGET_AFTER_HASH = "TARGET_AFTER_HASH"
    INLINE_DOCKER_COMMAND_ABSENT = "INLINE_DOCKER_COMMAND_ABSENT"
    FIXED_EXECUTABLE_PRESENT_ONCE = "FIXED_EXECUTABLE_PRESENT_ONCE"
    START_SCRIPT_HASH = "START_SCRIPT_HASH"
    RUNTIME_CONTRACT_HASH = "RUNTIME_CONTRACT_HASH"
    RENDER_CONFIG_EXACT_AFTER = "RENDER_CONFIG_EXACT_AFTER"
    MISSING_TOKEN_FAILS_CLOSED = "MISSING_TOKEN_FAILS_CLOSED"
    TOKEN_FILE_MODE_0600 = "TOKEN_FILE_MODE_0600"
    BOOTSTRAP_SECRET_ABSENT = "BOOTSTRAP_SECRET_ABSENT"
    CHILD_ARGV_EXACT = "CHILD_ARGV_EXACT"
    HEALTH_CHECK = "HEALTH_CHECK"
    READINESS_CHECK = "READINESS_CHECK"
    ZERO_EXTERNAL_EGRESS = "ZERO_EXTERNAL_EGRESS"
    ZERO_AWS_CALLS = "ZERO_AWS_CALLS"
    NO_WORKSPACE_CODE_EXECUTION = "NO_WORKSPACE_CODE_EXECUTION"


W4_VERIFICATION_CHECK_ORDER: tuple[WorkspaceVerificationCheckCode, ...] = tuple(
    WorkspaceVerificationCheckCode
)


class WorkspaceRecoveryClassification(StrEnum):
    """Fresh read-back classification for W3 crash windows."""

    SAFE_RESUMABLE_FOR_W3_APPLY = "SAFE_RESUMABLE_FOR_W3_APPLY"
    RECOVERY_READ_BACK = "RECOVERY_READ_BACK"
    AMBIGUOUS_STATE = "AMBIGUOUS_STATE"


class WorkspaceVerificationProofOrigin(StrEnum):
    """Durable effect evidence linked by a verified report."""

    APPLY_RECEIPT = "APPLY_RECEIPT"
    RECOVERY_READ_BACK = "RECOVERY_READ_BACK"


class WorkspaceVerificationCheck(NonZeroContract):
    """One ordered check containing bounded, secret-free normalized values."""

    code: WorkspaceVerificationCheckCode
    status: WorkspaceVerificationCheckStatus
    expected: str = Field(min_length=1, max_length=160)
    observed: str = Field(min_length=1, max_length=160)

    @field_validator("expected", "observed")
    @classmethod
    def validate_bounded_value(cls, value: str) -> str:
        if any(character in value for character in ("\n", "\r", "\x00")):
            raise ValueError("verification values must be single-line normalized data")
        return value


class WorkspaceRecoveryObservation(NonZeroContract):
    """Independent disk read-back used only to classify an ambiguous W3 window."""

    observation_id: Uuid7Identifier
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: Literal["workspace_render_incident_v1"]
    effect_id: Uuid7Identifier
    base_root_digest: Sha256Digest
    expected_before_sha256: Sha256Digest
    expected_after_sha256: Sha256Digest
    actual_target_sha256: Sha256Digest | None = None
    expected_changed_paths: tuple[Literal["render.yaml"], ...] = (W2_TARGET_PATH,)
    actual_changed_paths: tuple[str, ...] = Field(default=(), max_length=16)
    observed_root_digest: Sha256Digest | None = None
    integrity_proven: bool
    classification: WorkspaceRecoveryClassification
    observed_at: datetime
    observation_digest: Sha256Digest

    @field_validator("actual_changed_paths")
    @classmethod
    def validate_changed_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_workspace_relative_path(path) for path in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("actual changed paths must be sorted and unique")
        return normalized

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        return _utc("observed_at", value)

    def binding_payload(self) -> dict[str, object]:
        return {
            "actual_changed_paths": list(self.actual_changed_paths),
            "actual_target_sha256": self.actual_target_sha256,
            "base_root_digest": self.base_root_digest,
            "classification": self.classification.value,
            "effect_id": str(self.effect_id),
            "expected_after_sha256": self.expected_after_sha256,
            "expected_before_sha256": self.expected_before_sha256,
            "expected_changed_paths": list(self.expected_changed_paths),
            "fixture_version": self.fixture_version,
            "integrity_proven": self.integrity_proven,
            "observation_id": str(self.observation_id),
            "observed_at": self.observed_at.isoformat(),
            "observed_root_digest": self.observed_root_digest,
            "proposal_id": str(self.proposal_id),
            "run_id": str(self.run_id),
            "trace_id": str(self.trace_id),
            "workspace_id": str(self.workspace_id),
        }

    @model_validator(mode="after")
    def validate_observation_truth(self) -> Self:
        if self.classification is WorkspaceRecoveryClassification.SAFE_RESUMABLE_FOR_W3_APPLY:
            if (
                not self.integrity_proven
                or self.actual_target_sha256 != self.expected_before_sha256
                or self.actual_changed_paths
            ):
                raise ValueError("safe-resumable recovery requires exact unchanged before state")
        elif (
            self.classification is WorkspaceRecoveryClassification.RECOVERY_READ_BACK
            and (
                not self.integrity_proven
                or self.actual_target_sha256 != self.expected_after_sha256
                or self.actual_changed_paths != (W2_TARGET_PATH,)
            )
        ):
            raise ValueError("recovery read-back requires the exact approved effect")
        if self.observation_digest != canonical_workspace_json_digest(self.binding_payload()):
            raise ValueError("recovery observation digest does not match its content")
        return self

    @classmethod
    def create(cls, **values: object) -> WorkspaceRecoveryObservation:
        provisional = cls.model_construct(**values, observation_digest="0" * 64)
        return cls(
            **values,
            observation_digest=canonical_workspace_json_digest(provisional.binding_payload()),
        )


class WorkspaceVerificationReport(NonZeroContract):
    """Independent state proof; executor claims never determine its disposition."""

    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: Literal["workspace_render_incident_v1"]
    effect_id: Uuid7Identifier
    patch_digest: Sha256Digest
    base_root_digest: Sha256Digest
    expected_after_sha256: Sha256Digest
    actual_after_sha256: Sha256Digest | None = None
    expected_changed_paths: tuple[Literal["render.yaml"], ...] = (W2_TARGET_PATH,)
    actual_changed_paths: tuple[str, ...] = Field(default=(), max_length=16)
    supporting_start_script_sha256: Sha256Digest
    actual_start_script_sha256: Sha256Digest | None = None
    expected_runtime_contract_sha256: Sha256Digest
    actual_runtime_contract_sha256: Sha256Digest | None = None
    verification_profile_id: Literal["render_start_contract_v1"] = (
        W2_VERIFICATION_PROFILE_ID
    )
    apply_receipt_digest: Sha256Digest | None = None
    recovery_observation_digest: Sha256Digest | None = None
    observed_root_digest: Sha256Digest | None = None
    checks: tuple[WorkspaceVerificationCheck, ...] = Field(
        min_length=len(W4_VERIFICATION_CHECK_ORDER),
        max_length=len(W4_VERIFICATION_CHECK_ORDER),
    )
    verified_at: datetime
    disposition: WorkspaceVerificationDisposition
    report_digest: Sha256Digest

    @field_validator("actual_changed_paths")
    @classmethod
    def validate_changed_paths(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(normalize_workspace_relative_path(path) for path in value)
        if normalized != tuple(sorted(set(normalized))):
            raise ValueError("actual changed paths must be sorted and unique")
        return normalized

    @field_validator("verified_at")
    @classmethod
    def validate_verified_at(cls, value: datetime) -> datetime:
        return _utc("verified_at", value)

    def binding_payload(self) -> dict[str, object]:
        return {
            "actual_after_sha256": self.actual_after_sha256,
            "actual_changed_paths": list(self.actual_changed_paths),
            "actual_runtime_contract_sha256": self.actual_runtime_contract_sha256,
            "actual_start_script_sha256": self.actual_start_script_sha256,
            "apply_receipt_digest": self.apply_receipt_digest,
            "base_root_digest": self.base_root_digest,
            "checks": [check.model_dump(mode="json") for check in self.checks],
            "disposition": self.disposition.value,
            "effect_id": str(self.effect_id),
            "expected_after_sha256": self.expected_after_sha256,
            "expected_changed_paths": list(self.expected_changed_paths),
            "expected_runtime_contract_sha256": self.expected_runtime_contract_sha256,
            "fixture_version": self.fixture_version,
            "observed_root_digest": self.observed_root_digest,
            "patch_digest": self.patch_digest,
            "proposal_id": str(self.proposal_id),
            "recovery_observation_digest": self.recovery_observation_digest,
            "run_id": str(self.run_id),
            "supporting_start_script_sha256": self.supporting_start_script_sha256,
            "trace_id": str(self.trace_id),
            "verification_profile_id": self.verification_profile_id,
            "verified_at": self.verified_at.isoformat(),
            "workspace_id": str(self.workspace_id),
        }

    @model_validator(mode="after")
    def validate_report_truth(self) -> Self:
        if tuple(check.code for check in self.checks) != W4_VERIFICATION_CHECK_ORDER:
            raise ValueError("verification checks are not in canonical order")
        statuses = {check.status for check in self.checks}
        if self.disposition is WorkspaceVerificationDisposition.VERIFIED:
            if statuses != {WorkspaceVerificationCheckStatus.PASS}:
                raise ValueError("verified report requires every check to pass")
            if (
                self.actual_after_sha256 != self.expected_after_sha256
                or self.actual_changed_paths != self.expected_changed_paths
            ):
                raise ValueError("verified report does not prove the exact effect")
        elif self.disposition is WorkspaceVerificationDisposition.MISMATCH:
            if WorkspaceVerificationCheckStatus.FAIL not in statuses:
                raise ValueError("mismatch report requires a failed check")
        elif self.disposition is WorkspaceVerificationDisposition.DEPENDENCY_UNAVAILABLE:
            if WorkspaceVerificationCheckStatus.UNAVAILABLE not in statuses:
                raise ValueError("dependency-unavailable report requires unavailable evidence")
        elif statuses == {WorkspaceVerificationCheckStatus.PASS}:
            raise ValueError("reconciliation report cannot contain only passing checks")
        if self.report_digest != canonical_workspace_json_digest(self.binding_payload()):
            raise ValueError("verification report digest does not match its content")
        return self

    @classmethod
    def create(cls, **values: object) -> WorkspaceVerificationReport:
        provisional = cls.model_construct(**values, report_digest="0" * 64)
        return cls(
            **values,
            report_digest=canonical_workspace_json_digest(provisional.binding_payload()),
        )


class WorkspaceVerificationReceipt(NonZeroContract):
    """Durable terminal input created only from one verified independent report."""

    verification_id: Uuid7Identifier
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    effect_id: Uuid7Identifier
    report_digest: Sha256Digest
    observed_after_sha256: Sha256Digest
    verification_profile_id: Literal["render_start_contract_v1"] = (
        W2_VERIFICATION_PROFILE_ID
    )
    proof_origin: WorkspaceVerificationProofOrigin
    apply_receipt_digest: Sha256Digest | None = None
    recovery_observation_digest: Sha256Digest | None = None
    verified_at: datetime
    terminal_state: Literal["SUCCESS_WITH_EVIDENCE"] = "SUCCESS_WITH_EVIDENCE"
    success_with_evidence: Literal[True] = True
    verified_success: Literal[True] = True
    receipt_digest: Sha256Digest

    @field_validator("verified_at")
    @classmethod
    def validate_verified_at(cls, value: datetime) -> datetime:
        return _utc("verified_at", value)

    def binding_payload(self) -> dict[str, object]:
        return {
            "apply_receipt_digest": self.apply_receipt_digest,
            "effect_id": str(self.effect_id),
            "observed_after_sha256": self.observed_after_sha256,
            "proof_origin": self.proof_origin.value,
            "proposal_id": str(self.proposal_id),
            "recovery_observation_digest": self.recovery_observation_digest,
            "report_digest": self.report_digest,
            "run_id": str(self.run_id),
            "success_with_evidence": self.success_with_evidence,
            "terminal_state": self.terminal_state,
            "trace_id": str(self.trace_id),
            "verification_id": str(self.verification_id),
            "verification_profile_id": self.verification_profile_id,
            "verified_at": self.verified_at.isoformat(),
            "verified_success": self.verified_success,
            "workspace_id": str(self.workspace_id),
        }

    @model_validator(mode="after")
    def validate_receipt_truth(self) -> Self:
        if self.proof_origin is WorkspaceVerificationProofOrigin.APPLY_RECEIPT:
            if self.apply_receipt_digest is None or self.recovery_observation_digest is not None:
                raise ValueError("apply-receipt proof must bind only the apply receipt")
        elif (
            self.recovery_observation_digest is None
            or self.apply_receipt_digest is not None
        ):
            raise ValueError("recovery proof must bind only the recovery observation")
        if self.receipt_digest != canonical_workspace_json_digest(self.binding_payload()):
            raise ValueError("verification receipt digest does not match its content")
        return self

    @classmethod
    def create(cls, **values: object) -> WorkspaceVerificationReceipt:
        provisional = cls.model_construct(**values, receipt_digest="0" * 64)
        return cls(
            **values,
            receipt_digest=canonical_workspace_json_digest(provisional.binding_payload()),
        )


class WorkspaceVerificationCompletion(NonZeroContract):
    """Tool result returned only after report, receipt, and terminal state are durable."""

    report: WorkspaceVerificationReport
    receipt: WorkspaceVerificationReceipt
    terminal_state: Literal["SUCCESS_WITH_EVIDENCE"] = "SUCCESS_WITH_EVIDENCE"
    reconciled: bool = False
    verifier_fixed_process_probes: int = Field(ge=0, le=2)
    model_process_capabilities_registered: Literal[0] = 0
    workspace_code_executions: Literal[0] = 0
    arbitrary_command_executions: Literal[0] = 0

    @model_validator(mode="after")
    def validate_completion_binding(self) -> Self:
        if (
            self.report.disposition is not WorkspaceVerificationDisposition.VERIFIED
            or self.receipt.report_digest != self.report.report_digest
            or self.receipt.proposal_id != self.report.proposal_id
            or self.receipt.effect_id != self.report.effect_id
        ):
            raise ValueError("verification completion does not bind one verified report")
        return self
