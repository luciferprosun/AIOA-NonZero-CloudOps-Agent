"""Application-owned W3 approval lifecycle over durable workspace truth."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from aioa_cloudops_agent.nz import ApprovalDecision

from .authority_contracts import (
    WorkspaceApprovalDecisionRecord,
    WorkspaceApprovalPayload,
    WorkspaceApprovalRequestRecord,
    WorkspaceApprovalResumeRequest,
    WorkspaceAuthorityState,
    build_workspace_approval_payload,
    workspace_approval_request_hash,
)
from .authority_repository import (
    LocalFileWorkspaceAuthorityRepository,
    WorkspaceAuthorityConflict,
    WorkspaceAuthorityStorageError,
)
from .contracts import WorkspacePatchProposal


class WorkspaceAuthorityDenied(ValueError):
    """Safe caller-visible W3 policy denial with no private host details."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


class WorkspaceAuthorityService:
    """Bind W2 proposal persistence, exact request creation, and human decision."""

    def __init__(
        self,
        repository: LocalFileWorkspaceAuthorityRepository,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(repository, LocalFileWorkspaceAuthorityRepository):
            raise TypeError("repository must be LocalFileWorkspaceAuthorityRepository")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(UTC))

    @property
    def repository(self) -> LocalFileWorkspaceAuthorityRepository:
        return self._repository

    def persist_proposal(self, proposal: WorkspacePatchProposal) -> WorkspacePatchProposal:
        """Persist the complete proposal before any approval request can exist."""

        try:
            return self._repository.save_proposal(proposal).proposal
        except (WorkspaceAuthorityConflict, WorkspaceAuthorityStorageError) as error:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_PROPOSAL_PERSISTENCE_DENIED",
                "Durable workspace proposal could not be established.",
            ) from error

    def begin_approval(self, proposal_id: UUID) -> WorkspaceApprovalPayload:
        """Durably mark one unexpired proposal awaiting native confirmation."""

        record = self._load_record(proposal_id)
        now = self._clock()
        if now > record.proposal.expires_at:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_PROPOSAL_EXPIRED",
                "Workspace proposal expired before approval could begin.",
            )
        try:
            awaiting = self._repository.begin_approval(proposal_id)
        except (WorkspaceAuthorityConflict, WorkspaceAuthorityStorageError) as error:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_APPROVAL_STATE_DENIED",
                "Workspace proposal cannot enter approval from its durable state.",
            ) from error
        return build_workspace_approval_payload(awaiting.proposal)

    def durable_payload_for_interrupt(self, proposal_id: UUID) -> WorkspaceApprovalPayload:
        """Load an awaiting proposal and derive its prompt payload from durable truth."""

        record = self._load_record(proposal_id)
        if record.state is not WorkspaceAuthorityState.AWAITING_APPROVAL:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_NOT_AWAITING_APPROVAL",
                "Durable workspace proposal is not awaiting approval.",
            )
        if self._clock() > record.proposal.expires_at:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_PROPOSAL_EXPIRED",
                "Workspace proposal expired before confirmation.",
            )
        return build_workspace_approval_payload(record.proposal)

    def record_interrupt(
        self,
        proposal_id: UUID,
        interrupt_id: str,
    ) -> WorkspaceApprovalRequestRecord:
        """Persist the exact native interrupt/checkpoint before returning it."""

        payload = self.durable_payload_for_interrupt(proposal_id)
        request = WorkspaceApprovalRequestRecord(
            interrupt_id=interrupt_id,
            payload=payload,
            request_hash=workspace_approval_request_hash(payload),
            requested_at=self._clock(),
        )
        try:
            return self._repository.save_request(request)
        except (WorkspaceAuthorityConflict, WorkspaceAuthorityStorageError) as error:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_INTERRUPT_PERSISTENCE_DENIED",
                "Native workspace approval interrupt could not be persisted.",
            ) from error

    def decide(
        self,
        response: WorkspaceApprovalResumeRequest,
    ) -> tuple[WorkspaceApprovalDecisionRecord, bool]:
        """Validate all echoed facts and durably record decision before native resume."""

        if not isinstance(response, WorkspaceApprovalResumeRequest):
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_APPROVAL_RESPONSE_INVALID",
                "Workspace approval response must use the exact typed contract.",
            )
        record = self._load_record(response.proposal_id)
        request = self._repository.get_request(response.proposal_id)
        if request is None:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_APPROVAL_REQUEST_MISSING",
                "Durable workspace approval request is unavailable.",
            )
        payload = build_workspace_approval_payload(record.proposal)
        expected_identity = {
            "base_root_digest": payload.base_root_digest,
            "canonical_after_sha256": payload.canonical_after_sha256,
            "evidence_digest": payload.evidence_digest,
            "expected_runtime_contract_sha256": payload.expected_runtime_contract_sha256,
            "fixture_version": payload.fixture_version,
            "patch_digest": payload.patch_digest,
            "proposal_digest": payload.proposal_digest,
            "proposal_expiry": payload.proposal_expiry,
            "proposal_id": payload.proposal_id,
            "proposal_version": payload.proposal_version,
            "run_id": payload.run_id,
            "supporting_start_script_sha256": payload.supporting_start_script_sha256,
            "target_before_sha256": payload.target_before_sha256,
            "target_path": payload.target_path,
            "trace_id": payload.trace_id,
            "verification_profile_id": payload.verification_profile_id,
            "workspace_id": payload.workspace_id,
        }
        expected_hash = workspace_approval_request_hash(payload)
        if (
            response.echoed_payload_identity() != expected_identity
            or response.interrupt_id != request.interrupt_id
            or response.request_hash != request.request_hash
            or response.request_hash != expected_hash
        ):
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_APPROVAL_BINDING_MISMATCH",
                "Workspace decision does not match durable proposal and interrupt truth.",
            )
        if self._clock() > payload.proposal_expiry:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_PROPOSAL_EXPIRED",
                "Workspace proposal expired before the human decision.",
            )
        decision = WorkspaceApprovalDecisionRecord.create(
            request,
            response,
            decided_at=self._clock(),
        )
        try:
            return self._repository.save_decision(decision)
        except WorkspaceAuthorityConflict as error:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_APPROVAL_DECISION_CONFLICT",
                "Human decision conflicts with durable workspace authority truth.",
            ) from error
        except WorkspaceAuthorityStorageError as error:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_APPROVAL_STORAGE_UNAVAILABLE",
                "Human decision could not be durably persisted.",
            ) from error

    @staticmethod
    def approval_prompt(payload: WorkspaceApprovalPayload) -> str:
        """Render stable human facts; the canonical request hash ignores formatting."""

        if not isinstance(payload, WorkspaceApprovalPayload):
            raise TypeError("payload must be WorkspaceApprovalPayload")
        rendered = json.dumps(
            payload.model_dump(mode="json"),
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        return f"Approve exact W3 workspace patch?\n  Payload: {rendered}"

    def _load_record(self, proposal_id: UUID):
        try:
            record = self._repository.get_proposal_record(proposal_id)
        except WorkspaceAuthorityStorageError as error:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_AUTHORITY_UNAVAILABLE",
                "Durable workspace authority truth is unavailable.",
            ) from error
        if record is None:
            raise WorkspaceAuthorityDenied(
                "WORKSPACE_PROPOSAL_NOT_FOUND",
                "Durable workspace proposal does not exist.",
            )
        return record


