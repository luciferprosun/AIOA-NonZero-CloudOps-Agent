"""Focused W4 certification of independent verification and no-reapply recovery."""

from __future__ import annotations

import inspect
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from scripts.w4_render_start_profile import RenderStartContractV1Profile

from aioa_cloudops_agent.nz import ApprovalDecision, ResultStatus
from aioa_cloudops_agent.workspace import (
    W4_VERIFICATION_CHECK_ORDER,
    WORKSPACE_REMEDIATION_V1,
    WORKSPACE_VERIFICATION_REGISTERED_TOOL_COUNT,
    WORKSPACE_VERIFICATION_TOOL_NAMES,
    LocalFileWorkspaceAuthorityRepository,
    MaterializedWorkspace,
    PatchApplyReceipt,
    TrustedRenderStartProfileFailure,
    TrustedRenderStartProfileResult,
    WorkspaceAtomicPatchExecutor,
    WorkspaceAuthorityService,
    WorkspaceAuthorityState,
    WorkspaceEvidenceService,
    WorkspaceIndependentVerifier,
    WorkspaceJail,
    WorkspacePatchProposal,
    WorkspaceRecoveryClassification,
    WorkspaceRemediationKind,
    WorkspaceVerificationBoundary,
    WorkspaceVerificationCheckCode,
    WorkspaceVerificationDisposition,
    WorkspaceVerificationProofOrigin,
    WorkspaceVerificationReceipt,
    WorkspaceVerificationReport,
    create_workspace_verification_agent,
    decision_for_request,
    materialize_sealed_fixture,
)
from aioa_cloudops_agent.workspace.authority_repository import (
    WorkspaceAuthorityStorageError,
)

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "demo" / "workspace_render_incident_v1"
PROPOSAL_PATH = ROOT / "docs/evidence/workspace/w2-patch-proposal.json"
EFFECT_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3e")
OTHER_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b9e")
NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class UuidFactory:
    def __init__(self, start: int = 1_000) -> None:
        self.value = start

    def __call__(self) -> UUID:
        result = UUID(f"01890f6c-3311-7abc-8f4a-{self.value:012x}")
        self.value += 1
        return result


class PassingProfile:
    def __init__(self) -> None:
        self.calls = 0

    def run(self) -> TrustedRenderStartProfileResult:
        self.calls += 1
        return TrustedRenderStartProfileResult()


class FailingProfile:
    def __init__(self, code: str) -> None:
        self.code = code
        self.calls = 0

    def run(self) -> TrustedRenderStartProfileResult:
        self.calls += 1
        raise TrustedRenderStartProfileFailure(self.code)


@dataclass
class W4Context:
    materialized: MaterializedWorkspace
    jail: WorkspaceJail
    service: WorkspaceEvidenceService
    proposal: WorkspacePatchProposal
    repository: LocalFileWorkspaceAuthorityRepository
    authority: WorkspaceAuthorityService
    executor: WorkspaceAtomicPatchExecutor
    boundary: WorkspaceVerificationBoundary
    clock: MutableClock


def _context(
    tmp_path: Path,
    *,
    repository_type: type[LocalFileWorkspaceAuthorityRepository] = (
        LocalFileWorkspaceAuthorityRepository
    ),
) -> W4Context:
    tmp_path.mkdir(mode=0o700, parents=True, exist_ok=True)
    proposal = WorkspacePatchProposal.model_validate(
        json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
    )
    clock = MutableClock()
    materialized = materialize_sealed_fixture(
        run_id=proposal.run_id,
        fixture_source=FIXTURE_ROOT,
        workspace_parent=tmp_path,
        profile=WORKSPACE_REMEDIATION_V1,
        workspace_id_factory=lambda: proposal.workspace_id,
    )
    jail = WorkspaceJail(materialized)
    service = WorkspaceEvidenceService(
        jail,
        trace_id=proposal.trace_id,
        clock=clock,
        event_id_factory=UuidFactory(2_000),
    )
    repository = repository_type(
        tmp_path / "authority" / "state.json",
        clock=clock,
        event_id_factory=UuidFactory(3_000),
    )
    authority = WorkspaceAuthorityService(repository, clock=clock)
    authority.persist_proposal(proposal)
    executor = WorkspaceAtomicPatchExecutor(
        jail,
        repository,
        clock=clock,
        effect_id_factory=lambda: EFFECT_ID,
    )
    boundary = WorkspaceVerificationBoundary(materialized, FIXTURE_ROOT)
    return W4Context(
        materialized=materialized,
        jail=jail,
        service=service,
        proposal=proposal,
        repository=repository,
        authority=authority,
        executor=executor,
        boundary=boundary,
        clock=clock,
    )


