"""Phase 8 deterministic actuator contracts and fail-closed unit boundaries."""

from __future__ import annotations

import json
import os
import subprocess
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError
from tests.w7a_phase8_fixtures import (
    BASE_BRANCH,
    NOW,
    TARGET_BRANCH,
    build_phase8_fixture,
    git,
)

from aioa_cloudops_agent.execution import ExecutionRepositoryIdentity
from aioa_cloudops_agent.github import GitHubMcpReadPlane
from aioa_cloudops_agent.github.effect_repository import GitEffectRepositoryError
from aioa_cloudops_agent.github.repository_service import (
    GitHubHttpsRepositoryService,
    GitHubWriteCredential,
    GitRepositoryError,
    LocalBareGitRepositoryService,
)
from aioa_cloudops_agent.github.write_actuator import DeterministicGitHubWriteActuator
from aioa_cloudops_agent.github.write_contracts import GitWriteDisposition
from aioa_cloudops_agent.patchset import FileContentIdentity, PatchFileChange, PatchOperation
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest


def test_missing_durable_human_approval_denies_before_any_write(tmp_path):
    fixture = build_phase8_fixture(tmp_path, approved=False)

    result = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.DENIED
    assert result.failure_code == "EXECUTION_HUMAN_APPROVAL_REQUIRED"
    assert fixture.actuator.remote_write_attempts == 0
    assert fixture.service.readback_feature_ref(target_branch=TARGET_BRANCH) is None


def test_expired_approval_denies_without_verification_or_write(tmp_path):
    fixture = build_phase8_fixture(
        tmp_path,
        expires_at=NOW + timedelta(minutes=4),
    )

    result = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.DENIED
    assert result.failure_code == "EXECUTION_APPROVAL_EXPIRED"
    assert fixture.verifier.calls == 0
    assert fixture.actuator.remote_write_attempts == 0


