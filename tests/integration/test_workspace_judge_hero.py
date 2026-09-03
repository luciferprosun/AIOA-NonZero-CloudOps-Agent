"""W5 API and end-to-end proof for the fixed judge-facing workspace hero."""

from __future__ import annotations

import json
import stat
from pathlib import Path

import pytest

from aioa_cloudops_agent.agent import create_local_hitl_runtime
from aioa_cloudops_agent.config import LocalHitlSettings
from aioa_cloudops_agent.local_api import (
    WORKSPACE_HERO_SCENARIO_ID,
    LocalApiApplication,
    LocalApiTokenAuthorizer,
    WorkspaceHeroOrchestrator,
)
from aioa_cloudops_agent.local_api.judge_ui import (
    JUDGE_UI_BODY,
    JUDGE_UI_SCRIPT,
    JUDGE_UI_STYLE,
)
from aioa_cloudops_agent.local_api.workspace_hero_contracts import (
    WORKSPACE_HERO_RESPONSE_MAX_BYTES,
)
from aioa_cloudops_agent.local_api.workspace_hero_profile import (
    WorkspaceHeroRenderStartProfile,
)
from aioa_cloudops_agent.workspace import TrustedRenderStartProfileResult

TOKEN = "w5-judge-test-" + ("t" * 40)
WRONG_TOKEN = "w5-judge-wrong-" + ("w" * 40)


class CountingPassingProfile:
    def __init__(self) -> None:
        self.calls = 0

    def run(self) -> TrustedRenderStartProfileResult:
        self.calls += 1
        return TrustedRenderStartProfileResult()


def _application(
    tmp_path: Path,
    *,
    profile: CountingPassingProfile | None = None,
) -> tuple[LocalApiApplication, object, CountingPassingProfile]:
    runtime = create_local_hitl_runtime(
        LocalHitlSettings(
            state_path=tmp_path / "cloudops-truth.json",
            inventory_path=tmp_path / "cloudops-inventory.json",
        )
    )
    authorizer = LocalApiTokenAuthorizer(TOKEN)
    selected_profile = profile or CountingPassingProfile()
    hero = WorkspaceHeroOrchestrator(
        tmp_path / "workspace-hero",
        runtime.runtime_settings,
        nonce_deriver=authorizer.derive_workspace_decision_nonce,
        profile_factory=lambda: selected_profile,
    )
    return (
        LocalApiApplication(runtime, authorizer, workspace_hero=hero),
        runtime,
        selected_profile,
    )


def _call(
    application: LocalApiApplication,
    method: str,
    path: str,
    *,
    body: object | str | None = None,
    token: str | None = TOKEN,
    cookie: str | None = None,
    intent: bool = True,
    content_type: str | None = "application/json",
    query: str = "",
) -> tuple[int, dict[str, object], dict[str, str], str]:
    headers: dict[str, str] = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    if cookie is not None:
        headers["Cookie"] = cookie
    rendered = None
    if body is not None:
        if content_type is not None:
            headers["Content-Type"] = content_type
        if intent:
            headers["X-AIOA-Intent"] = "judge-console-v1"
        rendered = body if isinstance(body, str) else json.dumps(body)
    response = application.handle(
        {
            "method": method,
            "path": path,
            "headers": headers,
            "body": rendered,
            "query": query,
        }
    )
    raw_body = str(response["body"])
    return (
        int(response["statusCode"]),
        json.loads(raw_body),
        response["headers"],  # type: ignore[return-value]
        raw_body,
    )


def _start(application: LocalApiApplication) -> dict[str, object]:
    status, payload, _, _ = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body={"scenario_id": WORKSPACE_HERO_SCENARIO_ID},
    )
    assert status == 201, payload
    return payload["result"]  # type: ignore[return-value]


def _request_approval(
    application: LocalApiApplication,
    run_id: object,
) -> dict[str, object]:
    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{run_id}/approval-request",
        body={},
    )
    assert status == 200, payload
    return payload["result"]  # type: ignore[return-value]


