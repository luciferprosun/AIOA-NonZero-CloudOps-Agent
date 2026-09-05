"""Integrity-sealed at-most-once repository for Phase 8 remote effects."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from threading import RLock
from typing import Self
from uuid import UUID

from pydantic import model_validator

from aioa_cloudops_agent.execution import ExecutionApprovalDecision
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

from .write_contracts import (
    GitEffectOwnership,
    GitReconciliationMarker,
    GitRemoteWriteReceipt,
)

_PAYLOAD_TYPE = "AIOA_GITHUB_EFFECTS_V1"


class GitEffectRepositoryError(RuntimeError):
    """Durable effect truth is unavailable or conflicting."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class GitEffectSnapshot(NonZeroContract):
    decisions: tuple[ExecutionApprovalDecision, ...] = ()
    ownership: tuple[GitEffectOwnership, ...] = ()
    receipts: tuple[GitRemoteWriteReceipt, ...] = ()
    reconciliation: tuple[GitReconciliationMarker, ...] = ()

    @model_validator(mode="after")
    def validate_unique(self) -> Self:
        identities = (
            tuple(str(record.request_id) for record in self.decisions),
            tuple(str(record.operation_id) for record in self.ownership),
            tuple(str(record.operation_id) for record in self.receipts),
            tuple(str(record.operation_id) for record in self.reconciliation),
        )
        for values in identities:
            if len(values) != len(set(values)):
                raise ValueError("Git effect snapshot contains duplicate operation records")
        return self


