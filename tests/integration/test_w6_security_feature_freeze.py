"""W6 hostile-client, authority, dependency, source and supply-chain freeze proofs."""

from __future__ import annotations

import ast
import json
import subprocess
import tomllib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from pydantic import ValidationError
from tests.integration.test_workspace_judge_hero import (
    TOKEN,
    CountingPassingProfile,
    _application,
    _apply,
    _call,
    _decide,
    _request_approval,
    _start,
    _verify,
)

from aioa_cloudops_agent.agent import create_local_hitl_runtime
from aioa_cloudops_agent.config import LocalHitlSettings
from aioa_cloudops_agent.local_api import (
    WORKSPACE_HERO_SCENARIO_ID,
    LocalApiApplication,
    LocalApiTokenAuthorizer,
    WorkspaceHeroOrchestrator,
)
from aioa_cloudops_agent.local_api.contracts import LOCAL_API_BODY_MAX_BYTES
from aioa_cloudops_agent.local_api.judge_ui import JUDGE_UI_SCRIPT
from aioa_cloudops_agent.local_api.workspace_hero_contracts import (
    WorkspaceHeroDecisionRequest,
)

ROOT = Path(__file__).resolve().parents[2]
VALID_RUN_ID = "01890f6c-3311-7abc-8f4a-6e4f7f0b9b4a"
SECOND_TOKEN = "w6-second-operator-" + ("b" * 40)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    (
        (
            "POST",
            "/api/workspace-demo/runs",
            {"scenario_id": WORKSPACE_HERO_SCENARIO_ID},
        ),
        ("GET", f"/api/workspace-demo/runs/{VALID_RUN_ID}", None),
        ("POST", f"/api/workspace-demo/runs/{VALID_RUN_ID}/approval-request", {}),
        (
            "POST",
            f"/api/workspace-demo/runs/{VALID_RUN_ID}/decision",
            {"decision": "APPROVED", "request_fingerprint": "0" * 64},
        ),
        (
            "POST",
            f"/api/workspace-demo/runs/{VALID_RUN_ID}/resume",
            {"confirm_execution": True},
        ),
        (
            "POST",
            f"/api/workspace-demo/runs/{VALID_RUN_ID}/verify-or-reconcile",
            {},
        ),
    ),
)
def test_every_workspace_hero_route_rejects_unauthenticated_access(
    tmp_path: Path,
    method: str,
    path: str,
    body: object | None,
) -> None:
    application, runtime, profile = _application(tmp_path)

    status, payload, _, raw = _call(
        application,
        method,
        path,
        body=body,
        token=None,
        content_type=None if body is None else "application/json",
    )

    assert status == 401
    assert payload == {"error": "UNAUTHORIZED", "ok": False, "retryable": False}
    assert TOKEN not in raw
    assert profile.calls == 0
    assert runtime.cloud_provider.network_calls == 0


@pytest.mark.parametrize(
    ("path", "body"),
    (
        (
            "/api/workspace-demo/runs",
            {"scenario_id": WORKSPACE_HERO_SCENARIO_ID},
        ),
        (f"/api/workspace-demo/runs/{VALID_RUN_ID}/approval-request", {}),
        (
            f"/api/workspace-demo/runs/{VALID_RUN_ID}/decision",
            {"decision": "APPROVED", "request_fingerprint": "0" * 64},
        ),
        (
            f"/api/workspace-demo/runs/{VALID_RUN_ID}/resume",
            {"confirm_execution": True},
        ),
        (f"/api/workspace-demo/runs/{VALID_RUN_ID}/verify-or-reconcile", {}),
    ),
)
def test_cookie_authenticated_mutations_require_exact_browser_intent(
    tmp_path: Path,
    path: str,
    body: object,
) -> None:
    application, _, _ = _application(tmp_path)
    session_status, _, session_headers, _ = _call(
        application,
        "POST",
        "/api/session",
        body={},
    )
    cookie = session_headers["set-cookie"].split(";", 1)[0]

    missing, _, _, _ = _call(
        application,
        "POST",
        path,
        body=body,
        token=None,
        cookie=cookie,
        intent=False,
    )
    wrong = application.handle(
        {
            "method": "POST",
            "path": path,
            "headers": {
                "Content-Type": "application/json",
                "Cookie": cookie,
                "X-AIOA-Intent": "hostile-cross-origin",
            },
            "body": json.dumps(body),
            "query": "",
        }
    )

    assert session_status == 200
    assert missing == 401
    assert wrong["statusCode"] == 401


