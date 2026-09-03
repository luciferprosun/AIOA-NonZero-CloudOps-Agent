"""Focused W3 certification of exact human authority and atomic unverified apply."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError
from strands.hooks.events import BeforeToolCallEvent
from strands.interventions import Confirm, Deny

from aioa_cloudops_agent.agent import CURRENT_TOOL_NAMES
from aioa_cloudops_agent.nz import ApprovalDecision, ResultStatus
from aioa_cloudops_agent.providers import MockModelProvider, MockToolCall
from aioa_cloudops_agent.workspace import (
    APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME,
    WORKSPACE_AUTHORITY_REGISTERED_TOOL_COUNT,
    WORKSPACE_AUTHORITY_TOOL_NAMES,
    WORKSPACE_REMEDIATION_V1,
    LocalFileWorkspaceAuthorityRepository,
    PatchApplyReceipt,
    WorkspaceApprovalResumeRequest,
    WorkspaceAtomicPatchExecutor,
    WorkspaceAuthorityDenied,
    WorkspaceAuthorityService,
    WorkspaceAuthorityState,
    WorkspaceEvidenceService,
    WorkspaceJail,
    WorkspaceNativeApprovalFlow,
    WorkspacePatchProposal,
    WorkspacePatchProposalBuilder,
    WorkspaceReconciliationMarker,
    WorkspaceRemediationKind,
    build_workspace_approval_payload,
    create_workspace_authority_agent,
    decision_for_request,
    materialize_sealed_fixture,
    workspace_approval_request_hash,
)
from aioa_cloudops_agent.workspace.authority_repository import (
    WorkspaceAuthorityStorageError,
)

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "demo" / "workspace_render_incident_v1"
RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
OTHER_RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b4a")
TRACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3b")
WORKSPACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3c")
OTHER_WORKSPACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b4c")
PROPOSAL_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3d")
EFFECT_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3e")
NOW = datetime(2026, 9, 3, 8, 0, tzinfo=UTC)
CERTIFIED_NOW = datetime(2026, 9, 3, 4, 30, tzinfo=UTC)


class MutableClock:
    def __init__(self, value: datetime = NOW) -> None:
        self.value = value

    def __call__(self) -> datetime:
        return self.value


class UuidFactory:
    def __init__(self, start: int = 1) -> None:
        self.value = start

    def __call__(self) -> UUID:
        result = UUID(f"01890f6c-3311-7abc-8f4a-{self.value:012x}")
        self.value += 1
        return result


@dataclass
class W3Context:
    root: Path
    jail: WorkspaceJail
    service: WorkspaceEvidenceService
    proposal: WorkspacePatchProposal
    repository: LocalFileWorkspaceAuthorityRepository
    authority: WorkspaceAuthorityService
    executor: WorkspaceAtomicPatchExecutor
    clock: MutableClock


def _context(tmp_path: Path) -> W3Context:
    clock = MutableClock()
    materialized = materialize_sealed_fixture(
        run_id=RUN_ID,
        fixture_source=FIXTURE_ROOT,
        workspace_parent=tmp_path,
        profile=WORKSPACE_REMEDIATION_V1,
        workspace_id_factory=lambda: WORKSPACE_ID,
    )
    jail = WorkspaceJail(materialized)
    service = WorkspaceEvidenceService(
        jail,
        trace_id=TRACE_ID,
        clock=clock,
        event_id_factory=UuidFactory(100),
    )
    service.inspect_workspace_incident(materialized.ref)
    service.read_allowed_path(materialized.ref, "deployment.log")
    service.hash_allowed_path(materialized.ref, "render.yaml")
    service.hash_allowed_path(materialized.ref, "scripts/render_start.sh")
    service.hash_allowed_path(materialized.ref, "expected_runtime_contract.json")
    result = WorkspacePatchProposalBuilder(
        service,
        clock=clock,
        proposal_id_factory=lambda: PROPOSAL_ID,
    ).build(
        materialized.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=service.evidence_timeline,
    )
    assert result.status is ResultStatus.SUCCESS and result.value is not None
    repository = LocalFileWorkspaceAuthorityRepository(
        tmp_path / "authority" / "state.json",
        clock=clock,
        event_id_factory=UuidFactory(200),
    )
    authority = WorkspaceAuthorityService(repository, clock=clock)
    authority.persist_proposal(result.value)
    executor = WorkspaceAtomicPatchExecutor(
        jail,
        repository,
        clock=clock,
        effect_id_factory=lambda: EFFECT_ID,
    )
    return W3Context(
        root=materialized.root,
        jail=jail,
        service=service,
        proposal=result.value,
        repository=repository,
        authority=authority,
        executor=executor,
        clock=clock,
    )


def _certified_context(tmp_path: Path) -> W3Context:
    proposal = WorkspacePatchProposal.model_validate(
        json.loads(
            (ROOT / "docs/evidence/workspace/w2-patch-proposal.json").read_text(
                encoding="utf-8"
            )
        )
    )
    clock = MutableClock(CERTIFIED_NOW)
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
        event_id_factory=UuidFactory(400),
    )
    repository = LocalFileWorkspaceAuthorityRepository(
        tmp_path / "authority" / "state.json",
        clock=clock,
        event_id_factory=UuidFactory(500),
    )
    authority = WorkspaceAuthorityService(repository, clock=clock)
    authority.persist_proposal(proposal)
    executor = WorkspaceAtomicPatchExecutor(
        jail,
        repository,
        clock=clock,
        effect_id_factory=lambda: EFFECT_ID,
    )
    return W3Context(
        root=materialized.root,
        jail=jail,
        service=service,
        proposal=proposal,
        repository=repository,
        authority=authority,
        executor=executor,
        clock=clock,
    )


def _request(context: W3Context, interrupt_id: str = "v1:before_tool_call:w3-patch-1"):
    proposal_id = context.proposal.proposal_id
    context.authority.begin_approval(proposal_id)
    return context.authority.record_interrupt(proposal_id, interrupt_id)


def _decide(context: W3Context, decision: ApprovalDecision):
    request = _request(context)
    response = decision_for_request(
        request,
        decision=decision,
        actor_session_id="human-session-w3-001",
        decision_nonce="w3-decision-nonce-0001",
    )
    record, reconciled = context.authority.decide(response)
    assert reconciled is False
    return request, response, record


def _snapshot_tree(root: Path) -> dict[str, tuple[int, int, str]]:
    return {
        path.relative_to(root).as_posix(): (
            stat.S_IMODE(path.lstat().st_mode),
            path.lstat().st_size,
            hashlib.sha256(path.read_bytes()).hexdigest(),
        )
        for path in root.rglob("*")
        if path.is_file() and not path.is_symlink()
    }


def test_payload_is_exactly_derived_from_durable_w2_proposal(tmp_path: Path) -> None:
    context = _context(tmp_path)
    payload = context.authority.begin_approval(PROPOSAL_ID)

    assert payload == build_workspace_approval_payload(context.proposal)
    assert payload.proposal_id == PROPOSAL_ID
    assert payload.run_id == RUN_ID
    assert payload.workspace_id == WORKSPACE_ID
    assert payload.target_path == "render.yaml"
    assert payload.patch_digest == context.proposal.patch_digest
    assert payload.evidence_digest == context.proposal.evidence_digest
    assert payload.risk_class.value == "PLAN_AND_CONFIRM"
    assert payload.canonical_diff_sha256 == hashlib.sha256(
        context.proposal.preview.unified_diff.encode()
    ).hexdigest()
    assert "model" not in payload.model_dump_json().casefold()


def test_certified_w2_identity_anchors_apply_without_hardcoded_executor_values(
    tmp_path: Path,
) -> None:
    context = _certified_context(tmp_path)
    request, _, _ = _decide(context, ApprovalDecision.APPROVED)

    result = context.executor.apply(context.proposal.proposal_id)

    assert result.status is ResultStatus.SUCCESS and result.value is not None
    assert request.payload.base_root_digest == (
        "84172797b4203b01e7404649449ac7b6468e94b88e7aba9b2104d18c01668db8"
    )
    assert request.payload.target_before_sha256 == (
        "b957bbf10af3d711fbfeda271f8ba3b362894f4b02bb8d88239985769a3968db"
    )
    assert request.payload.canonical_after_sha256 == (
        "91eb20346909ca23779cdaf773586a9a925ebf59e90113615ecedcd24dc05314"
    )
    assert request.payload.patch_digest == (
        "73be5422645433ca51371ab992854e028149c9a06753b61e1d66bfe5ed0ee5f0"
    )
    assert request.payload.evidence_digest == (
        "4de8a59272f4f9cf57e2ad3c679897c2a9610d3fef858d0139268bb852ff6675"
    )
    assert result.value.after_sha256 == request.payload.canonical_after_sha256


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("proposal_id", UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b4d")),
        ("run_id", OTHER_RUN_ID),
        ("trace_id", UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b4b")),
        ("workspace_id", OTHER_WORKSPACE_ID),
        ("fixture_version", "workspace_other_v1"),
        ("base_root_digest", "1" * 64),
        ("target_path", "other.yaml"),
        ("target_before_sha256", "2" * 64),
        ("canonical_after_sha256", "3" * 64),
        ("patch_digest", "4" * 64),
        ("evidence_digest", "5" * 64),
        ("supporting_start_script_sha256", "6" * 64),
        ("expected_runtime_contract_sha256", "7" * 64),
        ("proposal_digest", "8" * 64),
        ("canonical_diff_sha256", "9" * 64),
        ("verification_profile_id", "changed_profile"),
        ("rollback_strategy", "changed rollback"),
        ("proposal_version", 2),
        ("proposal_expiry", NOW + timedelta(hours=2)),
        ("risk_class", "AUTO"),
        ("impact_summary", "changed impact"),
    ],
)
def test_request_hash_changes_for_every_bound_identity(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    payload = build_workspace_approval_payload(_context(tmp_path).proposal)

    changed = payload.model_copy(update={field: value})

    assert workspace_approval_request_hash(changed) != workspace_approval_request_hash(payload)


def test_resume_contract_forbids_mutation_material_and_requires_actor_nonce(
    tmp_path: Path,
) -> None:
    request = _request(_context(tmp_path))
    valid = decision_for_request(
        request,
        decision=ApprovalDecision.APPROVED,
        actor_session_id="human-session-w3-001",
        decision_nonce="w3-decision-nonce-0001",
    ).model_dump(mode="json")

    for forbidden in ("content", "command", "cwd", "argv", "environment", "verifier"):
        with pytest.raises(ValidationError):
            WorkspaceApprovalResumeRequest.model_validate({**valid, forbidden: "unsafe"})
    for missing in ("actor_session_id", "decision_nonce"):
        malformed = dict(valid)
        malformed.pop(missing)
        with pytest.raises(ValidationError):
            WorkspaceApprovalResumeRequest.model_validate(malformed)


def test_expired_proposal_cannot_begin_or_complete_approval(tmp_path: Path) -> None:
    context = _context(tmp_path)
    request = _request(context)
    context.clock.value = context.proposal.expires_at + timedelta(seconds=1)

    with pytest.raises(WorkspaceAuthorityDenied, match="expired"):
        context.authority.decide(
            decision_for_request(
                request,
                decision=ApprovalDecision.APPROVED,
                actor_session_id="human-session-w3-001",
                decision_nonce="w3-decision-nonce-0001",
            )
        )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("run_id", OTHER_RUN_ID),
        ("workspace_id", OTHER_WORKSPACE_ID),
        ("canonical_after_sha256", "9" * 64),
        ("patch_digest", "a" * 64),
        ("evidence_digest", "d" * 64),
        ("base_root_digest", "b" * 64),
        ("target_before_sha256", "c" * 64),
        ("supporting_start_script_sha256", "e" * 64),
        ("expected_runtime_contract_sha256", "f" * 64),
        ("proposal_digest", "1" * 64),
        ("verification_profile_id", "changed_profile"),
    ],
)
def test_cross_identity_and_drifted_decision_are_rejected(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    context = _context(tmp_path)
    request = _request(context)
    response = decision_for_request(
        request,
        decision=ApprovalDecision.APPROVED,
        actor_session_id="human-session-w3-001",
        decision_nonce="w3-decision-nonce-0001",
    ).model_copy(update={field: value})

    with pytest.raises(WorkspaceAuthorityDenied) as denied:
        context.authority.decide(response)

    assert denied.value.code == "WORKSPACE_APPROVAL_BINDING_MISMATCH"
    assert context.repository.get_decision(PROPOSAL_ID) is None


def test_denial_is_durable_terminal_and_zero_mutation(tmp_path: Path) -> None:
    context = _context(tmp_path)
    before = _snapshot_tree(context.root)
    _decide(context, ApprovalDecision.DENIED)

    result = context.executor.apply(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert _snapshot_tree(context.root) == before
    assert context.repository.get_proposal_record(PROPOSAL_ID).state is (
        WorkspaceAuthorityState.DENIED_BY_HUMAN
    )
    assert context.repository.get_ownership(PROPOSAL_ID) is None
    assert context.repository.get_receipt(PROPOSAL_ID) is None
    assert context.executor.mutation_count == 0


def test_unapproved_proposal_cannot_invoke_executor(tmp_path: Path) -> None:
    context = _context(tmp_path)
    before = _snapshot_tree(context.root)

    result = context.executor.apply(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_PATCH_NOT_APPROVED"
    assert _snapshot_tree(context.root) == before
    assert context.repository.get_ownership(PROPOSAL_ID) is None


@pytest.mark.parametrize("drift", ["target", "support", "unexpected"])
def test_pre_effect_workspace_drift_is_rejected_without_ownership(
    tmp_path: Path,
    drift: str,
) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    if drift == "unexpected":
        path = context.root / "unapproved.txt"
        path.write_text("unexpected\n", encoding="utf-8")
        path.chmod(0o400)
    else:
        relative = "render.yaml" if drift == "target" else "scripts/render_start.sh"
        path = context.root / relative
        path.chmod(0o600)
        path.write_text("changed\n", encoding="utf-8")
        path.chmod(0o400)

    result = context.executor.apply(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert context.executor.mutation_count == 0
    assert context.repository.get_ownership(PROPOSAL_ID) is None


def test_identical_decision_reconciles_and_conflict_fails_closed(tmp_path: Path) -> None:
    context = _context(tmp_path)
    request, response, original = _decide(context, ApprovalDecision.APPROVED)

    duplicate, reconciled = context.authority.decide(response)

    assert reconciled is True
    assert duplicate == original
    conflict = decision_for_request(
        request,
        decision=ApprovalDecision.DENIED,
        actor_session_id="human-session-w3-001",
        decision_nonce="w3-decision-nonce-0001",
    )
    with pytest.raises(WorkspaceAuthorityDenied) as denied:
        context.authority.decide(conflict)
    assert denied.value.code == "WORKSPACE_APPROVAL_DECISION_CONFLICT"


def test_changed_nonce_replay_is_rejected(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _, response, _ = _decide(context, ApprovalDecision.APPROVED)

    with pytest.raises(WorkspaceAuthorityDenied) as denied:
        context.authority.decide(
            response.model_copy(update={"decision_nonce": "w3-different-nonce-0002"})
        )

    assert denied.value.code == "WORKSPACE_APPROVAL_DECISION_CONFLICT"


def test_restart_preserves_exact_request_and_decision_binding(tmp_path: Path) -> None:
    context = _context(tmp_path)
    request, _, decision = _decide(context, ApprovalDecision.APPROVED)

    restarted = LocalFileWorkspaceAuthorityRepository(context.repository.path)

    assert restarted.get_request(PROPOSAL_ID) == request
    assert restarted.get_decision(PROPOSAL_ID) == decision
    assert restarted.get_proposal_record(PROPOSAL_ID).proposal == context.proposal
    assert stat.S_IMODE(context.repository.path.stat().st_mode) == 0o600


class _BeforeReplaceCrashExecutor(WorkspaceAtomicPatchExecutor):
    def _before_replace(self) -> None:
        record = self.repository.get_proposal_record(PROPOSAL_ID)
        assert record is not None and record.state is WorkspaceAuthorityState.APPLYING
        assert self.repository.get_ownership(PROPOSAL_ID) is not None
        raise OSError("simulated crash before replace")


def test_effect_ownership_is_durable_before_replace_and_safe_to_resume(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    before = (context.root / "render.yaml").read_bytes()
    crashing = _BeforeReplaceCrashExecutor(
        context.jail,
        context.repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )

    first = crashing.apply(PROPOSAL_ID)

    assert first.status is ResultStatus.FAILURE
    assert (context.root / "render.yaml").read_bytes() == before
    assert crashing.mutation_count == 0
    resumed = WorkspaceAtomicPatchExecutor(
        context.jail,
        context.repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )
    second = resumed.apply(PROPOSAL_ID)
    assert second.status is ResultStatus.SUCCESS
    assert resumed.mutation_count == 1


def test_atomic_apply_changes_exactly_render_yaml_and_is_unverified(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    before = _snapshot_tree(context.root)

    result = context.executor.apply(PROPOSAL_ID)

    assert result.status is ResultStatus.SUCCESS and result.value is not None
    receipt = result.value
    after = _snapshot_tree(context.root)
    changed = [path for path in before if before[path] != after[path]]
    assert changed == ["render.yaml"]
    assert after["render.yaml"][2] == context.proposal.canonical_after_sha256
    assert after["render.yaml"][0] == 0o400
    assert receipt.changed_paths == ("render.yaml",)
    assert receipt.status.value == "APPLIED_UNVERIFIED"
    assert receipt.verification_required is True
    assert receipt.success_with_evidence is False
    assert receipt.verified_success is False
    assert context.repository.get_proposal_record(PROPOSAL_ID).state is (
        WorkspaceAuthorityState.PATCH_APPLIED_UNVERIFIED
    )
    assert context.executor.mutation_count == 1


def test_duplicate_apply_returns_same_receipt_without_rewrite(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    first = context.executor.apply(PROPOSAL_ID)
    target = context.root / "render.yaml"
    first_metadata = target.stat()

    second = context.executor.apply(PROPOSAL_ID)

    assert first.value == second.value
    assert context.executor.mutation_count == 1
    assert target.stat().st_ino == first_metadata.st_ino
    assert target.stat().st_mtime_ns == first_metadata.st_mtime_ns


class _ReceiptCrashRepository(LocalFileWorkspaceAuthorityRepository):
    def __init__(self, path: Path, **kwargs: object) -> None:
        super().__init__(path, **kwargs)
        self.failed = False

    def save_receipt(self, receipt: PatchApplyReceipt) -> PatchApplyReceipt:
        if not self.failed:
            self.failed = True
            raise WorkspaceAuthorityStorageError("simulated lost receipt")
        return super().save_receipt(receipt)


def test_crash_after_effect_before_receipt_never_reapplies(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    crashing_repository = _ReceiptCrashRepository(
        context.repository.path,
        clock=context.clock,
        event_id_factory=UuidFactory(300),
    )
    crashing = WorkspaceAtomicPatchExecutor(
        context.jail,
        crashing_repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )

    first = crashing.apply(PROPOSAL_ID)
    assert first.status is ResultStatus.FAILURE
    assert crashing.mutation_count == 1
    restarted = WorkspaceAtomicPatchExecutor(
        context.jail,
        LocalFileWorkspaceAuthorityRepository(context.repository.path),
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )

    second = restarted.apply(PROPOSAL_ID)

    assert second.status is ResultStatus.FAILURE
    assert second.failure.code == "WORKSPACE_EFFECT_RECEIPT_MISSING"
    assert restarted.mutation_count == 0
    marker = restarted.repository.get_reconciliation(PROPOSAL_ID)
    assert isinstance(marker, WorkspaceReconciliationMarker)
    assert marker.reason_code == "TARGET_ALREADY_AFTER_WITHOUT_RECEIPT"


def test_ambiguous_target_after_applying_requires_reconciliation(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    crashing = _BeforeReplaceCrashExecutor(
        context.jail,
        context.repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )
    assert crashing.apply(PROPOSAL_ID).status is ResultStatus.FAILURE
    target = context.root / "render.yaml"
    target.chmod(0o600)
    target.write_text("services: []\n", encoding="utf-8")
    target.chmod(0o400)
    restarted = WorkspaceAtomicPatchExecutor(
        context.jail,
        context.repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )

    result = restarted.apply(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_TARGET_STATE_AMBIGUOUS"
    assert restarted.mutation_count == 0
    assert context.repository.get_proposal_record(PROPOSAL_ID).state is (
        WorkspaceAuthorityState.RECONCILIATION_REQUIRED
    )


@pytest.mark.parametrize("attack", ["symlink", "hardlink", "fifo"])
def test_unsafe_target_type_or_link_is_rejected_before_effect(
    tmp_path: Path,
    attack: str,
) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    target = context.root / "render.yaml"
    safe_copy = tmp_path / "outside-render.yaml"
    safe_copy.write_bytes(target.read_bytes())
    target.unlink()
    if attack == "symlink":
        target.symlink_to(safe_copy)
    elif attack == "hardlink":
        os.link(safe_copy, target)
    else:
        os.mkfifo(target, mode=0o400)

    result = context.executor.apply(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert context.executor.mutation_count == 0
    assert context.repository.get_ownership(PROPOSAL_ID) is None


class _ToctouSwapExecutor(WorkspaceAtomicPatchExecutor):
    def _before_replace(self) -> None:
        target = self.jail.server_root / "render.yaml"
        replacement = self.jail.server_root / ".external-swap"
        replacement.write_text("services: []\n", encoding="utf-8")
        replacement.chmod(0o400)
        os.replace(replacement, target)


def test_target_swap_immediately_before_replace_is_rejected(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    executor = _ToctouSwapExecutor(
        context.jail,
        context.repository,
        clock=context.clock,
        effect_id_factory=lambda: EFFECT_ID,
    )

    result = executor.apply(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert result.failure.code == "WORKSPACE_TARGET_TOCTOU_DENIED"
    assert executor.mutation_count == 0
    assert context.repository.get_proposal_record(PROPOSAL_ID).state is (
        WorkspaceAuthorityState.RECONCILIATION_REQUIRED
    )


def test_receipt_schema_cannot_claim_verified_success(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    receipt = context.executor.apply(PROPOSAL_ID).value
    assert receipt is not None
    payload = receipt.model_dump(mode="json")

    for update in ({"success_with_evidence": True}, {"verified_success": True}):
        with pytest.raises(ValidationError):
            PatchApplyReceipt.model_validate({**payload, **update})


def test_sixth_tool_accepts_only_proposal_id_and_no_forbidden_capabilities(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    runtime = create_workspace_authority_agent(
        context.service,
        context.jail.workspace_ref,
        context.authority,
        context.executor,
    )
    tool = runtime.tools.apply_approved_workspace_patch
    schema = tool.tool_spec["inputSchema"]["json"]

    assert WORKSPACE_AUTHORITY_REGISTERED_TOOL_COUNT == 6
    assert runtime.registered_tool_names == WORKSPACE_AUTHORITY_TOOL_NAMES
    assert set(schema["properties"]) == {"proposal_id"}
    assert schema["required"] == ["proposal_id"]
    with pytest.raises(TypeError):
        tool(proposal_id=PROPOSAL_ID, content="model bytes")
    forbidden = ("shell", "process", "network", "package", "git", "browser", "mcp")
    assert all(
        fragment not in name
        for name in runtime.registered_tool_names
        for fragment in forbidden
    )
    assert set(CURRENT_TOOL_NAMES).isdisjoint(runtime.registered_tool_names)


def _event(runtime, name: str, tool_input: object) -> BeforeToolCallEvent:
    return BeforeToolCallEvent(
        agent=runtime.agent,
        selected_tool=None,
        tool_use={"toolUseId": f"{name}-1", "name": name, "input": tool_input},
        invocation_state={},
    )


def test_native_intervention_denies_unknown_malformed_and_unready_apply(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    runtime = create_workspace_authority_agent(
        context.service,
        context.jail.workspace_ref,
        context.authority,
        context.executor,
    )
    unknown = asyncio.run(
        runtime.human_in_the_loop.before_tool_call(_event(runtime, "shell", {}))
    )
    malformed = asyncio.run(
        runtime.human_in_the_loop.before_tool_call(
            _event(
                runtime,
                APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME,
                {"proposal_id": str(PROPOSAL_ID), "path": "render.yaml"},
            )
        )
    )
    unready = asyncio.run(
        runtime.human_in_the_loop.before_tool_call(
            _event(
                runtime,
                APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME,
                {"proposal_id": str(PROPOSAL_ID)},
            )
        )
    )

    assert isinstance(unknown, Deny)
    assert isinstance(malformed, Deny)
    assert isinstance(unready, Deny)


def test_native_intervention_prompt_comes_from_durable_payload(tmp_path: Path) -> None:
    context = _context(tmp_path)
    context.authority.begin_approval(PROPOSAL_ID)
    runtime = create_workspace_authority_agent(
        context.service,
        context.jail.workspace_ref,
        context.authority,
        context.executor,
    )

    action = asyncio.run(
        runtime.human_in_the_loop.before_tool_call(
            _event(
                runtime,
                APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME,
                {"proposal_id": str(PROPOSAL_ID)},
            )
        )
    )

    assert isinstance(action, Confirm)
    assert context.proposal.patch_digest in action.prompt
    assert context.proposal.evidence_digest in action.prompt
    assert context.proposal.preview.after_text not in action.prompt
    assert "model rationale" not in action.prompt.casefold()


def test_native_strands_approval_applies_once_after_durable_decision(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    model = MockModelProvider(
        tool_plan=(
            MockToolCall(
                APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME,
                {"proposal_id": str(PROPOSAL_ID)},
            ),
        ),
        final_text="Patch effect recorded as unverified.",
    )
    runtime = create_workspace_authority_agent(
        context.service,
        context.jail.workspace_ref,
        context.authority,
        context.executor,
        model=model,
    )
    flow = WorkspaceNativeApprovalFlow(runtime)

    request_result = flow.request(PROPOSAL_ID)
    assert request_result.status is ResultStatus.SUCCESS
    assert request_result.value is not None
    assert request_result.value.interrupt_id.startswith("v1:before_tool_call:")
    assert context.repository.get_request(PROPOSAL_ID) == request_result.value
    assert context.repository.get_proposal_record(PROPOSAL_ID).state is (
        WorkspaceAuthorityState.AWAITING_APPROVAL
    )
    assert context.repository.get_decision(PROPOSAL_ID) is None
    response = decision_for_request(
        request_result.value,
        decision=ApprovalDecision.APPROVED,
        actor_session_id="human-session-w3-001",
        decision_nonce="w3-decision-nonce-0001",
    )
    resumed = flow.resume(response)

    assert resumed.status is ResultStatus.SUCCESS and resumed.value is not None
    assert resumed.value.state is WorkspaceAuthorityState.PATCH_APPLIED_UNVERIFIED
    assert resumed.value.verified_success is False
    assert context.executor.mutation_count == 1
    assert context.repository.get_decision(PROPOSAL_ID) is not None
    assert context.repository.get_receipt(PROPOSAL_ID) is not None
    assert model.network_calls == 0


def test_native_strands_denial_has_zero_effect(tmp_path: Path) -> None:
    context = _context(tmp_path)
    before = _snapshot_tree(context.root)
    model = MockModelProvider(
        tool_plan=(
            MockToolCall(
                APPLY_APPROVED_WORKSPACE_PATCH_TOOL_NAME,
                {"proposal_id": str(PROPOSAL_ID)},
            ),
        )
    )
    runtime = create_workspace_authority_agent(
        context.service,
        context.jail.workspace_ref,
        context.authority,
        context.executor,
        model=model,
    )
    flow = WorkspaceNativeApprovalFlow(runtime)
    request = flow.request(PROPOSAL_ID).value
    assert request is not None

    result = flow.resume(
        decision_for_request(
            request,
            decision=ApprovalDecision.DENIED,
            actor_session_id="human-session-w3-001",
            decision_nonce="w3-decision-nonce-0001",
        )
    )

    assert result.status is ResultStatus.SUCCESS and result.value is not None
    assert result.value.state is WorkspaceAuthorityState.DENIED_BY_HUMAN
    assert _snapshot_tree(context.root) == before
    assert context.executor.mutation_count == 0
    assert context.repository.get_ownership(PROPOSAL_ID) is None
    assert context.repository.get_receipt(PROPOSAL_ID) is None


def test_private_host_errors_are_redacted(tmp_path: Path) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    target = context.root / "render.yaml"
    target.unlink()
    target.symlink_to(tmp_path / "private-host-secret-location")

    result = context.executor.apply(PROPOSAL_ID)

    assert result.status is ResultStatus.FAILURE
    assert str(tmp_path) not in result.failure.message
    assert "private-host-secret-location" not in result.failure.message


def test_audit_timeline_records_authority_order_without_verified_success(
    tmp_path: Path,
) -> None:
    context = _context(tmp_path)
    _decide(context, ApprovalDecision.APPROVED)
    context.executor.apply(PROPOSAL_ID)
    snapshot = context.repository.read_snapshot()

    assert tuple(event.event_type for event in snapshot.audit_events) == (
        "PROPOSAL_PERSISTED",
        "APPROVAL_REQUESTED",
        "DECISION_RECORDED",
        "EFFECT_OWNED",
        "APPLY_RECORDED",
    )
    assert all("SUCCESS" not in event.event_type for event in snapshot.audit_events)


def test_tracked_w3_evidence_is_sanitized_and_binds_certified_w2() -> None:
    evidence_root = ROOT / "docs/evidence/workspace"
    approve = json.loads((evidence_root / "w3-approve-apply.json").read_text())
    deny = json.loads((evidence_root / "w3-deny.json").read_text())
    recovery = json.loads((evidence_root / "w3-replay-recovery.json").read_text())
    certified = "c9d9537e49e8388ba2ca5b92538383ca8c69d0d7fd2f704d2240002414736499"

    assert approve["source_w2_proposal_digest"] == certified
    assert approve["approval_payload"]["evidence_digest"] == (
        "4de8a59272f4f9cf57e2ad3c679897c2a9610d3fef858d0139268bb852ff6675"
    )
    assert approve["workspace_mutation_count"] == 1
    assert approve["changed_paths"] == ["render.yaml"]
    assert approve["receipt"]["status"] == "APPLIED_UNVERIFIED"
    assert approve["receipt"]["success_with_evidence"] is False
    assert deny["source_w2_proposal_digest"] == certified
    assert deny["workspace_mutation_count"] == 0
    assert deny["tree_unchanged"] is True
    assert recovery["source_w2_proposal_digest"] == certified
    assert recovery["duplicate_completed_apply"]["extra_mutations"] == 0
    assert recovery["crash_after_effect_before_receipt"][
        "recovery_extra_mutations"
    ] == 0
    rendered = json.dumps((approve, deny, recovery), sort_keys=True).casefold()
    assert "/media/" not in rendered
    assert "/home/" not in rendered
    assert "aioa_operator_token" not in rendered
    assert "w3-decision-nonce-0001" not in rendered
