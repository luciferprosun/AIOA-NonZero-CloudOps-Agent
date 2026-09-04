"""Provider-neutral sandbox surface and fail-closed Docker v1 scaffold."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
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
    normalize_sandbox_relative_path,
)

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
        {SandboxLifecycleState.REPOSITORY_STAGED, *_FAILURE_STATES}
    ),
    SandboxLifecycleState.REPOSITORY_STAGED: frozenset(
        {SandboxLifecycleState.SETUP, *_FAILURE_STATES}
    ),
    SandboxLifecycleState.SETUP: frozenset(
        {SandboxLifecycleState.READY, SandboxLifecycleState.SETUP_FAILED, *_FAILURE_STATES}
    ),
    SandboxLifecycleState.READY: frozenset(
        {SandboxLifecycleState.CODING_OFFLINE, *_FAILURE_STATES}
    ),
    SandboxLifecycleState.CODING_OFFLINE: frozenset(
        {SandboxLifecycleState.COLLECTING, SandboxLifecycleState.COMMAND_FAILED, *_FAILURE_STATES}
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
    network_mode: Literal["NONE", "PACKAGE_REGISTRY_ONLY"]
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
            *self._base(reference, network="aioa-w7a-package-registry-only"),
            *self._environment_flags({item.name: item.value for item in plan.environment}),
            self._toolbox.image_reference,
            *plan.argv,
        )
        return DockerInvocationPlan(
            phase="SETUP",
            argv=argv,
            network_mode="PACKAGE_REGISTRY_ONLY",
        )

    def offline(self, reference: SandboxRef, command: SandboxCommand) -> DockerInvocationPlan:
        environment = {item.name: item.value for item in command.environment}
        argv = (
            *self._base(reference, network="none"),
            *self._environment_flags(environment),
            self._toolbox.image_reference,
            *command.argv,
        )
        return DockerInvocationPlan(phase="CODING_OFFLINE", argv=argv, network_mode="NONE")

    def cleanup(self, reference: SandboxRef) -> DockerInvocationPlan:
        return DockerInvocationPlan(
            phase="CLEANUP",
            argv=(self._engine, "volume", "rm", reference.workspace_volume),
            network_mode="NONE",
        )

    def _base(self, reference: SandboxRef, *, network: str) -> tuple[str, ...]:
        limits = self._policy.limits
        return (
            self._engine,
            "run",
            "--rm",
            f"--name={reference.resource_name}",
            "--read-only",
            "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true",
            f"--pids-limit={limits.pids}",
            f"--memory={limits.memory_mebibytes}m",
            f"--cpus={limits.cpu_count:.1f}",
            f"--ulimit=nofile={limits.open_files}:{limits.open_files}",
            f"--user={self._policy.run_as_user}",
            "--workdir=/workspace",
            "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=64m",
            f"--mount=type=volume,src={reference.workspace_volume},dst=/workspace,rw",
            f"--network={network}",
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
    """Fail-closed Docker boundary for a host where Docker runtime is unavailable.

    The complete provider surface exists so orchestration does not bind directly to
    Docker. Runtime methods deliberately remain unavailable until an engine and the
    external content-addressed toolbox are independently certified.
    """

    def __init__(self, engine_path: str | None = None) -> None:
        self._engine_path = engine_path or shutil.which("docker")
        self._availability = _inspect_docker_executable(self._engine_path)

    def availability(self) -> DockerAvailability:
        return self._availability

    def create(self, policy: SandboxPolicy) -> SandboxRef:
        if not isinstance(policy, SandboxPolicy):
            raise SandboxPolicyDenied("SANDBOX_POLICY_INVALID")
        self._blocked()

    def stage_repository(
        self,
        source: Path,
        expected_identity: RepositorySourceIdentity,
    ) -> StagedRepoRef:
        del source, expected_identity
        self._blocked()

    def setup_environment(self, setup_plan: SetupPlan) -> SetupReceipt:
        del setup_plan
        self._blocked()

    def exec(self, command: SandboxCommand) -> CommandReceipt:
        del command
        self._blocked()

    def read_file(self, relative_path: str, max_bytes: int) -> FileReceipt:
        normalize_sandbox_relative_path(relative_path)
        if isinstance(max_bytes, bool) or not 1 <= max_bytes <= 16 * 1024 * 1024:
            raise SandboxPolicyDenied("SANDBOX_READ_BOUND_INVALID")
        self._blocked()

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
        self._blocked()

    def snapshot(self) -> SnapshotRef:
        self._blocked()

    def restore(self, snapshot: SnapshotRef) -> SandboxRef:
        del snapshot
        self._blocked()

    def collect_diff(self, base_identity: RepositorySourceIdentity) -> DiffReceipt:
        del base_identity
        self._blocked()

    def destroy(self) -> CleanupReceipt:
        self._blocked()

    def _blocked(self) -> None:
        if self._availability.status == "DOCKER_EXECUTABLE_MISSING":
            raise SandboxUnavailable("SANDBOX_DOCKER_EXECUTABLE_MISSING")
        if self._availability.status == "DOCKER_EXECUTABLE_INVALID":
            raise SandboxUnavailable("SANDBOX_DOCKER_EXECUTABLE_INVALID")
        raise SandboxUnavailable("SANDBOX_DOCKER_DAEMON_AND_TOOLBOX_UNCERTIFIED")


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