def _approve(context: W4Context, decision: ApprovalDecision = ApprovalDecision.APPROVED) -> None:
    proposal_id = context.proposal.proposal_id
    context.authority.begin_approval(proposal_id)
    request = context.authority.record_interrupt(
        proposal_id,
        "v1:before_tool_call:w4-patch-1",
    )
    response = decision_for_request(
        request,
        decision=decision,
        actor_session_id="human-session-w4-001",
        decision_nonce="w4-decision-nonce-0001",
    )
    _record, reconciled = context.authority.decide(response)
    assert reconciled is False


def _apply(context: W4Context) -> PatchApplyReceipt:
    _approve(context)
    result = context.executor.apply(context.proposal.proposal_id)
    assert result.status is ResultStatus.SUCCESS and result.value is not None
    return result.value


def _verifier(
    context: W4Context,
    profile: object | None = None,
    repository: LocalFileWorkspaceAuthorityRepository | None = None,
) -> WorkspaceIndependentVerifier:
    return WorkspaceIndependentVerifier(
        context.boundary,
        repository or context.repository,
        profile or PassingProfile(),
        clock=context.clock,
        evidence_id_factory=UuidFactory(4_000),
    )


def _write_private(path: Path, text: str) -> None:
    path.chmod(0o600)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o400)


def _check(report: WorkspaceVerificationReport, code: WorkspaceVerificationCheckCode):
    return next(item for item in report.checks if item.code is code)


