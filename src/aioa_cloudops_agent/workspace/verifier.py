"""W4 independent verifier and no-reapply crash-window reconciler."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from uuid import UUID

from aioa_cloudops_agent.nz import (
    ApprovalDecision,
    ControlResult,
    FailureDetail,
    FailureKind,
    generate_event_id,
)

from .authority_contracts import (
    PatchApplyReceipt,
    WorkspaceApprovalDecisionRecord,
    WorkspaceApprovalRequestRecord,
    WorkspaceAuthorityState,
    WorkspaceEffectOwnership,
    build_workspace_approval_payload,
    workspace_approval_request_hash,
)
from .authority_repository import (
    LocalFileWorkspaceAuthorityRepository,
    WorkspaceAuthorityConflict,
    WorkspaceAuthorityStorageError,
)
from .contracts import (
    W2_AFTER_LINE,
    W2_BEFORE_BLOCK,
    W2_TARGET_PATH,
    WorkspacePatchProposal,
    canonical_workspace_json_digest,
)
from .render_verification import (
    TrustedRenderStartProfile,
    TrustedRenderStartProfileFailure,
    TrustedRenderStartProfileResult,
)
from .verification_boundary import (
    IndependentWorkspaceObservation,
    WorkspaceVerificationBoundary,
    WorkspaceVerificationBoundaryError,
)
from .verification_contracts import (
    W4_VERIFICATION_CHECK_ORDER,
    WorkspaceRecoveryClassification,
    WorkspaceRecoveryObservation,
    WorkspaceVerificationCheck,
    WorkspaceVerificationCheckCode,
    WorkspaceVerificationCheckStatus,
    WorkspaceVerificationCompletion,
    WorkspaceVerificationDisposition,
    WorkspaceVerificationProofOrigin,
    WorkspaceVerificationReceipt,
    WorkspaceVerificationReport,
)

WorkspaceVerificationResult = ControlResult[WorkspaceVerificationCompletion]

_DEPENDENCY_PROFILE_FAILURES = frozenset(
    {
        "RUNTIME_PROBE_CHILD_FAILED",
        "RUNTIME_PROBE_TIMEOUT",
        "RUNTIME_PROBE_UNAVAILABLE",
    }
)


class _VerificationDenied(ValueError):
    def __init__(self, kind: FailureKind, code: str, message: str) -> None:
        self.kind = kind
        self.code = code
        self.message = message
        super().__init__(message)


class WorkspaceIndependentVerifier:
    """Verify proposal-id-only durable effects without trusting executor claims."""

    def __init__(
        self,
        boundary: WorkspaceVerificationBoundary,
        repository: LocalFileWorkspaceAuthorityRepository,
        profile: TrustedRenderStartProfile,
        *,
        clock: Callable[[], datetime] | None = None,
        evidence_id_factory: Callable[[], UUID] = generate_event_id,
    ) -> None:
        if not isinstance(boundary, WorkspaceVerificationBoundary):
            raise TypeError("boundary must be WorkspaceVerificationBoundary")
        if not isinstance(repository, LocalFileWorkspaceAuthorityRepository):
            raise TypeError("repository must be LocalFileWorkspaceAuthorityRepository")
        if not callable(getattr(profile, "run", None)):
            raise TypeError("profile must expose the fixed no-argument run boundary")
        if clock is not None and not callable(clock):
            raise TypeError("clock must be callable")
        if not callable(evidence_id_factory):
            raise TypeError("evidence_id_factory must be callable")
        self._boundary = boundary
        self._repository = repository
        self._profile = profile
        self._clock = clock or (lambda: datetime.now(UTC))
        self._evidence_id_factory = evidence_id_factory

    @property
    def repository(self) -> LocalFileWorkspaceAuthorityRepository:
        return self._repository

    @property
    def boundary(self) -> WorkspaceVerificationBoundary:
        return self._boundary

    def verify(self, proposal_id: UUID) -> WorkspaceVerificationResult:
        """Reopen, verify, persist proof, then and only then close success."""

        try:
            record = self._repository.get_proposal_record(proposal_id)
            if record is None:
                raise _VerificationDenied(
                    FailureKind.VALIDATION_FAILURE,
                    "WORKSPACE_VERIFICATION_PROPOSAL_NOT_FOUND",
                    "Durable workspace proposal is required for verification.",
                )
            proposal = WorkspacePatchProposal.model_validate(
                record.proposal.model_dump(mode="python")
            )
            request, _decision, ownership = self._validated_authority(proposal_id, proposal)
            existing_report = self._repository.get_verification_report(proposal_id)
            existing_receipt = self._repository.get_verification_receipt(proposal_id)
            observation = self._boundary.reopen(proposal)

            if existing_report is not None or existing_receipt is not None:
                return self._reconcile_existing(
                    record.state,
                    proposal,
                    ownership,
                    observation,
                    existing_report,
                    existing_receipt,
                )

            apply_receipt = self._validated_apply_receipt(
                proposal_id,
                proposal,
                request,
                ownership,
            )
            recovery = self._prepare_effect_truth(
                record.state,
                proposal,
                ownership,
                apply_receipt,
                observation,
            )
            self._repository.begin_verification(proposal_id)
            apply_receipt_digest = (
                None
                if apply_receipt is None
                else canonical_workspace_json_digest(
                    apply_receipt.model_dump(mode="json")
                )
            )
            recovery_digest = None if recovery is None else recovery.observation_digest
            static_checks = self._static_checks(proposal, observation)
            static_passed = all(
                check.status is WorkspaceVerificationCheckStatus.PASS
                for check in static_checks
            )
            profile_result: TrustedRenderStartProfileResult | None = None
            profile_failure: TrustedRenderStartProfileFailure | None = None
            if static_passed:
                try:
                    profile_value = self._profile.run()
                    profile_result = TrustedRenderStartProfileResult.model_validate(
                        profile_value.model_dump(mode="python")
                    )
                except TrustedRenderStartProfileFailure as error:
                    profile_failure = error
                except (AttributeError, OSError, RuntimeError, TypeError, ValueError) as error:
                    profile_failure = TrustedRenderStartProfileFailure(
                        "RUNTIME_PROBE_UNAVAILABLE"
                    )
                    profile_failure.__cause__ = error
            runtime_checks = self._runtime_checks(
                static_passed,
                profile_result,
                profile_failure,
            )
            checks = (*static_checks, *runtime_checks)
            if tuple(check.code for check in checks) != W4_VERIFICATION_CHECK_ORDER:
                raise RuntimeError("internal W4 verification check order is invalid")
            disposition = self._disposition(checks, observation, profile_failure)
            report = WorkspaceVerificationReport.create(
                proposal_id=proposal.proposal_id,
                run_id=proposal.run_id,
                trace_id=proposal.trace_id,
                workspace_id=proposal.workspace_id,
                fixture_version=proposal.fixture_version,
                effect_id=ownership.effect_id,
                patch_digest=proposal.patch_digest,
                base_root_digest=proposal.base_root_digest,
                expected_after_sha256=proposal.canonical_after_sha256,
                actual_after_sha256=observation.target_sha256,
                expected_changed_paths=(W2_TARGET_PATH,),
                actual_changed_paths=observation.actual_changed_paths,
                supporting_start_script_sha256=proposal.supporting_start_script_sha256,
                actual_start_script_sha256=observation.start_script_sha256,
                expected_runtime_contract_sha256=(
                    proposal.expected_runtime_contract_sha256
                ),
                actual_runtime_contract_sha256=observation.runtime_contract_sha256,
                verification_profile_id=proposal.verification_profile_id,
                apply_receipt_digest=apply_receipt_digest,
                recovery_observation_digest=recovery_digest,
                observed_root_digest=observation.observed_root_digest,
                checks=checks,
                verified_at=self._clock(),
                disposition=disposition,
            )
            report = self._repository.save_verification_report(report)
            if report.disposition is not WorkspaceVerificationDisposition.VERIFIED:
                return self._report_failure(report)
            receipt = self._receipt_from_report(report)
            receipt = self._repository.save_verification_receipt(receipt)
            current = self._repository.get_proposal_record(proposal_id)
            if current is None or current.state is not WorkspaceAuthorityState.SUCCESS_WITH_EVIDENCE:
                raise WorkspaceAuthorityStorageError("verified terminal state is unavailable")
            return WorkspaceVerificationResult.succeeded(
                WorkspaceVerificationCompletion(
                    report=report,
                    receipt=receipt,
                    reconciled=False,
                    verifier_fixed_process_probes=(
                        0 if profile_result is None else profile_result.process_executions
                    ),
                )
            )
        except _VerificationDenied as error:
            return self._failed(error.kind, error.code, error.message)
        except WorkspaceVerificationBoundaryError:
            return self._failed(
                FailureKind.DEPENDENCY_UNAVAILABLE,
                "WORKSPACE_VERIFICATION_BOUNDARY_UNAVAILABLE",
                "Independent workspace read-back is unavailable.",
                retryable=True,
            )
        except WorkspaceAuthorityConflict:
            return self._failed(
                FailureKind.IDEMPOTENCY_CONFLICT,
                "WORKSPACE_VERIFICATION_CONFLICT",
                "Durable verification truth conflicts with this request.",
            )
        except WorkspaceAuthorityStorageError:
            return self._failed(
                FailureKind.DEPENDENCY_UNAVAILABLE,
                "WORKSPACE_VERIFICATION_DURABILITY_UNAVAILABLE",
                "Durable workspace verification truth is unavailable.",
                retryable=True,
            )
        except (TypeError, ValueError):
            return self._failed(
                FailureKind.VALIDATION_FAILURE,
                "WORKSPACE_VERIFICATION_EVIDENCE_INVALID",
                "Workspace verification evidence failed strict validation.",
            )

    def _validated_authority(
        self,
        proposal_id: UUID,
        proposal: WorkspacePatchProposal,
    ) -> tuple[
        WorkspaceApprovalRequestRecord,
        WorkspaceApprovalDecisionRecord,
        WorkspaceEffectOwnership,
    ]:
        request_value = self._repository.get_request(proposal_id)
        decision_value = self._repository.get_decision(proposal_id)
        ownership_value = self._repository.get_ownership(proposal_id)
        if request_value is None or decision_value is None or ownership_value is None:
            raise _VerificationDenied(
                FailureKind.POLICY_DENIAL,
                "WORKSPACE_VERIFICATION_AUTHORITY_MISSING",
                "Exact durable proposal approval and effect ownership are required.",
            )
        request = WorkspaceApprovalRequestRecord.model_validate(
            request_value.model_dump(mode="python")
        )
        decision = WorkspaceApprovalDecisionRecord.model_validate(
            decision_value.model_dump(mode="python")
        )
        ownership = WorkspaceEffectOwnership.model_validate(
            ownership_value.model_dump(mode="python")
        )
        payload = build_workspace_approval_payload(proposal)
        expected_request_hash = workspace_approval_request_hash(payload)
        if (
            request.payload != payload
            or request.request_hash != expected_request_hash
            or decision.decision is not ApprovalDecision.APPROVED
            or decision.proposal_id != proposal.proposal_id
            or decision.run_id != proposal.run_id
            or decision.trace_id != proposal.trace_id
            or decision.workspace_id != proposal.workspace_id
            or decision.request_hash != expected_request_hash
            or decision.proposal_digest != proposal.proposal_digest
            or decision.patch_digest != proposal.patch_digest
            or decision.evidence_digest != proposal.evidence_digest
            or decision.base_root_digest != proposal.base_root_digest
            or ownership.proposal_id != proposal.proposal_id
            or ownership.run_id != proposal.run_id
            or ownership.trace_id != proposal.trace_id
            or ownership.workspace_id != proposal.workspace_id
            or ownership.after_sha256 != proposal.canonical_after_sha256
            or ownership.before_sha256 != proposal.target_before_sha256
            or ownership.patch_digest != proposal.patch_digest
            or ownership.approval_request_hash != expected_request_hash
            or ownership.decision_hash != decision.decision_hash
        ):
            raise _VerificationDenied(
                FailureKind.POLICY_DENIAL,
                "WORKSPACE_VERIFICATION_AUTHORITY_MISMATCH",
                "Durable approval does not bind the exact workspace effect.",
            )
        return request, decision, ownership

    def _validated_apply_receipt(
        self,
        proposal_id: UUID,
        proposal: WorkspacePatchProposal,
        request: WorkspaceApprovalRequestRecord,
        ownership: WorkspaceEffectOwnership,
    ) -> PatchApplyReceipt | None:
        value = self._repository.get_receipt(proposal_id)
        if value is None:
            return None
        receipt = PatchApplyReceipt.model_validate(value.model_dump(mode="python"))
        if (
            receipt.effect_id != ownership.effect_id
            or receipt.idempotency_key != ownership.idempotency_key
            or receipt.proposal_id != proposal.proposal_id
            or receipt.run_id != proposal.run_id
            or receipt.trace_id != proposal.trace_id
            or receipt.workspace_id != proposal.workspace_id
            or receipt.fixture_version != proposal.fixture_version
            or receipt.target_path != proposal.target_path
            or receipt.before_sha256 != proposal.target_before_sha256
            or receipt.after_sha256 != proposal.canonical_after_sha256
            or receipt.patch_digest != proposal.patch_digest
            or receipt.approval_request_hash != request.request_hash
        ):
            raise _VerificationDenied(
                FailureKind.RECOVERY_REQUIREMENT,
                "WORKSPACE_APPLY_RECEIPT_BINDING_MISMATCH",
                "Executor receipt is inconsistent and cannot establish effect truth.",
            )
        return receipt

    def _prepare_effect_truth(
        self,
        state: WorkspaceAuthorityState,
        proposal: WorkspacePatchProposal,
        ownership: WorkspaceEffectOwnership,
        receipt: PatchApplyReceipt | None,
        observed: IndependentWorkspaceObservation,
    ) -> WorkspaceRecoveryObservation | None:
        if state is WorkspaceAuthorityState.DENIED_BY_HUMAN:
            raise _VerificationDenied(
                FailureKind.POLICY_DENIAL,
                "WORKSPACE_DENIED_PROPOSAL_NOT_VERIFIABLE",
                "A denied workspace proposal cannot enter verification.",
            )
        if state in {
            WorkspaceAuthorityState.PATCH_PROPOSED,
            WorkspaceAuthorityState.AWAITING_APPROVAL,
            WorkspaceAuthorityState.APPROVED,
        }:
            raise _VerificationDenied(
                FailureKind.POLICY_DENIAL,
                "WORKSPACE_UNAPPLIED_PROPOSAL_NOT_VERIFIABLE",
                "An approved exact effect is required before verification.",
            )
        if state in {
            WorkspaceAuthorityState.VERIFICATION_FAILED,
            WorkspaceAuthorityState.DEPENDENCY_UNAVAILABLE,
        }:
            raise _VerificationDenied(
                FailureKind.RECOVERY_REQUIREMENT,
                "WORKSPACE_VERIFICATION_TERMINAL_REVIEW_REQUIRED",
                "Prior terminal verification evidence requires explicit review.",
            )
        if state is WorkspaceAuthorityState.PATCH_APPLIED_UNVERIFIED:
            if receipt is None:
                raise _VerificationDenied(
                    FailureKind.RECOVERY_REQUIREMENT,
                    "WORKSPACE_APPLY_RECEIPT_MISSING",
                    "Applied-unverified state lacks its exact effect receipt.",
                )
            return None
        if state is WorkspaceAuthorityState.VERIFYING:
            if receipt is not None:
                return None
            recovery = self._repository.get_recovery_observation(proposal.proposal_id)
            if recovery is not None:
                return WorkspaceRecoveryObservation.model_validate(
                    recovery.model_dump(mode="python")
                )
            raise _VerificationDenied(
                FailureKind.RECOVERY_REQUIREMENT,
                "WORKSPACE_VERIFYING_PROOF_MISSING",
                "Verifying state lacks its durable effect proof.",
            )
        if state not in {
            WorkspaceAuthorityState.APPLYING,
            WorkspaceAuthorityState.RECONCILIATION_REQUIRED,
        }:
            raise _VerificationDenied(
                FailureKind.RECOVERY_REQUIREMENT,
                "WORKSPACE_VERIFICATION_STATE_INVALID",
                "Workspace state cannot safely enter verification.",
            )

        exact_before = (
            observed.provenance_proven
            and observed.integrity_proven
            and observed.target_sha256 == proposal.target_before_sha256
            and not observed.actual_changed_paths
        )
        exact_after = (
            observed.provenance_proven
            and observed.integrity_proven
            and observed.target_sha256 == proposal.canonical_after_sha256
            and observed.actual_changed_paths == (W2_TARGET_PATH,)
        )
        marker = self._repository.get_reconciliation(proposal.proposal_id)
        if exact_before and state is WorkspaceAuthorityState.APPLYING:
            recovery = self._recovery_observation(
                proposal,
                ownership,
                observed,
                WorkspaceRecoveryClassification.SAFE_RESUMABLE_FOR_W3_APPLY,
            )
            self._save_or_reconcile_recovery(recovery)
            raise _VerificationDenied(
                FailureKind.RECOVERY_REQUIREMENT,
                "WORKSPACE_SAFE_RESUMABLE_FOR_W3_APPLY",
                "Exact before state is safe for W3 apply; W4 performed no mutation.",
            )
        marker_allows_recovery = marker is None or (
            marker.reason_code == "TARGET_ALREADY_AFTER_WITHOUT_RECEIPT"
            and marker.effect_id == ownership.effect_id
            and marker.observed_sha256 == proposal.canonical_after_sha256
        )
        if exact_after and marker_allows_recovery:
            recovery = self._recovery_observation(
                proposal,
                ownership,
                observed,
                WorkspaceRecoveryClassification.RECOVERY_READ_BACK,
            )
            return self._save_or_reconcile_recovery(recovery)

        recovery = self._recovery_observation(
            proposal,
            ownership,
            observed,
            WorkspaceRecoveryClassification.AMBIGUOUS_STATE,
        )
        self._save_or_reconcile_recovery(recovery)
        raise _VerificationDenied(
            FailureKind.RECOVERY_REQUIREMENT,
            "WORKSPACE_EFFECT_STATE_AMBIGUOUS",
            "Fresh read-back cannot prove exact before or approved after state.",
        )

    def _recovery_observation(
        self,
        proposal: WorkspacePatchProposal,
        ownership: WorkspaceEffectOwnership,
        observed: IndependentWorkspaceObservation,
        classification: WorkspaceRecoveryClassification,
    ) -> WorkspaceRecoveryObservation:
        return WorkspaceRecoveryObservation.create(
            observation_id=self._evidence_id_factory(),
            proposal_id=proposal.proposal_id,
            run_id=proposal.run_id,
            trace_id=proposal.trace_id,
            workspace_id=proposal.workspace_id,
            fixture_version=proposal.fixture_version,
            effect_id=ownership.effect_id,
            base_root_digest=proposal.base_root_digest,
            expected_before_sha256=proposal.target_before_sha256,
            expected_after_sha256=proposal.canonical_after_sha256,
            actual_target_sha256=observed.target_sha256,
            expected_changed_paths=(W2_TARGET_PATH,),
            actual_changed_paths=observed.actual_changed_paths,
            observed_root_digest=observed.observed_root_digest,
            integrity_proven=observed.provenance_proven and observed.integrity_proven,
            classification=classification,
            observed_at=self._clock(),
        )

    def _save_or_reconcile_recovery(
        self,
        candidate: WorkspaceRecoveryObservation,
    ) -> WorkspaceRecoveryObservation:
        existing = self._repository.get_recovery_observation(candidate.proposal_id)
        if existing is None:
            return self._repository.save_recovery_observation(candidate)
        existing = WorkspaceRecoveryObservation.model_validate(
            existing.model_dump(mode="python")
        )
        if (
            existing.classification != candidate.classification
            or existing.effect_id != candidate.effect_id
            or existing.actual_target_sha256 != candidate.actual_target_sha256
            or existing.actual_changed_paths != candidate.actual_changed_paths
            or existing.observed_root_digest != candidate.observed_root_digest
            or existing.integrity_proven != candidate.integrity_proven
        ):
            raise WorkspaceAuthorityConflict(
                "fresh recovery read-back conflicts with durable observation"
            )
        return existing

    @staticmethod
    def _static_checks(
        proposal: WorkspacePatchProposal,
        observed: IndependentWorkspaceObservation,
    ) -> tuple[WorkspaceVerificationCheck, ...]:
        render_text = observed.render_text or ""
        fixed_count = render_text.count(W2_AFTER_LINE)
        old_inline_absent = W2_BEFORE_BLOCK not in render_text and "dockerCommand: >-" not in (
            render_text
        )
        return (
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.PROPOSAL_BINDING,
                True,
                "exact-durable-proposal",
                "exact-durable-proposal",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.APPROVAL_BINDING,
                True,
                "exact-human-approval",
                "exact-human-approval",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.WORKSPACE_PROVENANCE,
                observed.provenance_proven
                and observed.base_root_digest == proposal.base_root_digest,
                proposal.base_root_digest,
                observed.base_root_digest if observed.provenance_proven else "unproven",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.EXACT_CHANGED_PATH_SET,
                observed.integrity_proven
                and observed.actual_changed_paths == (W2_TARGET_PATH,),
                W2_TARGET_PATH,
                ",".join(observed.actual_changed_paths) or "none",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.TARGET_AFTER_HASH,
                observed.target_sha256 == proposal.canonical_after_sha256,
                proposal.canonical_after_sha256,
                observed.target_sha256 or "unavailable",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.INLINE_DOCKER_COMMAND_ABSENT,
                old_inline_absent and bool(render_text),
                "absent",
                "absent" if old_inline_absent and render_text else "present-or-unproven",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.FIXED_EXECUTABLE_PRESENT_ONCE,
                fixed_count == 1,
                "exactly-once",
                f"count={fixed_count}",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.START_SCRIPT_HASH,
                observed.start_script_sha256
                == proposal.supporting_start_script_sha256,
                proposal.supporting_start_script_sha256,
                observed.start_script_sha256 or "unavailable",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.RUNTIME_CONTRACT_HASH,
                observed.runtime_contract_sha256
                == proposal.expected_runtime_contract_sha256,
                proposal.expected_runtime_contract_sha256,
                observed.runtime_contract_sha256 or "unavailable",
            ),
            WorkspaceIndependentVerifier._check(
                WorkspaceVerificationCheckCode.RENDER_CONFIG_EXACT_AFTER,
                observed.target_sha256 == proposal.canonical_after_sha256
                and render_text == proposal.preview.after_text,
                proposal.canonical_after_sha256,
                observed.target_sha256 or "unavailable",
            ),
        )

    @staticmethod
    def _runtime_checks(
        static_passed: bool,
        result: TrustedRenderStartProfileResult | None,
        failure: TrustedRenderStartProfileFailure | None,
    ) -> tuple[WorkspaceVerificationCheck, ...]:
        codes = W4_VERIFICATION_CHECK_ORDER[10:]
        if not static_passed:
            return tuple(
                WorkspaceIndependentVerifier._status_check(
                    code,
                    WorkspaceVerificationCheckStatus.NOT_RUN,
                    WorkspaceIndependentVerifier._runtime_expected(code),
                    "blocked-by-static-proof",
                )
                for code in codes
            )
        if failure is not None:
            status = (
                WorkspaceVerificationCheckStatus.UNAVAILABLE
                if failure.code in _DEPENDENCY_PROFILE_FAILURES
                else WorkspaceVerificationCheckStatus.FAIL
            )
            return tuple(
                WorkspaceIndependentVerifier._status_check(
                    code,
                    status,
                    WorkspaceIndependentVerifier._runtime_expected(code),
                    f"profile-error:{failure.code}",
                )
                for code in codes
            )
        if result is None:
            raise RuntimeError("fixed profile produced neither proof nor failure")
        values = (
            result.missing_token_fails_closed,
            result.token_mode_0600,
            result.bootstrap_secret_absent,
            result.child_argv_exact,
            result.health_passed,
            result.readiness_passed,
            result.external_egress_count == 0,
            result.aws_call_count == 0,
            result.workspace_code_executions == 0,
        )
        return tuple(
            WorkspaceIndependentVerifier._check(
                code,
                passed,
                WorkspaceIndependentVerifier._runtime_expected(code),
                WorkspaceIndependentVerifier._runtime_expected(code)
                if passed
                else "mismatch",
            )
            for code, passed in zip(codes, values, strict=True)
        )

    @staticmethod
    def _runtime_expected(code: WorkspaceVerificationCheckCode) -> str:
        return {
            WorkspaceVerificationCheckCode.MISSING_TOKEN_FAILS_CLOSED: "fail-closed",
            WorkspaceVerificationCheckCode.TOKEN_FILE_MODE_0600: "mode=0600",
            WorkspaceVerificationCheckCode.BOOTSTRAP_SECRET_ABSENT: "absent",
            WorkspaceVerificationCheckCode.CHILD_ARGV_EXACT: (
                "python -m aioa_cloudops_agent.portable_server"
            ),
            WorkspaceVerificationCheckCode.HEALTH_CHECK: "healthy",
            WorkspaceVerificationCheckCode.READINESS_CHECK: "ready",
            WorkspaceVerificationCheckCode.ZERO_EXTERNAL_EGRESS: "count=0",
            WorkspaceVerificationCheckCode.ZERO_AWS_CALLS: "count=0",
            WorkspaceVerificationCheckCode.NO_WORKSPACE_CODE_EXECUTION: "count=0",
        }[code]

    @staticmethod
    def _disposition(
        checks: tuple[WorkspaceVerificationCheck, ...],
        observed: IndependentWorkspaceObservation,
        profile_failure: TrustedRenderStartProfileFailure | None,
    ) -> WorkspaceVerificationDisposition:
        statuses = {check.status for check in checks}
        if statuses == {WorkspaceVerificationCheckStatus.PASS}:
            return WorkspaceVerificationDisposition.VERIFIED
        if WorkspaceVerificationCheckStatus.UNAVAILABLE in statuses:
            return WorkspaceVerificationDisposition.DEPENDENCY_UNAVAILABLE
        if not observed.provenance_proven:
            return WorkspaceVerificationDisposition.RECONCILIATION_REQUIRED
        if profile_failure is not None or WorkspaceVerificationCheckStatus.FAIL in statuses:
            return WorkspaceVerificationDisposition.MISMATCH
        return WorkspaceVerificationDisposition.RECONCILIATION_REQUIRED

    def _receipt_from_report(
        self,
        report: WorkspaceVerificationReport,
    ) -> WorkspaceVerificationReceipt:
        origin = (
            WorkspaceVerificationProofOrigin.APPLY_RECEIPT
            if report.apply_receipt_digest is not None
            else WorkspaceVerificationProofOrigin.RECOVERY_READ_BACK
        )
        if report.actual_after_sha256 is None:
            raise ValueError("verified report lacks observed after hash")
        return WorkspaceVerificationReceipt.create(
            verification_id=self._evidence_id_factory(),
            proposal_id=report.proposal_id,
            run_id=report.run_id,
            trace_id=report.trace_id,
            workspace_id=report.workspace_id,
            effect_id=report.effect_id,
            report_digest=report.report_digest,
            observed_after_sha256=report.actual_after_sha256,
            verification_profile_id=report.verification_profile_id,
            proof_origin=origin,
            apply_receipt_digest=report.apply_receipt_digest,
            recovery_observation_digest=report.recovery_observation_digest,
            verified_at=report.verified_at,
        )

    def _reconcile_existing(
        self,
        state: WorkspaceAuthorityState,
        proposal: WorkspacePatchProposal,
        ownership: WorkspaceEffectOwnership,
        observed: IndependentWorkspaceObservation,
        report_value: WorkspaceVerificationReport | None,
        receipt_value: WorkspaceVerificationReceipt | None,
    ) -> WorkspaceVerificationResult:
        if report_value is None:
            raise _VerificationDenied(
                FailureKind.RECOVERY_REQUIREMENT,
                "WORKSPACE_SUCCESS_REPORT_MISSING",
                "Verification receipt cannot be trusted without its durable report.",
            )
        report = WorkspaceVerificationReport.model_validate(
            report_value.model_dump(mode="python")
        )
        if (
            report.proposal_id != proposal.proposal_id
            or report.effect_id != ownership.effect_id
            or report.patch_digest != proposal.patch_digest
            or report.actual_after_sha256 != observed.target_sha256
            or report.actual_changed_paths != observed.actual_changed_paths
            or report.actual_start_script_sha256 != observed.start_script_sha256
            or report.actual_runtime_contract_sha256
            != observed.runtime_contract_sha256
            or not observed.provenance_proven
            or not observed.integrity_proven
        ):
            raise _VerificationDenied(
                FailureKind.RECOVERY_REQUIREMENT,
                "WORKSPACE_VERIFIED_STATE_DRIFTED",
                "Current workspace state no longer matches durable verification evidence.",
            )
        if report.disposition is not WorkspaceVerificationDisposition.VERIFIED:
            return self._report_failure(report)
        if receipt_value is None:
            if state is not WorkspaceAuthorityState.VERIFYING:
                raise _VerificationDenied(
                    FailureKind.RECOVERY_REQUIREMENT,
                    "WORKSPACE_VERIFICATION_RECEIPT_MISSING",
                    "Verified report exists outside its recoverable VERIFYING state.",
                )
            receipt = self._repository.save_verification_receipt(
                self._receipt_from_report(report)
            )
        else:
            receipt = WorkspaceVerificationReceipt.model_validate(
                receipt_value.model_dump(mode="python")
            )
            if (
                state is not WorkspaceAuthorityState.SUCCESS_WITH_EVIDENCE
                or receipt.report_digest != report.report_digest
                or receipt.effect_id != ownership.effect_id
            ):
                raise _VerificationDenied(
                    FailureKind.RECOVERY_REQUIREMENT,
                    "WORKSPACE_VERIFICATION_RECEIPT_MISMATCH",
                    "Terminal receipt does not match durable independent proof.",
                )
        return WorkspaceVerificationResult.succeeded(
            WorkspaceVerificationCompletion(
                report=report,
                receipt=receipt,
                reconciled=True,
                verifier_fixed_process_probes=0,
            )
        )

    @staticmethod
    def _check(
        code: WorkspaceVerificationCheckCode,
        passed: bool,
        expected: str,
        observed: str,
    ) -> WorkspaceVerificationCheck:
        return WorkspaceVerificationCheck(
            code=code,
            status=(
                WorkspaceVerificationCheckStatus.PASS
                if passed
                else WorkspaceVerificationCheckStatus.FAIL
            ),
            expected=expected,
            observed=observed,
        )

    @staticmethod
    def _status_check(
        code: WorkspaceVerificationCheckCode,
        status: WorkspaceVerificationCheckStatus,
        expected: str,
        observed: str,
    ) -> WorkspaceVerificationCheck:
        return WorkspaceVerificationCheck(
            code=code,
            status=status,
            expected=expected,
            observed=observed,
        )

    @staticmethod
    def _report_failure(report: WorkspaceVerificationReport) -> WorkspaceVerificationResult:
        if report.disposition is WorkspaceVerificationDisposition.DEPENDENCY_UNAVAILABLE:
            return WorkspaceIndependentVerifier._failed(
                FailureKind.DEPENDENCY_UNAVAILABLE,
                "WORKSPACE_TRUSTED_VERIFIER_UNAVAILABLE",
                "The fixed trusted verification profile is unavailable.",
                retryable=True,
            )
        if report.disposition is WorkspaceVerificationDisposition.RECONCILIATION_REQUIRED:
            return WorkspaceIndependentVerifier._failed(
                FailureKind.RECOVERY_REQUIREMENT,
                "WORKSPACE_VERIFICATION_RECONCILIATION_REQUIRED",
                "Independent workspace truth requires reconciliation.",
            )
        return WorkspaceIndependentVerifier._failed(
            FailureKind.VERIFICATION_FAILURE,
            "WORKSPACE_VERIFICATION_MISMATCH",
            "Independent workspace verification found a definite mismatch.",
        )

    @staticmethod
    def _failed(
        kind: FailureKind,
        code: str,
        message: str,
        *,
        retryable: bool = False,
    ) -> WorkspaceVerificationResult:
        return WorkspaceVerificationResult.failed(
            FailureDetail(
                kind=kind,
                code=code,
                message=message,
                retryable=retryable,
            )
        )