def _decide(
    application: LocalApiApplication,
    view: dict[str, object],
    decision: str,
) -> dict[str, object]:
    run_id = view["run_id"]
    card = view["approval_card"]
    assert isinstance(card, dict)
    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{run_id}/decision",
        body={
            "decision": decision,
            "request_fingerprint": card["request_fingerprint"],
        },
    )
    assert status == 200, payload
    return payload["result"]  # type: ignore[return-value]


def _approved(application: LocalApiApplication) -> dict[str, object]:
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    return _decide(application, requested, "APPROVED")


def _apply(application: LocalApiApplication, run_id: object) -> dict[str, object]:
    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{run_id}/resume",
        body={"confirm_execution": True},
    )
    assert status == 200, payload
    return payload["result"]  # type: ignore[return-value]


def _verify(application: LocalApiApplication, run_id: object) -> dict[str, object]:
    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{run_id}/verify-or-reconcile",
        body={},
    )
    assert status == 200, payload
    return payload["result"]  # type: ignore[return-value]


def test_workspace_hero_approve_apply_verify_and_replay(tmp_path: Path) -> None:
    application, runtime, profile = _application(tmp_path)
    started = _start(application)
    run_id = started["run_id"]
    requested = _request_approval(application, run_id)
    decided = _decide(application, requested, "APPROVED")
    applied = _apply(application, run_id)
    verified = _verify(application, run_id)
    replayed = _apply(application, run_id)
    refresh_status, refreshed, _, _ = _call(
        application,
        "GET",
        f"/api/workspace-demo/runs/{run_id}",
        content_type=None,
    )

    assert refresh_status == 200
    assert started["state"] == "PATCH_PROPOSED"
    assert requested["state"] == "AWAITING_APPROVAL"
    assert decided["state"] == "APPROVED"
    assert applied["state"] == "PATCH_APPLIED_UNVERIFIED"
    assert applied["success_with_evidence"] is False
    assert "verification" not in applied
    assert verified["state"] == "SUCCESS_WITH_EVIDENCE"
    assert replayed["replay"]["status"] == "REPLAY_REJECTED_RECONCILED"  # type: ignore[index]
    assert replayed["workspace_mutation_count"] == 1
    assert replayed["replay"]["additional_mutation_delta"] == 0  # type: ignore[index]
    assert replayed["replay"]["additional_profile_executions"] == 0  # type: ignore[index]
    assert refreshed["result"] == replayed
    assert profile.calls == 1
    assert runtime.cloud_provider.network_calls == 0
    assert runtime.model_provider.network_calls == 0


def test_workspace_hero_denial_is_a_zero_effect_safe_stop(tmp_path: Path) -> None:
    application, runtime, profile = _application(tmp_path)
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    denied = _decide(application, requested, "DENIED")

    apply_status, apply_payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/resume",
        body={"confirm_execution": True},
    )
    verify_status, _, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/verify-or-reconcile",
        body={},
    )

    assert denied["state"] == "DENIED_BY_HUMAN"
    assert denied["workspace_mutation_count"] == 0
    assert denied["executor_receipt_present"] is False
    assert denied["verification_receipt_present"] is False
    safe_stops = {
        item["stage"]
        for item in denied["timeline"]  # type: ignore[union-attr]
        if item["status"] == "SAFE_STOP"
    }
    assert safe_stops == {"PATCH_EFFECT", "VERIFICATION", "RECEIPT"}
    assert apply_status == verify_status == 403
    assert apply_payload["failure_code"] == "WORKSPACE_HERO_DENIED_TERMINAL"
    assert profile.calls == 0
    assert runtime.cloud_provider.network_calls == 0


