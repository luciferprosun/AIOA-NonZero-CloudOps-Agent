"""Phase 7 canonical capsule and exact authority adversarial tests."""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError
from tests.w7a_phase7_fixtures import NOW, RAW_NONCE, build_capsule

from aioa_cloudops_agent.execution import (
    EXECUTION_OPERATION_ORDER,
    ExecutionApprovalDecision,
    ExecutionAuthorityDenied,
    ExecutionCapsule,
    ExecutionRepositoryIdentity,
    build_execution_approval_decision,
    normalize_branch,
    require_execution_authority,
)
from aioa_cloudops_agent.nz import ApprovalDecision
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / "docs/evidence/w7a/phase7-execution-capsule.json"


def _decision(capsule: ExecutionCapsule, **updates: object) -> ExecutionApprovalDecision:
    decision = build_execution_approval_decision(
        capsule,
        decision=ApprovalDecision.APPROVED,
        actor_session_id=capsule.approval_request.actor_session_id,
        decision_nonce=RAW_NONCE,
        decided_at=NOW + timedelta(minutes=1),
    )
    material = decision.model_dump(exclude={"decision_sha256"})
    material.update(updates)
    provisional = ExecutionApprovalDecision.model_construct(
        **material,
        decision_sha256="0" * 64,
    )
    return ExecutionApprovalDecision(
        **material,
        decision_sha256=canonical_workspace_json_digest(provisional.content_payload()),
    )


def test_capsule_is_canonical_self_hashed_and_grants_nothing(tmp_path) -> None:
    first = build_capsule(tmp_path / "one")
    second = build_capsule(tmp_path / "two")

    assert first == second
    assert first.capsule_sha256 == canonical_workspace_json_digest(first.content_payload())
    assert first.authorizes_execution is False
    assert first.mutation_authority is False
    assert first.github_authority is False
    assert first.aws_authority is False
    assert first.allowed_operations == EXECUTION_OPERATION_ORDER
    assert first.changed_files == ("solver.py",)
    assert first.repository.name == "aioa-nonzero-cloudops-agent"


def test_capsule_rejects_unknown_or_authority_smuggling_fields(tmp_path) -> None:
    capsule = build_capsule(tmp_path)
    payload = capsule.model_dump()
    payload["shell"] = "git push --force origin main"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ExecutionCapsule.model_validate(payload)


@pytest.mark.parametrize(
    "branch",
    (
        "main",
        "refs/heads/codex/w7a-verified-pr-x",
        "codex//w7a-verified-pr-x",
        "codex/../main",
        "codex/w7a-verified-pr-x.lock",
        " codex/w7a-verified-pr-x",
    ),
)
def test_capsule_rejects_default_or_ambiguous_target_branch(tmp_path, branch: str) -> None:
    capsule = build_capsule(tmp_path)
    payload = capsule.model_dump()
    payload["target_branch"] = branch

    with pytest.raises(ValidationError):
        ExecutionCapsule.model_validate(payload)


def test_branch_normalizer_accepts_only_exact_short_ref() -> None:
    assert normalize_branch("codex/w7a-agent-execution-slice") == (
        "codex/w7a-agent-execution-slice"
    )
    with pytest.raises(ValueError):
        normalize_branch("codex/w7a@{1}")


def test_repository_identity_normalizes_case_before_hashing() -> None:
    identity = ExecutionRepositoryIdentity.normalize(
        "LuciferProSun",
        "AIOA-NonZero-CloudOps-Agent",
    )
    assert identity.owner == "luciferprosun"
    assert identity.name == "aioa-nonzero-cloudops-agent"
    with pytest.raises(ValidationError):
        ExecutionRepositoryIdentity(
            owner="LuciferProSun",
            name="repo",
            canonical_url="https://github.com/LuciferProSun/repo",
        )


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("base_head", "e" * 40),
        ("base_ref", "codex/other-base"),
        ("patchset_sha256", "f" * 64),
        ("authority", "MODEL_SAYS_APPROVED"),
    ),
)
def test_capsule_tampering_invalidates_canonical_binding(
    tmp_path,
    field: str,
    value: str,
) -> None:
    capsule = build_capsule(tmp_path)
    payload = capsule.model_dump()
    payload[field] = value

    with pytest.raises(ValidationError):
        ExecutionCapsule.model_validate(payload)


def test_changed_sandbox_identity_invalidates_capsule(tmp_path) -> None:
    capsule = build_capsule(tmp_path)
    payload = capsule.model_dump()
    payload["sandbox"]["policy_sha256"] = "f" * 64

    with pytest.raises(ValidationError, match=r"approval request|capsule digest"):
        ExecutionCapsule.model_validate(payload)


