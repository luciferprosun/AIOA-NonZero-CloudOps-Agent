"""Closed contracts for a subordinate, non-authoritative coding worker."""

from __future__ import annotations

import json
from collections.abc import Iterator
from enum import StrEnum
from pathlib import Path
from typing import Literal, Protocol, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from aioa_cloudops_agent.nz import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.redaction import contains_sensitive_material


class WorkerTerminalStatus(StrEnum):
    """Terminal truth for one worker task; success is never inferred from output text."""

    SUCCESS = "SUCCESS"
    CANCELLED = "CANCELLED"
    TIMEOUT = "TIMEOUT"
    WORKER_CRASH = "WORKER_CRASH"
    PROTOCOL_FAILURE = "PROTOCOL_FAILURE"
    POLICY_DENIED = "POLICY_DENIED"


class WorkerEventKind(StrEnum):
    """Normalized App Server events admitted into the AIOA control plane."""

    SESSION_STARTED = "SESSION_STARTED"
    TASK_ACCEPTED = "TASK_ACCEPTED"
    TURN_STARTED = "TURN_STARTED"
    ITEM_STARTED = "ITEM_STARTED"
    ITEM_COMPLETED = "ITEM_COMPLETED"
    DIFF_UPDATED = "DIFF_UPDATED"
    COMMAND_COMPLETED = "COMMAND_COMPLETED"
    APPROVAL_DENIED = "APPROVAL_DENIED"
    TURN_COMPLETED = "TURN_COMPLETED"
    TERMINAL_FAILURE = "TERMINAL_FAILURE"


class WorkerCapabilityProfile(NonZeroContract):
    """Server-owned Phase 2 authority envelope for a disposable local fixture."""

    profile_id: Literal["CODEX_LOCAL_FIXTURE_V1"] = "CODEX_LOCAL_FIXTURE_V1"
    workspace_read: Literal[True] = True
    workspace_write: Literal[True] = True
    local_process: Literal[True] = True
    network_access: Literal[False] = False
    github_read: Literal[False] = False
    github_write: Literal[False] = False
    aws_access: Literal[False] = False
    host_package_install: Literal[False] = False
    max_changed_files: int = Field(default=16, ge=1, le=64)
    max_diff_bytes: int = Field(default=512 * 1024, ge=1, le=1024 * 1024)


CODEX_LOCAL_FIXTURE_V1 = WorkerCapabilityProfile()


class WorkerWorkspaceIdentity(NonZeroContract):
    """Content-bound identity for one test-owned disposable workspace."""

    workspace_id: Uuid7Identifier
    root_path: str = Field(min_length=1, max_length=4096)
    expected_base_digest: Sha256Digest
    disposable: Literal[True] = True

    @field_validator("root_path")
    @classmethod
    def validate_root_path(cls, value: str) -> str:
        candidate = Path(value)
        if not candidate.is_absolute() or candidate != Path(candidate.as_posix()):
            raise ValueError("worker workspace root must be an absolute normalized path")
        if "\x00" in value:
            raise ValueError("worker workspace root contains a forbidden character")
        return value


class WorkerTask(NonZeroContract):
    """One bounded local task; it deliberately has no remote credential/authority field."""

    run_id: Uuid7Identifier
    task_id: Uuid7Identifier
    workspace: WorkerWorkspaceIdentity
    instruction: str = Field(min_length=1, max_length=16 * 1024)
    capability_profile: Literal["CODEX_LOCAL_FIXTURE_V1"] = "CODEX_LOCAL_FIXTURE_V1"
    timeout_seconds: float = Field(default=180.0, gt=0, le=900)
    max_events: int = Field(default=512, ge=8, le=4096)

    @field_validator("instruction")
    @classmethod
    def reject_secret_bearing_instruction(cls, value: str) -> str:
        if value != value.strip():
            raise ValueError("worker instruction must be canonical text")
        if contains_sensitive_material(value):
            raise ValueError("worker instruction contains credential-shaped material")
        return value


class WorkerSession(NonZeroContract):
    """Negotiated local App Server session identity."""

    session_id: Uuid7Identifier
    protocol_version: Literal[2] = 2
    server_user_agent: str = Field(min_length=1, max_length=256)
    workspace_root: str = Field(min_length=1, max_length=4096)