def test_hero_projection_is_exact_bounded_and_sanitized(tmp_path: Path) -> None:
    application, _, _ = _application(tmp_path)
    status, payload, _, raw = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body={"scenario_id": WORKSPACE_HERO_SCENARIO_ID},
    )
    view = payload["result"]
    card = view["approval_card"]  # type: ignore[index]

    assert status == 201
    assert len(raw.encode("utf-8")) < WORKSPACE_HERO_RESPONSE_MAX_BYTES + 512
    assert view["scenario_id"] == WORKSPACE_HERO_SCENARIO_ID  # type: ignore[index]
    assert card["target"] == "render.yaml"  # type: ignore[index]
    assert card["field_path"] == "services[0].dockerCommand"  # type: ignore[index]
    assert card["risk"] == "PLAN_AND_CONFIRM"  # type: ignore[index]
    assert card["evidence"] == [  # type: ignore[index]
        "deployment.log",
        "render.yaml",
        "scripts/render_start.sh",
        "expected_runtime_contract.json",
    ]
    assert "dockerCommand: /usr/local/bin/aioa-render-start" in view["patch_diff"]  # type: ignore[operator,index]
    assert len(view["timeline"]) == 10  # type: ignore[arg-type,index]
    assert TOKEN not in raw
    assert "decision_nonce" not in raw
    assert "actor_session_id" not in raw
    assert str(tmp_path) not in raw
    assert "workspace_root_name" not in raw


@pytest.mark.parametrize(
    "injected",
    [
        {"path": "render.yaml"},
        {"content": "owned"},
        {"diff": "@@ attacker"},
        {"command": "sh -c whoami"},
        {"url": "https://attacker.invalid"},
        {"scenario_id": WORKSPACE_HERO_SCENARIO_ID, "workspace": "/tmp/elsewhere"},
    ],
)
def test_start_contract_rejects_caller_controlled_capability_input(
    tmp_path: Path,
    injected: dict[str, object],
) -> None:
    application, _, _ = _application(tmp_path)
    body = {"scenario_id": WORKSPACE_HERO_SCENARIO_ID, **injected}
    status, payload, _, _ = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body=body,
    )

    assert status == 400
    assert payload["error"] == "BAD_REQUEST"


@pytest.mark.parametrize(
    "extra",
    [
        {"path": "render.yaml"},
        {"patch": "attacker-selected"},
        {"decision_nonce": "browser-controlled"},
        {"command": "apply"},
    ],
)
def test_decision_contract_accepts_only_decision_and_current_fingerprint(
    tmp_path: Path,
    extra: dict[str, str],
) -> None:
    application, _, _ = _application(tmp_path)
    started = _start(application)
    requested = _request_approval(application, started["run_id"])
    card = requested["approval_card"]
    assert isinstance(card, dict)

    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/decision",
        body={
            "decision": "APPROVED",
            "request_fingerprint": card["request_fingerprint"],
            **extra,
        },
    )

    assert status == 400
    assert payload["error"] == "BAD_REQUEST"


def test_authentication_precedes_hero_payload_parsing(tmp_path: Path) -> None:
    application, _, _ = _application(tmp_path)
    missing, missing_payload, _, _ = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body="{not-json",
        token=None,
    )
    wrong, wrong_payload, _, _ = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body={"scenario_id": WORKSPACE_HERO_SCENARIO_ID},
        token=WRONG_TOKEN,
    )

    assert missing == wrong == 401
    assert missing_payload["error"] == wrong_payload["error"] == "UNAUTHORIZED"


def test_cookie_mutation_requires_explicit_browser_intent(tmp_path: Path) -> None:
    application, _, _ = _application(tmp_path)
    session_status, _, headers, _ = _call(
        application,
        "POST",
        "/api/session",
        body={},
    )
    cookie = headers["set-cookie"].split(";", maxsplit=1)[0]
    denied, denied_payload, _, _ = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body={"scenario_id": WORKSPACE_HERO_SCENARIO_ID},
        token=None,
        cookie=cookie,
        intent=False,
    )
    allowed, _, _, _ = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body={"scenario_id": WORKSPACE_HERO_SCENARIO_ID},
        token=None,
        cookie=cookie,
        intent=True,
    )

    assert session_status == 200
    assert denied == 401
    assert denied_payload["error"] == "UNAUTHORIZED"
    assert allowed == 201


