"""Restart-safe atomic JSON implementation of the canonical durable truth contract."""

import fcntl
import json
import os
import tempfile
from collections.abc import Callable
from contextlib import contextmanager, suppress
from datetime import datetime
from pathlib import Path
from threading import RLock
from uuid import UUID

from aioa_cloudops_agent.nz import (
    ActionProposal,
    ActionResult,
    Approval,
    AuditEvent,
    BudgetCounters,
    Checkpoint,
    ExecutionAcknowledgement,
    IdempotencyRecord,
    IdempotencyStatus,
    ProposalState,
    Run,
    VerificationEvidence,
    WorkflowState,
)
from aioa_cloudops_agent.nz.errors import StorageDependencyError

from .memory import InMemoryTestDurableTruthRepository


class LocalFileDurableTruthRepository:
    """Atomic local state with process locking and full typed reconstruction."""

    def __init__(self, path: str | Path) -> None:
        if isinstance(path, str):
            if not path.strip():
                raise ValueError("local state path must not be empty")
            resolved = Path(path)
        elif isinstance(path, Path):
            resolved = path
        else:
            raise TypeError("local state path must be str or Path")
        if resolved.exists() and resolved.is_dir():
            raise StorageDependencyError("local state path must be a file")
        try:
            resolved.parent.mkdir(parents=True, exist_ok=True)
        except OSError as error:
            raise StorageDependencyError("local state directory is unavailable") from error
        self._path = resolved
        self._lock_path = resolved.with_name(f"{resolved.name}.lock")
        self._thread_lock = RLock()

    @property
    def path(self) -> Path:
        return self._path

    @contextmanager
    def _lock(self, *, exclusive: bool) -> object:
        with self._thread_lock:
            try:
                with self._lock_path.open("a+b") as handle:
                    os.chmod(self._lock_path, 0o600)
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
                    try:
                        yield
                    finally:
                        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            except OSError as error:
                raise StorageDependencyError("local state lock is unavailable") from error

    def _load(self) -> InMemoryTestDurableTruthRepository:
        if not self._path.exists():
            return InMemoryTestDurableTruthRepository()
        try:
            payload = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise StorageDependencyError("local durable state is corrupt or unreadable") from error
        return InMemoryTestDurableTruthRepository.from_snapshot(payload)

    def _write(self, repository: InMemoryTestDurableTruthRepository) -> None:
        serialized = json.dumps(
            repository.export_snapshot(),
            allow_nan=False,
            ensure_ascii=True,
            indent=2,
            sort_keys=True,
        ) + "\n"
        descriptor = -1
        temporary_name = ""
        try:
            descriptor, temporary_name = tempfile.mkstemp(
                dir=self._path.parent,
                prefix=f".{self._path.name}.",
                suffix=".tmp",
            )
            os.fchmod(descriptor, 0o600)
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                descriptor = -1
                handle.write(serialized)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary_name, self._path)
            directory_descriptor = os.open(self._path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_descriptor)
            finally:
                os.close(directory_descriptor)
        except OSError as error:
            if descriptor >= 0:
                os.close(descriptor)
            if temporary_name:
                with suppress(OSError):
                    Path(temporary_name).unlink(missing_ok=True)
            raise StorageDependencyError("local durable state write failed") from error

    def _read[Result](
        self,
        operation: Callable[[InMemoryTestDurableTruthRepository], Result],
    ) -> Result:
        with self._lock(exclusive=False):
            return operation(self._load())

    def _mutate[Result](
        self,
        operation: Callable[[InMemoryTestDurableTruthRepository], Result],
    ) -> Result:
        with self._lock(exclusive=True):
            repository = self._load()
            result = operation(repository)
            self._write(repository)
            return result

    def create_run(self, run: Run) -> Run:
        return self._mutate(lambda repository: repository.create_run(run))

    def get_run(self, run_id: UUID) -> Run | None:
        return self._read(lambda repository: repository.get_run(run_id))

    def transition_run(
        self,
        run_id: UUID,
        next_state: WorkflowState,
        *,
        expected_state: WorkflowState,
        expected_version: int,
        updated_at: datetime,
        approval_proposal_id: UUID | None = None,
        verification_proposal_id: UUID | None = None,
    ) -> Run:
        return self._mutate(
            lambda repository: repository.transition_run(
                run_id,
                next_state,
                expected_state=expected_state,
                expected_version=expected_version,
                updated_at=updated_at,
                approval_proposal_id=approval_proposal_id,
                verification_proposal_id=verification_proposal_id,
            )
        )

    def update_run_budget(
        self,
        run_id: UUID,
        budget: BudgetCounters,
        *,
        expected_version: int,
        updated_at: datetime,
    ) -> Run:
        return self._mutate(
            lambda repository: repository.update_run_budget(
                run_id,
                budget,
                expected_version=expected_version,
                updated_at=updated_at,
            )
        )

    def create_proposal(self, proposal: ActionProposal) -> ActionProposal:
        return self._mutate(lambda repository: repository.create_proposal(proposal))

    def get_proposal(self, proposal_id: UUID) -> ActionProposal | None:
        return self._read(lambda repository: repository.get_proposal(proposal_id))

    def transition_proposal(
        self,
        proposal_id: UUID,
        next_state: ProposalState,
        *,
        expected_state: ProposalState,
    ) -> ActionProposal:
        return self._mutate(
            lambda repository: repository.transition_proposal(
                proposal_id,
                next_state,
                expected_state=expected_state,
            )
        )

    def create_approval(self, approval: Approval) -> Approval:
        return self._mutate(lambda repository: repository.create_approval(approval))

    def get_approval(self, proposal_id: UUID) -> Approval | None:
        return self._read(lambda repository: repository.get_approval(proposal_id))

    def register_idempotency(self, record: IdempotencyRecord) -> IdempotencyRecord:
        return self._mutate(lambda repository: repository.register_idempotency(record))

    def get_idempotency(self, idempotency_key: str) -> IdempotencyRecord | None:
        return self._read(lambda repository: repository.get_idempotency(idempotency_key))

    def complete_idempotency(
        self,
        idempotency_key: str,
        result: ActionResult,
        *,
        completed_at: datetime,
        expected_status: IdempotencyStatus = IdempotencyStatus.REGISTERED,
    ) -> IdempotencyRecord:
        return self._mutate(
            lambda repository: repository.complete_idempotency(
                idempotency_key,
                result,
                completed_at=completed_at,
                expected_status=expected_status,
            )
        )

    def record_execution_acknowledgement(
        self,
        idempotency_key: str,
        acknowledgement: ExecutionAcknowledgement,
        *,
        expected_status: IdempotencyStatus = IdempotencyStatus.REGISTERED,
    ) -> IdempotencyRecord:
        return self._mutate(
            lambda repository: repository.record_execution_acknowledgement(
                idempotency_key,
                acknowledgement,
                expected_status=expected_status,
            )
        )

    def save_checkpoint(
        self,
        checkpoint: Checkpoint,
        *,
        expected_version: int | None,
    ) -> Checkpoint:
        return self._mutate(
            lambda repository: repository.save_checkpoint(
                checkpoint,
                expected_version=expected_version,
            )
        )

    def get_checkpoint(self, run_id: UUID) -> Checkpoint | None:
        return self._read(lambda repository: repository.get_checkpoint(run_id))

    def append_audit_event(self, event: AuditEvent) -> AuditEvent:
        return self._mutate(lambda repository: repository.append_audit_event(event))

    def get_audit_event(self, run_id: UUID, event_id: UUID) -> AuditEvent | None:
        return self._read(lambda repository: repository.get_audit_event(run_id, event_id))

    def list_audit_events(self, run_id: UUID, *, limit: int = 128) -> tuple[AuditEvent, ...]:
        """Read a bounded audit timeline for one exact run without scanning other state."""

        return self._read(
            lambda repository: repository.list_audit_events(run_id, limit=limit)
        )

    def create_verification_evidence(
        self,
        evidence: VerificationEvidence,
    ) -> VerificationEvidence:
        return self._mutate(
            lambda repository: repository.create_verification_evidence(evidence)
        )

    def get_verification_evidence(
        self,
        run_id: UUID,
        proposal_id: UUID,
    ) -> VerificationEvidence | None:
        return self._read(
            lambda repository: repository.get_verification_evidence(run_id, proposal_id)
        )
