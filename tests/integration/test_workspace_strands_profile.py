from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

import pytest
from strands import Agent

from aioa_cloudops_agent.agent import CURRENT_TOOL_NAMES
from aioa_cloudops_agent.config import (
    BedrockSettings,
    ModelProviderName,
    RuntimeMode,
    RuntimeSettings,
)
from aioa_cloudops_agent.domain import ContractValidationError
from aioa_cloudops_agent.nz import ResultStatus, generate_event_id
from aioa_cloudops_agent.providers import MockModelProvider, MockToolCall
from aioa_cloudops_agent.workspace import (
    HASH_WORKSPACE_ARTIFACT_TOOL_NAME,
    INSPECT_DEPLOYMENT_INCIDENT_TOOL_NAME,
    LIST_WORKSPACE_ARTIFACTS_TOOL_NAME,
    READ_WORKSPACE_ARTIFACT_TOOL_NAME,
    WORKSPACE_AGENT_COUNT,
    WORKSPACE_AGENT_ID,
    WORKSPACE_REGISTERED_TOOL_COUNT,
    WORKSPACE_REMEDIATION_V1,
    WORKSPACE_SYSTEM_PROMPT,
    WORKSPACE_TOOL_NAMES,
    WorkspaceEvidenceService,
    WorkspaceJail,
    WorkspaceOperation,
    create_workspace_investigation_agent,
    inspect_fixture_tree,
    materialize_sealed_fixture,
)

ROOT = Path(__file__).parents[2]
FIXTURE_ROOT = ROOT / "demo" / "workspace_render_incident_v1"
RUN_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3a")
TRACE_ID = UUID("01890f6c-3311-7abc-8f4a-6e4f7f0b9b3b")
NOW = datetime(2026, 9, 2, 20, 0, tzinfo=UTC)


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
        event_id_factory=generate_event_id,
    )
    runtime = create_workspace_investigation_agent(
        service,
        sealed.ref,
        model=model,
    )
    return sealed, service, runtime


def test_workspace_profile_creates_exactly_one_agent_and_four_tools(tmp_path: Path) -> None:
    _, _, runtime = _runtime(tmp_path)

    assert isinstance(runtime.agent, Agent)
    assert runtime.agent.agent_id == WORKSPACE_AGENT_ID
    assert WORKSPACE_AGENT_COUNT == 1
    assert WORKSPACE_REGISTERED_TOOL_COUNT == 4
    assert runtime.registered_tool_names == WORKSPACE_TOOL_NAMES == (
        INSPECT_DEPLOYMENT_INCIDENT_TOOL_NAME,
        LIST_WORKSPACE_ARTIFACTS_TOOL_NAME,
        READ_WORKSPACE_ARTIFACT_TOOL_NAME,
        HASH_WORKSPACE_ARTIFACT_TOOL_NAME,
    )
    assert runtime.agent.tool_names == list(WORKSPACE_TOOL_NAMES)


def test_workspace_tools_bind_identity_and_expose_minimal_schemas(tmp_path: Path) -> None:
    sealed, _, runtime = _runtime(tmp_path)

    inspect_result = runtime.tools.inspect_deployment_incident()
    list_result = runtime.tools.list_workspace_artifacts()
    read_result = runtime.tools.read_workspace_artifact(relative_path="deployment.log")
    hash_result = runtime.tools.hash_workspace_artifact(relative_path="deployment.log")

    assert inspect_result["status"] == ResultStatus.SUCCESS.value
    assert list_result["status"] == ResultStatus.SUCCESS.value
    assert read_result["status"] == ResultStatus.SUCCESS.value
    assert hash_result["status"] == ResultStatus.SUCCESS.value
    assert inspect_result["value"]["workspace"]["workspace_id"] == str(sealed.ref.workspace_id)
    assert "root" not in inspect_result["value"]["workspace"]
    assert runtime.tools.inspect_deployment_incident.tool_spec["inputSchema"]["json"] == {
        "properties": {},
        "required": [],
        "type": "object",
    }
    assert set(
        runtime.tools.read_workspace_artifact.tool_spec["inputSchema"]["json"]["properties"]
    ) == {"relative_path"}
    with pytest.raises(TypeError):
        runtime.tools.read_workspace_artifact(
            relative_path="deployment.log",
            root="/etc",
        )


def test_unknown_or_mutating_tool_is_absent_and_default_denied(tmp_path: Path) -> None:
    _, _, runtime = _runtime(tmp_path)

    forbidden = {
        "shell",
        "shell_execute",
        "write_file",
        "apply_patch",
        "git_push",
        "install_package",
        "browser_open",
        "mcp_call_tool",
        "terminate_instances",
    }
    assert forbidden.isdisjoint(runtime.registered_tool_names)
    assert runtime.human_in_the_loop._allowed_tools == set(WORKSPACE_TOOL_NAMES)
    assert runtime.human_in_the_loop._enable_trust is False
    assert runtime.human_in_the_loop._ask is None


