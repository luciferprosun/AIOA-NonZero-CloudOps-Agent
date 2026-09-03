import hashlib
import inspect
import json
import shutil
import stat
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

import aioa_cloudops_agent.workspace.proposal as proposal_module
from aioa_cloudops_agent.domain import AuthorityGate
from aioa_cloudops_agent.nz import ResultStatus
from aioa_cloudops_agent.workspace import (
    W2_AFTER_LINE,
    W2_AFTER_VALUE,
    W2_BEFORE_BLOCK,
    W2_ROLLBACK_STRATEGY,
    W2_VERIFICATION_PROFILE_ID,
    WORKSPACE_REMEDIATION_V1,
    WorkspaceEvidenceService,
    WorkspaceJail,
    WorkspacePatchPreview,
    WorkspacePatchProposal,
    WorkspacePatchProposalBuilder,
    WorkspacePatchProposalOutcome,
    WorkspaceRemediationKind,
    canonical_workspace_json_digest,
    inspect_fixture_tree,
    materialize_sealed_fixture,
)

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "demo" / "workspace_render_incident_v1"
RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
OTHER_RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b4a")
TRACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3b")
PROPOSAL_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3c")
STALE_EVENT_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3d")
WORKSPACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3e")
NOW = datetime(2026, 9, 3, 4, 30, tzinfo=UTC)


def _event_id_factory():
    counter = 0

    def next_id() -> UUID:
        nonlocal counter
        counter += 1
        return UUID(f"01890f6c-3311-7abc-8f4a-{counter:012x}")

    return next_id


def _setup(tmp_path: Path, *, run_id: UUID = RUN_ID, fixture_root: Path = FIXTURE_ROOT):
    workspace_parent = tmp_path / f"workspaces-{str(run_id)[-4:]}"
    workspace_parent.mkdir(parents=True)
    sealed = materialize_sealed_fixture(
        run_id=run_id,
        fixture_source=fixture_root,
        workspace_parent=workspace_parent,
        profile=WORKSPACE_REMEDIATION_V1,
        workspace_id_factory=lambda: WORKSPACE_ID,
    )
    service = WorkspaceEvidenceService(
        WorkspaceJail(sealed),
        trace_id=TRACE_ID,
        clock=lambda: NOW,
        event_id_factory=_event_id_factory(),
    )
    builder = WorkspacePatchProposalBuilder(
        service,
        clock=lambda: NOW,
        proposal_id_factory=lambda: PROPOSAL_ID,
    )
    return sealed, service, builder


def _required_evidence(service: WorkspaceEvidenceService, workspace_ref):
    assert service.inspect_workspace_incident(workspace_ref).status is ResultStatus.SUCCESS
    assert service.read_allowed_path(workspace_ref, "deployment.log").status is ResultStatus.SUCCESS
    assert service.hash_allowed_path(workspace_ref, "render.yaml").status is ResultStatus.SUCCESS
    assert (
        service.hash_allowed_path(workspace_ref, "scripts/render_start.sh").status
        is ResultStatus.SUCCESS
    )
    assert (
        service.hash_allowed_path(workspace_ref, "expected_runtime_contract.json").status
        is ResultStatus.SUCCESS
    )
    return service.evidence_timeline


def _successful_build(tmp_path: Path):
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)
    result = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=receipts,
    )
    assert result.status is ResultStatus.SUCCESS
    assert result.value is not None
    return sealed, service, builder, receipts, result.value


def _tree_snapshot(root: Path) -> tuple[tuple[object, ...], ...]:
    records: list[tuple[object, ...]] = []
    for path in sorted(root.rglob("*")):
        metadata = path.lstat()
        records.append(
            (
                path.relative_to(root).as_posix(),
                stat.S_IFMT(metadata.st_mode),
                stat.S_IMODE(metadata.st_mode),
                metadata.st_size,
                metadata.st_mtime_ns,
                hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None,
            )
        )
    return tuple(records)