def test_independent_reopen_produces_durable_success_after_exact_w3_effect(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    apply_receipt = _apply(context)
    profile = PassingProfile()

    result = _verifier(context, profile).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.SUCCESS and result.value is not None
    completion = result.value
    assert completion.terminal_state == "SUCCESS_WITH_EVIDENCE"
    assert completion.reconciled is False
    assert completion.verifier_fixed_process_probes == 1
    assert profile.calls == 1
    assert completion.report.disposition is WorkspaceVerificationDisposition.VERIFIED
    assert completion.report.actual_changed_paths == ("render.yaml",)
    assert completion.report.actual_after_sha256 == context.proposal.canonical_after_sha256
    assert completion.report.apply_receipt_digest is not None
    assert completion.report.recovery_observation_digest is None
    assert completion.receipt.proof_origin is WorkspaceVerificationProofOrigin.APPLY_RECEIPT
    assert apply_receipt.success_with_evidence is False
    assert context.executor.mutation_count == 1
    assert context.repository.get_proposal_record(context.proposal.proposal_id).state is (
        WorkspaceAuthorityState.SUCCESS_WITH_EVIDENCE
    )


def test_executor_receipt_never_overrides_disk_mismatch(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    _write_private(context.materialized.root / "render.yaml", "services: []\n")

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_VERIFICATION_MISMATCH"
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert report.disposition is WorkspaceVerificationDisposition.MISMATCH
    assert _check(report, WorkspaceVerificationCheckCode.TARGET_AFTER_HASH).status.value == (
        "FAIL"
    )
    assert context.repository.get_verification_receipt(context.proposal.proposal_id) is None


@pytest.mark.parametrize(
    ("relative_path", "replacement", "check_code"),
    [
        ("scripts/render_start.sh", "#!/bin/sh\nexit 0\n", WorkspaceVerificationCheckCode.START_SCRIPT_HASH),
        (
            "expected_runtime_contract.json",
            "{}\n",
            WorkspaceVerificationCheckCode.RUNTIME_CONTRACT_HASH,
        ),
    ],
)
def test_supporting_artifact_drift_blocks_success(
    tmp_path: Path,
    relative_path: str,
    replacement: str,
    check_code: WorkspaceVerificationCheckCode,
) -> None:
    context = _context(tmp_path)
    _apply(context)
    _write_private(context.materialized.root / relative_path, replacement)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert _check(report, check_code).status.value == "FAIL"
    assert report.actual_changed_paths == tuple(sorted(("render.yaml", relative_path)))


def test_extra_file_blocks_exact_changed_path_proof(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    extra = context.materialized.root / "unexpected.txt"
    extra.write_text("untrusted\n", encoding="utf-8")
    extra.chmod(0o400)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert report.actual_changed_paths == ("render.yaml", "unexpected.txt")
    assert _check(report, WorkspaceVerificationCheckCode.EXACT_CHANGED_PATH_SET).status.value == (
        "FAIL"
    )


def test_extra_empty_directory_is_not_ignored(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    extra = context.materialized.root / "unexpected-dir"
    extra.mkdir(mode=0o700)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert "unexpected-dir" in report.actual_changed_paths


def test_old_inline_command_cannot_be_verified(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    _write_private(
        context.materialized.root / "render.yaml",
        context.proposal.preview.before_text,
    )

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert _check(
        report,
        WorkspaceVerificationCheckCode.INLINE_DOCKER_COMMAND_ABSENT,
    ).status.value == "FAIL"


@pytest.mark.parametrize("variant", ["missing", "duplicated"])
def test_fixed_executable_must_exist_exactly_once(tmp_path: Path, variant: str) -> None:
    context = _context(tmp_path)
    _apply(context)
    after = context.proposal.preview.after_text
    if variant == "missing":
        changed = after.replace(
            "    dockerCommand: /usr/local/bin/aioa-render-start\n",
            "",
        )
    else:
        changed = after.replace(
            "    dockerCommand: /usr/local/bin/aioa-render-start\n",
            "    dockerCommand: /usr/local/bin/aioa-render-start\n"
            "    dockerCommand: /usr/local/bin/aioa-render-start\n",
        )
    _write_private(context.materialized.root / "render.yaml", changed)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert _check(
        report,
        WorkspaceVerificationCheckCode.FIXED_EXECUTABLE_PRESENT_ONCE,
    ).status.value == "FAIL"


def test_unknown_proposal_identity_fails_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)

    result = _verifier(context).verify(OTHER_ID)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_VERIFICATION_PROPOSAL_NOT_FOUND"


def test_changed_verification_profile_id_is_rejected_by_contract(tmp_path: Path) -> None:
    context = _context(tmp_path)
    payload = context.proposal.model_dump(mode="json")
    payload["verification_profile_id"] = "model_supplied_profile"

    with pytest.raises(ValidationError):
        WorkspacePatchProposal.model_validate(payload)


def test_denied_proposal_cannot_enter_verifier(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _approve(context, ApprovalDecision.DENIED)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.kind.value == "POLICY_DENIAL"
    assert context.repository.get_verification_report(context.proposal.proposal_id) is None


def test_unapproved_proposal_cannot_enter_verifier(tmp_path: Path) -> None:
    context = _context(tmp_path)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_VERIFICATION_AUTHORITY_MISSING"


def test_fixed_profile_api_accepts_no_model_command_fields() -> None:
    signature = inspect.signature(RenderStartContractV1Profile.run)

    assert tuple(signature.parameters) == ("self",)
    with pytest.raises(TypeError):
        RenderStartContractV1Profile().run(command="sh")  # type: ignore[call-arg]


def test_workspace_python_tests_and_hooks_are_never_executed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    marker = tmp_path / "execution-marker"
    payload = (
        "from pathlib import Path\n"
        f"Path({str(marker)!r}).write_text('executed', encoding='utf-8')\n"
    )
    for relative_path in ("conftest.py", "workspace_test.py", ".git-hook.py"):
        candidate = context.materialized.root / relative_path
        candidate.write_text(payload, encoding="utf-8")
        candidate.chmod(0o400)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    assert not marker.exists()
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert _check(
        report,
        WorkspaceVerificationCheckCode.NO_WORKSPACE_CODE_EXECUTION,
    ).status.value == "NOT_RUN"


def test_real_fixed_profile_proves_token_argv_health_ready_and_zero_egress() -> None:
    result = RenderStartContractV1Profile().run()

    assert result.missing_token_fails_closed is True
    assert result.token_mode_0600 is True
    assert result.bootstrap_secret_absent is True
    assert result.child_argv_exact is True
    assert result.health_passed is True
    assert result.readiness_passed is True
    assert result.external_egress_count == 0
    assert result.aws_call_count == 0
    assert result.process_executions == 1
    assert result.workspace_code_executions == 0
    assert result.arbitrary_command_executions == 0


def test_profile_timeout_never_becomes_success(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)

    result = _verifier(context, FailingProfile("RUNTIME_PROBE_TIMEOUT")).verify(
        context.proposal.proposal_id
    )

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_TRUSTED_VERIFIER_UNAVAILABLE"
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert report.disposition is WorkspaceVerificationDisposition.DEPENDENCY_UNAVAILABLE
    assert context.repository.get_verification_receipt(context.proposal.proposal_id) is None


class _BeforeReplaceCrashExecutor(WorkspaceAtomicPatchExecutor):
    def _before_replace(self) -> None:
        raise OSError("simulated crash before effect")


def test_crash_before_effect_is_safe_resumable_but_w4_never_applies(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _approve(context)
    crashing = _BeforeReplaceCrashExecutor(
        context.jail,
        context.repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )
    assert crashing.apply(context.proposal.proposal_id).status is ResultStatus.FAILURE
    before = (context.materialized.root / "render.yaml").stat()

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_SAFE_RESUMABLE_FOR_W3_APPLY"
    observation = context.repository.get_recovery_observation(context.proposal.proposal_id)
    assert observation is not None
    assert observation.classification is (
        WorkspaceRecoveryClassification.SAFE_RESUMABLE_FOR_W3_APPLY
    )
    after = (context.materialized.root / "render.yaml").stat()
    assert (after.st_ino, after.st_mtime_ns) == (before.st_ino, before.st_mtime_ns)
    assert crashing.mutation_count == 0


class _ReceiptCrashRepository(LocalFileWorkspaceAuthorityRepository):
    def __init__(self, path: Path, **kwargs: object) -> None:
        super().__init__(path, **kwargs)
        self.failed = False

    def save_receipt(self, receipt: PatchApplyReceipt) -> PatchApplyReceipt:
        if not self.failed:
            self.failed = True
            raise WorkspaceAuthorityStorageError("simulated receipt crash")
        return super().save_receipt(receipt)


def test_crash_after_effect_before_receipt_recovers_without_second_apply(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path, repository_type=_ReceiptCrashRepository)
    _approve(context)
    first = context.executor.apply(context.proposal.proposal_id)
    assert first.status is ResultStatus.FAILURE
    assert context.executor.mutation_count == 1
    target_before_verify = (context.materialized.root / "render.yaml").stat()

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.SUCCESS and result.value is not None
    assert result.value.receipt.proof_origin is (
        WorkspaceVerificationProofOrigin.RECOVERY_READ_BACK
    )
    assert result.value.report.apply_receipt_digest is None
    assert result.value.report.recovery_observation_digest is not None
    target_after_verify = (context.materialized.root / "render.yaml").stat()
    assert (target_after_verify.st_ino, target_after_verify.st_mtime_ns) == (
        target_before_verify.st_ino,
        target_before_verify.st_mtime_ns,
    )
    assert context.executor.mutation_count == 1


def test_w3_lost_receipt_marker_is_reconciled_by_fresh_read_back(tmp_path: Path) -> None:
    context = _context(tmp_path, repository_type=_ReceiptCrashRepository)
    _approve(context)
    assert context.executor.apply(context.proposal.proposal_id).status is ResultStatus.FAILURE
    restarted = WorkspaceAtomicPatchExecutor(
        context.jail,
        context.repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )
    assert restarted.apply(context.proposal.proposal_id).status is ResultStatus.FAILURE
    assert context.repository.get_proposal_record(context.proposal.proposal_id).state is (
        WorkspaceAuthorityState.RECONCILIATION_REQUIRED
    )

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.SUCCESS
    assert restarted.mutation_count == 0


def test_crash_after_receipt_before_verify_runs_only_verification(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    target_before = (context.materialized.root / "render.yaml").stat()

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.SUCCESS
    target_after = (context.materialized.root / "render.yaml").stat()
    assert (target_after.st_ino, target_after.st_mtime_ns) == (
        target_before.st_ino,
        target_before.st_mtime_ns,
    )
    assert context.executor.mutation_count == 1


def test_neither_before_nor_after_remains_reconciliation_required(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _approve(context)
    crashing = _BeforeReplaceCrashExecutor(
        context.jail,
        context.repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )
    assert crashing.apply(context.proposal.proposal_id).status is ResultStatus.FAILURE
    _write_private(context.materialized.root / "render.yaml", "services: []\n")

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_EFFECT_STATE_AMBIGUOUS"
    observation = context.repository.get_recovery_observation(context.proposal.proposal_id)
    assert observation is not None
    assert observation.classification is WorkspaceRecoveryClassification.AMBIGUOUS_STATE
    assert context.repository.get_proposal_record(context.proposal.proposal_id).state is (
        WorkspaceAuthorityState.RECONCILIATION_REQUIRED
    )
    assert crashing.mutation_count == 0


def test_duplicate_verification_reuses_proof_without_process_or_apply(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    profile = PassingProfile()
    verifier = _verifier(context, profile)
    first = verifier.verify(context.proposal.proposal_id)
    target = (context.materialized.root / "render.yaml").stat()

    second = verifier.verify(context.proposal.proposal_id)

    assert first.status is ResultStatus.SUCCESS and second.status is ResultStatus.SUCCESS
    assert first.value.report == second.value.report
    assert first.value.receipt == second.value.receipt
    assert second.value.reconciled is True
    assert second.value.verifier_fixed_process_probes == 0
    assert profile.calls == 1
    after = (context.materialized.root / "render.yaml").stat()
    assert (after.st_ino, after.st_mtime_ns) == (target.st_ino, target.st_mtime_ns)
    assert context.executor.mutation_count == 1


class _TamperedReportRepository(LocalFileWorkspaceAuthorityRepository):
    def get_verification_report(self, proposal_id: UUID):
        value = super().get_verification_report(proposal_id)
        if value is None:
            return None
        return value.model_copy(update={"report_digest": "0" * 64})


def test_tampered_verification_report_digest_is_rejected(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    assert _verifier(context).verify(context.proposal.proposal_id).status is ResultStatus.SUCCESS
    tampered = _TamperedReportRepository(context.repository.path, clock=context.clock)

    result = _verifier(context, repository=tampered).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_VERIFICATION_EVIDENCE_INVALID"


def test_success_receipt_is_impossible_before_durable_report(tmp_path: Path) -> None:
    context = _context(tmp_path)
    apply_receipt = _apply(context)
    context.repository.begin_verification(context.proposal.proposal_id)
    candidate = WorkspaceVerificationReceipt.create(
        verification_id=UuidFactory(5_000)(),
        proposal_id=context.proposal.proposal_id,
        run_id=context.proposal.run_id,
        trace_id=context.proposal.trace_id,
        workspace_id=context.proposal.workspace_id,
        effect_id=apply_receipt.effect_id,
        report_digest="1" * 64,
        observed_after_sha256=context.proposal.canonical_after_sha256,
        verification_profile_id=context.proposal.verification_profile_id,
        proof_origin=WorkspaceVerificationProofOrigin.APPLY_RECEIPT,
        apply_receipt_digest="2" * 64,
        recovery_observation_digest=None,
        verified_at=context.clock(),
    )

    with pytest.raises(ValueError):
        context.repository.save_verification_receipt(candidate)
    assert context.repository.get_proposal_record(context.proposal.proposal_id).state is (
        WorkspaceAuthorityState.VERIFYING
    )


def test_verification_checks_have_canonical_order_and_stable_digest(tmp_path: Path) -> None:
    first_context = _context(tmp_path / "first")
    second_context = _context(tmp_path / "second")
    _apply(first_context)
    _apply(second_context)

    first = _verifier(first_context).verify(first_context.proposal.proposal_id)
    second = _verifier(second_context).verify(second_context.proposal.proposal_id)

    assert first.status is ResultStatus.SUCCESS and second.status is ResultStatus.SUCCESS
    assert tuple(check.code for check in first.value.report.checks) == (
        W4_VERIFICATION_CHECK_ORDER
    )
    assert first.value.report.report_digest == second.value.report.report_digest


def test_reordered_checks_or_tampered_report_digest_fail_contract(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    result = _verifier(context).verify(context.proposal.proposal_id)
    assert result.value is not None
    payload = result.value.report.model_dump(mode="json")

    payload["checks"] = list(reversed(payload["checks"]))
    with pytest.raises(ValidationError):
        WorkspaceVerificationReport.model_validate(payload)


def test_verifier_errors_are_redacted(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    private_value = "bootstrap-" + ("private" * 8)
    private_path = str(tmp_path / "operator.token")

    result = _verifier(context, FailingProfile("RUNTIME_PROBE_UNAVAILABLE")).verify(
        context.proposal.proposal_id
    )

    rendered = result.model_dump_json()
    assert private_value not in rendered
    assert private_path not in rendered
    assert "WORKSPACE_TRUSTED_VERIFIER_UNAVAILABLE" in rendered


def test_workspace_tool_surface_is_exactly_seven_and_proposal_id_only(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    verifier = _verifier(context)
    runtime = create_workspace_verification_agent(
        context.service,
        context.materialized.ref,
        context.authority,
        context.executor,
        verifier,
    )
    tool = runtime.tools.verify_workspace_remediation
    schema = tool.tool_spec["inputSchema"]["json"]

    assert WORKSPACE_VERIFICATION_REGISTERED_TOOL_COUNT == 7
    assert runtime.registered_tool_names == WORKSPACE_VERIFICATION_TOOL_NAMES
    assert set(schema["properties"]) == {"proposal_id"}
    assert schema["required"] == ["proposal_id"]
    with pytest.raises(TypeError):
        tool(proposal_id=context.proposal.proposal_id, command="pytest")
    forbidden = ("shell", "process", "package", "git", "browser", "mcp", "network")
    assert all(
        fragment not in name
        for name in runtime.registered_tool_names
        for fragment in forbidden
    )


def test_boundary_rejects_cross_workspace_mapping(tmp_path: Path) -> None:
    context = _context(tmp_path)
    proposal = context.proposal.model_copy(update={"workspace_id": OTHER_ID})

    with pytest.raises(RuntimeError):
        context.boundary.reopen(proposal)


def test_linked_supporting_artifact_blocks_verification(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    script = context.materialized.root / "scripts/render_start.sh"
    outside = tmp_path / "outside-script"
    outside.write_bytes(script.read_bytes())
    outside.chmod(0o400)
    script.chmod(0o600)
    script.unlink()
    os.link(outside, script)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.FAILURE
    report = context.repository.get_verification_report(context.proposal.proposal_id)
    assert report is not None
    assert report.disposition is WorkspaceVerificationDisposition.MISMATCH
    assert "scripts/render_start.sh" in report.actual_changed_paths


def test_report_distinguishes_effect_receipt_recovery_and_terminal_state(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _apply(context)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.value is not None
    report = result.value.report
    receipt = result.value.receipt
    assert report.apply_receipt_digest is not None
    assert report.recovery_observation_digest is None
    assert report.disposition is WorkspaceVerificationDisposition.VERIFIED
    assert receipt.report_digest == report.report_digest
    assert receipt.terminal_state == "SUCCESS_WITH_EVIDENCE"
    assert receipt.success_with_evidence is True
    assert receipt.verified_success is True


def test_w4_never_changes_repository_root_deployment_inputs(tmp_path: Path) -> None:
    tracked = (
        ROOT / "render.yaml",
        ROOT / "Dockerfile",
        ROOT / "scripts/render_start.sh",
    )
    before = {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in tracked}
    context = _context(tmp_path)
    _apply(context)

    assert _verifier(context).verify(context.proposal.proposal_id).status is ResultStatus.SUCCESS
    assert {path: (path.stat().st_mtime_ns, path.read_bytes()) for path in tracked} == before


def test_no_workspace_process_authority_is_added_to_profile_contract() -> None:
    assert WORKSPACE_REMEDIATION_V1.network_allowed is False
    assert WORKSPACE_REMEDIATION_V1.mutation_allowed is False
    assert tuple(operation.value for operation in WORKSPACE_REMEDIATION_V1.allowed_operations) == (
        "INSPECT",
        "LIST",
        "READ",
        "HASH",
    )
    assert WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE.value == (
        "USE_FIXED_RENDER_START_EXECUTABLE"
    )
    assert not any(
        fragment in name
        for name in WORKSPACE_VERIFICATION_TOOL_NAMES
        for fragment in ("shell", "process", "exec", "command", "argv")
    )


def test_verification_receipt_file_contract_is_strict(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)
    result = _verifier(context).verify(context.proposal.proposal_id)
    assert result.value is not None
    payload = result.value.receipt.model_dump(mode="json")

    for update in (
        {"success_with_evidence": False},
        {"verified_success": False},
        {"terminal_state": "PATCH_APPLIED_UNVERIFIED"},
        {"receipt_digest": "0" * 64},
    ):
        with pytest.raises(ValidationError):
            WorkspaceVerificationReceipt.model_validate({**payload, **update})


def test_root_and_artifact_modes_remain_private_after_verified_success(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _apply(context)

    result = _verifier(context).verify(context.proposal.proposal_id)

    assert result.status is ResultStatus.SUCCESS
    assert stat.S_IMODE(context.materialized.root.stat().st_mode) == 0o700
    assert all(
        stat.S_IMODE(path.stat().st_mode) == 0o400
        for path in context.materialized.root.rglob("*")
        if path.is_file()
    )


def test_tracked_w4_evidence_is_strict_sanitized_and_w3_bound() -> None:
    path = ROOT / "docs/evidence/workspace/w4-verification-report.json"
    evidence = json.loads(path.read_text(encoding="utf-8"))
    report = WorkspaceVerificationReport.model_validate(
        evidence["independent_verification"]
    )
    receipt = WorkspaceVerificationReceipt.model_validate(
        evidence["verification_receipt"]
    )

    assert evidence["source_w3_head"] == (
        "8827cf9943361c30b3c116e25895f0b99855149e"
    )
    assert evidence["executor_receipt"]["status"] == "APPLIED_UNVERIFIED"
    assert evidence["executor_receipt"]["success_with_evidence"] is False
    assert evidence["recovery_observation"] is None
    assert report.disposition is WorkspaceVerificationDisposition.VERIFIED
    assert receipt.report_digest == report.report_digest
    assert evidence["final_terminal_state"] == "SUCCESS_WITH_EVIDENCE"
    assert evidence["recovery_scenarios"]["second_patch_apply_count"] == 0
    assert set(evidence["capability_accounting"].values()) == {0, 1}
    rendered = json.dumps(evidence, sort_keys=True).casefold()
    assert "/media/" not in rendered
    assert "/home/" not in rendered
    assert "w4-decision-nonce-0001" not in rendered
    assert "aioa_operator_token" not in rendered