def test_unknown_scenario_and_malformed_run_identity_fail_closed(tmp_path: Path) -> None:
    application, _, _ = _application(tmp_path)
    unknown, unknown_payload, _, _ = _call(
        application,
        "POST",
        "/api/workspace-demo/runs",
        body={"scenario_id": "ANY_OTHER_SCENARIO"},
    )
    malformed, malformed_payload, _, _ = _call(
        application,
        "GET",
        "/api/workspace-demo/runs/not-a-uuid",
        content_type=None,
    )

    assert unknown == malformed == 400
    assert unknown_payload["error"] == malformed_payload["error"] == "BAD_REQUEST"


def test_stale_request_fingerprint_is_rejected_without_effect(tmp_path: Path) -> None:
    application, _, profile = _application(tmp_path)
    started = _start(application)
    _request_approval(application, started["run_id"])

    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/decision",
        body={"decision": "APPROVED", "request_fingerprint": "0" * 64},
    )
    _, refreshed, _, _ = _call(
        application,
        "GET",
        f"/api/workspace-demo/runs/{started['run_id']}",
        content_type=None,
    )

    assert status == 403
    assert payload["failure_code"] == "WORKSPACE_HERO_STALE_APPROVAL_REQUEST"
    assert refreshed["result"]["state"] == "AWAITING_APPROVAL"
    assert refreshed["result"]["workspace_mutation_count"] == 0
    assert profile.calls == 0


def test_cross_run_request_fingerprint_cannot_authorize_another_patch(
    tmp_path: Path,
) -> None:
    application, _, _ = _application(tmp_path)
    first = _request_approval(application, _start(application)["run_id"])
    second = _request_approval(application, _start(application)["run_id"])
    first_card = first["approval_card"]
    assert isinstance(first_card, dict)

    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{second['run_id']}/decision",
        body={
            "decision": "APPROVED",
            "request_fingerprint": first_card["request_fingerprint"],
        },
    )

    assert status == 403
    assert payload["failure_code"] == "WORKSPACE_HERO_STALE_APPROVAL_REQUEST"


def test_apply_requires_prior_exact_approval(tmp_path: Path) -> None:
    application, _, profile = _application(tmp_path)
    started = _start(application)

    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{started['run_id']}/resume",
        body={"confirm_execution": True},
    )

    assert status == 403
    assert payload["failure_code"] == "WORKSPACE_HERO_APPLY_NOT_APPROVED"
    assert profile.calls == 0


def test_verify_cannot_create_success_before_the_exact_effect(tmp_path: Path) -> None:
    application, _, profile = _application(tmp_path)
    approved = _approved(application)

    status, payload, _, _ = _call(
        application,
        "POST",
        f"/api/workspace-demo/runs/{approved['run_id']}/verify-or-reconcile",
        body={},
    )

    assert status == 422
    assert payload["error"] == "WORKFLOW_FAILED"
    assert profile.calls == 0


def test_refresh_reconstructs_identical_authoritative_projection(tmp_path: Path) -> None:
    application, runtime, profile = _application(tmp_path)
    requested = _request_approval(application, _start(application)["run_id"])
    authorizer = LocalApiTokenAuthorizer(TOKEN)
    reconstructed = LocalApiApplication(
        runtime,
        authorizer,
        workspace_hero=WorkspaceHeroOrchestrator(
            tmp_path / "workspace-hero",
            runtime.runtime_settings,
            nonce_deriver=authorizer.derive_workspace_decision_nonce,
            profile_factory=lambda: profile,
        ),
    )

    status, payload, _, _ = _call(
        reconstructed,
        "GET",
        f"/api/workspace-demo/runs/{requested['run_id']}",
        content_type=None,
    )

    assert status == 200
    assert payload["result"] == requested