def _replace_receipt(receipts, path: str, transform):
    changed = []
    for receipt in receipts:
        if receipt.artifact is not None and receipt.artifact.relative_path == path:
            changed.append(transform(receipt))
        else:
            changed.append(receipt)
    return tuple(changed)


def test_w2_builds_exact_content_addressed_non_applying_proposal(tmp_path: Path) -> None:
    sealed, _, _, _, proposal = _successful_build(tmp_path)

    assert proposal.outcome is WorkspacePatchProposalOutcome.PROPOSAL_READY
    assert proposal.workspace_id == sealed.ref.workspace_id
    assert proposal.root_digest == proposal.base_root_digest == sealed.ref.root_digest
    assert proposal.target_path == "render.yaml"
    assert proposal.target_before_sha256 == proposal.preview.before_sha256
    assert proposal.canonical_after_sha256 == proposal.preview.after_sha256
    assert proposal.patch_digest == proposal.preview.patch_digest
    assert proposal.proposal_digest == canonical_workspace_json_digest(
        proposal.content_payload()
    )
    assert len(proposal.evidence_references) == 5


def test_entire_successful_proposal_flow_has_zero_workspace_mutation(tmp_path: Path) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)
    before = _tree_snapshot(sealed.root)

    result = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=receipts,
    )

    assert result.status is ResultStatus.SUCCESS
    assert _tree_snapshot(sealed.root) == before


def test_patch_and_proposal_content_are_deterministic_for_same_inputs(tmp_path: Path) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)

    first = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=receipts,
    )
    second = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=receipts,
    )

    assert first.value is not None and second.value is not None
    assert first.value == second.value
    assert first.value.patch_digest == second.value.patch_digest
    assert first.value.evidence_digest == second.value.evidence_digest


def test_target_before_hash_matches_current_confined_render_read(tmp_path: Path) -> None:
    sealed, _, _, _, proposal = _successful_build(tmp_path)

    assert proposal.target_before_sha256 == hashlib.sha256(
        (sealed.root / "render.yaml").read_bytes()
    ).hexdigest()


def test_transform_replaces_only_exact_docker_command_block(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)

    assert proposal.change.replacement_value == W2_AFTER_VALUE
    assert proposal.preview.before_text.count(W2_BEFORE_BLOCK) == 1
    assert proposal.preview.after_text == proposal.preview.before_text.replace(
        W2_BEFORE_BLOCK,
        W2_AFTER_LINE,
        1,
    )


def test_diff_headers_and_line_endings_are_canonical(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)
    preview = proposal.preview

    assert preview.unified_diff.startswith("--- a/render.yaml\n+++ b/render.yaml\n")
    assert "\r" not in preview.unified_diff
    assert preview.line_endings == "LF"
    assert f"+    dockerCommand: {W2_AFTER_VALUE}\n" in preview.unified_diff


def test_patch_identity_excludes_ui_diff_rendering(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)

    assert "unified_diff" not in proposal.preview.canonical_patch_payload()
    assert "before_text" not in proposal.preview.canonical_patch_payload()
    assert proposal.patch_digest == proposal.preview.canonical_patch_digest()


def test_contract_rejects_modified_ui_diff(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)
    payload = proposal.preview.model_dump(mode="python")
    payload["unified_diff"] = f"{payload['unified_diff']} "

    with pytest.raises(ValidationError, match="canonical server rendering"):
        WorkspacePatchPreview.model_validate(payload)


def test_contract_rejects_unrelated_after_content_change(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)
    payload = proposal.preview.model_dump(mode="python")
    payload["after_text"] = payload["after_text"].replace("plan: free", "plan: paid")
    payload["after_sha256"] = hashlib.sha256(payload["after_text"].encode()).hexdigest()

    with pytest.raises(ValidationError, match="outside the canonical replacement"):
        WorkspacePatchPreview.model_validate(payload)