@pytest.mark.parametrize(
    ("method", "path"),
    (
        ("GET", "/api/workspace-demo/runs"),
        ("POST", f"/api/workspace-demo/runs/{VALID_RUN_ID}"),
        ("GET", f"/api/workspace-demo/runs/{VALID_RUN_ID}/approval-request"),
        ("GET", f"/api/workspace-demo/runs/{VALID_RUN_ID}/decision"),
        ("GET", f"/api/workspace-demo/runs/{VALID_RUN_ID}/resume"),
        ("GET", f"/api/workspace-demo/runs/{VALID_RUN_ID}/verify-or-reconcile"),
    ),
)
def test_workspace_method_confusion_fails_before_workflow_dispatch(
    tmp_path: Path,
    method: str,
    path: str,
) -> None:
    application, _, profile = _application(tmp_path)

    status, payload, _, _ = _call(
        application,
        method,
        path,
        content_type=None,
    )

    assert status == 405
    assert payload == {
        "error": "METHOD_NOT_ALLOWED",
        "ok": False,
        "retryable": False,
    }
    assert profile.calls == 0


@pytest.mark.parametrize(
    "malformed",
    (
        "{",
        "[]",
        '{"scenario_id":NaN}',
        '{"scenario_id":"FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1",'
        '"scenario_id":"FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1"}',
        '{"scenario_id":"FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1","target":"/tmp/x"}',
        '{"scenario_id":{"unexpected":"shape"}}',
    ),
)
def test_strict_json_and_unknown_field_attacks_are_rejected_before_start(
    tmp_path: Path,
    malformed: str,
) -> None:
    application, runtime, profile = _application(tmp_path)

    status, payload, _, raw = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body=malformed,
    )

    assert status == 400
    assert payload == {"error": "BAD_REQUEST", "ok": False, "retryable": False}
    assert "/tmp/x" not in raw
    assert profile.calls == 0
    assert runtime.cloud_provider.network_calls == 0


def test_content_type_body_shape_header_collision_and_size_bounds_fail_closed(
    tmp_path: Path,
) -> None:
    application, _, profile = _application(tmp_path)
    path = "/api/workspace-demo/runs"
    valid = json.dumps({"scenario_id": WORKSPACE_HERO_SCENARIO_ID})

    wrong_type, _, _, _ = _call(
        application,
        "POST",
        path,
        body=valid,
        content_type="text/plain",
    )
    oversized, _, _, _ = _call(
        application,
        "POST",
        path,
        body="x" * (LOCAL_API_BODY_MAX_BYTES + 1),
    )
    non_string = application.handle(
        {
            "method": "POST",
            "path": path,
            "headers": {"Content-Type": "application/json"},
            "body": {"scenario_id": WORKSPACE_HERO_SCENARIO_ID},
            "query": "",
        }
    )
    duplicate_header = application.handle(
        {
            "method": "POST",
            "path": path,
            "headers": {
                "Authorization": f"Bearer {TOKEN}",
                "authorization": f"Bearer {TOKEN}",
                "Content-Type": "application/json",
            },
            "body": valid,
            "query": "",
        }
    )

    assert wrong_type == 415
    assert oversized == 413
    assert non_string["statusCode"] == 400
    assert duplicate_header["statusCode"] == 400
    assert profile.calls == 0


@pytest.mark.parametrize(
    "smuggled_field",
    (
        "target",
        "path",
        "content",
        "diff",
        "command",
        "url",
        "environment",
        "verifier_profile",
        "proposal_id",
        "patch_digest",
        "evidence_digest",
        "workspace_id",
        "run_id",
        "approval_state",
    ),
)
def test_decision_contract_rejects_every_authority_smuggling_field(
    smuggled_field: str,
) -> None:
    payload: dict[str, object] = {
        "decision": "APPROVED",
        "request_fingerprint": "1" * 64,
        smuggled_field: "hostile-client-value",
    }

    with pytest.raises(ValidationError):
        WorkspaceHeroDecisionRequest.model_validate(payload)


