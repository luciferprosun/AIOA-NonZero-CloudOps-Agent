from __future__ import annotations

import copy
from datetime import UTC, datetime
from pathlib import Path

import pytest
from scripts.day15 import build_lambda_artifact
from scripts.day15 import run_day15_gate as gate
from scripts.day15.validate_template import (
    DEFAULT_TEMPLATE,
    lambda_configuration_sha256,
    load_template,
)


def _context(tmp_path: Path, template: dict[str, object]) -> gate.GateContext:
    return gate.GateContext(
        template=template,
        template_path=DEFAULT_TEMPLATE,
        rendered_template=None,
        rendered_template_path=None,
        template_has_sam=True,
        artifact=tmp_path / "missing.zip",
        lock=gate.DEFAULT_LOCK,
        manifest=tmp_path / "missing.manifest.json",
        scan_report=tmp_path / "missing.scan.json",
        toolchain=gate.DEFAULT_TOOLCHAIN,
        external_receipt=tmp_path / "missing.external.json",
        external_attestation_key=None,
        region="eu-central-1",
        judge_token_not_after="2026-08-25T00:00:00Z",
        lambda_configuration_sha256=lambda_configuration_sha256(template),
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    )


def test_deployment_decision_requires_all_ten_gates_to_pass() -> None:
    passing = tuple(gate._result(definition, "PASS") for definition in gate.GATES)
    assert gate._payload(passing, mode="full")["ready_for_deployment"] is True

    for status in ("FAIL", "PARTIAL", "BLOCKED"):
        changed = (gate._result(gate.GATES[0], status, (f"TEST_{status}",)), *passing[1:])
        decision = gate._payload(changed, mode="full")
        assert decision["status"] == status
        assert decision["ready_for_deployment"] is False

    assert gate._payload(passing, mode="validate-only")["ready_for_deployment"] is False


def test_local_gate_never_performs_aws_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_subprocess(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("the local deployment gate must not start AWS or shell commands")

    monkeypatch.setattr(build_lambda_artifact.subprocess, "run", forbidden_subprocess)
    template = load_template(DEFAULT_TEMPLATE)
    payload = gate.run_gate(
        artifact=tmp_path / "missing.zip",
        manifest=tmp_path / "missing.manifest.json",
        scan_report=tmp_path / "missing.scan.json",
        external_receipt=tmp_path / "missing.external.json",
        region="eu-central-1",
        judge_token_not_after="2026-08-25T00:00:00Z",
        lambda_configuration_sha256=lambda_configuration_sha256(template),
        clock=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
    )

    assert payload["aws_calls_performed"] is False
    assert payload["deployment_performed"] is False
    assert payload["ready_for_deployment"] is False


def test_g01_current_handlers_routes_resume_and_server_budgets_are_frozen(
    tmp_path: Path,
) -> None:
    result = gate._gate_runtime(_context(tmp_path, load_template(DEFAULT_TEMPLATE)))

    assert result.status == "PASS"
    assert result.reasons == ()


def test_g01_rejects_declared_handler_that_does_not_exist(tmp_path: Path) -> None:
    template = copy.deepcopy(load_template(DEFAULT_TEMPLATE))
    functions = gate._functions(template)
    orchestrator = next(
        resource for name, resource in functions.items() if gate._is_orchestrator(name, resource)
    )
    orchestrator["Properties"]["Handler"] = (
        "aioa_cloudops_agent.judge.lambda_handler.nonexistent_handler"
    )

    result = gate._gate_runtime(_context(tmp_path, template))

    assert result.status == "FAIL"
    assert "LAMBDA_HANDLER_CONTRACT_INVALID" in result.reasons


@pytest.mark.parametrize(
    ("source_attribute", "reason"),
    (
        ("JUDGE_ROUTER_SOURCES", "JUDGE_ROUTE_METHOD_CONTRACT_INVALID"),
        ("JUDGE_CONFIG_SOURCE", "SERVER_OWNED_BUDGET_CONTRACT_INVALID"),
        ("JUDGE_RUNTIME_SOURCE", "FRESH_REQUEST_RUNTIME_CONTRACT_INVALID"),
        ("APPROVAL_RESUME_SOURCE", "COLD_START_RESUME_CONTRACT_INVALID"),
        ("RUNTIME_PROOF_CONTRACTS", "RUNTIME_PROOF_CONTRACT_MISSING"),
    ),
)
def test_g01_rejects_missing_authority_or_proof_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_attribute: str,
    reason: str,
) -> None:
    missing = tmp_path / "missing.py"
    if source_attribute == "JUDGE_ROUTER_SOURCES":
        monkeypatch.setattr(
            gate,
            source_attribute,
            (missing, gate.JUDGE_ROUTER_SOURCES[1]),
        )
    elif source_attribute == "RUNTIME_PROOF_CONTRACTS":
        monkeypatch.setattr(gate, source_attribute, ((missing, ("test_missing",)),))
    else:
        monkeypatch.setattr(gate, source_attribute, missing)

    result = gate._gate_runtime(_context(tmp_path, load_template(DEFAULT_TEMPLATE)))

    assert result.status == "FAIL"
    assert reason in result.reasons


