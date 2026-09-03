"""Strict W3 contracts for exact human authority and one unverified patch effect."""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.domain import AuthorityGate
from aioa_cloudops_agent.nz import ApprovalDecision, NonZeroContract
from aioa_cloudops_agent.nz.identifiers import (
    IdempotencyKey,
    NonEmptyText,
    Sha256Digest,
    ShortIdentifier,
    Uuid7Identifier,
)

from .contracts import (
    W2_TARGET_PATH,
    W2_VERIFICATION_PROFILE_ID,
    WorkspacePatchProposal,
    canonical_workspace_json_digest,
)

W3_IMPACT_SUMMARY: Literal[
    "Atomically replace only render.yaml in this disposable workspace; runtime verification and deployment remain pending."
] = (
    "Atomically replace only render.yaml in this disposable workspace; runtime verification "
    "and deployment remain pending."
)


def _utc(name: str, value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() != timedelta(0):
        raise ValueError(f"{name} must be a timezone-aware UTC datetime")
    return value


class WorkspaceAuthorityState(StrEnum):
    """Closed W3 lifecycle; no member represents verified runtime success."""

    PATCH_PROPOSED = "PATCH_PROPOSED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    APPROVED = "APPROVED"
    DENIED_BY_HUMAN = "DENIED_BY_HUMAN"
    APPLYING = "APPLYING"
    PATCH_APPLIED_UNVERIFIED = "PATCH_APPLIED_UNVERIFIED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class WorkspaceApplyStatus(StrEnum):
    """Truthful W3 effect outcomes."""

    APPLIED_UNVERIFIED = "APPLIED_UNVERIFIED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"


class WorkspaceProposalRecord(NonZeroContract):
    """The complete W2 proposal retained as authoritative W3 durable truth."""

    proposal: WorkspacePatchProposal
    proposal_digest: Sha256Digest
    state: WorkspaceAuthorityState = WorkspaceAuthorityState.PATCH_PROPOSED
    stored_at: datetime
    version: Literal[1] = 1

    @field_validator("stored_at")
    @classmethod
    def validate_stored_at(cls, value: datetime) -> datetime:
        return _utc("stored_at", value)

    @model_validator(mode="after")
    def validate_proposal_identity(self) -> Self:
        if self.proposal_digest != self.proposal.proposal_digest:
            raise ValueError("durable proposal digest does not match W2 proposal")
        return self


class WorkspaceApprovalPayload(NonZeroContract):
    """Exact human-visible authority facts copied only from durable W2 truth."""

    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: Literal["workspace_render_incident_v1"]
    base_root_digest: Sha256Digest
    target_path: Literal["render.yaml"] = W2_TARGET_PATH
    target_before_sha256: Sha256Digest
    canonical_after_sha256: Sha256Digest
    patch_digest: Sha256Digest
    evidence_digest: Sha256Digest
    supporting_start_script_sha256: Sha256Digest
    expected_runtime_contract_sha256: Sha256Digest
    verification_profile_id: Literal["render_start_contract_v1"] = (
        W2_VERIFICATION_PROFILE_ID
    )
    rollback_strategy: str = Field(min_length=1, max_length=512)
    proposal_version: Literal[1] = 1
    proposal_expiry: datetime
    proposal_digest: Sha256Digest
    risk_class: Literal[AuthorityGate.PLAN_AND_CONFIRM] = AuthorityGate.PLAN_AND_CONFIRM
    canonical_diff_sha256: Sha256Digest
    impact_summary: Literal[
        "Atomically replace only render.yaml in this disposable workspace; runtime verification and deployment remain pending."
    ] = W3_IMPACT_SUMMARY

    @field_validator("proposal_expiry")
    @classmethod
    def validate_expiry(cls, value: datetime) -> datetime:
        return _utc("proposal_expiry", value)


def build_workspace_approval_payload(
    proposal: WorkspacePatchProposal,
) -> WorkspaceApprovalPayload:
    """Derive every human-authority field from one already-validated proposal."""

    if not isinstance(proposal, WorkspacePatchProposal):
        raise TypeError("proposal must be WorkspacePatchProposal")
    return WorkspaceApprovalPayload(
        proposal_id=proposal.proposal_id,
        run_id=proposal.run_id,
        trace_id=proposal.trace_id,
        workspace_id=proposal.workspace_id,
        fixture_version=proposal.fixture_version,
        base_root_digest=proposal.base_root_digest,
        target_path=proposal.target_path,
        target_before_sha256=proposal.target_before_sha256,
        canonical_after_sha256=proposal.canonical_after_sha256,
        patch_digest=proposal.patch_digest,
        evidence_digest=proposal.evidence_digest,
        supporting_start_script_sha256=proposal.supporting_start_script_sha256,
        expected_runtime_contract_sha256=proposal.expected_runtime_contract_sha256,
        verification_profile_id=proposal.verification_profile_id,
        rollback_strategy=proposal.rollback_strategy,
        proposal_version=proposal.version,
        proposal_expiry=proposal.expires_at,
        proposal_digest=proposal.proposal_digest,
        risk_class=proposal.risk_class,
        canonical_diff_sha256=hashlib.sha256(
            proposal.preview.unified_diff.encode("utf-8")
        ).hexdigest(),
    )


def workspace_approval_request_hash(payload: WorkspaceApprovalPayload) -> str:
    """Hash canonical payload JSON; display formatting is deliberately excluded."""

    if not isinstance(payload, WorkspaceApprovalPayload):
        raise TypeError("payload must be WorkspaceApprovalPayload")
    return canonical_workspace_json_digest(payload.model_dump(mode="json"))


class WorkspaceApprovalRequestRecord(NonZeroContract):
    """Durable native-interrupt checkpoint returned to the human caller."""

    interrupt_id: NonEmptyText
    payload: WorkspaceApprovalPayload
    request_hash: Sha256Digest
    requested_at: datetime
    reconciled: bool = False

    @field_validator("requested_at")
    @classmethod
    def validate_requested_at(cls, value: datetime) -> datetime:
        return _utc("requested_at", value)

    @model_validator(mode="after")
    def validate_request_binding(self) -> Self:
        if self.request_hash != workspace_approval_request_hash(self.payload):
            raise ValueError("workspace approval request hash does not match payload")
        if self.requested_at > self.payload.proposal_expiry:
            raise ValueError("workspace approval request cannot start after proposal expiry")
        return self


class WorkspaceApprovalResumeRequest(NonZeroContract):
    """External decision that echoes identities but cannot supply mutation bytes."""

    interrupt_id: NonEmptyText
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: Literal["workspace_render_incident_v1"]
    base_root_digest: Sha256Digest
    target_path: Literal["render.yaml"] = W2_TARGET_PATH
    target_before_sha256: Sha256Digest
    canonical_after_sha256: Sha256Digest
    patch_digest: Sha256Digest
    evidence_digest: Sha256Digest
    supporting_start_script_sha256: Sha256Digest
    expected_runtime_contract_sha256: Sha256Digest
    verification_profile_id: Literal["render_start_contract_v1"] = (
        W2_VERIFICATION_PROFILE_ID
    )
    proposal_version: Literal[1] = 1
    proposal_expiry: datetime
    proposal_digest: Sha256Digest
    request_hash: Sha256Digest
    decision: ApprovalDecision
    actor_session_id: ShortIdentifier
    decision_nonce: NonEmptyText = Field(min_length=16, max_length=256)

    @field_validator("proposal_expiry")
    @classmethod
    def validate_proposal_expiry(cls, value: datetime) -> datetime:
        return _utc("proposal_expiry", value)

    def echoed_payload_identity(self) -> dict[str, object]:
        """Return fields that must equal the durable payload exactly."""

        return {
            "base_root_digest": self.base_root_digest,
            "canonical_after_sha256": self.canonical_after_sha256,
            "evidence_digest": self.evidence_digest,
            "expected_runtime_contract_sha256": self.expected_runtime_contract_sha256,
            "fixture_version": self.fixture_version,
            "patch_digest": self.patch_digest,
            "proposal_digest": self.proposal_digest,
            "proposal_expiry": self.proposal_expiry,
            "proposal_id": self.proposal_id,
            "proposal_version": self.proposal_version,
            "run_id": self.run_id,
            "supporting_start_script_sha256": self.supporting_start_script_sha256,
            "target_before_sha256": self.target_before_sha256,
            "target_path": self.target_path,
            "trace_id": self.trace_id,
            "verification_profile_id": self.verification_profile_id,
            "workspace_id": self.workspace_id,
        }


class WorkspaceApprovalDecisionRecord(NonZeroContract):
    """Immutable first human decision, including actor and one-time nonce binding."""

    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    interrupt_id: NonEmptyText
    request_hash: Sha256Digest
    proposal_digest: Sha256Digest
    patch_digest: Sha256Digest
    evidence_digest: Sha256Digest
    base_root_digest: Sha256Digest
    decision: ApprovalDecision
    actor_session_id: ShortIdentifier
    decision_nonce_hash: Sha256Digest
    decided_at: datetime
    decision_hash: Sha256Digest

    @field_validator("decided_at")
    @classmethod
    def validate_decided_at(cls, value: datetime) -> datetime:
        return _utc("decided_at", value)

    def binding_payload(self) -> dict[str, object]:
        return {
            "actor_session_id": self.actor_session_id,
            "base_root_digest": self.base_root_digest,
            "decided_at": self.decided_at.isoformat(),
            "decision": self.decision.value,
            "decision_nonce_hash": self.decision_nonce_hash,
            "evidence_digest": self.evidence_digest,
            "interrupt_id": self.interrupt_id,
            "patch_digest": self.patch_digest,
            "proposal_digest": self.proposal_digest,
            "proposal_id": str(self.proposal_id),
            "request_hash": self.request_hash,
            "run_id": str(self.run_id),
            "trace_id": str(self.trace_id),
            "workspace_id": str(self.workspace_id),
        }

    @model_validator(mode="after")
    def validate_decision_binding(self) -> Self:
        if self.decision_hash != canonical_workspace_json_digest(self.binding_payload()):
            raise ValueError("workspace decision hash does not match bound content")
        return self

    @classmethod
    def create(
        cls,
        request: WorkspaceApprovalRequestRecord,
        response: WorkspaceApprovalResumeRequest,
        *,
        decided_at: datetime,
    ) -> WorkspaceApprovalDecisionRecord:
        payload = request.payload
        values: dict[str, object] = {
            "proposal_id": payload.proposal_id,
            "run_id": payload.run_id,
            "trace_id": payload.trace_id,
            "workspace_id": payload.workspace_id,
            "interrupt_id": request.interrupt_id,
            "request_hash": request.request_hash,
            "proposal_digest": payload.proposal_digest,
            "patch_digest": payload.patch_digest,
            "evidence_digest": payload.evidence_digest,
            "base_root_digest": payload.base_root_digest,
            "decision": response.decision,
            "actor_session_id": response.actor_session_id,
            "decision_nonce_hash": hashlib.sha256(
                response.decision_nonce.encode("utf-8")
            ).hexdigest(),
            "decided_at": decided_at,
        }
        provisional = cls.model_construct(**values, decision_hash="0" * 64)
        return cls(
            **values,
            decision_hash=canonical_workspace_json_digest(provisional.binding_payload()),
        )


class WorkspaceEffectOwnership(NonZeroContract):
    """Durable write-before-effect ownership of the one exact replacement."""

    effect_id: Uuid7Identifier
    idempotency_key: IdempotencyKey
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: Literal["workspace_render_incident_v1"]
    target_path: Literal["render.yaml"] = W2_TARGET_PATH
    before_sha256: Sha256Digest
    after_sha256: Sha256Digest
    patch_digest: Sha256Digest
    approval_request_hash: Sha256Digest
    decision_hash: Sha256Digest
    registered_at: datetime
    ownership_hash: Sha256Digest

    @field_validator("registered_at")
    @classmethod
    def validate_registered_at(cls, value: datetime) -> datetime:
        return _utc("registered_at", value)

    def binding_payload(self) -> dict[str, object]:
        return {
            "after_sha256": self.after_sha256,
            "approval_request_hash": self.approval_request_hash,
            "before_sha256": self.before_sha256,
            "decision_hash": self.decision_hash,
            "effect_id": str(self.effect_id),
            "fixture_version": self.fixture_version,
            "idempotency_key": self.idempotency_key,
            "patch_digest": self.patch_digest,
            "proposal_id": str(self.proposal_id),
            "registered_at": self.registered_at.isoformat(),
            "run_id": str(self.run_id),
            "target_path": self.target_path,
            "trace_id": str(self.trace_id),
            "workspace_id": str(self.workspace_id),
        }

    @model_validator(mode="after")
    def validate_ownership_binding(self) -> Self:
        if self.ownership_hash != canonical_workspace_json_digest(self.binding_payload()):
            raise ValueError("workspace effect ownership hash does not match")
        return self

    @classmethod
    def create(
        cls,
        proposal: WorkspacePatchProposal,
        decision: WorkspaceApprovalDecisionRecord,
        *,
        effect_id: Uuid7Identifier,
        registered_at: datetime,
    ) -> WorkspaceEffectOwnership:
        values: dict[str, object] = {
            "effect_id": effect_id,
            "idempotency_key": f"workspace-patch:{proposal.proposal_digest}",
            "proposal_id": proposal.proposal_id,
            "run_id": proposal.run_id,
            "trace_id": proposal.trace_id,
            "workspace_id": proposal.workspace_id,
            "fixture_version": proposal.fixture_version,
            "target_path": proposal.target_path,
            "before_sha256": proposal.target_before_sha256,
            "after_sha256": proposal.canonical_after_sha256,
            "patch_digest": proposal.patch_digest,
            "approval_request_hash": decision.request_hash,
            "decision_hash": decision.decision_hash,
            "registered_at": registered_at,
        }
        provisional = cls.model_construct(**values, ownership_hash="0" * 64)
        return cls(
            **values,
            ownership_hash=canonical_workspace_json_digest(provisional.binding_payload()),
        )


class PatchApplyReceipt(NonZeroContract):
    """Proof of one file effect; explicitly not runtime verification or success."""

    effect_id: Uuid7Identifier
    idempotency_key: IdempotencyKey
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    fixture_version: Literal["workspace_render_incident_v1"]
    target_path: Literal["render.yaml"] = W2_TARGET_PATH
    before_sha256: Sha256Digest
    after_sha256: Sha256Digest
    patch_digest: Sha256Digest
    approval_request_hash: Sha256Digest
    changed_paths: tuple[Literal["render.yaml"], ...] = (W2_TARGET_PATH,)
    post_apply_root_digest: Sha256Digest
    started_at: datetime
    completed_at: datetime
    status: Literal[WorkspaceApplyStatus.APPLIED_UNVERIFIED] = (
        WorkspaceApplyStatus.APPLIED_UNVERIFIED
    )
    verification_required: Literal[True] = True
    success_with_evidence: Literal[False] = False
    verified_success: Literal[False] = False

    @field_validator("started_at", "completed_at")
    @classmethod
    def validate_timestamps(cls, value: datetime, info: object) -> datetime:
        return _utc(getattr(info, "field_name", "timestamp"), value)

    @model_validator(mode="after")
    def validate_effect_truth(self) -> Self:
        if self.completed_at < self.started_at:
            raise ValueError("apply completion cannot precede start")
        if self.changed_paths != (W2_TARGET_PATH,):
            raise ValueError("W3 receipt must contain exactly render.yaml")
        return self


class WorkspaceReconciliationMarker(NonZeroContract):
    """Durable fail-closed marker for an ambiguous or recovered effect window."""

    effect_id: Uuid7Identifier
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    target_path: Literal["render.yaml"] = W2_TARGET_PATH
    observed_sha256: Sha256Digest
    before_sha256: Sha256Digest
    after_sha256: Sha256Digest
    reason_code: Literal[
        "TARGET_ALREADY_AFTER_WITHOUT_RECEIPT",
        "TARGET_DIGEST_AMBIGUOUS",
        "POST_WRITE_PROOF_INCOMPLETE",
    ]
    recorded_at: datetime
    status: Literal[WorkspaceApplyStatus.RECONCILIATION_REQUIRED] = (
        WorkspaceApplyStatus.RECONCILIATION_REQUIRED
    )
    verification_required: Literal[True] = True
    success_with_evidence: Literal[False] = False

    @field_validator("recorded_at")
    @classmethod
    def validate_recorded_at(cls, value: datetime) -> datetime:
        return _utc("recorded_at", value)


class WorkspaceAuthorityAuditEvent(NonZeroContract):
    """Small content-addressed W3 authority event without private path data."""

    event_id: Uuid7Identifier
    proposal_id: Uuid7Identifier
    run_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    event_type: Literal[
        "PROPOSAL_PERSISTED",
        "APPROVAL_REQUESTED",
        "DECISION_RECORDED",
        "EFFECT_OWNED",
        "APPLY_RECORDED",
        "RECONCILIATION_REQUIRED",
    ]
    payload_sha256: Sha256Digest
    recorded_at: datetime

    @field_validator("recorded_at")
    @classmethod
    def validate_event_time(cls, value: datetime) -> datetime:
        return _utc("recorded_at", value)
