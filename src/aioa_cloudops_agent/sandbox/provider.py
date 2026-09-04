"""Provider-neutral sandbox surface and fail-closed Docker v1 scaffold."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import stat
import tarfile
from collections.abc import Mapping
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Literal, Protocol, Self, runtime_checkable

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.nz import Sha256Digest, generate_event_id
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.redaction import contains_sensitive_material

from .contracts import (
    CleanupReceipt,
    CommandReceipt,
    DiffReceipt,
    DockerToolboxIdentity,
    FileReceipt,
    RepositorySourceIdentity,
    SandboxCommand,
    SandboxLifecycleState,
    SandboxPolicy,
    SandboxRef,
    SetupPlan,
    SetupReceipt,
    SnapshotRef,
    StagedRepoRef,
    WriteReceipt,
    canonical_sandbox_digest,
    normalize_sandbox_relative_path,
)
from .docker_runtime import DockerCli, DockerCliFailure, DockerCliResult
from .setup import DeterministicSetupPlanner

_ACTIVE_STATES = frozenset(
    {
        SandboxLifecycleState.CREATED,
        SandboxLifecycleState.REPOSITORY_STAGED,
        SandboxLifecycleState.SETUP,
        SandboxLifecycleState.READY,
        SandboxLifecycleState.CODING_OFFLINE,
        SandboxLifecycleState.COLLECTING,
    }
)
_FAILURE_STATES = frozenset(
    {
        SandboxLifecycleState.SETUP_FAILED,
        SandboxLifecycleState.COMMAND_FAILED,
        SandboxLifecycleState.POLICY_DENIED,
        SandboxLifecycleState.RESOURCE_LIMIT,
        SandboxLifecycleState.CLEANUP_FAILED,
        SandboxLifecycleState.SANDBOX_CRASHED,
    }
)
_TRANSITIONS = {
    SandboxLifecycleState.CREATED: frozenset(
        {
            SandboxLifecycleState.REPOSITORY_STAGED,
            SandboxLifecycleState.DESTROYED,
            *_FAILURE_STATES,
        }
    ),
    SandboxLifecycleState.REPOSITORY_STAGED: frozenset(
        {SandboxLifecycleState.SETUP, SandboxLifecycleState.DESTROYED, *_FAILURE_STATES}
    ),
    SandboxLifecycleState.SETUP: frozenset(
        {
            SandboxLifecycleState.READY,
            SandboxLifecycleState.SETUP_FAILED,
            SandboxLifecycleState.DESTROYED,
            *_FAILURE_STATES,
        }
    ),
    SandboxLifecycleState.READY: frozenset(
        {SandboxLifecycleState.CODING_OFFLINE, SandboxLifecycleState.DESTROYED, *_FAILURE_STATES}
    ),
    SandboxLifecycleState.CODING_OFFLINE: frozenset(
        {
            SandboxLifecycleState.COLLECTING,
            SandboxLifecycleState.COMMAND_FAILED,
            SandboxLifecycleState.DESTROYED,
            *_FAILURE_STATES,
        }
    ),
    SandboxLifecycleState.COLLECTING: frozenset(
        {SandboxLifecycleState.DESTROYED, *_FAILURE_STATES}
    ),
    **{
        failure: frozenset({SandboxLifecycleState.DESTROYED, SandboxLifecycleState.CLEANUP_FAILED})
        for failure in _FAILURE_STATES
        if failure is not SandboxLifecycleState.CLEANUP_FAILED
    },
    SandboxLifecycleState.CLEANUP_FAILED: frozenset({SandboxLifecycleState.DESTROYED}),
    SandboxLifecycleState.DESTROYED: frozenset(),
}


class SandboxError(RuntimeError):
    """Base stable error for a sandbox control-plane failure."""


class SandboxPolicyDenied(SandboxError):
    """The requested transition or operation is outside the closed policy."""


class SandboxUnavailable(SandboxError):
    """A real isolation engine is absent or has not been proven usable."""


class DockerAvailability(NonZeroContract):
    available: bool
    status: Literal[
        "AVAILABLE",
        "DOCKER_EXECUTABLE_MISSING",
        "DOCKER_EXECUTABLE_INVALID",
        "DOCKER_DAEMON_UNPROVEN",
    ]
    engine_path_sha256: Sha256Digest | None = None
    host_install_attempted: Literal[False] = False

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.available != (self.status == "AVAILABLE"):
            raise ValueError("Docker availability status is contradictory")
        if self.available and self.engine_path_sha256 is None:
            raise ValueError("available Docker requires a content identity")
        return self


class DockerInvocationPlan(NonZeroContract):
    """Inspectable structured argv; it is not proof that Docker executed it."""

    phase: Literal["STAGE", "SETUP", "CODING_OFFLINE", "COLLECT", "CLEANUP"]
    argv: tuple[str, ...] = Field(min_length=2, max_length=96)
    network_mode: Literal["NONE"]
    privileged: Literal[False] = False
    host_bind_mounts: Literal[0] = 0
    docker_socket_mounts: Literal[0] = 0
    host_home_mounts: Literal[0] = 0
    structured_argv: Literal[True] = True

    @field_validator("argv")
    @classmethod
    def validate_argv(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not part or "\x00" in part or "\n" in part or "\r" in part for part in value):
            raise ValueError("Docker invocation argv contains an invalid element")
        rendered = " ".join(value)
        if contains_sensitive_material(value):
            raise ValueError("Docker invocation contains credential-shaped material")
        forbidden = (
            "--privileged",
            "/var/run/docker.sock",
            "/run/docker.sock",
            "/home/",
            "/.aws",
            "/.ssh",
            "/.config",
        )
        if any(item in rendered for item in forbidden):
            raise ValueError("Docker invocation contains a forbidden authority path/flag")
        return value


class SandboxLifecycle:
    """In-memory transition guard; receipts remain the durable evidence boundary."""

    def __init__(self, reference: SandboxRef) -> None:
        if reference.state is not SandboxLifecycleState.CREATED:
            raise SandboxPolicyDenied("SANDBOX_LIFECYCLE_MUST_START_CREATED")
        self._reference = reference
        self._history = [reference.state]

    @property
    def reference(self) -> SandboxRef:
        return self._reference

    @property
    def history(self) -> tuple[SandboxLifecycleState, ...]:
        return tuple(self._history)

    def transition(self, target: SandboxLifecycleState) -> SandboxRef:
        if not isinstance(target, SandboxLifecycleState):
            raise SandboxPolicyDenied("SANDBOX_STATE_UNKNOWN")
        if target not in _TRANSITIONS[self._reference.state]:
            raise SandboxPolicyDenied("SANDBOX_STATE_TRANSITION_DENIED")
        self._reference = self._reference.model_copy(update={"state": target})
        self._history.append(target)
        return self._reference


@runtime_checkable
class SandboxProvider(Protocol):
    """Implementation-neutral Phase 4 target surface; no GitHub/AWS methods."""

    def availability(self) -> DockerAvailability: ...

    def create(self, policy: SandboxPolicy) -> SandboxRef: ...

    def stage_repository(
        self,
        source: Path,
        expected_identity: RepositorySourceIdentity,
    ) -> StagedRepoRef: ...

    def setup_environment(self, setup_plan: SetupPlan) -> SetupReceipt: ...

    def exec(self, command: SandboxCommand) -> CommandReceipt: ...

    def read_file(self, relative_path: str, max_bytes: int) -> FileReceipt: ...

    def write_file(
        self,
        relative_path: str,
        content: bytes,
        policy: SandboxPolicy,
    ) -> WriteReceipt: ...

    def snapshot(self) -> SnapshotRef: ...

    def restore(self, snapshot: SnapshotRef) -> SandboxRef: ...

    def collect_diff(self, base_identity: RepositorySourceIdentity) -> DiffReceipt: ...

    def destroy(self) -> CleanupReceipt: ...


class DockerCommandPlanBuilder:
    """Build hardened Docker argv without executing or broadening authority."""

    def __init__(
        self,
        engine_path: str,
        toolbox: DockerToolboxIdentity,
        policy: SandboxPolicy,
    ) -> None:
        path = Path(engine_path)
        if not path.is_absolute() or path.as_posix() != engine_path:
            raise ValueError("Docker engine path must be canonical and absolute")
        self._engine = engine_path
        self._toolbox = toolbox
        self._policy = policy

    def setup(self, reference: SandboxRef, plan: SetupPlan) -> DockerInvocationPlan:
        if plan.repository_tree_sha256 == "0" * 64:
            raise SandboxPolicyDenied("SANDBOX_SETUP_SOURCE_IDENTITY_INVALID")
        argv = (
            *self._base(reference),
            *self._environment_flags({item.name: item.value for item in plan.environment}),
            self._toolbox.image_reference,
            *plan.argv,
        )
        return DockerInvocationPlan(
            phase="SETUP",
            argv=argv,
            network_mode="NONE",
        )

    def offline(
        self,
        reference: SandboxRef,
        command: SandboxCommand,
        inherited_environment: Mapping[str, str] | None = None,
    ) -> DockerInvocationPlan:
        environment = dict(inherited_environment or {})
        environment.update({item.name: item.value for item in command.environment})
        argv = (
            *self._base(reference),
            *self._environment_flags(environment),
            self._toolbox.image_reference,
            *command.argv,
        )
        return DockerInvocationPlan(phase="CODING_OFFLINE", argv=argv, network_mode="NONE")

    def staging_container(self, reference: SandboxRef) -> DockerInvocationPlan:
        base = self._base(reference)
        argv = (
            base[0],
            "create",
            *base[3:],
            self._toolbox.image_reference,
            "true",
        )
        return DockerInvocationPlan(phase="STAGE", argv=argv, network_mode="NONE")

    def package_manager_version(
        self,
        reference: SandboxRef,
        ecosystem: Literal["PYTHON", "NODE"],
    ) -> DockerInvocationPlan:
        command = (
            ("python", "-P", "-m", "pip", "--version")
            if ecosystem == "PYTHON"
            else ("npm", "--version")
        )
        return self._internal(reference, command)

    def read_file(self, reference: SandboxRef, relative_path: str) -> DockerInvocationPlan:
        return self._internal(
            reference,
            ("aioa-read-file", normalize_sandbox_relative_path(relative_path)),
        )

    def atomic_write(self, reference: SandboxRef, relative_path: str) -> DockerInvocationPlan:
        return self._internal(
            reference,
            ("aioa-atomic-write", normalize_sandbox_relative_path(relative_path)),
        )

    def workspace_probe(
        self,
        reference: SandboxRef,
        mode: Literal["source", "working", "setup"],
        *,
        phase: Literal["STAGE", "COLLECT"] = "COLLECT",
    ) -> DockerInvocationPlan:
        return self._internal(reference, ("aioa-workspace-probe", mode), phase=phase)

    def runtime_probe(self, reference: SandboxRef) -> DockerInvocationPlan:
        return self._internal(reference, ("aioa-runtime-probe",))

    def _internal(
        self,
        reference: SandboxRef,
        command: tuple[str, ...],
        *,
        phase: Literal["STAGE", "COLLECT"] = "COLLECT",
    ) -> DockerInvocationPlan:
        argv = (
            *self._base(reference),
            self._toolbox.image_reference,
            *command,
        )
        return DockerInvocationPlan(phase=phase, argv=argv, network_mode="NONE")

    def cleanup(self, reference: SandboxRef) -> DockerInvocationPlan:
        return DockerInvocationPlan(
            phase="CLEANUP",
            argv=(self._engine, "volume", "rm", reference.workspace_volume),
            network_mode="NONE",
        )

    def _base(self, reference: SandboxRef) -> tuple[str, ...]:
        limits = self._policy.limits
        return (
            self._engine,
            "run",
            "--rm",
            "--interactive",
            "--pull=never",
            f"--name={reference.resource_name}",
            f"--label=dev.aioa.sandbox-id={reference.sandbox_id}",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            f"--pids-limit={limits.pids}",
            f"--memory={limits.memory_mebibytes}m",
            f"--cpus={limits.cpu_count:.1f}",
            f"--ulimit=nofile={limits.open_files}:{limits.open_files}",
            f"--user={self._policy.run_as_user}",
            "--workdir=/workspace",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m,mode=1777",
            f"--mount=type=volume,src={reference.workspace_volume},dst=/workspace",
            "--network=none",
        )

    @staticmethod
    def _environment_flags(source: Mapping[str, str]) -> tuple[str, ...]:
        fixed = {
            "HOME": "/workspace",
            "LANG": "C.UTF-8",
            "PATH": "/usr/local/bin:/usr/bin:/bin",
            "PYTHONDONTWRITEBYTECODE": "1",
            **source,
        }
        if any(contains_sensitive_material({name: value}) for name, value in fixed.items()):
            raise SandboxPolicyDenied("SANDBOX_ENVIRONMENT_SECRET_DENIED")
        return tuple(
            item for name, value in sorted(fixed.items()) for item in ("--env", f"{name}={value}")
        )


class DockerSandboxProvider:
    """Stateful, single-sandbox boundary for a certified rootless Docker toolbox."""

    def __init__(
        self,
        engine_path: str | None = None,
        *,
        toolbox: DockerToolboxIdentity | None = None,
    ) -> None:
        self._engine_path = engine_path or shutil.which("docker")
        self._availability = _inspect_docker_executable(self._engine_path)
        self._toolbox = toolbox
        self._cli: DockerCli | None = None
        self._policy: SandboxPolicy | None = None
        self._reference: SandboxRef | None = None
        self._lifecycle: SandboxLifecycle | None = None
        self._builder: DockerCommandPlanBuilder | None = None
        self._source_identity: RepositorySourceIdentity | None = None
        self._base_records: dict[str, tuple[str, int]] = {}
        self._setup_plan: SetupPlan | None = None
        self._environment_manifest_sha256 = canonical_sandbox_digest([])
        if (
            toolbox is not None
            and self._engine_path is not None
            and self._availability.status == "DOCKER_DAEMON_UNPROVEN"
        ):
            self._cli = DockerCli(self._engine_path)
            try:
                self._certify_runtime(toolbox)
            except (DockerCliFailure, ValueError, json.JSONDecodeError, KeyError, TypeError):
                self._cli = None
            else:
                self._availability = self._availability.model_copy(
                    update={"available": True, "status": "AVAILABLE"}
                )

    def availability(self) -> DockerAvailability:
        return self._availability

    def create(self, policy: SandboxPolicy) -> SandboxRef:
        if not isinstance(policy, SandboxPolicy):
            raise SandboxPolicyDenied("SANDBOX_POLICY_INVALID")
        cli, toolbox = self._runtime()
        if self._reference is not None:
            raise SandboxPolicyDenied("SANDBOX_PROVIDER_ALREADY_OWNS_RESOURCE")
        reference = new_sandbox_ref(policy)
        result = cli.checked(
            (
                "volume",
                "create",
                "--label=dev.aioa.owner=w7a",
                f"--label=dev.aioa.sandbox-id={reference.sandbox_id}",
                reference.workspace_volume,
            ),
            failure_code="SANDBOX_VOLUME_CREATE_FAILED",
        )
        if result.stdout.decode("utf-8", errors="strict").strip() != reference.workspace_volume:
            raise SandboxUnavailable("SANDBOX_VOLUME_IDENTITY_MISMATCH")
        self._policy = policy
        self._reference = reference
        self._lifecycle = SandboxLifecycle(reference)
        self._builder = DockerCommandPlanBuilder(self._engine_path or "", toolbox, policy)
        try:
            empty = self._probe_workspace("working", phase="STAGE")
            if empty["file_count"] != 0:
                raise SandboxUnavailable("SANDBOX_VOLUME_NOT_EMPTY")
        except BaseException:
            self._remove_owned_resources(best_effort=True)
            self._clear_state()
            raise
        return reference

    def stage_repository(
        self,
        source: Path,
        expected_identity: RepositorySourceIdentity,
    ) -> StagedRepoRef:
        reference, lifecycle, builder, cli = self._active()
        if lifecycle.reference.state is not SandboxLifecycleState.CREATED:
            raise SandboxPolicyDenied("SANDBOX_STAGE_STATE_INVALID")
        if not isinstance(expected_identity, RepositorySourceIdentity):
            raise SandboxPolicyDenied("SANDBOX_SOURCE_IDENTITY_INVALID")
        observed = DeterministicSetupPlanner().inspect_repository(
            source,
            source_commit=expected_identity.source_commit,
        )
        if observed != expected_identity:
            raise SandboxPolicyDenied("SANDBOX_SOURCE_IDENTITY_MISMATCH")
        archive, records = _build_staging_archive(source)
        staging = builder.staging_container(reference)
        self._run_plan(staging, failure_code="SANDBOX_STAGE_CONTAINER_CREATE_FAILED")
        try:
            cli.checked(
                ("cp", "-", f"{reference.resource_name}:/workspace"),
                stdin=archive,
                timeout_seconds=60.0,
                output_limit=1024 * 1024,
                failure_code="SANDBOX_STAGE_COPY_FAILED",
            )
        finally:
            self._remove_owned_container(best_effort=False)
        probe = self._probe_workspace("source", phase="STAGE")
        if (
            probe["tree_sha256"] != expected_identity.tree_sha256
            or probe["file_count"] != expected_identity.file_count
            or probe["total_bytes"] != expected_identity.total_bytes
        ):
            raise SandboxUnavailable("SANDBOX_STAGED_SOURCE_VERIFICATION_FAILED")
        lifecycle.transition(SandboxLifecycleState.REPOSITORY_STAGED)
        self._source_identity = expected_identity
        self._base_records = records
        return StagedRepoRef(
            sandbox_id=reference.sandbox_id,
            repository=expected_identity,
            archive_sha256=hashlib.sha256(archive).hexdigest(),
        )

    def setup_environment(self, setup_plan: SetupPlan) -> SetupReceipt:
        reference, lifecycle, builder, _ = self._active()
        if lifecycle.reference.state is not SandboxLifecycleState.REPOSITORY_STAGED:
            raise SandboxPolicyDenied("SANDBOX_SETUP_STATE_INVALID")
        if (
            self._source_identity is None
            or setup_plan.repository_tree_sha256 != self._source_identity.tree_sha256
        ):
            raise SandboxPolicyDenied("SANDBOX_SETUP_SOURCE_IDENTITY_MISMATCH")
        lifecycle.transition(SandboxLifecycleState.SETUP)
        invocation = builder.setup(reference, setup_plan)
        try:
            result = self._run_plan(
                invocation,
                timeout_seconds=self._require_policy().limits.command_timeout_seconds,
                failure_code="SANDBOX_SETUP_COMMAND_FAILED",
            )
            probe = self._probe_workspace("setup")
            if probe["file_count"] <= 0:
                raise SandboxUnavailable("SANDBOX_SETUP_MANIFEST_EMPTY")
            version = (
                self._run_plan(
                    builder.package_manager_version(
                        reference,
                        "PYTHON" if setup_plan.ecosystem.value.startswith("PYTHON") else "NODE",
                    ),
                    failure_code="SANDBOX_PACKAGE_MANAGER_VERSION_FAILED",
                )
                .stdout.decode("utf-8", errors="strict")
                .strip()
            )
            if not version or len(version) > 128:
                raise SandboxUnavailable("SANDBOX_PACKAGE_MANAGER_VERSION_INVALID")
        except BaseException:
            self._remove_owned_container(best_effort=True)
            lifecycle.transition(SandboxLifecycleState.SETUP_FAILED)
            raise
        lifecycle.transition(SandboxLifecycleState.READY)
        self._setup_plan = setup_plan
        self._environment_manifest_sha256 = str(probe["tree_sha256"])
        return SetupReceipt(
            sandbox_id=reference.sandbox_id,
            plan_sha256=setup_plan.plan_sha256,
            ecosystem=setup_plan.ecosystem,
            package_manager_version=version,
            duration_milliseconds=result.duration_milliseconds,
            stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
            stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),
            installed_manifest_sha256=self._environment_manifest_sha256,
            toolbox_image_sha256=self._require_toolbox().image_digest,
        )

    def exec(self, command: SandboxCommand) -> CommandReceipt:
        reference, lifecycle, builder, _ = self._active()
        if lifecycle.reference.state is SandboxLifecycleState.READY:
            lifecycle.transition(SandboxLifecycleState.CODING_OFFLINE)
        if lifecycle.reference.state is not SandboxLifecycleState.CODING_OFFLINE:
            raise SandboxPolicyDenied("SANDBOX_COMMAND_STATE_INVALID")
        if self._setup_plan is None:
            raise SandboxPolicyDenied("SANDBOX_COMMAND_SETUP_REQUIRED")
        inherited = {item.name: item.value for item in self._setup_plan.environment}
        invocation = builder.offline(reference, command, inherited)
        try:
            result = self._run_plan(
                invocation,
                timeout_seconds=min(
                    command.timeout_seconds,
                    self._require_policy().limits.command_timeout_seconds,
                ),
                output_limit=self._require_policy().limits.output_bytes,
                allow_nonzero=True,
                failure_code="SANDBOX_COMMAND_EXECUTION_FAILED",
            )
        except DockerCliFailure as error:
            self._remove_owned_container(best_effort=True)
            timed_out = error.code in {"DOCKER_CLI_TIMEOUT", "DOCKER_CLI_WAIT_TIMEOUT"}
            state = (
                SandboxLifecycleState.RESOURCE_LIMIT
                if timed_out
                else SandboxLifecycleState.COMMAND_FAILED
            )
            lifecycle.transition(state)
            return CommandReceipt(
                sandbox_id=reference.sandbox_id,
                profile=command.profile,
                argv_sha256=canonical_sandbox_digest(list(command.argv)),
                exit_code=124 if timed_out else (error.returncode or 1),
                duration_milliseconds=0,
                stdout_sha256=hashlib.sha256(b"").hexdigest(),
                stderr_sha256=hashlib.sha256(b"").hexdigest(),
                output_truncated=not timed_out,
                state=state,
            )
        if result.returncode == 0:
            state = SandboxLifecycleState.CODING_OFFLINE
        elif result.returncode == 137:
            state = SandboxLifecycleState.RESOURCE_LIMIT
        elif result.returncode in {132, 133, 134, 135, 136, 138, 139}:
            state = SandboxLifecycleState.SANDBOX_CRASHED
        else:
            state = SandboxLifecycleState.COMMAND_FAILED
        if state is not SandboxLifecycleState.CODING_OFFLINE:
            lifecycle.transition(state)
        return CommandReceipt(
            sandbox_id=reference.sandbox_id,
            profile=command.profile,
            argv_sha256=canonical_sandbox_digest(list(command.argv)),
            exit_code=result.returncode,
            duration_milliseconds=result.duration_milliseconds,
            stdout_sha256=hashlib.sha256(result.stdout).hexdigest(),
            stderr_sha256=hashlib.sha256(result.stderr).hexdigest(),
            output_truncated=result.output_truncated,
            state=state,
        )

    def read_file(self, relative_path: str, max_bytes: int) -> FileReceipt:
        normalize_sandbox_relative_path(relative_path)
        if isinstance(max_bytes, bool) or not 1 <= max_bytes <= 16 * 1024 * 1024:
            raise SandboxPolicyDenied("SANDBOX_READ_BOUND_INVALID")
        reference, lifecycle, builder, _ = self._active()
        if lifecycle.reference.state not in {
            SandboxLifecycleState.READY,
            SandboxLifecycleState.CODING_OFFLINE,
        }:
            raise SandboxPolicyDenied("SANDBOX_READ_STATE_INVALID")
        result = self._run_plan(
            builder.read_file(reference, relative_path),
            output_limit=max(1024, max_bytes + 1),
            failure_code="SANDBOX_READ_FAILED",
        )
        if len(result.stdout) > max_bytes:
            raise SandboxPolicyDenied("SANDBOX_READ_SIZE_EXCEEDED")
        return FileReceipt(
            sandbox_id=reference.sandbox_id,
            relative_path=relative_path,
            sha256=hashlib.sha256(result.stdout).hexdigest(),
            size=len(result.stdout),
        )

    def write_file(
        self,
        relative_path: str,
        content: bytes,
        policy: SandboxPolicy,
    ) -> WriteReceipt:
        normalize_sandbox_relative_path(relative_path)
        if not isinstance(content, bytes) or len(content) > 16 * 1024 * 1024:
            raise SandboxPolicyDenied("SANDBOX_WRITE_BOUND_INVALID")
        if not isinstance(policy, SandboxPolicy):
            raise SandboxPolicyDenied("SANDBOX_POLICY_INVALID")
        reference, lifecycle, builder, _ = self._active()
        if lifecycle.reference.state is SandboxLifecycleState.READY:
            lifecycle.transition(SandboxLifecycleState.CODING_OFFLINE)
        if lifecycle.reference.state is not SandboxLifecycleState.CODING_OFFLINE:
            raise SandboxPolicyDenied("SANDBOX_WRITE_STATE_INVALID")
        if policy.policy_sha256 != self._require_policy().policy_sha256:
            raise SandboxPolicyDenied("SANDBOX_WRITE_POLICY_MISMATCH")
        result = self._run_plan(
            builder.atomic_write(reference, relative_path),
            stdin=content,
            output_limit=4096,
            failure_code="SANDBOX_WRITE_FAILED",
        )
        payload = _json_object(result.stdout, "SANDBOX_WRITE_RECEIPT_INVALID")
        expected_sha256 = hashlib.sha256(content).hexdigest()
        if payload.get("sha256") != expected_sha256 or payload.get("size") != len(content):
            raise SandboxUnavailable("SANDBOX_WRITE_VERIFICATION_FAILED")
        previous = payload.get("previous_sha256")
        if previous is not None and not isinstance(previous, str):
            raise SandboxUnavailable("SANDBOX_WRITE_RECEIPT_INVALID")
        return WriteReceipt(
            sandbox_id=reference.sandbox_id,
            relative_path=relative_path,
            sha256=expected_sha256,
            size=len(content),
            previous_sha256=previous,
        )

    def snapshot(self) -> SnapshotRef:
        reference, lifecycle, _, _ = self._active()
        if lifecycle.reference.state not in {
            SandboxLifecycleState.READY,
            SandboxLifecycleState.CODING_OFFLINE,
        }:
            raise SandboxPolicyDenied("SANDBOX_SNAPSHOT_STATE_INVALID")
        working = self._probe_workspace("working")
        return SnapshotRef(
            sandbox_id=reference.sandbox_id,
            repository_tree_sha256=str(working["tree_sha256"]),
            environment_manifest_sha256=self._environment_manifest_sha256,
        )

    def restore(self, snapshot: SnapshotRef) -> SandboxRef:
        reference, lifecycle, _, _ = self._active()
        if snapshot.sandbox_id != reference.sandbox_id:
            raise SandboxPolicyDenied("SANDBOX_SNAPSHOT_IDENTITY_MISMATCH")
        if lifecycle.reference.state not in {
            SandboxLifecycleState.READY,
            SandboxLifecycleState.CODING_OFFLINE,
        }:
            raise SandboxPolicyDenied("SANDBOX_RESTORE_STATE_INVALID")
        working = self._probe_workspace("working")
        setup = self._probe_workspace("setup")
        if (
            working["tree_sha256"] != snapshot.repository_tree_sha256
            or setup["tree_sha256"] != snapshot.environment_manifest_sha256
        ):
            raise SandboxPolicyDenied("SANDBOX_MANIFEST_ONLY_SNAPSHOT_DRIFT")
        return lifecycle.reference

    def collect_diff(self, base_identity: RepositorySourceIdentity) -> DiffReceipt:
        reference, lifecycle, _, _ = self._active()
        if self._source_identity != base_identity:
            raise SandboxPolicyDenied("SANDBOX_DIFF_BASE_IDENTITY_MISMATCH")
        if lifecycle.reference.state is SandboxLifecycleState.READY:
            lifecycle.transition(SandboxLifecycleState.CODING_OFFLINE)
        if lifecycle.reference.state is not SandboxLifecycleState.CODING_OFFLINE:
            raise SandboxPolicyDenied("SANDBOX_DIFF_STATE_INVALID")
        lifecycle.transition(SandboxLifecycleState.COLLECTING)
        probe = self._probe_workspace("working")
        current = _records_from_probe(probe)
        changed = tuple(
            sorted(
                path
                for path in set(self._base_records) | set(current)
                if self._base_records.get(path) != current.get(path)
            )
        )
        material = {
            "base_tree_sha256": base_identity.tree_sha256,
            "current_tree_sha256": probe["tree_sha256"],
            "changed_paths": list(changed),
        }
        return DiffReceipt(
            sandbox_id=reference.sandbox_id,
            base_tree_sha256=base_identity.tree_sha256,
            current_tree_sha256=str(probe["tree_sha256"]),
            changed_paths=changed,
            diff_sha256=canonical_sandbox_digest(material),
        )

    def destroy(self) -> CleanupReceipt:
        reference, lifecycle, _, _ = self._active()
        try:
            self._remove_owned_resources(best_effort=False)
            if self._owned_resources_remaining():
                raise SandboxUnavailable("SANDBOX_CLEANUP_ORPHANS_REMAIN")
        except BaseException:
            if lifecycle.reference.state is not SandboxLifecycleState.CLEANUP_FAILED:
                lifecycle.transition(SandboxLifecycleState.CLEANUP_FAILED)
            raise
        if lifecycle.reference.state is not SandboxLifecycleState.DESTROYED:
            lifecycle.transition(SandboxLifecycleState.DESTROYED)
        receipt = CleanupReceipt(
            sandbox_id=reference.sandbox_id,
            owned_resource_name=reference.resource_name,
        )
        self._clear_state()
        return receipt

    def _runtime(self) -> tuple[DockerCli, DockerToolboxIdentity]:
        if not self._availability.available or self._cli is None or self._toolbox is None:
            self._blocked()
        return self._cli, self._toolbox

    def _active(
        self,
    ) -> tuple[SandboxRef, SandboxLifecycle, DockerCommandPlanBuilder, DockerCli]:
        cli, _ = self._runtime()
        if self._reference is None or self._lifecycle is None or self._builder is None:
            raise SandboxPolicyDenied("SANDBOX_RESOURCE_NOT_CREATED")
        return self._reference, self._lifecycle, self._builder, cli

    def _certify_runtime(self, toolbox: DockerToolboxIdentity) -> None:
        if self._cli is None:
            raise DockerCliFailure("DOCKER_CLI_UNAVAILABLE")
        version = self._cli.checked(
            ("version", "--format", "{{.Server.Version}}"),
            failure_code="DOCKER_DAEMON_UNAVAILABLE",
        )
        if not version.stdout.strip():
            raise DockerCliFailure("DOCKER_SERVER_VERSION_EMPTY")
        info = self._cli.checked(
            ("info", "--format", "{{json .SecurityOptions}}"),
            failure_code="DOCKER_INFO_UNAVAILABLE",
        )
        if "rootless" not in info.stdout.decode("utf-8", errors="strict").casefold():
            raise DockerCliFailure("DOCKER_ROOTLESS_REQUIRED")
        inspected = self._cli.checked(
            ("image", "inspect", toolbox.image_reference),
            failure_code="DOCKER_TOOLBOX_IMAGE_UNAVAILABLE",
            output_limit=1024 * 1024,
        )
        payload = json.loads(inspected.stdout)
        if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
            raise ValueError("Docker image inspection result is invalid")
        image = payload[0]
        config = image["Config"]
        labels = config.get("Labels") or {}
        if (
            image.get("Id") != f"sha256:{toolbox.image_digest}"
            or config.get("User") != toolbox.non_root_user
            or config.get("WorkingDir") != "/workspace"
            or labels.get("org.opencontainers.image.revision") != toolbox.source_commit
            or labels.get("dev.aioa.sandbox.policy") != "DOCKER_SANDBOX_V1"
        ):
            raise ValueError("Docker toolbox identity does not match the certified contract")

    def _run_plan(
        self,
        plan: DockerInvocationPlan,
        *,
        stdin: bytes = b"",
        timeout_seconds: float = 30.0,
        output_limit: int = 128 * 1024,
        allow_nonzero: bool = False,
        failure_code: str,
    ) -> DockerCliResult:
        cli, _ = self._runtime()
        if plan.argv[0] != self._engine_path:
            raise SandboxPolicyDenied("SANDBOX_DOCKER_ENGINE_IDENTITY_MISMATCH")
        result = cli.run(
            plan.argv[1:],
            stdin=stdin,
            timeout_seconds=timeout_seconds,
            output_limit=output_limit,
        )
        if result.output_truncated or (result.returncode != 0 and not allow_nonzero):
            raise DockerCliFailure(failure_code, returncode=result.returncode)
        return result

    def _probe_workspace(
        self,
        mode: Literal["source", "working", "setup"],
        *,
        phase: Literal["STAGE", "COLLECT"] = "COLLECT",
    ) -> dict[str, object]:
        reference, _, builder, _ = self._active()
        result = self._run_plan(
            builder.workspace_probe(reference, mode, phase=phase),
            output_limit=128 * 1024,
            failure_code="SANDBOX_WORKSPACE_PROBE_FAILED",
        )
        payload = _json_object(result.stdout, "SANDBOX_WORKSPACE_PROBE_INVALID")
        if (
            payload.get("mode") != mode
            or payload.get("uid") != 65532
            or payload.get("gid") != 65532
            or payload.get("sensitive_environment_names") != []
        ):
            raise SandboxUnavailable("SANDBOX_WORKSPACE_PROBE_CONTRACT_FAILED")
        _records_from_probe(payload)
        return payload

    def _remove_owned_container(self, *, best_effort: bool) -> None:
        if self._reference is None or self._cli is None:
            return
        result = self._cli.run(
            ("container", "inspect", self._reference.resource_name),
            output_limit=1024 * 1024,
        )
        if result.returncode != 0:
            return
        payload = json.loads(result.stdout)
        labels = payload[0].get("Config", {}).get("Labels", {})
        if labels.get("dev.aioa.sandbox-id") != str(self._reference.sandbox_id):
            if best_effort:
                return
            raise SandboxPolicyDenied("SANDBOX_CONTAINER_OWNERSHIP_MISMATCH")
        removal = self._cli.run(("rm", "-f", self._reference.resource_name))
        if removal.returncode != 0 and not best_effort:
            raise SandboxUnavailable("SANDBOX_CONTAINER_CLEANUP_FAILED")

    def _remove_owned_resources(self, *, best_effort: bool) -> None:
        if self._reference is None or self._cli is None:
            return
        self._remove_owned_container(best_effort=best_effort)
        inspection = self._cli.run(("volume", "inspect", self._reference.workspace_volume))
        if inspection.returncode != 0:
            if best_effort:
                return
            raise SandboxUnavailable("SANDBOX_VOLUME_MISSING_DURING_CLEANUP")
        payload = json.loads(inspection.stdout)
        labels = payload[0].get("Labels") or {}
        if labels.get("dev.aioa.sandbox-id") != str(self._reference.sandbox_id):
            if best_effort:
                return
            raise SandboxPolicyDenied("SANDBOX_VOLUME_OWNERSHIP_MISMATCH")
        removal = self._cli.run(("volume", "rm", self._reference.workspace_volume))
        if removal.returncode != 0 and not best_effort:
            raise SandboxUnavailable("SANDBOX_VOLUME_CLEANUP_FAILED")

    def _owned_resources_remaining(self) -> bool:
        if self._reference is None or self._cli is None:
            return False
        container = self._cli.run(("container", "inspect", self._reference.resource_name))
        volume = self._cli.run(("volume", "inspect", self._reference.workspace_volume))
        return container.returncode == 0 or volume.returncode == 0

    def _clear_state(self) -> None:
        self._policy = None
        self._reference = None
        self._lifecycle = None
        self._builder = None
        self._source_identity = None
        self._base_records = {}
        self._setup_plan = None
        self._environment_manifest_sha256 = canonical_sandbox_digest([])

    def _require_policy(self) -> SandboxPolicy:
        if self._policy is None:
            raise SandboxPolicyDenied("SANDBOX_POLICY_NOT_BOUND")
        return self._policy

    def _require_toolbox(self) -> DockerToolboxIdentity:
        if self._toolbox is None:
            raise SandboxPolicyDenied("SANDBOX_TOOLBOX_NOT_BOUND")
        return self._toolbox

    def _blocked(self) -> None:
        if self._availability.status == "DOCKER_EXECUTABLE_MISSING":
            raise SandboxUnavailable("SANDBOX_DOCKER_EXECUTABLE_MISSING")
        if self._availability.status == "DOCKER_EXECUTABLE_INVALID":
            raise SandboxUnavailable("SANDBOX_DOCKER_EXECUTABLE_INVALID")
        raise SandboxUnavailable("SANDBOX_DOCKER_DAEMON_AND_TOOLBOX_UNCERTIFIED")


def _build_staging_archive(source: Path) -> tuple[bytes, dict[str, tuple[str, int]]]:
    buffer = io.BytesIO()
    records: dict[str, tuple[str, int]] = {}
    total_bytes = 0
    with tarfile.open(fileobj=buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for candidate in sorted(source.rglob("*")):
            relative = candidate.relative_to(source).as_posix()
            metadata = candidate.lstat()
            parts = PurePosixPath(relative).parts
            folded_parts = tuple(part.casefold() for part in parts)
            if not parts or folded_parts[0] == ".git":
                raise SandboxPolicyDenied("SANDBOX_STAGE_GIT_AUTHORITY_DENIED")
            if folded_parts[0] in {".aws", ".ssh"} or folded_parts[-1] in {
                ".env",
                "credentials",
            }:
                raise SandboxPolicyDenied("SANDBOX_STAGE_SECRET_PATH_DENIED")
            if stat.S_ISLNK(metadata.st_mode):
                raise SandboxPolicyDenied("SANDBOX_STAGE_LINK_DENIED")
            item = tarfile.TarInfo(relative + ("/" if stat.S_ISDIR(metadata.st_mode) else ""))
            item.uid = 65532
            item.gid = 65532
            item.uname = ""
            item.gname = ""
            item.mtime = 0
            item.mode = metadata.st_mode & 0o777
            if stat.S_ISDIR(metadata.st_mode):
                item.type = tarfile.DIRTYPE
                archive.addfile(item)
                continue
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1:
                raise SandboxPolicyDenied("SANDBOX_STAGE_FILE_TYPE_DENIED")
            content = _secure_stage_read(source, relative, metadata)
            total_bytes += len(content)
            if len(records) >= 256 or total_bytes > 16 * 1024 * 1024:
                raise SandboxPolicyDenied("SANDBOX_STAGE_SIZE_LIMIT_EXCEEDED")
            item.size = len(content)
            archive.addfile(item, io.BytesIO(content))
            records[relative] = (
                hashlib.sha256(content).hexdigest(),
                metadata.st_mode & 0o777,
            )
    return buffer.getvalue(), records


def _secure_stage_read(source: Path, relative: str, expected: os.stat_result) -> bytes:
    """Read one staged file through no-follow descriptors and reject source drift."""

    file_flags = os.O_RDONLY | os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0)
    directory_flags = file_flags | getattr(os, "O_DIRECTORY", 0)
    descriptors: list[int] = []
    try:
        current = os.open(source, directory_flags)
        descriptors.append(current)
        parts = PurePosixPath(relative).parts
        for part in parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        descriptor = os.open(parts[-1], file_flags, dir_fd=current)
        descriptors.append(descriptor)
        before = os.fstat(descriptor)
        expected_identity = (
            expected.st_dev,
            expected.st_ino,
            expected.st_size,
            expected.st_mtime_ns,
        )
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_nlink != 1
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != expected_identity
            or before.st_size > 16 * 1024 * 1024
        ):
            raise SandboxPolicyDenied("SANDBOX_STAGE_SOURCE_DRIFT")
        content = bytearray()
        while len(content) < before.st_size:
            chunk = os.read(descriptor, min(64 * 1024, before.st_size - len(content)))
            if not chunk:
                raise SandboxPolicyDenied("SANDBOX_STAGE_SOURCE_SHORT_READ")
            content.extend(chunk)
        if os.read(descriptor, 1):
            raise SandboxPolicyDenied("SANDBOX_STAGE_SOURCE_GREW")
        after = os.fstat(descriptor)
        if (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
        ) != expected_identity:
            raise SandboxPolicyDenied("SANDBOX_STAGE_SOURCE_DRIFT")
        return bytes(content)
    except SandboxPolicyDenied:
        raise
    except OSError as error:
        raise SandboxPolicyDenied("SANDBOX_STAGE_SECURE_READ_FAILED") from error
    finally:
        for descriptor in reversed(descriptors):
            with suppress(OSError):
                os.close(descriptor)


def _json_object(raw: bytes, code: str) -> dict[str, object]:
    try:
        payload = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise SandboxUnavailable(code) from error
    if not isinstance(payload, dict):
        raise SandboxUnavailable(code)
    return payload


def _records_from_probe(payload: Mapping[str, object]) -> dict[str, tuple[str, int]]:
    raw_records = payload.get("records")
    if not isinstance(raw_records, list) or len(raw_records) > 256:
        raise SandboxUnavailable("SANDBOX_WORKSPACE_RECORDS_INVALID")
    normalized: list[tuple[str, str, int]] = []
    for record in raw_records:
        if not isinstance(record, list) or len(record) != 3:
            raise SandboxUnavailable("SANDBOX_WORKSPACE_RECORD_INVALID")
        path, digest, mode = record
        if not isinstance(path, str) or not path or len(path) > 1024:
            raise SandboxUnavailable("SANDBOX_WORKSPACE_PATH_INVALID")
        candidate = PurePosixPath(path)
        if candidate.is_absolute() or candidate.as_posix() != path or ".." in candidate.parts:
            raise SandboxUnavailable("SANDBOX_WORKSPACE_PATH_INVALID")
        if (
            not isinstance(digest, str)
            or len(digest) != 64
            or any(character not in "0123456789abcdef" for character in digest)
            or not isinstance(mode, int)
            or isinstance(mode, bool)
            or not 0 <= mode <= 0o777
        ):
            raise SandboxUnavailable("SANDBOX_WORKSPACE_RECORD_INVALID")
        normalized.append((path, digest, mode))
    if normalized != sorted(normalized) or len({item[0] for item in normalized}) != len(normalized):
        raise SandboxUnavailable("SANDBOX_WORKSPACE_RECORD_ORDER_INVALID")
    encoded = json.dumps(normalized, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    expected_tree = hashlib.sha256(encoded).hexdigest()
    if (
        payload.get("file_count") != len(normalized)
        or payload.get("tree_sha256") != expected_tree
        or not isinstance(payload.get("total_bytes"), int)
        or not 0 <= int(payload["total_bytes"]) <= 16 * 1024 * 1024
    ):
        raise SandboxUnavailable("SANDBOX_WORKSPACE_IDENTITY_INVALID")
    return {path: (digest, mode) for path, digest, mode in normalized}


def new_sandbox_ref(policy: SandboxPolicy, *, now: datetime | None = None) -> SandboxRef:
    """Create an opaque owned identity for lifecycle and command-plan tests."""

    sandbox_id = generate_event_id()
    resource = f"aioa-w7a-{sandbox_id}"
    return SandboxRef(
        sandbox_id=sandbox_id,
        resource_name=resource,
        workspace_volume=resource,
        state=SandboxLifecycleState.CREATED,
        policy_sha256=policy.policy_sha256,
        created_at=now or datetime.now(UTC),
    )


def _inspect_docker_executable(engine_path: str | None) -> DockerAvailability:
    if engine_path is None:
        return DockerAvailability(available=False, status="DOCKER_EXECUTABLE_MISSING")
    path = Path(engine_path)
    try:
        metadata = path.lstat()
        resolved = path.resolve(strict=True)
    except OSError:
        return DockerAvailability(available=False, status="DOCKER_EXECUTABLE_INVALID")
    if (
        resolved != path
        or stat.S_ISLNK(metadata.st_mode)
        or not stat.S_ISREG(metadata.st_mode)
        or not os.access(path, os.X_OK)
    ):
        return DockerAvailability(available=False, status="DOCKER_EXECUTABLE_INVALID")
    digest = _sha256_file(path)
    return DockerAvailability(
        available=False,
        status="DOCKER_DAEMON_UNPROVEN",
        engine_path_sha256=digest,
    )


def _sha256_file(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