def test_unsupported_remediation_kind_fails_closed(tmp_path: Path) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)

    result = builder.build(sealed.ref, "MODEL_AUTHORED_PATCH", evidence_receipts=receipts)

    assert result.status is ResultStatus.FAILURE
    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.UNSUPPORTED_REMEDIATION


def test_root_and_base_digest_drift_rejects_proposal(tmp_path: Path) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)
    drifted = sealed.ref.model_copy(
        update={"root_digest": "0" * 64, "created_from_digest": "0" * 64}
    )

    result = builder.build(
        drifted,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=receipts,
    )

    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.BASE_DIGEST_MISMATCH


def test_cross_workspace_evidence_rejects_proposal(tmp_path: Path) -> None:
    first, _, builder = _setup(tmp_path / "first", run_id=RUN_ID)
    second, second_service, _ = _setup(tmp_path / "second", run_id=OTHER_RUN_ID)
    foreign_receipts = _required_evidence(second_service, second.ref)

    result = builder.build(
        first.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=foreign_receipts,
    )

    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.STALE_EVIDENCE


def test_unretained_evidence_receipt_rejects_proposal(tmp_path: Path) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = list(_required_evidence(service, sealed.ref))
    receipts[0] = receipts[0].model_copy(update={"event_id": STALE_EVENT_ID})

    result = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=tuple(receipts),
    )

    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.STALE_EVIDENCE


def test_target_evidence_digest_mismatch_rejects_proposal(tmp_path: Path) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)

    def corrupt(receipt):
        artifact = receipt.artifact.model_copy(update={"sha256": "0" * 64})
        return receipt.model_copy(update={"artifact": artifact, "sha256": "0" * 64})

    result = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=_replace_receipt(receipts, "render.yaml", corrupt),
    )

    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.TARGET_DIGEST_MISMATCH


@pytest.mark.parametrize(
    "path",
    ("scripts/render_start.sh", "expected_runtime_contract.json"),
)
def test_supporting_artifact_digest_mismatch_rejects_proposal(
    tmp_path: Path,
    path: str,
) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)

    def corrupt(receipt):
        artifact = receipt.artifact.model_copy(update={"sha256": "f" * 64})
        return receipt.model_copy(update={"artifact": artifact, "sha256": "f" * 64})

    result = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=_replace_receipt(receipts, path, corrupt),
    )

    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.SUPPORTING_ARTIFACT_MISMATCH


def test_incomplete_evidence_fails_closed(tmp_path: Path) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)[:-1]

    result = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=receipts,
    )

    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.STALE_EVIDENCE


def test_builder_api_rejects_model_supplied_diff_or_target_argument(tmp_path: Path) -> None:
    sealed, _, builder = _setup(tmp_path)

    with pytest.raises(TypeError):
        builder.build(
            sealed.ref,
            WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
            unified_diff="model content",
        )
    with pytest.raises(TypeError):
        builder.build(
            sealed.ref,
            WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
            target_path="other.yaml",
        )


def test_one_byte_candidate_identity_change_changes_patch_digest(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)
    payload = proposal.preview.canonical_patch_payload()
    replacement = "0" if proposal.canonical_after_sha256[-1] != "0" else "1"
    payload["after_sha256"] = f"{proposal.canonical_after_sha256[:-1]}{replacement}"

    assert canonical_workspace_json_digest(payload) != proposal.patch_digest


def test_one_byte_evidence_identity_change_changes_evidence_digest(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)
    evidence = [reference.model_dump(mode="json") for reference in proposal.evidence_references]
    original = evidence[0]["receipt_sha256"]
    replacement = "0" if original[-1] != "0" else "1"
    evidence[0]["receipt_sha256"] = f"{original[:-1]}{replacement}"

    assert canonical_workspace_json_digest(evidence) != proposal.evidence_digest