def test_private_w5_files_are_owner_only(tmp_path: Path) -> None:
    application, _, _ = _application(tmp_path)
    started = _start(application)
    run_root = tmp_path / "workspace-hero" / "runs" / str(started["run_id"])

    assert stat.S_IMODE(run_root.stat().st_mode) == 0o700
    assert stat.S_IMODE((run_root / "manifest.json").stat().st_mode) == 0o600
    assert stat.S_IMODE((run_root / "authority.json").stat().st_mode) == 0o600


def test_no_generic_execution_or_mutation_routes_were_exposed(tmp_path: Path) -> None:
    application, _, _ = _application(tmp_path)
    forbidden = (
        "/api/shell",
        "/api/process",
        "/api/files/write",
        "/api/patch/apply",
        "/api/git/commit",
        "/api/packages/install",
        "/api/browser",
        "/api/mcp",
        "/api/fetch-url",
    )

    assert all(_call(application, "GET", path, content_type=None)[0] == 404 for path in forbidden)


def test_hero_ui_exposes_all_ten_truthful_stages_and_exact_controls() -> None:
    expected_stages = (
        "OBSERVE",
        "EVIDENCE",
        "ROOT_CAUSE",
        "PATCH_PROPOSAL",
        "POLICY",
        "HUMAN_DECISION",
        "PATCH_EFFECT",
        "VERIFICATION",
        "RECEIPT",
        "RECOVERY_REPLAY",
    )

    assert all(f'data-hero-stage="{stage}"' in JUDGE_UI_BODY for stage in expected_stages)
    assert "The model proposes.<br>The human authorizes.<br>Evidence decides." in JUDGE_UI_BODY
    assert "FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1" in JUDGE_UI_SCRIPT
    assert all(
        f'id="{control}"' in JUDGE_UI_BODY
        for control in (
            "hero-review",
            "hero-approve",
            "hero-deny",
            "hero-execute",
            "hero-verify",
            "hero-replay",
        )
    )


def test_hero_ui_renders_server_text_without_html_interpretation() -> None:
    assert "byId('hero-diff').textContent =" in JUDGE_UI_SCRIPT
    assert "byId('hero-raw-output').textContent =" in JUDGE_UI_SCRIPT
    assert "item.textContent = String(value)" in JUDGE_UI_SCRIPT
    assert "innerHTML" not in JUDGE_UI_SCRIPT
    assert "document.write" not in JUDGE_UI_SCRIPT
    assert "eval(" not in JUDGE_UI_SCRIPT


def test_hero_ui_is_refresh_safe_busy_safe_and_responsive() -> None:
    busy_position = JUDGE_UI_SCRIPT.index("ui.busy = true")
    action_position = JUDGE_UI_SCRIPT.index("try { await action(); }")

    assert busy_position < action_position
    assert "fragment.get('hero_run')" in JUDGE_UI_SCRIPT
    assert "refreshHero" in JUDGE_UI_SCRIPT
    assert "workspace_mutation_count === before" in JUDGE_UI_SCRIPT
    assert ".hero-workspace-grid { grid-template-columns: 1fr; }" in JUDGE_UI_STYLE
    assert ".hero-pipeline { display: flex;" in JUDGE_UI_STYLE
    assert "prefers-reduced-motion" in JUDGE_UI_STYLE
    assert "focus-visible" in JUDGE_UI_STYLE
    assert "localStorage" not in JUDGE_UI_BODY
    assert "sessionStorage" not in JUDGE_UI_BODY


def test_fixed_render_start_profile_proves_local_boot_contract() -> None:
    result = WorkspaceHeroRenderStartProfile().run()

    assert result == TrustedRenderStartProfileResult()
    assert result.missing_token_fails_closed is True
    assert result.token_mode_0600 is True
    assert result.bootstrap_secret_absent is True
    assert result.child_argv_exact is True
    assert result.health_passed is True
    assert result.readiness_passed is True
    assert result.external_egress_count == result.aws_call_count == 0
    assert result.workspace_code_executions == result.arbitrary_command_executions == 0