def test_duplicate_or_reordered_terminal_events_fail_closed(tmp_path) -> None:
    capsule = build_capsule(tmp_path)
    reordered = capsule.model_dump()
    reordered_events = list(reordered["verification"]["events"])
    reordered_events[0], reordered_events[1] = reordered_events[1], reordered_events[0]
    reordered["verification"]["events"] = reordered_events
    duplicated = capsule.model_dump()
    duplicated_events = list(duplicated["verification"]["events"])
    duplicated_events[1] = duplicated_events[0]
    duplicated["verification"]["events"] = duplicated_events

    with pytest.raises(ValidationError, match="events"):
        ExecutionCapsule.model_validate(reordered)
    with pytest.raises(ValidationError, match="events"):
        ExecutionCapsule.model_validate(duplicated)


def test_missing_human_approval_never_grants_authority(tmp_path) -> None:
    capsule = build_capsule(tmp_path)
    with pytest.raises(ExecutionAuthorityDenied) as denied:
        require_execution_authority(capsule, None, validated_at=NOW)
    assert denied.value.code == "EXECUTION_HUMAN_APPROVAL_REQUIRED"


def test_exact_human_decision_yields_receipt_but_not_effect_success(tmp_path) -> None:
    capsule = build_capsule(tmp_path)
    receipt = require_execution_authority(
        capsule,
        _decision(capsule),
        validated_at=NOW + timedelta(minutes=2),
    )
    assert receipt.granted is True
    assert receipt.remote_effect_completed is False
    assert receipt.capsule_sha256 == capsule.capsule_sha256
    assert receipt.permitted_operations == EXECUTION_OPERATION_ORDER


@pytest.mark.parametrize(
    ("updates", "code"),
    (
        ({"actor_session_id": "wrong-session"}, "EXECUTION_APPROVAL_BINDING_MISMATCH"),
        ({"decision_nonce_sha256": "1" * 64}, "EXECUTION_APPROVAL_BINDING_MISMATCH"),
        ({"request_sha256": "2" * 64}, "EXECUTION_APPROVAL_BINDING_MISMATCH"),
        ({"capsule_sha256": "3" * 64}, "EXECUTION_APPROVAL_BINDING_MISMATCH"),
        ({"decision": ApprovalDecision.DENIED}, "EXECUTION_DENIED_BY_HUMAN"),
    ),
)
def test_wrong_actor_nonce_request_capsule_or_denial_fails_closed(
    tmp_path,
    updates: dict[str, object],
    code: str,
) -> None:
    capsule = build_capsule(tmp_path)
    with pytest.raises(ExecutionAuthorityDenied) as denied:
        require_execution_authority(
            capsule,
            _decision(capsule, **updates),
            validated_at=NOW + timedelta(minutes=2),
        )
    assert denied.value.code == code


def test_expired_approval_and_completed_operation_replay_are_denied(tmp_path) -> None:
    capsule = build_capsule(tmp_path)
    decision = _decision(capsule)
    with pytest.raises(ExecutionAuthorityDenied) as expired:
        require_execution_authority(
            capsule,
            decision,
            validated_at=capsule.approval_request.expires_at + timedelta(seconds=1),
        )
    assert expired.value.code == "EXECUTION_APPROVAL_EXPIRED"
    with pytest.raises(ExecutionAuthorityDenied) as replay:
        require_execution_authority(
            capsule,
            decision,
            validated_at=NOW + timedelta(minutes=2),
            completed_operation_ids={str(capsule.operation_id)},
        )
    assert replay.value.code == "EXECUTION_OPERATION_REPLAY_DENIED"


def test_raw_nonce_and_credentials_are_not_serialized(tmp_path) -> None:
    capsule = build_capsule(tmp_path)
    decision = _decision(capsule)
    rendered = capsule.model_dump_json() + decision.model_dump_json()
    assert RAW_NONCE not in rendered
    assert "ghp_" not in rendered
    assert "AWS_SECRET_ACCESS_KEY" not in rendered


def test_phase7_evidence_is_self_hashed_and_contains_no_live_authority() -> None:
    evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    claimed = evidence.pop("evidence_sha256")
    canonical = json.dumps(
        evidence,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")

    assert claimed == hashlib.sha256(canonical).hexdigest()
    capsule = ExecutionCapsule.model_validate(evidence["capsule"])
    assert capsule.capsule_sha256 == (
        "9d052d8c3a1c314b9da46f827d112ab8d1c6867dc951c35cf54e9508b65bea1b"
    )
    assert evidence["synthetic_contract_fixture_only"] is True
    assert evidence["human_approval_bound"] is False
    assert evidence["product_runtime_github_writes"] == 0
    assert evidence["aws_calls"] == 0