class LocalFileGitEffectRepository:
    """Owner-only locked state whose claim precedes every remote write attempt."""

    def __init__(self, path: Path) -> None:
        if not isinstance(path, Path) or not path.is_absolute():
            raise GitEffectRepositoryError("GIT_EFFECT_STATE_PATH_INVALID")
        try:
            validate_local_path(path)
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            path.parent.chmod(0o700)
            validate_local_path(path)
        except (OSError, LocalIntegrityError) as error:
            raise GitEffectRepositoryError("GIT_EFFECT_STATE_PATH_INVALID") from error
        self._path = path
        self._lock_path = path.with_name(f"{path.name}.lock")
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
            except GitEffectRepositoryError:
                raise
            except (OSError, LocalIntegrityError) as error:
                raise GitEffectRepositoryError("GIT_EFFECT_STATE_UNAVAILABLE") from error

    def _load(self) -> GitEffectSnapshot:
        if not self._path.exists():
            return GitEffectSnapshot()
        try:
            envelope = read_private_json(self._path)
            payload, _ = open_local_payload(envelope, payload_type=_PAYLOAD_TYPE)
            return GitEffectSnapshot.model_validate(payload)
        except (OSError, LocalIntegrityError, TypeError, ValueError) as error:
            raise GitEffectRepositoryError("GIT_EFFECT_STATE_CORRUPT") from error

    def _write(self, snapshot: GitEffectSnapshot) -> None:
        try:
            envelope = seal_local_payload(
                snapshot.model_dump(mode="json"),
                payload_type=_PAYLOAD_TYPE,
            )
            atomic_write_private_json(self._path, envelope)
        except (OSError, LocalIntegrityError, TypeError, ValueError) as error:
            raise GitEffectRepositoryError("GIT_EFFECT_STATE_WRITE_FAILED") from error

    @staticmethod
    def _find(records: tuple[object, ...], operation_id: UUID):
        return next(
            (record for record in records if getattr(record, "operation_id", None) == operation_id),
            None,
        )

    def read_snapshot(self) -> GitEffectSnapshot:
        with self._lock(exclusive=False):
            return self._load()

    def completed_operation_ids(self) -> tuple[str, ...]:
        snapshot = self.read_snapshot()
        return tuple(str(receipt.operation_id) for receipt in snapshot.receipts)

    def get_ownership(self, operation_id: UUID) -> GitEffectOwnership | None:
        snapshot = self.read_snapshot()
        return self._find(snapshot.ownership, operation_id)

    def get_decision(self, request_id: UUID) -> ExecutionApprovalDecision | None:
        snapshot = self.read_snapshot()
        return next(
            (record for record in snapshot.decisions if record.request_id == request_id),
            None,
        )

    def save_decision(
        self,
        decision: ExecutionApprovalDecision,
    ) -> ExecutionApprovalDecision:
        """Persist an externally obtained human decision before actuator invocation."""

        if not isinstance(decision, ExecutionApprovalDecision):
            raise TypeError("decision must be ExecutionApprovalDecision")
        with self._lock(exclusive=True):
            snapshot = self._load()
            existing = next(
                (
                    record
                    for record in snapshot.decisions
                    if record.request_id == decision.request_id
                ),
                None,
            )
            if existing is not None:
                if existing != decision:
                    raise GitEffectRepositoryError("GIT_APPROVAL_DECISION_CONFLICT")
                return existing
            self._write(
                snapshot.model_copy(update={"decisions": (*snapshot.decisions, decision)})
            )
            return decision

    def get_receipt(self, operation_id: UUID) -> GitRemoteWriteReceipt | None:
        snapshot = self.read_snapshot()
        return self._find(snapshot.receipts, operation_id)

    def get_reconciliation(self, operation_id: UUID) -> GitReconciliationMarker | None:
        snapshot = self.read_snapshot()
        return self._find(snapshot.reconciliation, operation_id)

    def claim(self, ownership: GitEffectOwnership) -> GitEffectOwnership:
        if not isinstance(ownership, GitEffectOwnership):
            raise TypeError("ownership must be GitEffectOwnership")
        with self._lock(exclusive=True):
            snapshot = self._load()
            existing = self._find(snapshot.ownership, ownership.operation_id)
            if existing is not None:
                if existing != ownership:
                    raise GitEffectRepositoryError("GIT_EFFECT_OWNERSHIP_CONFLICT")
                return existing
            if any(
                record.idempotency_key == ownership.idempotency_key
                for record in snapshot.ownership
            ):
                raise GitEffectRepositoryError("GIT_EFFECT_IDEMPOTENCY_CONFLICT")
            if self._find(snapshot.receipts, ownership.operation_id) is not None or self._find(
                snapshot.reconciliation, ownership.operation_id
            ) is not None:
                raise GitEffectRepositoryError("GIT_EFFECT_STATE_CONFLICT")
            self._write(
                snapshot.model_copy(update={"ownership": (*snapshot.ownership, ownership)})
            )
            return ownership

    def save_receipt(self, receipt: GitRemoteWriteReceipt) -> GitRemoteWriteReceipt:
        if not isinstance(receipt, GitRemoteWriteReceipt):
            raise TypeError("receipt must be GitRemoteWriteReceipt")
        with self._lock(exclusive=True):
            snapshot = self._load()
            existing = self._find(snapshot.receipts, receipt.operation_id)
            if existing is not None:
                if existing != receipt:
                    raise GitEffectRepositoryError("GIT_EFFECT_RECEIPT_CONFLICT")
                return existing
            ownership = self._find(snapshot.ownership, receipt.operation_id)
            if ownership is None or ownership.ownership_sha256 != receipt.ownership_sha256:
                raise GitEffectRepositoryError("GIT_EFFECT_OWNERSHIP_MISSING")
            if self._find(snapshot.reconciliation, receipt.operation_id) is not None:
                raise GitEffectRepositoryError("GIT_EFFECT_RECONCILIATION_OPEN")
            self._write(snapshot.model_copy(update={"receipts": (*snapshot.receipts, receipt)}))
            return receipt

    def save_reconciliation(
        self,
        marker: GitReconciliationMarker,
    ) -> GitReconciliationMarker:
        if not isinstance(marker, GitReconciliationMarker):
            raise TypeError("marker must be GitReconciliationMarker")
        with self._lock(exclusive=True):
            snapshot = self._load()
            existing = self._find(snapshot.reconciliation, marker.operation_id)
            if existing is not None:
                if existing != marker:
                    raise GitEffectRepositoryError("GIT_EFFECT_RECONCILIATION_CONFLICT")
                return existing
            ownership = self._find(snapshot.ownership, marker.operation_id)
            if ownership is None or ownership.ownership_sha256 != marker.ownership_sha256:
                raise GitEffectRepositoryError("GIT_EFFECT_OWNERSHIP_MISSING")
            if self._find(snapshot.receipts, marker.operation_id) is not None:
                raise GitEffectRepositoryError("GIT_EFFECT_ALREADY_VERIFIED")
            self._write(
                snapshot.model_copy(
                    update={"reconciliation": (*snapshot.reconciliation, marker)}
                )
            )
            return marker
