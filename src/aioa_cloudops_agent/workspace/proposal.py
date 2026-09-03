"""Pure W2 builder for one proof-carrying, non-applying patch proposal."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from uuid import UUID

from pydantic import ValidationError

from aioa_cloudops_agent.domain import AuthorityGate, ContractValidationError
from aioa_cloudops_agent.nz import (
    ControlResult,
    FailureDetail,
    FailureKind,
    ResultStatus,
    generate_proposal_id,
)

from .contracts import (
    W2_AFTER_LINE,
    W2_BEFORE_BLOCK,
    W2_ROLLBACK_STRATEGY,
    W2_TARGET_PATH,
    W2_VERIFICATION_PROFILE_ID,
    WorkspaceEvidenceOutcome,
    WorkspaceEvidenceReceipt,
    WorkspaceOperation,
    WorkspacePatchChange,
    WorkspacePatchPreview,
    WorkspacePatchProposal,
    WorkspacePatchProposalOutcome,
    WorkspacePatchTarget,
    WorkspaceProposalEvidenceRef,
    WorkspaceRef,
    WorkspaceRemediationKind,
    canonical_workspace_json_digest,
    canonical_workspace_unified_diff,
)
from .evidence import WorkspaceEvidenceService

W2_CERTIFIED_W1_ROOT_DIGEST = (
    "84172797b4203b01e7404649449ac7b6468e94b88e7aba9b2104d18c01668db8"
)
W2_RENDER_BEFORE_SHA256 = (
    "b957bbf10af3d711fbfeda271f8ba3b362894f4b02bb8d88239985769a3968db"
)
W2_RENDER_START_SCRIPT_SHA256 = (
    "d350917c132a338605f630fde97a2ac017e1664fe9cf413a7153827326e6d250"
)
W2_EXPECTED_RUNTIME_CONTRACT_SHA256 = (
    "8bf5a36539ea313a578e194e1c84568586770cc792d60709ebde106df9325178"
)

WorkspacePatchProposalBuildResult = ControlResult[WorkspacePatchProposal]

_REQUIRED_EVIDENCE = (
    (WorkspaceOperation.INSPECT, None),
    (WorkspaceOperation.READ, "deployment.log"),
    (WorkspaceOperation.HASH, "render.yaml"),
    (WorkspaceOperation.HASH, "scripts/render_start.sh"),
    (WorkspaceOperation.HASH, "expected_runtime_contract.json"),
)


class WorkspacePatchProposalBuilder:
    """Build canonical proposal data while retaining zero workspace write authority."""

    def __init__(
        self,
        service: WorkspaceEvidenceService,
        *,
        clock: Callable[[], datetime] | None = None,
        proposal_id_factory: Callable[[], UUID] = generate_proposal_id,
    ) -> None:
        if not isinstance(service, WorkspaceEvidenceService):
            raise ContractValidationError("service must be WorkspaceEvidenceService")
        if clock is not None and not callable(clock):
            raise ContractValidationError("clock must be callable")
        if not callable(proposal_id_factory):
            raise ContractValidationError("proposal_id_factory must be callable")
        self._service = service
        self._clock = clock or (lambda: datetime.now(UTC))
        self._proposal_id_factory = proposal_id_factory

    @property
    def service(self) -> WorkspaceEvidenceService:
        return self._service

    def build(
        self,
        workspace_ref: WorkspaceRef | object,
        remediation_kind: WorkspaceRemediationKind | object,
        *,
        evidence_receipts: tuple[WorkspaceEvidenceReceipt, ...] | None = None,
    ) -> WorkspacePatchProposalBuildResult:
        """Return an inert exact preview; never open a writable handle or apply bytes."""

        if not isinstance(remediation_kind, WorkspaceRemediationKind):
            return self._failed(
                WorkspacePatchProposalOutcome.UNSUPPORTED_REMEDIATION,
                FailureKind.POLICY_DENIAL,
                "Requested remediation is outside the closed W2 policy",
            )
        if remediation_kind is not WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE:
            return self._failed(
                WorkspacePatchProposalOutcome.UNSUPPORTED_REMEDIATION,
                FailureKind.POLICY_DENIAL,
                "Requested remediation is outside the closed W2 policy",
            )
        current_ref = self._service.workspace_ref
        if not isinstance(workspace_ref, WorkspaceRef):
            return self._failed(
                WorkspacePatchProposalOutcome.POLICY_DENIED,
                FailureKind.POLICY_DENIAL,
                "Workspace reference failed strict validation",
            )
        if (
            workspace_ref.run_id != current_ref.run_id
            or workspace_ref.workspace_id != current_ref.workspace_id
            or workspace_ref.fixture_version != current_ref.fixture_version
        ):
            return self._failed(
                WorkspacePatchProposalOutcome.STALE_WORKSPACE,
                FailureKind.POLICY_DENIAL,
                "Workspace identity is outside the current sealed run",
            )
        if (
            workspace_ref.root_digest != current_ref.root_digest
            or workspace_ref.created_from_digest != current_ref.created_from_digest
            or current_ref.root_digest != W2_CERTIFIED_W1_ROOT_DIGEST
        ):
            return self._failed(
                WorkspacePatchProposalOutcome.BASE_DIGEST_MISMATCH,
                FailureKind.VALIDATION_FAILURE,
                "Workspace base digest does not match the certified W1 fixture",
            )
        if workspace_ref != current_ref:
            return self._failed(
                WorkspacePatchProposalOutcome.STALE_WORKSPACE,
                FailureKind.POLICY_DENIAL,
                "Workspace reference is stale",
            )

        supplied = evidence_receipts
        if supplied is None:
            supplied = self._service.evidence_timeline
        selected_or_failure = self._select_required_evidence(supplied)
        if isinstance(selected_or_failure, ControlResult):
            return selected_or_failure
        selected = selected_or_failure

        render_read = self._service.read_allowed_path(workspace_ref, W2_TARGET_PATH)
        if render_read.status is ResultStatus.FAILURE or render_read.value is None:
            return self._map_read_failure(render_read.failure)
        if render_read.value.receipt.truncated:
            return self._failed(
                WorkspacePatchProposalOutcome.VALIDATION_FAILURE,
                FailureKind.VALIDATION_FAILURE,
                "Canonical render.yaml cannot be truncated",
            )
        before_text = render_read.value.text
        target_artifact = render_read.value.receipt.artifact
        target_evidence = selected[(WorkspaceOperation.HASH, W2_TARGET_PATH)]
        if (
            target_artifact.sha256 != target_evidence.sha256
            or target_artifact.sha256 != W2_RENDER_BEFORE_SHA256
        ):
            return self._failed(
                WorkspacePatchProposalOutcome.TARGET_DIGEST_MISMATCH,
                FailureKind.VALIDATION_FAILURE,
                "render.yaml no longer matches the exact observed W1 target",
            )

        support_hashes: dict[str, str] = {}
        for path, expected_sha256 in (
            ("scripts/render_start.sh", W2_RENDER_START_SCRIPT_SHA256),
            ("expected_runtime_contract.json", W2_EXPECTED_RUNTIME_CONTRACT_SHA256),
        ):
            current_hash = self._service.hash_allowed_path(workspace_ref, path)
            if current_hash.status is ResultStatus.FAILURE or current_hash.value is None:
                return self._map_read_failure(current_hash.failure)
            evidence = selected[(WorkspaceOperation.HASH, path)]
            if current_hash.value.sha256 != evidence.sha256 or evidence.sha256 != expected_sha256:
                return self._failed(
                    WorkspacePatchProposalOutcome.SUPPORTING_ARTIFACT_MISMATCH,
                    FailureKind.VALIDATION_FAILURE,
                    "Supporting artifact no longer matches sealed W1 evidence",
                )
            support_hashes[path] = current_hash.value.sha256

        if (
            len(re.findall(r"(?m)^\s*dockerCommand\s*:", before_text)) != 1
            or before_text.count(W2_BEFORE_BLOCK) != 1
        ):
            return self._failed(
                WorkspacePatchProposalOutcome.AMBIGUOUS_TARGET,
                FailureKind.VALIDATION_FAILURE,
                "render.yaml does not contain exactly one canonical W2 target",
            )
        after_text = before_text.replace(W2_BEFORE_BLOCK, W2_AFTER_LINE, 1)
        if after_text == before_text or after_text.count(W2_AFTER_LINE) != 1:
            return self._failed(
                WorkspacePatchProposalOutcome.AMBIGUOUS_TARGET,
                FailureKind.VALIDATION_FAILURE,
                "Canonical W2 replacement could not be constructed exactly once",
            )

        evidence_refs = tuple(self._evidence_ref(receipt) for receipt in selected.values())
        evidence_digest = canonical_workspace_json_digest(
            [reference.model_dump(mode="json") for reference in evidence_refs]
        )
        before_sha256 = hashlib.sha256(before_text.encode("utf-8")).hexdigest()
        after_sha256 = hashlib.sha256(after_text.encode("utf-8")).hexdigest()
        change = WorkspacePatchChange(
            expected_before_block_sha256=hashlib.sha256(
                W2_BEFORE_BLOCK.encode("utf-8")
            ).hexdigest(),
        )
        patch_payload = {
            "after_sha256": after_sha256,
            "before_sha256": before_sha256,
            "change": change.canonical_payload(),
            "schema_version": 1,
            "target_path": W2_TARGET_PATH,
        }
        patch_digest = canonical_workspace_json_digest(patch_payload)
        try:
            preview = WorkspacePatchPreview(
                before_text=before_text,
                after_text=after_text,
                before_sha256=before_sha256,
                after_sha256=after_sha256,
                unified_diff=canonical_workspace_unified_diff(before_text, after_text),
                change=change,
                patch_digest=patch_digest,
            )
            target = WorkspacePatchTarget(
                artifact=target_artifact,
                before_sha256=before_sha256,
            )
            created_at = self._clock()
            values: dict[str, object] = {
                "proposal_id": self._proposal_id_factory(),
                "run_id": workspace_ref.run_id,
                "trace_id": evidence_refs[0].trace_id,
                "workspace_id": workspace_ref.workspace_id,
                "fixture_version": workspace_ref.fixture_version,
                "root_digest": workspace_ref.root_digest,
                "base_root_digest": workspace_ref.root_digest,
                "target_before_sha256": before_sha256,
                "canonical_after_sha256": after_sha256,
                "patch_digest": patch_digest,
                "evidence_digest": evidence_digest,
                "evidence_references": evidence_refs,
                "supporting_start_script_sha256": support_hashes[
                    "scripts/render_start.sh"
                ],
                "expected_runtime_contract_sha256": support_hashes[
                    "expected_runtime_contract.json"
                ],
                "risk_class": AuthorityGate.PLAN_AND_CONFIRM,
                "rollback_strategy": W2_ROLLBACK_STRATEGY,
                "verification_profile_id": W2_VERIFICATION_PROFILE_ID,
                "diagnosis_evidence_paths": (
                    "deployment.log",
                    "expected_runtime_contract.json",
                    "render.yaml",
                    "scripts/render_start.sh",
                ),
                "target": target,
                "change": change,
                "preview": preview,
                "created_at": created_at,
                "expires_at": created_at + timedelta(hours=24),
                "proposal_digest": "0" * 64,
            }
            provisional = WorkspacePatchProposal.model_construct(**values)
            values["proposal_digest"] = canonical_workspace_json_digest(
                provisional.content_payload()
            )
            proposal = WorkspacePatchProposal.model_validate(values)
        except (TypeError, ValueError, ValidationError):
            return self._failed(
                WorkspacePatchProposalOutcome.VALIDATION_FAILURE,
                FailureKind.VALIDATION_FAILURE,
                "Canonical proposal failed strict Non-Zero validation",
            )
        return ControlResult[WorkspacePatchProposal].succeeded(proposal)

    def _select_required_evidence(
        self,
        receipts: object,
    ) -> (
        dict[tuple[WorkspaceOperation, str | None], WorkspaceEvidenceReceipt]
        | WorkspacePatchProposalBuildResult
    ):
        if not isinstance(receipts, tuple) or not receipts:
            return self._failed(
                WorkspacePatchProposalOutcome.STALE_EVIDENCE,
                FailureKind.VALIDATION_FAILURE,
                "Required W1 evidence receipts are absent",
            )
        timeline_by_event = {receipt.event_id: receipt for receipt in self._service.evidence_timeline}
        current_ref = self._service.workspace_ref
        validated: list[WorkspaceEvidenceReceipt] = []
        for receipt in receipts:
            if not isinstance(receipt, WorkspaceEvidenceReceipt):
                return self._failed(
                    WorkspacePatchProposalOutcome.VALIDATION_FAILURE,
                    FailureKind.VALIDATION_FAILURE,
                    "Evidence input failed strict receipt validation",
                )
            if (
                receipt.run_id != current_ref.run_id
                or receipt.workspace_id != current_ref.workspace_id
                or receipt.fixture_version != current_ref.fixture_version
            ):
                return self._failed(
                    WorkspacePatchProposalOutcome.STALE_EVIDENCE,
                    FailureKind.POLICY_DENIAL,
                    "Evidence belongs to a different workspace",
                )
            retained = timeline_by_event.get(receipt.event_id)
            if retained is None:
                return self._failed(
                    WorkspacePatchProposalOutcome.STALE_EVIDENCE,
                    FailureKind.VALIDATION_FAILURE,
                    "Evidence receipt is not retained by the current read plane",
                )
            if retained != receipt:
                path = receipt.artifact.relative_path if receipt.artifact is not None else None
                if path == W2_TARGET_PATH:
                    outcome = WorkspacePatchProposalOutcome.TARGET_DIGEST_MISMATCH
                elif path in {
                    "scripts/render_start.sh",
                    "expected_runtime_contract.json",
                }:
                    outcome = WorkspacePatchProposalOutcome.SUPPORTING_ARTIFACT_MISMATCH
                else:
                    outcome = WorkspacePatchProposalOutcome.STALE_EVIDENCE
                return self._failed(
                    outcome,
                    FailureKind.VALIDATION_FAILURE,
                    "Evidence receipt content no longer matches retained W1 evidence",
                )
            if (
                receipt.outcome is not WorkspaceEvidenceOutcome.SUCCESS
                or receipt.policy.outcome.value != "ALLOW"
            ):
                return self._failed(
                    WorkspacePatchProposalOutcome.POLICY_DENIED,
                    FailureKind.POLICY_DENIAL,
                    "Only successful allowed W1 evidence can support a proposal",
                )
            validated.append(receipt)

        selected: dict[tuple[WorkspaceOperation, str | None], WorkspaceEvidenceReceipt] = {}
        for operation, path in _REQUIRED_EVIDENCE:
            match = next(
                (
                    receipt
                    for receipt in validated
                    if receipt.operation is operation
                    and (
                        (path is None and receipt.artifact is None)
                        or (
                            receipt.artifact is not None
                            and receipt.artifact.relative_path == path
                        )
                    )
                ),
                None,
            )
            if match is None:
                return self._failed(
                    WorkspacePatchProposalOutcome.STALE_EVIDENCE,
                    FailureKind.VALIDATION_FAILURE,
                    "Required exact W1 evidence is incomplete",
                )
            selected[(operation, path)] = match
        inspection = selected[(WorkspaceOperation.INSPECT, None)]
        if inspection.sha256 != current_ref.root_digest:
            return self._failed(
                WorkspacePatchProposalOutcome.BASE_DIGEST_MISMATCH,
                FailureKind.VALIDATION_FAILURE,
                "Incident observation does not bind the current base root digest",
            )
        return selected

    @staticmethod
    def _evidence_ref(receipt: WorkspaceEvidenceReceipt) -> WorkspaceProposalEvidenceRef:
        artifact_path = receipt.artifact.relative_path if receipt.artifact is not None else None
        artifact_sha256 = receipt.artifact.sha256 if receipt.artifact is not None else receipt.sha256
        return WorkspaceProposalEvidenceRef(
            event_id=receipt.event_id,
            run_id=receipt.run_id,
            trace_id=receipt.trace_id,
            workspace_id=receipt.workspace_id,
            fixture_version=receipt.fixture_version,
            operation=receipt.operation,
            artifact_path=artifact_path,
            artifact_sha256=artifact_sha256,
            receipt_sha256=canonical_workspace_json_digest(receipt.model_dump(mode="json")),
        )

    def _map_read_failure(self, failure: FailureDetail | None) -> WorkspacePatchProposalBuildResult:
        if failure is not None and failure.code in {
            "WORKSPACE_ROOT_DIGEST_MISMATCH",
            "WORKSPACE_ROOT_REPLACED",
            "WORKSPACE_TAMPER_DETECTED",
        }:
            return self._failed(
                WorkspacePatchProposalOutcome.BASE_DIGEST_MISMATCH,
                FailureKind.VALIDATION_FAILURE,
                "Sealed workspace base changed during proposal generation",
            )
        return self._failed(
            WorkspacePatchProposalOutcome.VALIDATION_FAILURE,
            FailureKind.VALIDATION_FAILURE,
            "Sealed artifact could not be read through the confined evidence plane",
        )

    @staticmethod
    def _failed(
        outcome: WorkspacePatchProposalOutcome,
        kind: FailureKind,
        message: str,
    ) -> WorkspacePatchProposalBuildResult:
        return ControlResult[WorkspacePatchProposal].failed(
            FailureDetail(
                kind=kind,
                code=outcome.value,
                message=message,
                retryable=False,
            )
        )


def build_workspace_patch_proposal(
    service: WorkspaceEvidenceService,
    workspace_ref: WorkspaceRef,
    remediation_kind: WorkspaceRemediationKind,
    *,
    clock: Callable[[], datetime] | None = None,
    proposal_id_factory: Callable[[], UUID] = generate_proposal_id,
    evidence_receipts: tuple[WorkspaceEvidenceReceipt, ...] | None = None,
) -> WorkspacePatchProposalBuildResult:
    """Functional facade for the same pure, non-applying W2 builder."""

    return WorkspacePatchProposalBuilder(
        service,
        clock=clock,
        proposal_id_factory=proposal_id_factory,
    ).build(
        workspace_ref,
        remediation_kind,
        evidence_receipts=evidence_receipts,
    )
