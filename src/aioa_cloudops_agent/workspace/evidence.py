"""Typed read/list/hash evidence services for the W1 sealed workspace."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from threading import Lock
from uuid import UUID

from aioa_cloudops_agent.domain import ContractValidationError, validate_correlation_id
from aioa_cloudops_agent.nz import ControlResult, FailureDetail, FailureKind

from .contracts import (
    WorkspaceArtifactRef,
    WorkspaceEvidenceOutcome,
    WorkspaceEvidenceReceipt,
    WorkspaceHashResult,
    WorkspaceListResult,
    WorkspaceObservation,
    WorkspaceOperation,
    WorkspacePolicyDecision,
    WorkspaceReadReceipt,
    WorkspaceReadResult,
    WorkspaceRef,
)
from .fixture import canonical_artifact_set_digest
from .jail import WorkspaceJail, WorkspaceJailViolation

WorkspaceInspectionResult = ControlResult[WorkspaceObservation]
WorkspaceListingResult = ControlResult[WorkspaceListResult]
WorkspaceArtifactReadResult = ControlResult[WorkspaceReadResult]
WorkspaceArtifactHashResult = ControlResult[WorkspaceHashResult]


class WorkspaceEvidenceService:
    """Produce bounded receipts without granting filesystem or process authority."""

    def __init__(
        self,
        jail: WorkspaceJail,
        *,
        trace_id: UUID,
        clock: Callable[[], datetime],
        event_id_factory: Callable[[], UUID],
    ) -> None:
        if not isinstance(jail, WorkspaceJail):
            raise ContractValidationError("jail must be WorkspaceJail")
        if not callable(clock) or not callable(event_id_factory):
            raise ContractValidationError("clock and event_id_factory must be callable")
        validate_correlation_id(trace_id)
        self._jail = jail
        self._trace_id = trace_id
        self._clock = clock
        self._event_id_factory = event_id_factory
        self._timeline: list[WorkspaceEvidenceReceipt] = []
        self._timeline_lock = Lock()

    @property
    def workspace_ref(self) -> WorkspaceRef:
        return self._jail.workspace_ref

    @property
    def profile(self):
        return self._jail.profile

    @property
    def evidence_timeline(self) -> tuple[WorkspaceEvidenceReceipt, ...]:
        """Return an immutable snapshot of successful read-only observations."""

        with self._timeline_lock:
            return tuple(self._timeline)

    def inspect_workspace_incident(
        self,
        workspace_ref: WorkspaceRef,
    ) -> WorkspaceInspectionResult:
        """Describe symptoms and evidence scope without deciding the root cause."""

        try:
            artifacts, policy = self._jail.list_artifacts(
                workspace_ref,
                operation=WorkspaceOperation.INSPECT,
            )
        except WorkspaceJailViolation as error:
            return self._failed(error)
        receipt = self._workspace_receipt(
            operation=WorkspaceOperation.INSPECT,
            artifacts=artifacts,
            policy=policy,
        )
        observation = WorkspaceObservation(
            workspace=workspace_ref,
            incident_id="render-runtime-start-127",
            observed_symptoms=(
                "Container image build completed before runtime startup",
                "Runtime process exited with status 127",
                "Deployment output contains a File name too long error",
            ),
            allowed_artifacts=artifacts,
            recommended_review_order=(
                "deployment.log",
                "render.yaml",
                "scripts/render_start.sh",
                "expected_runtime_contract.json",
                "README.md",
            ),
            receipt=receipt,
        )
        self._record(receipt)
        return ControlResult[WorkspaceObservation].succeeded(observation)

    def list_allowed_artifacts(
        self,
        workspace_ref: WorkspaceRef,
    ) -> WorkspaceListingResult:
        """List only the deterministic server allowlist and record its digest."""

        try:
            artifacts, policy = self._jail.list_artifacts(workspace_ref)
        except WorkspaceJailViolation as error:
            return self._failed(error)
        receipt = self._workspace_receipt(
            operation=WorkspaceOperation.LIST,
            artifacts=artifacts,
            policy=policy,
        )
        result = WorkspaceListResult(artifacts=artifacts, receipt=receipt)
        self._record(receipt)
        return ControlResult[WorkspaceListResult].succeeded(result)

    def read_allowed_path(
        self,
        workspace_ref: WorkspaceRef,
        relative_path: object,
    ) -> WorkspaceArtifactReadResult:
        """Resolve a model-supplied name only through the server-owned allowlist."""

        try:
            artifact, _ = self._jail.artifact_ref(
                workspace_ref,
                relative_path,
                operation=WorkspaceOperation.READ,
            )
        except WorkspaceJailViolation as error:
            return self._failed(error)
        return self.read_allowed_artifact(workspace_ref, artifact)

    def read_allowed_artifact(
        self,
        workspace_ref: WorkspaceRef,
        artifact_ref: WorkspaceArtifactRef,
    ) -> WorkspaceArtifactReadResult:
        """Read bounded UTF-8 content and retain explicit truncation metadata."""

        try:
            jailed = self._jail.read_artifact(
                workspace_ref,
                artifact_ref,
                operation=WorkspaceOperation.READ,
            )
        except WorkspaceJailViolation as error:
            return self._failed(error)
        try:
            decoded = jailed.content.decode("utf-8")
        except UnicodeDecodeError:
            return self._validation_failure(
                "WORKSPACE_TEXT_ENCODING_INVALID",
                "Allowlisted artifact is not valid UTF-8 text",
            )
        encoded = decoded.encode("utf-8")
        limit = self._jail.profile.max_read_bytes
        if len(encoded) > limit:
            prefix = encoded[:limit].decode("utf-8", errors="ignore")
            returned_bytes = len(prefix.encode("utf-8"))
            truncated = True
            text = prefix
        else:
            returned_bytes = len(encoded)
            truncated = False
            text = decoded
        receipt = WorkspaceReadReceipt(
            **self._receipt_fields(
                operation=WorkspaceOperation.READ,
                policy=jailed.policy,
                artifact=jailed.artifact,
                observed_size=len(jailed.content),
                sha256=jailed.artifact.sha256,
                returned_bytes=returned_bytes,
                truncated=truncated,
            )
        )
        result = WorkspaceReadResult(text=text, receipt=receipt)
        self._record(receipt)
        return ControlResult[WorkspaceReadResult].succeeded(result)

    def hash_allowed_path(
        self,
        workspace_ref: WorkspaceRef,
        relative_path: object,
    ) -> WorkspaceArtifactHashResult:
        """Resolve and hash one allowlisted name through a separate operation receipt."""

        try:
            artifact, _ = self._jail.artifact_ref(
                workspace_ref,
                relative_path,
                operation=WorkspaceOperation.HASH,
            )
        except WorkspaceJailViolation as error:
            return self._failed(error)
        return self.hash_allowed_artifact(workspace_ref, artifact)

    def hash_allowed_artifact(
        self,
        workspace_ref: WorkspaceRef,
        artifact_ref: WorkspaceArtifactRef,
    ) -> WorkspaceArtifactHashResult:
        """Re-read the full file and return its canonical content identity."""

        try:
            jailed = self._jail.read_artifact(
                workspace_ref,
                artifact_ref,
                operation=WorkspaceOperation.HASH,
            )
        except WorkspaceJailViolation as error:
            return self._failed(error)
        receipt = WorkspaceReadReceipt(
            **self._receipt_fields(
                operation=WorkspaceOperation.HASH,
                policy=jailed.policy,
                artifact=jailed.artifact,
                observed_size=len(jailed.content),
                sha256=jailed.artifact.sha256,
                returned_bytes=0,
                truncated=False,
            )
        )
        result = WorkspaceHashResult(sha256=jailed.artifact.sha256, receipt=receipt)
        self._record(receipt)
        return ControlResult[WorkspaceHashResult].succeeded(result)

    def _workspace_receipt(
        self,
        *,
        operation: WorkspaceOperation,
        artifacts: tuple[WorkspaceArtifactRef, ...],
        policy: WorkspacePolicyDecision,
    ) -> WorkspaceEvidenceReceipt:
        return WorkspaceEvidenceReceipt(
            **self._receipt_fields(
                operation=operation,
                policy=policy,
                artifact=None,
                observed_size=sum(artifact.size for artifact in artifacts),
                sha256=canonical_artifact_set_digest(self._jail.profile, artifacts),
                returned_bytes=0,
                truncated=False,
            )
        )

    def _receipt_fields(
        self,
        *,
        operation: WorkspaceOperation,
        policy: WorkspacePolicyDecision,
        artifact: WorkspaceArtifactRef | None,
        observed_size: int,
        sha256: str,
        returned_bytes: int,
        truncated: bool,
    ) -> dict[str, object]:
        ref = self._jail.workspace_ref
        return {
            "event_id": self._event_id_factory(),
            "run_id": ref.run_id,
            "trace_id": self._trace_id,
            "workspace_id": ref.workspace_id,
            "fixture_version": ref.fixture_version,
            "operation": operation,
            "outcome": WorkspaceEvidenceOutcome.SUCCESS,
            "artifact": artifact,
            "observed_size": observed_size,
            "sha256": sha256,
            "returned_bytes": returned_bytes,
            "truncated": truncated,
            "provenance": "sealed_fixture:workspace_render_incident_v1",
            "observed_at": self._clock(),
            "policy": policy,
        }

    def _record(self, receipt: WorkspaceEvidenceReceipt) -> None:
        with self._timeline_lock:
            self._timeline.append(receipt)

    @staticmethod
    def _failed(error: WorkspaceJailViolation):
        return ControlResult.failed(
            FailureDetail(
                kind=error.failure_kind,
                code=error.decision.reason_code,
                message=error.decision.reason,
                retryable=False,
            )
        )

    @staticmethod
    def _validation_failure(code: str, message: str):
        return ControlResult.failed(
            FailureDetail(
                kind=FailureKind.VALIDATION_FAILURE,
                code=code,
                message=message,
                retryable=False,
            )
        )
