"""Strict evidence contracts for the finite W7A test-repair-review loop."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, model_validator

from aioa_cloudops_agent.agent import WorkerTerminalStatus
from aioa_cloudops_agent.nz import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.patchset import PatchSet
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

MAX_REPAIR_ATTEMPTS = 2


class RepairLoopState(StrEnum):
    """Closed finite state machine; unknown or incomplete never means PASS."""

    PROPOSED_PATCH = "PROPOSED_PATCH"
    VALIDATING = "VALIDATING"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    REPAIRING_1 = "REPAIRING_1"
    REPAIRING_2 = "REPAIRING_2"
    VALIDATED = "VALIDATED"
    REVIEWING = "REVIEWING"
    REVIEW_PASS = "REVIEW_PASS"
    REVIEW_REJECTED = "REVIEW_REJECTED"
    FINAL_PATCH_READY = "FINAL_PATCH_READY"
    REPAIR_EXHAUSTED = "REPAIR_EXHAUSTED"
    POLICY_DENIED = "POLICY_DENIED"
    WORKER_FAILED = "WORKER_FAILED"
    TEST_TIMEOUT = "TEST_TIMEOUT"
    SANDBOX_CRASHED = "SANDBOX_CRASHED"


class ValidationStage(StrEnum):
    """The deterministic Phase 6 validation ladder."""

    V0_PATCHSET_POLICY = "V0_PATCHSET_POLICY"
    V1_FAST_STATIC = "V1_FAST_STATIC"
    V2_TARGETED_TESTS = "V2_TARGETED_TESTS"
    V4_SEMANTIC_REVIEW = "V4_SEMANTIC_REVIEW"
    V5_SECRET_DETERMINISTIC_RECHECK = "V5_SECRET_DETERMINISTIC_RECHECK"
    V6_FINAL_GATES = "V6_FINAL_GATES"


class ValidationOutcome(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    POLICY_DENIED = "POLICY_DENIED"
    TIMEOUT = "TIMEOUT"
    CRASH = "CRASH"


class RepairLoopResultStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"


class RepairLoopRequest(NonZeroContract):
    """One parent task; no command, remote, credential or arbitrary policy fields."""

    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    task_id: Uuid7Identifier
    operation_correlation_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    base_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    max_repair_attempts: Literal[2] = MAX_REPAIR_ATTEMPTS


class ValidationStepReceipt(NonZeroContract):
    """Bounded observation for one server-owned validation step."""

    stage: ValidationStage
    outcome: ValidationOutcome
    evidence_sha256: Sha256Digest
    sandbox_id: Uuid7Identifier | None = None
    exit_code: int | None = Field(default=None, ge=0, le=255)
    stdout_sha256: Sha256Digest | None = None
    stderr_sha256: Sha256Digest | None = None
    output_truncated: bool = False
    failure_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{2,95}$",
    )
    network_mode: Literal["NONE"] = "NONE"
    raw_output_retained: Literal[False] = False

    @model_validator(mode="after")
    def validate_outcome(self) -> Self:
        if self.outcome is ValidationOutcome.PASS:
            if self.failure_code is not None or self.exit_code not in {None, 0}:
                raise ValueError("successful validation cannot carry a failure")
        elif self.failure_code is None:
            raise ValueError("failed validation requires a stable failure code")
        return self


class RepairAttemptReceipt(NonZeroContract):
    """One initial candidate or bounded repair attempt."""

    attempt_number: int = Field(ge=0, le=2)
    is_repair: bool
    worker_run_id: Uuid7Identifier
    worker_status: WorkerTerminalStatus
    worker_result_sha256: Sha256Digest
    patchset_sha256: Sha256Digest | None = None
    validation_steps: tuple[ValidationStepReceipt, ...] = Field(max_length=6)
    outcome: ValidationOutcome
    failure_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{2,95}$",
    )
    sandbox_cleanup_orphans: int = Field(default=0, ge=0, le=1_000)
    github_mutations: Literal[0] = 0
    aws_calls: Literal[0] = 0

    @model_validator(mode="after")
    def validate_attempt(self) -> Self:
        if self.is_repair is not (self.attempt_number > 0):
            raise ValueError("repair flag does not match attempt number")
        if self.outcome is ValidationOutcome.PASS:
            if self.failure_code is not None or self.patchset_sha256 is None:
                raise ValueError("passing attempt requires PatchSet and forbids failure")
        elif self.failure_code is None:
            raise ValueError("failed attempt requires a stable failure code")
        return self


class RepairLoopResult(NonZeroContract):
    """Self-hashed terminal loop receipt with no remote mutation authority."""

    schema_version: Literal[1] = 1
    authority: Literal["AIOA_W7A_FINITE_REPAIR_LOOP_V1"] = "AIOA_W7A_FINITE_REPAIR_LOOP_V1"
    run_id: Uuid7Identifier
    trace_id: Uuid7Identifier
    task_id: Uuid7Identifier
    operation_correlation_id: Uuid7Identifier
    workspace_id: Uuid7Identifier
    base_head: str = Field(pattern=r"^[0-9a-f]{40}$")
    max_repair_attempts: Literal[2] = MAX_REPAIR_ATTEMPTS
    status: RepairLoopResultStatus
    terminal_state: RepairLoopState
    state_history: tuple[RepairLoopState, ...] = Field(min_length=2, max_length=16)
    attempts: tuple[RepairAttemptReceipt, ...] = Field(min_length=1, max_length=3)
    final_patchset: PatchSet | None = None
    final_failure_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{2,95}$",
    )
    each_repair_new_patchset_hash: bool
    final_review_passed: bool
    final_policy_recheck_passed: bool
    final_secret_scan_passed: bool
    sandbox_cleanup_orphans: int = Field(ge=0, le=1_000)
    product_github_mutations: Literal[0] = 0
    aws_calls: Literal[0] = 0
    aws_mutations: Literal[0] = 0
    external_deployments: Literal[0] = 0
    receipt_sha256: Sha256Digest

    @model_validator(mode="after")
    def validate_terminal_truth(self) -> Self:
        numbers = tuple(attempt.attempt_number for attempt in self.attempts)
        if numbers != tuple(range(len(self.attempts))):
            raise ValueError("repair attempts must be contiguous and start at zero")
        if self.state_history[-1] is not self.terminal_state:
            raise ValueError("state history must end at terminal state")
        if self.sandbox_cleanup_orphans != sum(
            attempt.sandbox_cleanup_orphans for attempt in self.attempts
        ):
            raise ValueError("cleanup orphan total mismatch")
        if self.status is RepairLoopResultStatus.PASS:
            if (
                self.terminal_state is not RepairLoopState.FINAL_PATCH_READY
                or self.final_patchset is None
                or self.final_failure_code is not None
                or not self.final_review_passed
                or not self.final_policy_recheck_passed
                or not self.final_secret_scan_passed
                or self.attempts[-1].outcome is not ValidationOutcome.PASS
                or self.sandbox_cleanup_orphans != 0
            ):
                raise ValueError("passing loop lacks mandatory final proof")
        elif self.final_failure_code is None or self.final_patchset is not None:
            raise ValueError("failed loop requires a failure and forbids final PatchSet")
        if self.receipt_sha256 != canonical_workspace_json_digest(self.content_payload()):
            raise ValueError("repair-loop receipt digest mismatch")
        return self

    def content_payload(self) -> dict[str, object]:
        return self.model_dump(mode="json", exclude={"receipt_sha256"})
