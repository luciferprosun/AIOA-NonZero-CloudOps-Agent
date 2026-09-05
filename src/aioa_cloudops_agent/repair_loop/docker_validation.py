"""Real Phase 4 Docker validation backend for canonical Phase 5 PatchSets."""

from __future__ import annotations

from pathlib import Path

from aioa_cloudops_agent.patchset import BoundedPatchSetPolicy, PatchSet, PatchSetPolicyDenied
from aioa_cloudops_agent.sandbox import (
    DOCKER_SANDBOX_V1,
    CommandReceipt,
    DeterministicSetupPlanner,
    DockerSandboxProvider,
    DockerToolboxIdentity,
    SandboxCommand,
    SandboxCommandProfile,
    SandboxLifecycleState,
    SandboxPolicy,
    normalize_sandbox_relative_path,
)
from aioa_cloudops_agent.workspace.contracts import canonical_workspace_json_digest

from .contracts import ValidationOutcome, ValidationStage, ValidationStepReceipt


class DockerValidationBackend:
    """Open one credentialless, network-none validation sandbox per candidate."""

    def __init__(
        self,
        *,
        base_root: Path,
        toolbox: DockerToolboxIdentity,
        targeted_test_path: str,
        policy: SandboxPolicy = DOCKER_SANDBOX_V1,
        patchset_policy: BoundedPatchSetPolicy | None = None,
    ) -> None:
        normalized = normalize_sandbox_relative_path(targeted_test_path)
        if not Path(normalized).name.startswith("test_") or not normalized.endswith(".py"):
            raise ValueError("targeted test path is outside the fixed Python test profile")
        self._base_root = base_root
        self._toolbox = toolbox
        self._targeted_test_path = normalized
        self._policy = policy
        self._patchset_policy = patchset_policy or BoundedPatchSetPolicy()

    def open(self, candidate_root: Path, patchset: PatchSet) -> DockerValidationSession:
        return DockerValidationSession(
            base_root=self._base_root,
            candidate_root=candidate_root,
            patchset=patchset,
            toolbox=self._toolbox,
            targeted_test_path=self._targeted_test_path,
            policy=self._policy,
            patchset_policy=self._patchset_policy,
        )


