"""Finite, fail-closed test-repair-review orchestration."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol
from uuid import UUID

from aioa_cloudops_agent.agent import WorkerResult, WorkerTerminalStatus
from aioa_cloudops_agent.nz import generate_event_id
from aioa_cloudops_agent.patchset import (
    BoundedPatchSetPolicy,
    PatchOperation,
    PatchSet,
    PatchSetContext,
    PatchSetPolicyDenied,
)
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

from .contracts import (
    RepairAttemptReceipt,
    RepairLoopRequest,
    RepairLoopResult,
    RepairLoopResultStatus,
    RepairLoopState,
    ValidationOutcome,
    ValidationStage,
    ValidationStepReceipt,
)

_ZERO_DIGEST = "0" * 64


@dataclass(frozen=True, slots=True)
class CandidateWorkspace:
    """Server-internal candidate root; the host path is never serialized."""

    root: Path
    worker_run_id: UUID
    worker_result: WorkerResult


class RepairCandidateProducer(Protocol):
    """Produce actual candidate state; narration is deliberately absent."""

    def produce(self, attempt_number: int, feedback_code: str | None) -> CandidateWorkspace: ...


class ValidationSession(Protocol):
    """One owned validation sandbox spanning V1/V2 and final V6."""

    def validate_fast_and_targeted(self) -> tuple[ValidationStepReceipt, ...]: ...

    def validate_final(self) -> ValidationStepReceipt: ...

    def close(self) -> int: ...


class ValidationBackend(Protocol):
    def open(self, candidate_root: Path, patchset: PatchSet) -> ValidationSession: ...


class DeterministicSemanticReviewer:
    """Reject common test weakening and fixture-specific bypasses from canonical diff."""

    _ADDED_DENY = re.compile(
        r"(?:pytest\.mark\.(?:skip|xfail)|pytest\.skip\(|unittest\.skip|"
        r"#\s*noqa|type:\s*ignore|disable[_-]?(?:test|lint|check)|"
        r"(?:monkeypatch|mock)\.|(?:allow|enable).*(?:network|credential))",
        flags=re.IGNORECASE,
    )
    _HARDCODED_RETURN = re.compile(
        r"^\+\s*return\s+(?:[-+]?\d+(?:\.\d+)?|True|False|None|[\"'])\s*$"
    )

    def review(self, patchset: PatchSet) -> ValidationStepReceipt:
        if not isinstance(patchset, PatchSet):
            raise TypeError("semantic review requires a canonical PatchSet")
        reason: str | None = None
        for change in patchset.files:
            test_path = change.path.startswith("tests/") or Path(change.path).name.startswith(
                "test_"
            )
            if test_path and change.operation is PatchOperation.DELETE:
                reason = "REVIEW_TEST_DELETION_DENIED"
                break
        lines = patchset.canonical_diff.splitlines()
        if reason is None:
            for line in lines:
                if line.startswith("+") and not line.startswith("+++"):
                    if self._ADDED_DENY.search(line):
                        reason = "REVIEW_BYPASS_PATTERN_DENIED"
                        break
                    if self._HARDCODED_RETURN.fullmatch(line):
                        reason = "REVIEW_FIXTURE_HARDCODE_DENIED"
                        break
        if reason is None:
            for line in lines:
                if line.startswith("-") and not line.startswith("---"):
                    lowered = line.casefold()
                    if "assert" in lowered or "raise" in lowered:
                        reason = "REVIEW_ASSERTION_WEAKENING_DENIED"
                        break
        material = {
            "patchset_sha256": patchset.patchset_sha256,
            "review_policy": "W7A_SEMANTIC_REVIEW_V1",
            "result": "PASS" if reason is None else "POLICY_DENIED",
        }
        return ValidationStepReceipt(
            stage=ValidationStage.V4_SEMANTIC_REVIEW,
            outcome=(ValidationOutcome.PASS if reason is None else ValidationOutcome.POLICY_DENIED),
            evidence_sha256=canonical_workspace_json_digest(material),
            failure_code=reason,
        )


class BoundedRepairLoopCoordinator:
    """Run at most one initial attempt and two repairs with fresh identities."""

    def __init__(
        self,
        *,
        patchset_policy: BoundedPatchSetPolicy | None = None,
        reviewer: DeterministicSemanticReviewer | None = None,
        id_factory=generate_event_id,
        clock=lambda: datetime.now(UTC),
    ) -> None:
        self._policy = patchset_policy or BoundedPatchSetPolicy()
        self._reviewer = reviewer or DeterministicSemanticReviewer()
        self._id_factory = id_factory
        self._clock = clock

    def run(
        self,
        *,
        request: RepairLoopRequest,
        base_root: Path,
        producer: RepairCandidateProducer,
        validator: ValidationBackend,
    ) -> RepairLoopResult:
        if not isinstance(request, RepairLoopRequest):
            raise TypeError("repair loop requires RepairLoopRequest")
        history = [RepairLoopState.PROPOSED_PATCH]
        attempts: list[RepairAttemptReceipt] = []
        previous_hashes: set[str] = set()
        feedback: str | None = None

        for attempt_number in range(request.max_repair_attempts + 1):
            if attempt_number:
                history.append(
                    RepairLoopState.REPAIRING_1
                    if attempt_number == 1
                    else RepairLoopState.REPAIRING_2
                )
            candidate = producer.produce(attempt_number, feedback)
            worker_digest = _worker_result_digest(candidate.worker_result)
            worker_failure = self._validate_worker(request, candidate)
            if worker_failure is not None:
                attempts.append(
                    _attempt(
                        attempt_number,
                        candidate,
                        worker_digest,
                        outcome=ValidationOutcome.FAIL,
                        failure_code=worker_failure,
                    )
                )
                history.append(RepairLoopState.WORKER_FAILED)
                return _result(request, history, attempts, failure_code=worker_failure)

            context = PatchSetContext(
                patchset_id=self._id_factory(),
                task_id=request.task_id,
                operation_correlation_id=request.operation_correlation_id,
                run_id=request.run_id,
                trace_id=request.trace_id,
                worker_run_id=candidate.worker_run_id,
                workspace_id=request.workspace_id,
                observed_at=self._clock(),
            )
            try:
                patchset = self._policy.evaluate(
                    base_root=base_root,
                    final_root=candidate.root,
                    base_head=request.base_head,
                    context=context,
                )
                self._policy.recheck(
                    base_root=base_root,
                    final_root=candidate.root,
                    patchset=patchset,
                    checked_at=self._clock(),
                )
            except PatchSetPolicyDenied as error:
                attempts.append(
                    _attempt(
                        attempt_number,
                        candidate,
                        worker_digest,
                        outcome=ValidationOutcome.POLICY_DENIED,
                        failure_code=error.code,
                    )
                )
                history.append(RepairLoopState.POLICY_DENIED)
                return _result(request, history, attempts, failure_code=error.code)

            if patchset.patchset_sha256 in previous_hashes:
                code = "REPAIR_PATCHSET_NOT_NEW"
                attempts.append(
                    _attempt(
                        attempt_number,
                        candidate,
                        worker_digest,
                        patchset=patchset,
                        outcome=ValidationOutcome.POLICY_DENIED,
                        failure_code=code,
                    )
                )
                history.append(RepairLoopState.POLICY_DENIED)
                return _result(
                    request,
                    history,
                    attempts,
                    failure_code=code,
                    each_new=False,
                )
            previous_hashes.add(patchset.patchset_sha256)
            v0 = _policy_step(patchset)
            history.append(RepairLoopState.VALIDATING)
            session: ValidationSession | None = None
            cleanup_orphans = 0
            steps: list[ValidationStepReceipt] = [v0]
            try:
                session = validator.open(candidate.root, patchset)
                first_steps = session.validate_fast_and_targeted()
                _validate_step_sequence(first_steps, final=False)
                steps.extend(first_steps)
                failure = next(
                    (step for step in first_steps if step.outcome is not ValidationOutcome.PASS),
                    None,
                )
                if failure is not None:
                    feedback = failure.failure_code or "VALIDATION_FAILED"
                    cleanup_orphans = session.close()
                    session = None
                    attempts.append(
                        _attempt(
                            attempt_number,
                            candidate,
                            worker_digest,
                            patchset=patchset,
                            steps=tuple(steps),
                            outcome=failure.outcome,
                            failure_code=feedback,
                            cleanup_orphans=cleanup_orphans,
                        )
                    )
                    if cleanup_orphans:
                        history.append(RepairLoopState.SANDBOX_CRASHED)
                        return _result(
                            request,
                            history,
                            attempts,
                            failure_code="REPAIR_SANDBOX_CLEANUP_ORPHANS",
                        )
                    if failure.outcome is ValidationOutcome.TIMEOUT:
                        history.append(RepairLoopState.TEST_TIMEOUT)
                        return _result(request, history, attempts, failure_code=feedback)
                    if failure.outcome is ValidationOutcome.CRASH:
                        history.append(RepairLoopState.SANDBOX_CRASHED)
                        return _result(request, history, attempts, failure_code=feedback)
                    history.append(RepairLoopState.VALIDATION_FAILED)
                    if attempt_number == request.max_repair_attempts:
                        history.append(RepairLoopState.REPAIR_EXHAUSTED)
                        return _result(request, history, attempts, failure_code=feedback)
                    continue

                history.extend((RepairLoopState.VALIDATED, RepairLoopState.REVIEWING))
                review = self._reviewer.review(patchset)
                steps.append(review)
                if review.outcome is not ValidationOutcome.PASS:
                    code = review.failure_code or "REVIEW_REJECTED"
                    cleanup_orphans = session.close()
                    session = None
                    attempts.append(
                        _attempt(
                            attempt_number,
                            candidate,
                            worker_digest,
                            patchset=patchset,
                            steps=tuple(steps),
                            outcome=review.outcome,
                            failure_code=code,
                            cleanup_orphans=cleanup_orphans,
                        )
                    )
                    if cleanup_orphans:
                        history.append(RepairLoopState.SANDBOX_CRASHED)
                        return _result(
                            request,
                            history,
                            attempts,
                            failure_code="REPAIR_SANDBOX_CLEANUP_ORPHANS",
                        )
                    history.append(RepairLoopState.REVIEW_REJECTED)
                    return _result(request, history, attempts, failure_code=code)
                history.append(RepairLoopState.REVIEW_PASS)
                recheck = self._policy.recheck(
                    base_root=base_root,
                    final_root=candidate.root,
                    patchset=patchset,
                    checked_at=self._clock(),
                )
                steps.append(_recheck_step(recheck.receipt_sha256))
                final = session.validate_final()
                _validate_step_sequence((final,), final=True)
                steps.append(final)
                if final.outcome is not ValidationOutcome.PASS:
                    code = final.failure_code or "FINAL_VALIDATION_FAILED"
                    cleanup_orphans = session.close()
                    session = None
                    attempts.append(
                        _attempt(
                            attempt_number,
                            candidate,
                            worker_digest,
                            patchset=patchset,
                            steps=tuple(steps),
                            outcome=final.outcome,
                            failure_code=code,
                            cleanup_orphans=cleanup_orphans,
                        )
                    )
                    if cleanup_orphans:
                        history.append(RepairLoopState.SANDBOX_CRASHED)
                        return _result(
                            request,
                            history,
                            attempts,
                            failure_code="REPAIR_SANDBOX_CLEANUP_ORPHANS",
                        )
                    if final.outcome is ValidationOutcome.TIMEOUT:
                        history.append(RepairLoopState.TEST_TIMEOUT)
                        return _result(request, history, attempts, failure_code=code)
                    if final.outcome is ValidationOutcome.CRASH:
                        history.append(RepairLoopState.SANDBOX_CRASHED)
                        return _result(request, history, attempts, failure_code=code)
                    feedback = code
                    history.append(RepairLoopState.VALIDATION_FAILED)
                    if attempt_number == request.max_repair_attempts:
                        history.append(RepairLoopState.REPAIR_EXHAUSTED)
                        return _result(request, history, attempts, failure_code=code)
                    continue
                cleanup_orphans = session.close()
                session = None
                if cleanup_orphans:
                    attempts.append(
                        _attempt(
                            attempt_number,
                            candidate,
                            worker_digest,
                            patchset=patchset,
                            steps=tuple(steps),
                            outcome=ValidationOutcome.CRASH,
                            failure_code="REPAIR_SANDBOX_CLEANUP_ORPHANS",
                            cleanup_orphans=cleanup_orphans,
                        )
                    )
                    history.append(RepairLoopState.SANDBOX_CRASHED)
                    return _result(
                        request,
                        history,
                        attempts,
                        failure_code="REPAIR_SANDBOX_CLEANUP_ORPHANS",
                    )
                attempts.append(
                    _attempt(
                        attempt_number,
                        candidate,
                        worker_digest,
                        patchset=patchset,
                        steps=tuple(steps),
                        outcome=ValidationOutcome.PASS,
                        cleanup_orphans=cleanup_orphans,
                    )
                )
                history.append(RepairLoopState.FINAL_PATCH_READY)
                return _result(
                    request,
                    history,
                    attempts,
                    final_patchset=patchset,
                )
            except Exception as error:
                code = (
                    str(error)
                    if re.fullmatch(r"[A-Z][A-Z0-9_]{2,95}", str(error))
                    else "REPAIR_VALIDATION_BACKEND_FAILURE"
                )
                if session is not None:
                    try:
                        cleanup_orphans = session.close()
                    except Exception:
                        cleanup_orphans = 1
                    session = None
                attempts.append(
                    _attempt(
                        attempt_number,
                        candidate,
                        worker_digest,
                        patchset=patchset,
                        steps=tuple(steps),
                        outcome=ValidationOutcome.CRASH,
                        failure_code=code,
                        cleanup_orphans=cleanup_orphans,
                    )
                )
                history.append(RepairLoopState.SANDBOX_CRASHED)
                return _result(request, history, attempts, failure_code=code)
            finally:
                if session is not None:
                    session.close()
        raise RuntimeError("finite repair loop escaped its closed state machine")

    @staticmethod
    def _validate_worker(
        request: RepairLoopRequest,
        candidate: CandidateWorkspace,
    ) -> str | None:
        result = candidate.worker_result
        if (
            result.status is not WorkerTerminalStatus.SUCCESS
            or result.run_id != request.run_id
            or result.task_id != candidate.worker_run_id
            or result.github_mutations != 0
            or result.aws_calls != 0
        ):
            return result.failure_code or "WORKER_RESULT_INVALID"
        if not candidate.root.is_absolute():
            return "WORKER_CANDIDATE_ROOT_INVALID"
        return None


def _worker_result_digest(result: WorkerResult) -> str:
    return canonical_workspace_json_digest(result.model_dump(mode="json"))


def _policy_step(patchset: PatchSet) -> ValidationStepReceipt:
    return ValidationStepReceipt(
        stage=ValidationStage.V0_PATCHSET_POLICY,
        outcome=ValidationOutcome.PASS,
        evidence_sha256=patchset.patchset_sha256,
    )


def _recheck_step(receipt_sha256: str) -> ValidationStepReceipt:
    return ValidationStepReceipt(
        stage=ValidationStage.V5_SECRET_DETERMINISTIC_RECHECK,
        outcome=ValidationOutcome.PASS,
        evidence_sha256=receipt_sha256,
    )


def _validate_step_sequence(
    steps: tuple[ValidationStepReceipt, ...],
    *,
    final: bool,
) -> None:
    expected = (
        (ValidationStage.V6_FINAL_GATES,)
        if final
        else (ValidationStage.V1_FAST_STATIC, ValidationStage.V2_TARGETED_TESTS)
    )
    observed = tuple(step.stage for step in steps)
    valid_prefix_failure = (
        not final and observed == expected[:1] and steps[0].outcome is not ValidationOutcome.PASS
    )
    if observed != expected and not valid_prefix_failure:
        raise ValueError("validator returned an unauthorized validation sequence")


def _attempt(
    attempt_number: int,
    candidate: CandidateWorkspace,
    worker_digest: str,
    *,
    patchset: PatchSet | None = None,
    steps: tuple[ValidationStepReceipt, ...] = (),
    outcome: ValidationOutcome,
    failure_code: str | None = None,
    cleanup_orphans: int = 0,
) -> RepairAttemptReceipt:
    return RepairAttemptReceipt(
        attempt_number=attempt_number,
        is_repair=attempt_number > 0,
        worker_run_id=candidate.worker_run_id,
        worker_status=candidate.worker_result.status,
        worker_result_sha256=worker_digest,
        patchset_sha256=None if patchset is None else patchset.patchset_sha256,
        validation_steps=steps,
        outcome=outcome,
        failure_code=failure_code,
        sandbox_cleanup_orphans=cleanup_orphans,
    )


def _result(
    request: RepairLoopRequest,
    history: list[RepairLoopState],
    attempts: list[RepairAttemptReceipt],
    *,
    final_patchset: PatchSet | None = None,
    failure_code: str | None = None,
    each_new: bool = True,
) -> RepairLoopResult:
    success = final_patchset is not None and failure_code is None
    values: dict[str, object] = {
        **request.model_dump(),
        "status": RepairLoopResultStatus.PASS if success else RepairLoopResultStatus.FAIL,
        "terminal_state": history[-1],
        "state_history": tuple(history),
        "attempts": tuple(attempts),
        "final_patchset": final_patchset,
        "final_failure_code": failure_code,
        "each_repair_new_patchset_hash": each_new,
        "final_review_passed": success,
        "final_policy_recheck_passed": success,
        "final_secret_scan_passed": success,
        "sandbox_cleanup_orphans": sum(item.sandbox_cleanup_orphans for item in attempts),
    }
    provisional = RepairLoopResult.model_construct(**values, receipt_sha256=_ZERO_DIGEST)
    return RepairLoopResult(
        **values,
        receipt_sha256=canonical_workspace_json_digest(provisional.content_payload()),
    )