@pytest.mark.parametrize(
    ("source_attribute", "original", "changed", "reason"),
    (
        (
            "JUDGE_ROUTER_SOURCES",
            'request.path == "/ready"',
            'request.path == "/unreviewed"',
            "JUDGE_ROUTE_METHOD_CONTRACT_INVALID",
        ),
        (
            "JUDGE_CONFIG_SOURCE",
            "JUDGE_MAX_TURNS: Final = 8",
            "JUDGE_MAX_TURNS: Final = 9",
            "SERVER_OWNED_BUDGET_CONTRACT_INVALID",
        ),
        (
            "JUDGE_RUNTIME_SOURCE",
            "self._agent_factory(",
            "self._unreviewed_factory(",
            "FRESH_REQUEST_RUNTIME_CONTRACT_INVALID",
        ),
        (
            "APPROVAL_RESUME_SOURCE",
            "class AuthenticatedApprovalResumeService:",
            "class UnreviewedApprovalResumeService:",
            "COLD_START_RESUME_CONTRACT_INVALID",
        ),
    ),
)
def test_g01_rejects_semantic_runtime_contract_bypass(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source_attribute: str,
    original: str,
    changed: str,
    reason: str,
) -> None:
    configured = getattr(gate, source_attribute)
    source = configured[0] if source_attribute == "JUDGE_ROUTER_SOURCES" else configured
    assert isinstance(source, Path)
    text = source.read_text(encoding="utf-8")
    assert original in text
    changed_source = tmp_path / source.name
    changed_source.write_text(text.replace(original, changed, 1), encoding="utf-8")
    if source_attribute == "JUDGE_ROUTER_SOURCES":
        monkeypatch.setattr(gate, source_attribute, (changed_source, configured[1]))
    else:
        monkeypatch.setattr(gate, source_attribute, changed_source)

    result = gate._gate_runtime(_context(tmp_path, load_template(DEFAULT_TEMPLATE)))

    assert result.status == "FAIL"
    assert reason in result.reasons


def test_g06_requires_explicit_cfn_rule_even_when_region_parameter_is_allowlisted(
    tmp_path: Path,
) -> None:
    template = copy.deepcopy(load_template(DEFAULT_TEMPLATE))
    assert template["Parameters"]["DeploymentRegion"]["AllowedValues"] == ["eu-central-1"]
    template.pop("Rules")
    template["Conditions"]["DecoyRegionCondition"] = {
        "Fn::Equals": [{"Ref": "AWS::Region"}, "eu-central-1"]
    }

    result = gate._gate_region(_context(tmp_path, template))

    assert result.status == "FAIL"
    assert result.reasons == ("TEMPLATE_REGION_GUARD_MISSING",)


@pytest.mark.parametrize(
    "logical_id",
    (
        "OrchestratorFunctionUrl",
        "PublicFunctionUrlInvokePermission",
        "PublicFunctionInvokeViaUrlPermission",
    ),
)
def test_g09_requires_ingress_condition_on_url_and_both_public_permissions(
    tmp_path: Path,
    logical_id: str,
) -> None:
    template = copy.deepcopy(load_template(DEFAULT_TEMPLATE))
    template["Resources"][logical_id].pop("Condition")

    result = gate._gate_public_surface(_context(tmp_path, template))

    assert result.status == "FAIL"
    assert any("CONDITION" in reason for reason in result.reasons)


def test_g09_requires_exact_fail_closed_public_ingress_condition_binding(
    tmp_path: Path,
) -> None:
    template = copy.deepcopy(load_template(DEFAULT_TEMPLATE))
    template["Conditions"]["PublicIngressEnabledCondition"] = {
        "Fn::Equals": [{"Ref": "PublicIngressEnabled"}, "false"]
    }

    result = gate._gate_public_surface(_context(tmp_path, template))

    assert result.status == "FAIL"
    assert result.reasons == ("PUBLIC_INGRESS_CONDITION_BINDING_INVALID",)