def test_api_authority_smuggling_cannot_change_durable_request_or_workspace(
    tmp_path: Path,
) -> None:
    application, _, profile = _application(tmp_path)
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    card = requested["approval_card"]
    assert isinstance(card, dict)
    baseline_fingerprint = card["request_fingerprint"]

    for field in (
        "target",
        "path",
        "content",
        "diff",
        "command",
        "url",
        "environment",
        "verifier_profile",
        "proposal_id",
        "patch_digest",
        "evidence_digest",
        "workspace_id",
        "run_id",
        "approval_state",
    ):
        status, _, _, _ = _call(
            application,
            "POST",
            f"/api/workspace-demo/runs/{started['run_id']}/decision",
            body={
                "decision": "APPROVED",
                "request_fingerprint": baseline_fingerprint,
                field: "hostile-client-value",
            },
        )
        assert status == 400

    status, current, _, _ = _call(
        application,
        "GET",
        f"/api/workspace-demo/runs/{started['run_id']}",
        content_type=None,
    )
    view = current["result"]
    assert status == 200
    assert view["state"] == "AWAITING_APPROVAL"
    assert view["workspace_mutation_count"] == 0
    assert view["approval_card"]["request_fingerprint"] == baseline_fingerprint
    assert profile.calls == 0


def test_different_authenticated_operator_cannot_consume_an_existing_request(
    tmp_path: Path,
) -> None:
    runtime = create_local_hitl_runtime(
        LocalHitlSettings(
            state_path=tmp_path / "shared-truth.json",
            inventory_path=tmp_path / "shared-inventory.json",
        )
    )
    first_authorizer = LocalApiTokenAuthorizer(TOKEN)
    profile = CountingPassingProfile()
    first_hero = WorkspaceHeroOrchestrator(
        tmp_path / "shared-hero",
        runtime.runtime_settings,
        nonce_deriver=first_authorizer.derive_workspace_decision_nonce,
        profile_factory=lambda: profile,
    )
    first = LocalApiApplication(runtime, first_authorizer, workspace_hero=first_hero)
    second_authorizer = LocalApiTokenAuthorizer(SECOND_TOKEN)
    restarted_hero = WorkspaceHeroOrchestrator(
        tmp_path / "shared-hero",
        runtime.runtime_settings,
        nonce_deriver=second_authorizer.derive_workspace_decision_nonce,
        profile_factory=lambda: profile,
    )
    second = LocalApiApplication(
        runtime,
        second_authorizer,
        workspace_hero=restarted_hero,
    )
    started = _start(first)
    requested = _request_approval(first, started["run_id"])
    card = requested["approval_card"]
    assert isinstance(card, dict)

    denied, payload, _, _ = _call(
        second,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/decision",
        body={
            "decision": "APPROVED",
            "request_fingerprint": card["request_fingerprint"],
        },
        token=SECOND_TOKEN,
    )
    _, current, _, _ = _call(
        first,
        "GET",
        f"/api/workspace-demo/runs/{started['run_id']}",
        content_type=None,
    )

    assert denied == 403
    assert payload["error"] == "POLICY_DENIED"
    assert current["result"]["state"] == "AWAITING_APPROVAL"
    assert current["result"]["workspace_mutation_count"] == 0
    assert profile.calls == 0


def test_denial_is_terminal_and_cannot_be_reused_as_approval(
    tmp_path: Path,
) -> None:
    application, _, profile = _application(tmp_path)
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    denied = _decide(application, requested, "DENIED")
    card = requested["approval_card"]
    assert isinstance(card, dict)

    reuse, _, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/decision",
        body={
            "decision": "APPROVED",
            "request_fingerprint": card["request_fingerprint"],
        },
    )
    resume, _, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/resume",
        body={"confirm_execution": True},
    )

    assert denied["state"] == "DENIED_BY_HUMAN"
    assert reuse in {403, 409}
    assert resume == 403
    assert denied["workspace_mutation_count"] == 0
    assert profile.calls == 0