class DockerValidationSession:
    """One owned Docker lifecycle; close is idempotent and reports orphan count."""

    _COLLECT = ("python", "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider")
    _FINAL = ("python", "-m", "pytest", "-q", "-p", "no:cacheprovider")

    def __init__(
        self,
        *,
        base_root: Path,
        candidate_root: Path,
        patchset: PatchSet,
        toolbox: DockerToolboxIdentity,
        targeted_test_path: str,
        policy: SandboxPolicy,
        patchset_policy: BoundedPatchSetPolicy,
    ) -> None:
        self._patchset = patchset
        self._targeted = (
            "python",
            "-m",
            "pytest",
            "-q",
            "-p",
            "no:cacheprovider",
            targeted_test_path,
        )
        self._provider = DockerSandboxProvider(toolbox=toolbox)
        self._closed = False
        self._cleanup_orphans = 0
        self._base_identity = None
        if not self._provider.availability().available:
            raise RuntimeError("REPAIR_DOCKER_PROVIDER_UNAVAILABLE")
        created = False
        try:
            planner = DeterministicSetupPlanner()
            identity = planner.inspect_repository(
                base_root,
                source_commit=patchset.base_head,
            )
            if identity != patchset.repository:
                raise PatchSetPolicyDenied("REPAIR_BASE_IDENTITY_MISMATCH")
            setup = planner.plan_python(base_root, identity.tree_sha256)
            self._provider.create(policy)
            created = True
            self._provider.stage_repository(base_root, identity)
            self._provider.setup_environment(setup)
            for relative_path, content in patchset_policy.bound_after_contents(
                final_root=candidate_root,
                patchset=patchset,
            ):
                receipt = self._provider.write_file(relative_path, content, policy)
                expected = next(
                    change.after for change in patchset.files if change.path == relative_path
                )
                if expected is None or receipt.sha256 != expected.sha256:
                    raise PatchSetPolicyDenied("REPAIR_SANDBOX_WRITE_IDENTITY_MISMATCH")
            snapshot = self._provider.snapshot()
            if snapshot.repository_tree_sha256 != patchset.final_tree_sha256:
                raise PatchSetPolicyDenied("REPAIR_SANDBOX_FINAL_TREE_MISMATCH")
            self._base_identity = identity
        except BaseException:
            if created:
                self.close()
            raise

    def validate_fast_and_targeted(self) -> tuple[ValidationStepReceipt, ...]:
        collect = self._run(ValidationStage.V1_FAST_STATIC, self._COLLECT)
        if collect.outcome is not ValidationOutcome.PASS:
            return (collect,)
        return (collect, self._run(ValidationStage.V2_TARGETED_TESTS, self._targeted))

    def validate_final(self) -> ValidationStepReceipt:
        final = self._run(ValidationStage.V6_FINAL_GATES, self._FINAL)
        if final.outcome is not ValidationOutcome.PASS:
            return final
        if self._base_identity is None:
            raise RuntimeError("REPAIR_VALIDATION_BASE_IDENTITY_MISSING")
        diff = self._provider.collect_diff(self._base_identity)
        expected_paths = tuple(change.path for change in self._patchset.files)
        material = {
            "command_evidence_sha256": final.evidence_sha256,
            "diff_sha256": diff.diff_sha256,
            "patchset_sha256": self._patchset.patchset_sha256,
            "sandbox_tree_sha256": diff.current_tree_sha256,
        }
        if (
            diff.changed_paths != expected_paths
            or diff.current_tree_sha256 != self._patchset.final_tree_sha256
        ):
            return ValidationStepReceipt(
                stage=ValidationStage.V6_FINAL_GATES,
                outcome=ValidationOutcome.FAIL,
                evidence_sha256=canonical_workspace_json_digest(material),
                sandbox_id=final.sandbox_id,
                exit_code=1,
                stdout_sha256=final.stdout_sha256,
                stderr_sha256=final.stderr_sha256,
                output_truncated=final.output_truncated,
                failure_code="REPAIR_SANDBOX_DIFF_IDENTITY_MISMATCH",
            )
        return final.model_copy(
            update={"evidence_sha256": canonical_workspace_json_digest(material)}
        )

    def close(self) -> int:
        if self._closed:
            return self._cleanup_orphans
        cleanup = self._provider.destroy()
        self._cleanup_orphans = cleanup.orphaned_resources
        self._closed = True
        return self._cleanup_orphans

    def _run(
        self,
        stage: ValidationStage,
        argv: tuple[str, ...],
    ) -> ValidationStepReceipt:
        receipt = self._provider.exec(
            SandboxCommand(
                profile=SandboxCommandProfile.PYTHON_TEST,
                argv=argv,
                timeout_seconds=60,
            )
        )
        outcome, code = _command_outcome(receipt)
        material = {
            "argv_sha256": receipt.argv_sha256,
            "exit_code": receipt.exit_code,
            "network_mode": receipt.network_mode,
            "output_truncated": receipt.output_truncated,
            "patchset_sha256": self._patchset.patchset_sha256,
            "stage": stage.value,
            "state": receipt.state.value,
            "stderr_sha256": receipt.stderr_sha256,
            "stdout_sha256": receipt.stdout_sha256,
        }
        return ValidationStepReceipt(
            stage=stage,
            outcome=outcome,
            evidence_sha256=canonical_workspace_json_digest(material),
            sandbox_id=receipt.sandbox_id,
            exit_code=receipt.exit_code,
            stdout_sha256=receipt.stdout_sha256,
            stderr_sha256=receipt.stderr_sha256,
            output_truncated=receipt.output_truncated,
            failure_code=code,
        )


def _command_outcome(receipt: CommandReceipt) -> tuple[ValidationOutcome, str | None]:
    if receipt.exit_code == 0 and receipt.state is SandboxLifecycleState.CODING_OFFLINE:
        return ValidationOutcome.PASS, None
    if receipt.exit_code == 124 or receipt.state is SandboxLifecycleState.RESOURCE_LIMIT:
        return ValidationOutcome.TIMEOUT, "REPAIR_TEST_TIMEOUT"
    if receipt.state is SandboxLifecycleState.SANDBOX_CRASHED:
        return ValidationOutcome.CRASH, "REPAIR_SANDBOX_CRASHED"
    return ValidationOutcome.FAIL, "REPAIR_TEST_FAILED"
