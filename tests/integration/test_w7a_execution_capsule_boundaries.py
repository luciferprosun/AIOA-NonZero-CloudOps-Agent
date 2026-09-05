"""Cross-phase proof that Phase 7 composes evidence without an execution engine."""

from __future__ import annotations

from tests.w7a_phase7_fixtures import build_capsule, build_phase5_phase6_fixture

from aioa_cloudops_agent.execution import ExecutionCapsule, build_execution_capsule
from aioa_cloudops_agent.github import GitHubToolInventory
from aioa_cloudops_agent.sandbox import SandboxProvider


def test_real_phase5_patchset_and_phase6_receipts_are_bound_without_new_authority(
    tmp_path,
) -> None:
    capsule = build_capsule(tmp_path)

    assert isinstance(capsule, ExecutionCapsule)
    assert capsule.patchset_sha256
    assert len(capsule.verification.events) == 6
    assert capsule.authorizes_execution is False
    assert capsule.credential_policy.worker == "NONE"
    assert capsule.credential_policy.sandbox == "NONE"
    assert capsule.credential_policy.test_process == "NONE"
    assert not hasattr(capsule, "execute")
    assert not hasattr(capsule, "push")


def test_capsule_builder_requires_validated_cross_phase_contracts(tmp_path) -> None:
    capsule = build_capsule(tmp_path / "valid")
    patchset, loop = build_phase5_phase6_fixture(tmp_path / "other")

    try:
        build_execution_capsule(capsule, patchset=patchset, repair_result=loop)
    except TypeError as error:
        assert str(error) == "request must be ExecutionCapsuleBuildRequest"
    else:
        raise AssertionError("capsule builder accepted its own output as new authority")


def test_read_only_github_mcp_and_sandbox_interfaces_gain_no_write_capability() -> None:
    assert GitHubToolInventory.model_fields["read_only"].default is True
    assert GitHubToolInventory.model_fields["runtime_write_tools"].default == 0
    exposed = set(SandboxProvider.__abstractmethods__)
    assert not exposed.intersection({"push", "commit", "merge", "create_pull_request"})