def decision_for_request(
    request: WorkspaceApprovalRequestRecord,
    *,
    decision: ApprovalDecision,
    actor_session_id: str,
    decision_nonce: str,
) -> WorkspaceApprovalResumeRequest:
    """Build the exact external resume shape without accepting mutation material."""

    payload = request.payload
    return WorkspaceApprovalResumeRequest(
        interrupt_id=request.interrupt_id,
        proposal_id=payload.proposal_id,
        run_id=payload.run_id,
        trace_id=payload.trace_id,
        workspace_id=payload.workspace_id,
        fixture_version=payload.fixture_version,
        base_root_digest=payload.base_root_digest,
        target_path=payload.target_path,
        target_before_sha256=payload.target_before_sha256,
        canonical_after_sha256=payload.canonical_after_sha256,
        patch_digest=payload.patch_digest,
        evidence_digest=payload.evidence_digest,
        supporting_start_script_sha256=payload.supporting_start_script_sha256,
        expected_runtime_contract_sha256=payload.expected_runtime_contract_sha256,
        verification_profile_id=payload.verification_profile_id,
        proposal_version=payload.proposal_version,
        proposal_expiry=payload.proposal_expiry,
        proposal_digest=payload.proposal_digest,
        request_hash=request.request_hash,
        decision=decision,
        actor_session_id=actor_session_id,
        decision_nonce=decision_nonce,
    )