class WorkerTaskHandle(NonZeroContract):
    """Correlation identity binding AIOA task, App Server thread, and turn."""

    session_id: Uuid7Identifier
    run_id: Uuid7Identifier
    task_id: Uuid7Identifier
    thread_id: str = Field(min_length=1, max_length=256)
    turn_id: str = Field(min_length=1, max_length=256)


class WorkerCommandResult(NonZeroContract):
    """Bounded command observation emitted by Codex; never execution authority."""

    item_id: str = Field(min_length=1, max_length=256)
    command: str = Field(min_length=1, max_length=4096)
    status: Literal["completed", "failed", "declined"]
    exit_code: int | None = Field(default=None, ge=-1, le=255)
    output: str = Field(default="", max_length=32 * 1024)

    @field_validator("command", "output")
    @classmethod
    def reject_sensitive_command_material(cls, value: str) -> str:
        if contains_sensitive_material(value):
            raise ValueError("worker command observation contains credential-shaped material")
        return value


class WorkerEvent(NonZeroContract):
    """Strict, sequence-bound event normalized from an untrusted protocol message."""

    event_id: Uuid7Identifier
    run_id: Uuid7Identifier
    task_id: Uuid7Identifier
    sequence: int = Field(ge=1, le=1_000_000)
    kind: WorkerEventKind
    source_method: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9/._-]{0,127}$")
    payload: dict[str, JsonValue] = Field(default_factory=dict)

    @field_validator("payload")
    @classmethod
    def bound_payload(cls, value: dict[str, JsonValue]) -> dict[str, JsonValue]:
        encoded = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        )
        if len(encoded.encode("utf-8")) > 128 * 1024:
            raise ValueError("worker event payload exceeds the normalized bound")
        if contains_sensitive_material(encoded):
            raise ValueError("worker event payload contains credential-shaped material")
        return value


class WorkerResult(NonZeroContract):
    """Terminal candidate result owned by AIOA, not a remote-write authorization."""

    run_id: Uuid7Identifier
    task_id: Uuid7Identifier
    status: WorkerTerminalStatus
    candidate_diff: str = Field(default="", max_length=1024 * 1024)
    changed_files: tuple[str, ...] = Field(default=(), max_length=64)
    commands: tuple[WorkerCommandResult, ...] = Field(default=(), max_length=128)
    summary: str = Field(default="", max_length=32 * 1024)
    failure_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z][A-Z0-9_]{2,95}$",
    )
    evidence_digests: tuple[Sha256Digest, ...] = Field(default=(), max_length=128)
    github_mutations: Literal[0] = 0
    aws_calls: Literal[0] = 0

    @field_validator("changed_files")
    @classmethod
    def validate_changed_files(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        canonical: list[str] = []
        for item in value:
            path = Path(item)
            if path.is_absolute() or ".." in path.parts or item != path.as_posix():
                raise ValueError("worker changed file must be a canonical relative path")
            canonical.append(item)
        if tuple(sorted(set(canonical))) != value:
            raise ValueError("worker changed files must be unique and sorted")
        return value

    @model_validator(mode="after")
    def validate_terminal_truth(self) -> Self:
        if self.status is WorkerTerminalStatus.SUCCESS:
            if self.failure_code is not None:
                raise ValueError("successful worker result forbids failure_code")
        elif self.failure_code is None:
            raise ValueError("non-success worker result requires failure_code")
        if contains_sensitive_material(self.candidate_diff) or contains_sensitive_material(self.summary):
            raise ValueError("worker result contains credential-shaped material")
        return self


class CodingWorker(Protocol):
    """Replaceable subordinate-worker boundary; AIOA retains policy and authority."""

    def start(self, task: WorkerTask) -> WorkerSession: ...

    def send_task(self, task: WorkerTask) -> WorkerTaskHandle: ...

    def stream_events(self, handle: WorkerTaskHandle) -> Iterator[WorkerEvent]: ...

    def receive_result(self, handle: WorkerTaskHandle) -> WorkerResult: ...

    def pause_or_interrupt(self, handle: WorkerTaskHandle) -> None: ...

    def cancel(self, handle: WorkerTaskHandle) -> None: ...

    def close(self) -> None: ...

