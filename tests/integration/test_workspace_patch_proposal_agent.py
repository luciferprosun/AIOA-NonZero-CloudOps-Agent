from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest

from aioa_cloudops_agent.agent import CURRENT_TOOL_NAMES
from aioa_cloudops_agent.nz import ResultStatus
from aioa_cloudops_agent.providers import MockModelProvider, MockToolCall
from aioa_cloudops_agent.workspace import (
    BUILD_WORKSPACE_PATCH_PROPOSAL_TOOL_NAME,
    WORKSPACE_REMEDIATION_V1,
    WORKSPACE_TOOL_NAMES,
    WorkspaceEvidenceService,
    WorkspaceJail,
    WorkspacePatchProposalOutcome,
    WorkspaceRemediationKind,
    create_workspace_investigation_agent,
    inspect_fixture_tree,
    materialize_sealed_fixture,
)

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "demo" / "workspace_render_incident_v1"
RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
TRACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3b")
NOW = datetime(2026, 9, 3, 4, 30, tzinfo=UTC)


def _event_id_factory():
    counter = 0

    def next_id() -> UUID:
        nonlocal counter
        counter += 1
        return UUID(f"01890f6c-3311-7abc-8f4a-{counter:012x}")

    return next_id


def _runtime(tmp_path: Path, *, model: MockModelProvider | None = None):
    sealed = materialize_sealed_fixture(
        run_id=RUN_ID,
        fixture_source=FIXTURE_ROOT,
        workspace_parent=tmp_path,
        profile=WORKSPACE_REMEDIATION_V1,
    )
    service = WorkspaceEvidenceService(
        WorkspaceJail(sealed),
        trace_id=TRACE_ID,
        clock=lambda: NOW,
        event_id_factory=_event_id_factory(),
    )
    runtime = create_workspace_investigation_agent(service, sealed.ref, model=model)
    return sealed, service, runtime


def _prime_required_evidence(runtime) -> None:
    runtime.tools.inspect_deployment_incident()
    runtime.tools.read_workspace_artifact(relative_path="deployment.log")
    runtime.tools.hash_workspace_artifact(relative_path="render.yaml")
    runtime.tools.hash_workspace_artifact(relative_path="scripts/render_start.sh")
    runtime.tools.hash_workspace_artifact(
        relative_path="expected_runtime_contract.json"
    )


def test_fifth_tool_schema_accepts_only_closed_remediation_kind(tmp_path: Path) -> None:
    _, _, runtime = _runtime(tmp_path)
    tool = runtime.tools.build_workspace_patch_proposal
    schema = tool.tool_spec["inputSchema"]["json"]

    assert tool.tool_name == BUILD_WORKSPACE_PATCH_PROPOSAL_TOOL_NAME
    assert set(schema["properties"]) == {"remediation_kind"}
    assert schema["required"] == ["remediation_kind"]
    assert "no filesystem mutation" in tool.tool_spec["description"].casefold()
    assert "no execution authority" in tool.tool_spec["description"].casefold()
    with pytest.raises(TypeError):
        tool(
            remediation_kind=WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE,
            unified_diff="model authored",
        )


def test_fifth_tool_fails_closed_without_exact_prior_evidence(tmp_path: Path) -> None:
    _, _, runtime = _runtime(tmp_path)

    result = runtime.tools.build_workspace_patch_proposal(
        remediation_kind=WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE
    )

    assert result["status"] == ResultStatus.FAILURE
    assert result["failure"]["code"] == WorkspacePatchProposalOutcome.STALE_EVIDENCE


def test_fifth_tool_returns_exact_inert_preview_with_zero_workspace_effect(
    tmp_path: Path,
) -> None:
    sealed, _, runtime = _runtime(tmp_path)
    _prime_required_evidence(runtime)
    before = inspect_fixture_tree(sealed.root, WORKSPACE_REMEDIATION_V1)

    result = runtime.tools.build_workspace_patch_proposal(
        remediation_kind=WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE
    )

    assert result["status"] == ResultStatus.SUCCESS
    proposal = result["value"]
    assert proposal["outcome"] == WorkspacePatchProposalOutcome.PROPOSAL_READY
    assert proposal["target_path"] == "render.yaml"
    assert proposal["change"]["replacement_value"] == (
        "/usr/local/bin/aioa-render-start"
    )
    assert proposal["risk_class"] == "PLAN_AND_CONFIRM"
    assert proposal["authorizes_execution"] is False
    assert proposal["apply_authority_granted"] is False
    assert inspect_fixture_tree(sealed.root, WORKSPACE_REMEDIATION_V1) == before