def test_proposal_requires_plan_and_confirm_but_grants_no_authority(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)

    assert proposal.risk_class is AuthorityGate.PLAN_AND_CONFIRM
    assert proposal.authorizes_execution is False
    assert proposal.apply_authority_granted is False
    assert proposal.mutation_allowed is False
    assert proposal.process_execution_allowed is False
    assert proposal.network_allowed is False


def test_proposal_binds_exact_rollback_and_verification_profile(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)

    assert proposal.rollback_strategy == W2_ROLLBACK_STRATEGY
    assert proposal.verification_profile_id == W2_VERIFICATION_PROFILE_ID


def test_proposal_contract_rejects_unknown_model_fields(tmp_path: Path) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)
    payload = proposal.model_dump(mode="python")
    payload["apply_now"] = True

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        WorkspacePatchProposal.model_validate(payload)


def test_outcome_taxonomy_is_closed_and_complete() -> None:
    assert {outcome.value for outcome in WorkspacePatchProposalOutcome} == {
        "PROPOSAL_READY",
        "UNSUPPORTED_REMEDIATION",
        "STALE_WORKSPACE",
        "STALE_EVIDENCE",
        "BASE_DIGEST_MISMATCH",
        "TARGET_DIGEST_MISMATCH",
        "SUPPORTING_ARTIFACT_MISMATCH",
        "AMBIGUOUS_TARGET",
        "POLICY_DENIED",
        "VALIDATION_FAILURE",
    }


def test_builder_registers_no_process_network_git_or_package_implementation() -> None:
    source = inspect.getsource(proposal_module)

    assert "subprocess" not in source
    assert "os.system" not in source
    assert "socket" not in source
    assert "boto" not in source
    assert "git " not in source
    assert "pip " not in source
    assert "open(" not in source
    assert "write_" not in source
    assert "unlink(" not in source


def test_ambiguous_docker_command_target_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "ambiguous-source"
    shutil.copytree(FIXTURE_ROOT, source)
    render_path = source / "render.yaml"
    render_path.write_text(
        render_path.read_text(encoding="utf-8") + W2_BEFORE_BLOCK,
        encoding="utf-8",
    )
    _, root_digest = inspect_fixture_tree(source, WORKSPACE_REMEDIATION_V1)
    render_digest = hashlib.sha256(render_path.read_bytes()).hexdigest()
    monkeypatch.setattr(proposal_module, "W2_CERTIFIED_W1_ROOT_DIGEST", root_digest)
    monkeypatch.setattr(proposal_module, "W2_RENDER_BEFORE_SHA256", render_digest)
    sealed, service, builder = _setup(tmp_path / "run", fixture_root=source)
    receipts = _required_evidence(service, sealed.ref)

    result = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=receipts,
    )

    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.AMBIGUOUS_TARGET


def test_workspace_tamper_after_evidence_is_redacted_and_rejected(tmp_path: Path) -> None:
    sealed, service, builder = _setup(tmp_path)
    receipts = _required_evidence(service, sealed.ref)
    target = sealed.root / "render.yaml"
    target.chmod(0o600)
    target.write_text(target.read_text(encoding="utf-8") + "# drift\n", encoding="utf-8")

    result = builder.build(
        sealed.ref,
        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
        evidence_receipts=receipts,
    )

    assert result.failure is not None
    assert result.failure.code == WorkspacePatchProposalOutcome.BASE_DIGEST_MISMATCH
    assert str(tmp_path) not in result.failure.message


def test_tracked_demo_receipt_is_exactly_reproducible_and_contract_valid(
    tmp_path: Path,
) -> None:
    _, _, _, _, proposal = _successful_build(tmp_path)
    evidence_path = ROOT / "docs" / "evidence" / "workspace" / "w2-patch-proposal.json"
    tracked = json.loads(evidence_path.read_text(encoding="utf-8"))

    assert WorkspacePatchProposal.model_validate(tracked) == proposal
    assert tracked == proposal.model_dump(mode="json")