def test_workspace_drift_after_approval_blocks_the_exact_effect(
    tmp_path: Path,
) -> None:
    application, _, profile = _application(tmp_path)
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    approved = _decide(application, requested, "APPROVED")
    workspace_parent = (
        tmp_path
        / "workspace-hero"
        / "runs"
        / str(started["run_id"])
        / "workspaces"
    )
    target = next(workspace_parent.glob("*/render.yaml"))
    target.chmod(0o600)
    target.write_bytes(target.read_bytes() + b"\n# hostile post-approval drift\n")

    effect, payload, _, raw = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/resume",
        body={"confirm_execution": True},
    )
    _, current, _, _ = _call(
        application,
        "GET",
        f"/api/workspace-demo/runs/{started['run_id']}",
        content_type=None,
    )

    assert approved["state"] == "APPROVED"
    assert effect in {409, 422}
    assert payload["error"] in {"CONFLICT", "WORKFLOW_FAILED"}
    assert current["result"]["workspace_mutation_count"] == 0
    assert current["result"]["executor_receipt_present"] is False
    assert str(target) not in raw
    assert profile.calls == 0


def test_two_same_session_tabs_can_create_only_one_semantic_effect(
    tmp_path: Path,
) -> None:
    application, runtime, profile = _application(tmp_path)
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    approved = _decide(application, requested, "APPROVED")

    def resume_from_tab(_tab: int):
        return _call(
            application,
            "POST",
            f"/api/workspace-demo/runs/{started['run_id']}/resume",
            body={"confirm_execution": True},
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(resume_from_tab, (1, 2)))

    verified = _verify(application, started["run_id"])
    replayed = _apply(application, started["run_id"])

    assert approved["state"] == "APPROVED"
    assert all(result[0] == 200 for result in results)
    assert verified["workspace_mutation_count"] == 1
    assert replayed["workspace_mutation_count"] == 1
    assert replayed["replay"]["additional_mutation_delta"] == 0
    assert replayed["replay"]["additional_profile_executions"] == 0
    assert profile.calls == 1
    assert runtime.cloud_provider.network_calls == 0


def test_concurrent_conflicting_human_decisions_have_one_durable_winner(
    tmp_path: Path,
) -> None:
    application, _, profile = _application(tmp_path)
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    card = requested["approval_card"]
    assert isinstance(card, dict)

    def decide_from_tab(decision: str):
        return _call(
            application,
            "POST",
            f"/api/workspace-demo/runs/{started['run_id']}/decision",
            body={
                "decision": decision,
                "request_fingerprint": card["request_fingerprint"],
            },
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = tuple(executor.map(decide_from_tab, ("APPROVED", "DENIED")))

    statuses = [result[0] for result in results]
    _, current, _, _ = _call(
        application,
        "GET",
        f"/api/workspace-demo/runs/{started['run_id']}",
        content_type=None,
    )
    view = current["result"]

    assert statuses.count(200) == 1
    assert set(statuses).issubset({200, 403, 409})
    assert view["state"] in {"APPROVED", "DENIED_BY_HUMAN"}
    assert view["workspace_mutation_count"] == 0
    assert profile.calls == 0


def test_missing_verifier_dependency_cannot_leak_or_become_success(
    tmp_path: Path,
) -> None:
    runtime = create_local_hitl_runtime(
        LocalHitlSettings(
            state_path=tmp_path / "dependency-truth.json",
            inventory_path=tmp_path / "dependency-inventory.json",
        )
    )
    authorizer = LocalApiTokenAuthorizer(TOKEN)
    sensitive_failure = "/home/private/operator-token-do-not-emit"

    def unavailable_profile() -> object:
        raise RuntimeError(sensitive_failure)

    application = LocalApiApplication(
        runtime,
        authorizer,
        workspace_hero=WorkspaceHeroOrchestrator(
            tmp_path / "dependency-hero",
            runtime.runtime_settings,
            nonce_deriver=authorizer.derive_workspace_decision_nonce,
            profile_factory=unavailable_profile,
        ),
    )
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    _decide(application, requested, "APPROVED")
    applied = _apply(application, started["run_id"])

    failed, payload, _, raw = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/verify-or-reconcile",
        body={},
    )
    _, current, _, _ = _call(
        application,
        "GET",
        f"/api/workspace-demo/runs/{started['run_id']}",
        content_type=None,
    )

    assert applied["state"] == "PATCH_APPLIED_UNVERIFIED"
    assert failed == 500
    assert payload == {"error": "INTERNAL_ERROR", "ok": False, "retryable": False}
    assert sensitive_failure not in raw
    assert TOKEN not in raw
    assert current["result"]["state"] == "PATCH_APPLIED_UNVERIFIED"
    assert current["result"]["success_with_evidence"] is False
    assert current["result"]["verification_receipt_present"] is False