def test_workspace_profile_is_offline_mock_only(tmp_path: Path) -> None:
    sealed, service, runtime = _runtime(tmp_path)

    assert runtime.model_settings.provider_name is ModelProviderName.MOCK
    assert runtime.model_settings.external_network_allowed is False
    assert runtime.model_settings.aws_calls_allowed is False
    assert runtime.service.profile.network_allowed is False
    assert runtime.service.profile.mutation_allowed is False
    aws_settings = RuntimeSettings(
        mode=RuntimeMode.AWS,
        model_provider=ModelProviderName.BEDROCK,
        aws_integration_enabled=True,
        bedrock=BedrockSettings(),
    )
    with pytest.raises(ContractValidationError, match="portable mock"):
        create_workspace_investigation_agent(
            service,
            sealed.ref,
            runtime_settings=aws_settings,
        )


def test_existing_cloudops_five_tool_factory_surface_is_unchanged() -> None:
    assert CURRENT_TOOL_NAMES == (
        "inspect_instance",
        "read_utilization_metrics",
        "build_remediation_evidence",
        "stop_sandbox_instance",
        "verify_instance_state",
    )
    assert set(CURRENT_TOOL_NAMES).isdisjoint(WORKSPACE_TOOL_NAMES)


def test_workspace_prompt_keeps_model_subordinate_and_w1_read_only() -> None:
    normalized = WORKSPACE_SYSTEM_PROMPT.casefold()

    assert "model output is not execution authority" in normalized
    assert "untrusted data" in normalized
    assert "facts" in normalized
    assert "agent_inference" in normalized
    assert "alternative_hypothesis" in normalized
    assert "recommended_next_step" in normalized
    assert "phase w2" in normalized
    assert "w1 must not apply" in normalized


def test_agent_constructs_evidence_referencing_diagnosis_without_mutation(tmp_path: Path) -> None:
    final_text = """FACTS
- deployment.log records exit status 127 and File name too long.
- render.yaml contains an inline startup command; scripts/render_start.sh is a separate fixed executable.
AGENT_INFERENCE
- The inline startup contract is the primary quoting/dispatch hypothesis (high confidence), supported by deployment.log and render.yaml.
ALTERNATIVE_HYPOTHESIS
- Token bootstrap failure is less likely but should be checked against expected_runtime_contract.json and scripts/render_start.sh.
RECOMMENDED_NEXT_STEP
- Build an exact patch proposal in Phase W2; do not mutate or deploy in W1."""
    model = MockModelProvider(
        tool_plan=(
            MockToolCall("inspect_deployment_incident", {}),
            MockToolCall("list_workspace_artifacts", {}),
            MockToolCall("read_workspace_artifact", {"relative_path": "deployment.log"}),
            MockToolCall("read_workspace_artifact", {"relative_path": "render.yaml"}),
            MockToolCall(
                "read_workspace_artifact",
                {"relative_path": "scripts/render_start.sh"},
            ),
            MockToolCall("hash_workspace_artifact", {"relative_path": "render.yaml"}),
        ),
        final_text=final_text,
    )
    sealed, service, runtime = _runtime(tmp_path, model=model)
    before = inspect_fixture_tree(sealed.root, WORKSPACE_REMEDIATION_V1)

    result = runtime.agent("Diagnose this sealed deployment incident from evidence.")

    assert str(result).rstrip() == final_text
    assert model.calls == 7
    assert model.network_calls == 0
    assert tuple(event.operation for event in service.evidence_timeline) == (
        WorkspaceOperation.INSPECT,
        WorkspaceOperation.LIST,
        WorkspaceOperation.READ,
        WorkspaceOperation.READ,
        WorkspaceOperation.READ,
        WorkspaceOperation.HASH,
    )
    assert inspect_fixture_tree(sealed.root, WORKSPACE_REMEDIATION_V1) == before
    assert "deployment.log" in str(result)
    assert "render.yaml" in str(result)
    assert "scripts/render_start.sh" in str(result)
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in FIXTURE_ROOT.rglob("*")
        if path.is_file()
    )
    assert "primary quoting/dispatch hypothesis" not in fixture_text


def test_agent_trace_attributes_bind_profile_run_and_workspace(tmp_path: Path) -> None:
    sealed, _, runtime = _runtime(tmp_path)
    attributes = runtime.agent.trace_attributes

    assert attributes["aioa.agent_id"] == WORKSPACE_AGENT_ID
    assert attributes["aioa.profile_id"] == "WORKSPACE_REMEDIATION_V1"
    assert attributes["aioa.profile_version"] == "1"
    assert attributes["aioa.run_id"] == str(RUN_ID)
    assert attributes["aioa.workspace_id"] == str(sealed.ref.workspace_id)
    assert attributes["aioa.authority_gate"] == "AUTO"
    assert attributes["aioa.operation_class"] == "READ_ONLY"
    assert attributes["aioa.network_allowed"] == "false"
    assert attributes["aioa.mutation_allowed"] == "false"
