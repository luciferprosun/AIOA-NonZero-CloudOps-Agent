"""Restart-safe W3 workspace authority repository with atomic fail-closed writes."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Self
from uuid import UUID

from pydantic import Field, model_validator

from aioa_cloudops_agent.nz import ApprovalDecision, generate_event_id
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.persistence.local_integrity import (
    LocalIntegrityError,
    atomic_write_private_json,
    locked_private_file,
    open_local_payload,
    read_private_json,
    seal_local_payload,
    validate_local_path,
)

from .authority_contracts import (
    PatchApplyReceipt,
    WorkspaceApprovalDecisionRecord,
    WorkspaceApprovalRequestRecord,
    WorkspaceAuthorityAuditEvent,
    WorkspaceAuthorityState,
    WorkspaceEffectOwnership,
    WorkspaceProposalRecord,
    WorkspaceReconciliationMarker,
)
from .contracts import WorkspacePatchProposal, canonical_workspace_json_digest

_WORKSPACE_AUTHORITY_PAYLOAD_TYPE = "AIOA_WORKSPACE_AUTHORITY_V1"


class WorkspaceAuthorityConflict(ValueError):
    """An incompatible durable state or duplicate was observed."""


class WorkspaceAuthorityStorageError(RuntimeError):
    """The local durable authority snapshot could not be trusted or written."""


class WorkspaceAuthoritySnapshot(NonZeroContract):
    """One integrity-sealed W3 truth snapshot."""

    schema_version: int = Field(default=1, ge=1, le=1)
    proposals: tuple[WorkspaceProposalRecord, ...] = ()
    requests: tuple[WorkspaceApprovalRequestRecord, ...] = ()
    decisions: tuple[WorkspaceApprovalDecisionRecord, ...] = ()
    ownership: tuple[WorkspaceEffectOwnership, ...] = ()
    receipts: tuple[PatchApplyReceipt, ...] = ()
    reconciliations: tuple[WorkspaceReconciliationMarker, ...] = ()
    audit_events: tuple[WorkspaceAuthorityAuditEvent, ...] = ()

    @model_validator(mode="after")
    def validate_unique_records(self) -> Self:
        collections = (
            (self.proposals, lambda item: str(item.proposal.proposal_id)),
            (self.requests, lambda item: str(item.payload.proposal_id)),
            (self.decisions, lambda item: str(item.proposal_id)),
            (self.ownership, lambda item: str(item.proposal_id)),
            (self.receipts, lambda item: str(item.proposal_id)),
            (self.reconciliations, lambda item: str(item.proposal_id)),
            (self.audit_events, lambda item: str(item.event_id)),
        )
        for records, key in collections:
            identities = tuple(key(item) for item in records)
            if len(identities) != len(set(identities)):
                raise ValueError("workspace authority snapshot contains duplicate records")
        return self


class LocalFileWorkspaceAuthorityRepository:
    """Owner-only, locked, integrity-bound durable truth for workspace W3."""

    def __init__(
        self,
        path: str | Path,
        *,
        clock: Callable[[], datetime] | None = None,
        event_id_factory: Callable[[], UUID] = generate_event_id,
    ) -> None:
        if isinstance(path, str):
            if not path.strip():
                raise ValueError("workspace authority path must not be empty")
            resolved = Path(path)
        elif isinstance(path, Path):
            resolved = path
        else:
            raise TypeError("workspace authority path must be str or Path")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(event_id_factory):
            raise TypeError("event_id_factory must be callable")
        try:
            validate_local_path(resolved)
            resolved.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            validate_local_path(resolved)
        except (OSError, LocalIntegrityError) as error:
            raise WorkspaceAuthorityStorageError(
                "workspace authority directory is unavailable"
            ) from error
        self._path = resolved
        self._lock_path = resolved.with_name(f"{resolved.name}.lock")
        self._clock = clock or (lambda: datetime.now(UTC))
        self._event_id_factory = event_id_factory
        self._thread_lock = RLock()

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def _lock(self, *, exclusive: bool):
        with self._thread_lock:
            try:
                with locked_private_file(self._lock_path, exclusive=exclusive):
                    yield
            except WorkspaceAuthorityConflict:
                raise
            except (OSError, LocalIntegrityError) as error:
                raise WorkspaceAuthorityStorageError(
                    "workspace authority lock is unavailable"
                ) from error

    def _load(self) -> WorkspaceAuthoritySnapshot:
        if not self._path.exists():
            return WorkspaceAuthoritySnapshot()
        try:
            envelope = read_private_json(self._path)
            payload, _ = open_local_payload(
                envelope,
                payload_type=_WORKSPACE_AUTHORITY_PAYLOAD_TYPE,
            )
            return WorkspaceAuthoritySnapshot.model_validate(payload)
        except (OSError, LocalIntegrityError, TypeError, ValueError) as error:
            raise WorkspaceAuthorityStorageError(
                "workspace authority state is corrupt or unreadable"
            ) from error

    def _write(self, snapshot: WorkspaceAuthoritySnapshot) -> None:
        try:
            envelope = seal_local_payload(
                snapshot.model_dump(mode="json"),
                payload_type=_WORKSPACE_AUTHORITY_PAYLOAD_TYPE,
            )
            atomic_write_private_json(self._path, envelope)
        except (OSError, LocalIntegrityError, TypeError, ValueError) as error:
            raise WorkspaceAuthorityStorageError(
                "workspace authority state write failed"
            ) from error

    def _read[Result](self, operation: Callable[[WorkspaceAuthoritySnapshot], Result]) -> Result:
        with self._lock(exclusive=False):
            return operation(self._load())

    def _mutate[Result](
        self,
        operation: Callable[[WorkspaceAuthoritySnapshot], tuple[WorkspaceAuthoritySnapshot, Result]],
    ) -> Result:
        with self._lock(exclusive=True):
            next_snapshot, result = operation(self._load())
            self._write(next_snapshot)
            return result

    def assert_ready(self) -> None:
        self._read(lambda _snapshot: None)

    def read_snapshot(self) -> WorkspaceAuthoritySnapshot:
        return self._read(lambda snapshot: snapshot)

    @staticmethod
    def _by_proposal(records: tuple[object, ...], proposal_id: UUID):
        for record in records:
            candidate = getattr(record, "proposal_id", None)
            if candidate is None and isinstance(record, WorkspaceProposalRecord):
                candidate = record.proposal.proposal_id
            if candidate is None and isinstance(record, WorkspaceApprovalRequestRecord):
                candidate = record.payload.proposal_id
            if candidate == proposal_id:
                return record
        return None

    def get_proposal_record(self, proposal_id: UUID) -> WorkspaceProposalRecord | None:
        return self._read(
            lambda snapshot: self._by_proposal(snapshot.proposals, proposal_id)
        )

    def get_request(self, proposal_id: UUID) -> WorkspaceApprovalRequestRecord | None:
        return self._read(lambda snapshot: self._by_proposal(snapshot.requests, proposal_id))

    def get_decision(self, proposal_id: UUID) -> WorkspaceApprovalDecisionRecord | None:
        return self._read(lambda snapshot: self._by_proposal(snapshot.decisions, proposal_id))

    def get_ownership(self, proposal_id: UUID) -> WorkspaceEffectOwnership | None:
        return self._read(lambda snapshot: self._by_proposal(snapshot.ownership, proposal_id))

    def get_receipt(self, proposal_id: UUID) -> PatchApplyReceipt | None:
        return self._read(lambda snapshot: self._by_proposal(snapshot.receipts, proposal_id))

    def get_reconciliation(self, proposal_id: UUID) -> WorkspaceReconciliationMarker | None:
        return self._read(
            lambda snapshot: self._by_proposal(snapshot.reconciliations, proposal_id)
        )

    def save_proposal(self, proposal: WorkspacePatchProposal) -> WorkspaceProposalRecord:
        if not isinstance(proposal, WorkspacePatchProposal):
            raise TypeError("proposal must be WorkspacePatchProposal")

        def operation(snapshot: WorkspaceAuthoritySnapshot):
            existing = self._by_proposal(snapshot.proposals, proposal.proposal_id)
            if existing is not None:
                if not isinstance(existing, WorkspaceProposalRecord) or existing.proposal != proposal:
                    raise WorkspaceAuthorityConflict("conflicting workspace proposal exists")
                return snapshot, existing
            record = WorkspaceProposalRecord(
                proposal=proposal,
                proposal_digest=proposal.proposal_digest,
                stored_at=self._clock(),
            )
            event = self._event(record, "PROPOSAL_PERSISTED", proposal.proposal_digest)
            return (
                snapshot.model_copy(
                    update={
                        "proposals": (*snapshot.proposals, record),
                        "audit_events": (*snapshot.audit_events, event),
                    }
                ),
                record,
            )

        return self._mutate(operation)

    def begin_approval(self, proposal_id: UUID) -> WorkspaceProposalRecord:
        def operation(snapshot: WorkspaceAuthoritySnapshot):
            record = self._require_proposal(snapshot, proposal_id)
            if record.state is WorkspaceAuthorityState.AWAITING_APPROVAL:
                return snapshot, record
            if record.state is not WorkspaceAuthorityState.PATCH_PROPOSED:
                raise WorkspaceAuthorityConflict("proposal cannot enter approval from current state")
            updated = record.model_copy(
                update={"state": WorkspaceAuthorityState.AWAITING_APPROVAL}
            )
            return self._replace_proposal(snapshot, updated), updated

        return self._mutate(operation)

    def save_request(
        self,
        request: WorkspaceApprovalRequestRecord,
    ) -> WorkspaceApprovalRequestRecord:
        if not isinstance(request, WorkspaceApprovalRequestRecord):
            raise TypeError("request must be WorkspaceApprovalRequestRecord")

        def operation(snapshot: WorkspaceAuthoritySnapshot):
            record = self._require_proposal(snapshot, request.payload.proposal_id)
            if record.state is not WorkspaceAuthorityState.AWAITING_APPROVAL:
                raise WorkspaceAuthorityConflict("proposal is not awaiting approval")
            if record.proposal.proposal_digest != request.payload.proposal_digest:
                raise WorkspaceAuthorityConflict("approval request proposal binding conflicts")
            existing = self._by_proposal(snapshot.requests, request.payload.proposal_id)
            if existing is not None:
                if existing != request.model_copy(update={"reconciled": existing.reconciled}):
                    raise WorkspaceAuthorityConflict("conflicting approval request exists")
                return snapshot, existing
            event = self._event(record, "APPROVAL_REQUESTED", request.request_hash)
            return (
                snapshot.model_copy(
                    update={
                        "requests": (*snapshot.requests, request),
                        "audit_events": (*snapshot.audit_events, event),
                    }
                ),
                request,
            )

        return self._mutate(operation)

    def save_decision(
        self,
        decision: WorkspaceApprovalDecisionRecord,
    ) -> tuple[WorkspaceApprovalDecisionRecord, bool]:
        if not isinstance(decision, WorkspaceApprovalDecisionRecord):
            raise TypeError("decision must be WorkspaceApprovalDecisionRecord")

        def operation(snapshot: WorkspaceAuthoritySnapshot):
            record = self._require_proposal(snapshot, decision.proposal_id)
            request = self._by_proposal(snapshot.requests, decision.proposal_id)
            existing = self._by_proposal(snapshot.decisions, decision.proposal_id)
            if existing is not None:
                semantically_identical = decision.model_copy(
                    update={"decided_at": existing.decided_at, "decision_hash": existing.decision_hash}
                )
                if existing != semantically_identical:
                    raise WorkspaceAuthorityConflict("conflicting human decision exists")
                return snapshot, (existing, True)
            if (
                record.state is not WorkspaceAuthorityState.AWAITING_APPROVAL
                or not isinstance(request, WorkspaceApprovalRequestRecord)
                or request.interrupt_id != decision.interrupt_id
                or request.request_hash != decision.request_hash
                or record.proposal.proposal_digest != decision.proposal_digest
            ):
                raise WorkspaceAuthorityConflict("human decision prerequisites do not match")
            target_state = (
                WorkspaceAuthorityState.APPROVED
                if decision.decision is ApprovalDecision.APPROVED
                else WorkspaceAuthorityState.DENIED_BY_HUMAN
            )
            updated = record.model_copy(update={"state": target_state})
            event = self._event(record, "DECISION_RECORDED", decision.decision_hash)
            next_snapshot = self._replace_proposal(snapshot, updated).model_copy(
                update={
                    "decisions": (*snapshot.decisions, decision),
                    "audit_events": (*snapshot.audit_events, event),
                }
            )
            return next_snapshot, (decision, False)

        return self._mutate(operation)

    def claim_effect(
        self,
        ownership: WorkspaceEffectOwnership,
    ) -> tuple[WorkspaceEffectOwnership, bool]:
        if not isinstance(ownership, WorkspaceEffectOwnership):
            raise TypeError("ownership must be WorkspaceEffectOwnership")

        def operation(snapshot: WorkspaceAuthoritySnapshot):
            record = self._require_proposal(snapshot, ownership.proposal_id)
            decision = self._by_proposal(snapshot.decisions, ownership.proposal_id)
            existing = self._by_proposal(snapshot.ownership, ownership.proposal_id)
            if existing is not None:
                if existing != ownership:
                    raise WorkspaceAuthorityConflict("conflicting effect ownership exists")
                return snapshot, (existing, True)
            if (
                record.state is not WorkspaceAuthorityState.APPROVED
                or not isinstance(decision, WorkspaceApprovalDecisionRecord)
                or decision.decision is not ApprovalDecision.APPROVED
                or decision.decision_hash != ownership.decision_hash
                or record.proposal.proposal_digest
                != self._proposal_digest_for_ownership(record.proposal, ownership)
            ):
                raise WorkspaceAuthorityConflict("effect ownership prerequisites do not match")
            updated = record.model_copy(update={"state": WorkspaceAuthorityState.APPLYING})
            event = self._event(record, "EFFECT_OWNED", ownership.ownership_hash)
            next_snapshot = self._replace_proposal(snapshot, updated).model_copy(
                update={
                    "ownership": (*snapshot.ownership, ownership),
                    "audit_events": (*snapshot.audit_events, event),
                }
            )
            return next_snapshot, (ownership, False)

        return self._mutate(operation)

    def save_receipt(self, receipt: PatchApplyReceipt) -> PatchApplyReceipt:
        if not isinstance(receipt, PatchApplyReceipt):
            raise TypeError("receipt must be PatchApplyReceipt")

        def operation(snapshot: WorkspaceAuthoritySnapshot):
            record = self._require_proposal(snapshot, receipt.proposal_id)
            ownership = self._by_proposal(snapshot.ownership, receipt.proposal_id)
            existing = self._by_proposal(snapshot.receipts, receipt.proposal_id)
            if existing is not None:
                if existing != receipt:
                    raise WorkspaceAuthorityConflict("conflicting apply receipt exists")
                return snapshot, existing
            if (
                record.state is not WorkspaceAuthorityState.APPLYING
                or not isinstance(ownership, WorkspaceEffectOwnership)
                or ownership.effect_id != receipt.effect_id
                or ownership.idempotency_key != receipt.idempotency_key
                or ownership.after_sha256 != receipt.after_sha256
                or ownership.approval_request_hash != receipt.approval_request_hash
            ):
                raise WorkspaceAuthorityConflict("apply receipt prerequisites do not match")
            updated = record.model_copy(
                update={"state": WorkspaceAuthorityState.PATCH_APPLIED_UNVERIFIED}
            )
            receipt_digest = canonical_workspace_json_digest(receipt.model_dump(mode="json"))
            event = self._event(record, "APPLY_RECORDED", receipt_digest)
            next_snapshot = self._replace_proposal(snapshot, updated).model_copy(
                update={
                    "receipts": (*snapshot.receipts, receipt),
                    "audit_events": (*snapshot.audit_events, event),
                }
            )
            return next_snapshot, receipt

        return self._mutate(operation)

    def save_reconciliation(
        self,
        marker: WorkspaceReconciliationMarker,
    ) -> WorkspaceReconciliationMarker:
        if not isinstance(marker, WorkspaceReconciliationMarker):
            raise TypeError("marker must be WorkspaceReconciliationMarker")

        def operation(snapshot: WorkspaceAuthoritySnapshot):
            record = self._require_proposal(snapshot, marker.proposal_id)
            ownership = self._by_proposal(snapshot.ownership, marker.proposal_id)
            existing = self._by_proposal(snapshot.reconciliations, marker.proposal_id)
            if existing is not None:
                if existing != marker.model_copy(update={"recorded_at": existing.recorded_at}):
                    raise WorkspaceAuthorityConflict("conflicting reconciliation marker exists")
                return snapshot, existing
            if (
                record.state is not WorkspaceAuthorityState.APPLYING
                or not isinstance(ownership, WorkspaceEffectOwnership)
                or ownership.effect_id != marker.effect_id
            ):
                raise WorkspaceAuthorityConflict("reconciliation prerequisites do not match")
            updated = record.model_copy(
                update={"state": WorkspaceAuthorityState.RECONCILIATION_REQUIRED}
            )
            marker_digest = canonical_workspace_json_digest(marker.model_dump(mode="json"))
            event = self._event(record, "RECONCILIATION_REQUIRED", marker_digest)
            next_snapshot = self._replace_proposal(snapshot, updated).model_copy(
                update={
                    "reconciliations": (*snapshot.reconciliations, marker),
                    "audit_events": (*snapshot.audit_events, event),
                }
            )
            return next_snapshot, marker

        return self._mutate(operation)

    @staticmethod
    def _proposal_digest_for_ownership(
        proposal: WorkspacePatchProposal,
        ownership: WorkspaceEffectOwnership,
    ) -> str:
        if (
            proposal.proposal_id != ownership.proposal_id
            or proposal.run_id != ownership.run_id
            or proposal.trace_id != ownership.trace_id
            or proposal.workspace_id != ownership.workspace_id
            or proposal.fixture_version != ownership.fixture_version
            or proposal.target_path != ownership.target_path
            or proposal.target_before_sha256 != ownership.before_sha256
            or proposal.canonical_after_sha256 != ownership.after_sha256
            or proposal.patch_digest != ownership.patch_digest
        ):
            return ""
        return proposal.proposal_digest

    @staticmethod
    def _require_proposal(
        snapshot: WorkspaceAuthoritySnapshot,
        proposal_id: UUID,
    ) -> WorkspaceProposalRecord:
        record = LocalFileWorkspaceAuthorityRepository._by_proposal(
            snapshot.proposals,
            proposal_id,
        )
        if not isinstance(record, WorkspaceProposalRecord):
            raise WorkspaceAuthorityConflict("workspace proposal does not exist")
        return record

    @staticmethod
    def _replace_proposal(
        snapshot: WorkspaceAuthoritySnapshot,
        replacement: WorkspaceProposalRecord,
    ) -> WorkspaceAuthoritySnapshot:
        proposals = tuple(
            replacement
            if record.proposal.proposal_id == replacement.proposal.proposal_id
            else record
            for record in snapshot.proposals
        )
        return snapshot.model_copy(update={"proposals": proposals})

    def _event(
        self,
        record: WorkspaceProposalRecord,
        event_type: str,
        payload_sha256: str,
    ) -> WorkspaceAuthorityAuditEvent:
        return WorkspaceAuthorityAuditEvent(
            event_id=self._event_id_factory(),
            proposal_id=record.proposal.proposal_id,
            run_id=record.proposal.run_id,
            workspace_id=record.proposal.workspace_id,
            event_type=event_type,
            payload_sha256=payload_sha256,
            recorded_at=self._clock(),
        )