def test_workspace_and_cloudops_tool_surfaces_remain_exact_and_disjoint(
    tmp_path: Path,
) -> None:
    _, _, runtime = _runtime(tmp_path)

    assert tuple(runtime.agent.tool_names) == WORKSPACE_TOOL_NAMES
    assert len(WORKSPACE_TOOL_NAMES) == 5
    assert WORKSPACE_TOOL_NAMES[-1] == BUILD_WORKSPACE_PATCH_PROPOSAL_TOOL_NAME
    assert len(CURRENT_TOOL_NAMES) == 5
    assert set(CURRENT_TOOL_NAMES).isdisjoint(WORKSPACE_TOOL_NAMES)


def test_agent_reasoning_path_builds_evidence_bound_proposal_without_execution(
    tmp_path: Path,
) -> None:
    final_text = """FACTS
- deployment.log records exit 127 and File name too long; render.yaml contains the long inline dockerCommand.
AGENT_INFERENCE
- The inline startup dispatch is the primary hypothesis. A missing token is an alternative hypothesis, not a verified fact.
SUPPORTING_EVIDENCE
- deployment.log, render.yaml, scripts/render_start.sh, expected_runtime_contract.json.
EXACT_PATCH_PREVIEW
- Replace only services[0].dockerCommand with /usr/local/bin/aioa-render-start; no patch was applied.
RISK_CLASS
- PLAN_AND_CONFIRM for any future apply.
EXPECTED_VERIFICATION_PROFILE
- render_start_contract_v1.
HUMAN_DECISION_REQUIRED
- Yes. W2 grants no execution authority; a separately authorized W3 decision is required."""
    model = MockModelProvider(
        tool_plan=(
            MockToolCall("inspect_deployment_incident", {}),
            MockToolCall("list_workspace_artifacts", {}),
            MockToolCall("read_workspace_artifact", {"relative_path": "deployment.log"}),
            MockToolCall("read_workspace_artifact", {"relative_path": "render.yaml"}),
            MockToolCall("hash_workspace_artifact", {"relative_path": "render.yaml"}),
            MockToolCall(
                "hash_workspace_artifact",
                {"relative_path": "scripts/render_start.sh"},
            ),
            MockToolCall(
                "hash_workspace_artifact",
                {"relative_path": "expected_runtime_contract.json"},
            ),
            MockToolCall(
                "build_workspace_patch_proposal",
                {
                    "remediation_kind": (
                        WorkspaceRemediationKind.USE_FIXED_RENDER_START_EXECUTABLE.value
                    )
                },
            ),
        ),
        final_text=final_text,
    )
    sealed, service, runtime = _runtime(tmp_path, model=model)
    before = inspect_fixture_tree(sealed.root, WORKSPACE_REMEDIATION_V1)

    result = runtime.agent("Build the exact evidence-bound W2 proposal.")

    assert str(result).rstrip() == final_text
    assert model.calls == 9
    assert model.network_calls == 0
    assert inspect_fixture_tree(sealed.root, WORKSPACE_REMEDIATION_V1) == before
    assert len(service.evidence_timeline) == 10
    for heading in (
        "FACTS",
        "AGENT_INFERENCE",
        "SUPPORTING_EVIDENCE",
        "EXACT_PATCH_PREVIEW",
        "RISK_CLASS",
        "EXPECTED_VERIFICATION_PROFILE",
        "HUMAN_DECISION_REQUIRED",
    ):
        assert heading in str(result)
    assert "alternative hypothesis, not a verified fact" in str(result)


def test_profile_registers_no_apply_process_network_package_or_git_tool(
    tmp_path: Path,
) -> None:
    _, _, runtime = _runtime(tmp_path)
    forbidden_fragments = (
        "apply",
        "write",
        "delete",
        "shell",
        "process",
        "network",
        "package",
        "install",
        "git",
        "browser",
        "mcp",
    )

    assert all(
        fragment not in tool_name
        for tool_name in runtime.registered_tool_names
        for fragment in forbidden_fragments
    )
    assert runtime.service.profile.mutation_allowed is False
    assert runtime.service.profile.network_allowed is False