def test_corrupt_durable_authority_envelope_fails_closed_without_private_detail(
    tmp_path: Path,
) -> None:
    application, _, _ = _application(tmp_path)
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    _decide(application, requested, "APPROVED")
    _apply(application, started["run_id"])
    authority_path = (
        tmp_path
        / "workspace-hero"
        / "runs"
        / str(started["run_id"])
        / "authority.json"
    )
    envelope = json.loads(authority_path.read_text(encoding="utf-8"))
    envelope["payload_sha256"] = "0" * 64
    authority_path.write_text(json.dumps(envelope), encoding="utf-8")

    status, payload, _, raw = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/verify-or-reconcile",
        body={},
    )

    assert status == 500
    assert payload == {"error": "INTERNAL_ERROR", "ok": False, "retryable": False}
    assert str(authority_path) not in raw
    assert TOKEN not in raw


def test_judge_ui_uses_only_non_executable_dynamic_text_sinks() -> None:
    for dangerous in (
        ".innerHTML",
        ".outerHTML",
        "insertAdjacentHTML",
        "document.write",
        "localStorage",
        "sessionStorage",
        "eval(",
        "new Function",
    ):
        assert dangerous not in JUDGE_UI_SCRIPT
    assert JUDGE_UI_SCRIPT.count(".textContent") >= 20
    assert "Content-Security-Policy" not in JUDGE_UI_SCRIPT


def test_workspace_and_hero_source_keep_forbidden_capabilities_out() -> None:
    paths = (
        *sorted((ROOT / "src/aioa_cloudops_agent/workspace").glob("*.py")),
        ROOT / "src/aioa_cloudops_agent/local_api/application.py",
        ROOT / "src/aioa_cloudops_agent/local_api/workspace_hero.py",
        ROOT / "src/aioa_cloudops_agent/local_api/workspace_hero_contracts.py",
        ROOT / "src/aioa_cloudops_agent/local_api/workspace_hero_fixture.py",
    )
    forbidden_import_roots = {
        "httpx",
        "importlib",
        "requests",
        "shlex",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_calls = {"eval", "exec", "compile"}
    findings: list[str] = []

    for path in paths:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split(".", 1)[0] in forbidden_import_roots:
                        findings.append(f"{path.name}:import:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                if node.module.split(".", 1)[0] in forbidden_import_roots:
                    findings.append(f"{path.name}:from:{node.module}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in forbidden_calls:
                    findings.append(f"{path.name}:call:{node.func.id}")
                if (
                    isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name)
                    and node.func.value.id == "os"
                    and node.func.attr in {"popen", "system"}
                ):
                    findings.append(f"{path.name}:call:os.{node.func.attr}")

    assert findings == []


def test_runtime_dependencies_and_lock_inputs_are_exactly_pinned() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    runtime_dependencies = project["project"]["dependencies"]
    assert runtime_dependencies
    assert all("==" in dependency for dependency in runtime_dependencies)
    assert not any("pytest" in dependency or "ruff" in dependency for dependency in runtime_dependencies)

    for relative in ("requirements/build.lock", "requirements/portable.lock"):
        entries = [
            line
            for line in (ROOT / relative).read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        ]
        assert entries
        assert all("==" in entry and "--hash=sha256:" in entry for entry in entries)


def test_container_context_and_tracked_inventory_exclude_private_runtime_state() -> None:
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8").splitlines()
    assert dockerignore[:2] == [
        "# Deny by default. The runtime build receives only the explicitly re-included files.",
        "**",
    ]
    assert not any(
        item in line
        for line in dockerignore
        for item in (
            ".git",
            ".local",
            ".aioa-private",
            ".pytest_cache",
            "tests/",
            "docs/audits/",
            "browser",
            "cookies",
        )
    )
    result = subprocess.run(
        ("git", "ls-files", "-z"),
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
        timeout=20,
    )
    tracked = result.stdout.decode("utf-8").split("\0")
    forbidden_parts = {
        ".aioa-private",
        ".local",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
    }
    assert not any(forbidden_parts.intersection(Path(path).parts) for path in tracked if path)
    assert not any(
        Path(path).suffix.casefold() in {".key", ".p12", ".pem", ".pfx"}
        for path in tracked
        if path
    )