def test_remote_identity_mismatch_is_denied(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    wrong_service = LocalBareGitRepositoryService(
        fixture.bare.resolve(),
        ExecutionRepositoryIdentity.normalize("luciferprosun", "different-repository"),
    )
    actuator = DeterministicGitHubWriteActuator(
        wrong_service,
        fixture.repository,
        fixture.verifier,
        clock=lambda: NOW + timedelta(minutes=5),
    )

    result = actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.DENIED
    assert result.failure_code == "GIT_REMOTE_IDENTITY_MISMATCH"
    assert actuator.remote_write_attempts == 0


def test_base_drift_is_denied_before_disposable_workspace(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    tree = git("rev-parse", f"{fixture.base_head}^{{tree}}", cwd=fixture.bare)
    drift = git(
        "-c",
        "user.name=AIOA Fixture",
        "-c",
        "user.email=fixture@aioa.invalid",
        "commit-tree",
        tree,
        "-p",
        fixture.base_head,
        "-m",
        "drift",
        cwd=fixture.bare,
    )
    git("update-ref", f"refs/heads/{BASE_BRANCH}", drift, fixture.base_head, cwd=fixture.bare)

    result = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.DENIED
    assert result.failure_code == "GIT_BASE_DRIFT_DENIED"
    assert fixture.actuator.remote_write_attempts == 0


def test_preexisting_target_ref_is_denied(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    git(
        "update-ref",
        f"refs/heads/{TARGET_BRANCH}",
        fixture.base_head,
        "0" * 40,
        cwd=fixture.bare,
    )

    result = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.DENIED
    assert result.failure_code == "GIT_TARGET_ALREADY_EXISTS"
    assert fixture.actuator.remote_write_attempts == 0


def test_changed_after_content_invalidates_exact_patchset(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    (fixture.final_root / "solver.py").write_text(
        "def add(a, b):\n    return a * b\n",
        encoding="utf-8",
    )

    result = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.DENIED
    assert result.failure_code == "PATCHSET_TOCTOU_DRIFT_DETECTED"
    assert fixture.actuator.remote_write_attempts == 0


def test_verifier_crash_is_a_closed_denial_before_effect_ownership(tmp_path):
    fixture = build_phase8_fixture(tmp_path)

    class CrashingVerifier:
        def verify(self, **_kwargs):
            raise RuntimeError("untrusted diagnostic text")

    actuator = DeterministicGitHubWriteActuator(
        fixture.service,
        fixture.repository,
        CrashingVerifier(),
        clock=lambda: NOW + timedelta(minutes=5),
    )

    result = actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.DENIED
    assert result.failure_code == "GIT_ACTUATION_DEPENDENCY_FAILED"
    assert actuator.remote_write_attempts == 0
    assert fixture.repository.get_ownership(fixture.capsule.operation_id) is None


@pytest.mark.parametrize("trick", ["symlink", "hardlink"])
def test_symlink_and_hardlink_after_content_are_denied(tmp_path, trick):
    fixture = build_phase8_fixture(tmp_path)
    target = fixture.final_root / "solver.py"
    target.unlink()
    source = tmp_path / "outside.py"
    source.write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    if trick == "symlink":
        target.symlink_to(source)
    else:
        os.link(source, target)

    result = fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    assert result.disposition is GitWriteDisposition.DENIED
    assert result.failure_code in {
        "PATCHSET_HARDLINK_DENIED",
        "PATCHSET_SYMLINK_DENIED",
        "PATCHSET_TOCTOU_DRIFT_DETECTED",
    }
    assert fixture.actuator.remote_write_attempts == 0


def test_worker_style_environment_credentials_never_enter_read_or_test_git_process(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setenv("GH_TOKEN", "synthetic-value-never-used")
    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-value-never-used")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "synthetic-value-never-used")
    monkeypatch.setenv("SSH_AUTH_SOCK", "/tmp/synthetic-agent.sock")
    fixture = build_phase8_fixture(tmp_path, approved=False)

    fixture.actuator.execute(
        fixture.capsule,
        patchset=fixture.patchset,
        base_root=fixture.base_root.resolve(),
        final_root=fixture.final_root.resolve(),
    )

    names = set(fixture.service.child_environment_names)
    assert names.isdisjoint(
        {"GH_TOKEN", "GITHUB_TOKEN", "AWS_ACCESS_KEY_ID", "SSH_AUTH_SOCK"}
    )
    assert fixture.verifier.calls == 0


def test_live_adapter_keeps_write_credential_out_of_argv_and_destroys_it(
    tmp_path,
    monkeypatch,
):
    captured: dict[str, object] = {}

    def fake_run(arguments, **kwargs):
        captured["arguments"] = arguments
        captured["environment"] = kwargs["env"]
        return subprocess.CompletedProcess(arguments, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(subprocess, "run", fake_run)
    identity = ExecutionRepositoryIdentity.normalize(
        "luciferprosun",
        "AIOA-NonZero-CloudOps-Agent",
    )
    service = GitHubHttpsRepositoryService(identity)
    raw = "synthetic-" + "credential-material"
    credential = GitHubWriteCredential(SecretStr(raw))

    acknowledgement = service.push_feature_ref_once(
        workspace=tmp_path.resolve(),
        commit_sha="a" * 40,
        target_branch=TARGET_BRANCH,
        credential=credential,
    )

    assert acknowledgement.value == "ACKNOWLEDGED"
    assert raw not in " ".join(captured["arguments"])
    environment = captured["environment"]
    assert isinstance(environment, dict)
    assert raw not in repr(credential)
    assert raw not in credential._git_environment()["GIT_CONFIG_VALUE_0"]
    assert set(service.child_environment_names).isdisjoint(
        {"GH_TOKEN", "GITHUB_TOKEN", "AWS_ACCESS_KEY_ID", "SSH_AUTH_SOCK"}
    )


@pytest.mark.parametrize(
    "target",
    ["main", "refs/heads/main", "codex/w7a-verified-pr-*", "codex/../main"],
)
def test_default_wildcard_and_ambiguous_targets_cannot_reach_push(tmp_path, target):
    fixture = build_phase8_fixture(tmp_path)

    with pytest.raises((GitRepositoryError, ValueError)):
        fixture.service.push_feature_ref_once(
            workspace=tmp_path.resolve(),
            commit_sha=fixture.base_head,
            target_branch=target,
            credential=None,
        )

    assert fixture.service.readback_feature_ref(target_branch=TARGET_BRANCH) is None


def test_no_force_tag_merge_or_generic_refspec_api_exists(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    public_names = {
        name for name in dir(fixture.service) if not name.startswith("_")
    }

    assert not any(
        marker in name
        for name in public_names
        for marker in ("force", "tag", "merge", "refspec")
    )
    assert "push_feature_ref_once" in public_names


def test_patch_file_traversal_cannot_enter_the_actuator_contract():
    with pytest.raises(ValidationError):
        PatchFileChange(
            path="../solver.py",
            operation=PatchOperation.ADD,
            before=None,
            after=FileContentIdentity(sha256="a" * 64, size=1, mode=0o644),
            lines_added=1,
            lines_deleted=0,
        )


def test_github_mcp_remains_read_only_and_cannot_supply_write_authority():
    public_names = {name for name in dir(GitHubMcpReadPlane) if not name.startswith("_")}

    assert not any(
        marker in name
        for name in public_names
        for marker in ("create", "delete", "merge", "push", "update")
    )


def test_strict_remote_observation_rejects_extra_authority_field(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    observation = fixture.service.observe(
        base_ref=BASE_BRANCH,
        target_branch=TARGET_BRANCH,
    )
    payload = observation.model_dump(mode="json")
    payload["force"] = True

    with pytest.raises(ValidationError):
        type(observation).model_validate(payload)


def test_durable_effect_state_detects_tampering(tmp_path):
    fixture = build_phase8_fixture(tmp_path)
    path = fixture.repository.path
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["payload"]["decisions"][0]["actor_session_id"] = "tampered-actor"
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(0o600)

    with pytest.raises(GitEffectRepositoryError):
        fixture.repository.read_snapshot()


def test_partial_phase8_evidence_is_self_hashed_and_never_claims_live_authority():
    root = Path(__file__).resolve().parents[2]
    request = json.loads(
        (root / "docs/evidence/w7a/phase8-human-approval-request.json").read_text(
            encoding="utf-8"
        )
    )
    proof = json.loads(
        (root / "docs/evidence/w7a/phase8-local-bare-remote-proof.json").read_text(
            encoding="utf-8"
        )
    )

    assert request["request_artifact_sha256"] == canonical_workspace_json_digest(
        {key: value for key, value in request.items() if key != "request_artifact_sha256"}
    )
    assert request["human_decision_present"] is False
    assert request["live_github_execution_ready"] is False
    assert proof["proof_sha256"] == canonical_workspace_json_digest(
        {key: value for key, value in proof.items() if key != "proof_sha256"}
    )
    assert proof["scope"] == "DISPOSABLE_LOCAL_BARE_REMOTE_TEST_ONLY"
    assert proof["product_runtime_github_writes"] == 0
    assert not (root / "docs/evidence/w7a/phase8-remote-write-receipt.json").exists()
