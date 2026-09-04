"""Strict, taint-preserving contracts for GitHub MCP read context."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.nz import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.nz.contracts import NonZeroContract

GITHUB_REMOTE_TAINT = "REMOTE_UNTRUSTED_DATA"
_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REPOSITORY = re.compile(r"^[A-Za-z0-9._-]{1,100}$")
_REF = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,255}$")
_SHA = re.compile(r"^[0-9a-f]{40}$")


class GitHubVisibility(StrEnum):
    """Normalized repository visibility without inferring unavailable provider data."""

    PUBLIC = "PUBLIC"
    PRIVATE = "PRIVATE"
    INTERNAL = "INTERNAL"
    UNKNOWN = "UNKNOWN"


class GitHubRepositoryIdentity(NonZeroContract):
    """Exact namespace for every GitHub read and normalized context object."""

    owner: str
    name: str
    canonical_url: str

    @field_validator("owner")
    @classmethod
    def validate_owner(cls, value: str) -> str:
        if _OWNER.fullmatch(value) is None:
            raise ValueError("GitHub owner is not canonical")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        if _REPOSITORY.fullmatch(value) is None or value in {".", ".."}:
            raise ValueError("GitHub repository name is not canonical")
        return value

    @model_validator(mode="after")
    def validate_url_binding(self) -> Self:
        expected = f"https://github.com/{self.owner}/{self.name}"
        if self.canonical_url != expected:
            raise ValueError("GitHub canonical_url does not match owner/name")
        return self

    @classmethod
    def create(cls, owner: str, name: str) -> GitHubRepositoryIdentity:
        return cls(owner=owner, name=name, canonical_url=f"https://github.com/{owner}/{name}")


class GitHubObservation(NonZeroContract):
    """Freshness and content identity retained separately for deduplicated reads."""

    observation_id: Uuid7Identifier
    source_tool: str = Field(pattern=r"^[a-z][a-z0-9_]{1,95}$")
    request_sha256: Sha256Digest
    content_sha256: Sha256Digest
    evidence_key: Sha256Digest
    observed_at: datetime
    truncated: bool = False
    taint: Literal["REMOTE_UNTRUSTED_DATA"] = GITHUB_REMOTE_TAINT

    @field_validator("observed_at")
    @classmethod
    def validate_observed_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() != timedelta(0):
            raise ValueError("GitHub observation must use timezone-aware UTC")
        return value


class GitHubToolDescriptor(NonZeroContract):
    """Digest-only inventory entry; raw schemas/descriptions are not authority."""

    name: str = Field(pattern=r"^[a-z][a-z0-9_]{1,95}$")
    read_only_hint: Literal[True] = True
    schema_sha256: Sha256Digest
    description_sha256: Sha256Digest


class GitHubToolInventory(NonZeroContract):
    """Effective server inventory after the server-enforced read-only filter."""

    protocol_version: Literal["2025-06-18"] = "2025-06-18"
    server_name: Literal["github-mcp-server"] = "github-mcp-server"
    server_version: Literal["1.0.5"] = "1.0.5"
    server_commit: Literal["c471ae94bb04059dc26e12c305e219c8fd4299e4"] = (
        "c471ae94bb04059dc26e12c305e219c8fd4299e4"
    )
    toolsets: tuple[
        Literal["repos"],
        Literal["issues"],
        Literal["pull_requests"],
        Literal["actions"],
    ] = (
        "repos",
        "issues",
        "pull_requests",
        "actions",
    )
    tools: tuple[GitHubToolDescriptor, ...] = Field(min_length=1, max_length=128)
    inventory_sha256: Sha256Digest
    read_only: Literal[True] = True
    lockdown_mode: Literal[True] = True
    runtime_write_tools: Literal[0] = 0

    @field_validator("tools")
    @classmethod
    def validate_tools(
        cls,
        value: tuple[GitHubToolDescriptor, ...],
    ) -> tuple[GitHubToolDescriptor, ...]:
        names = tuple(item.name for item in value)
        if names != tuple(sorted(set(names))):
            raise ValueError("GitHub MCP tools must be unique and sorted")
        return value


class RepoContext(NonZeroContract):
    """Repository/ref identity normalized from read-only MCP observations."""

    repository: GitHubRepositoryIdentity
    default_branch: str
    requested_ref: str
    observed_sha: str
    visibility: GitHubVisibility
    observation: GitHubObservation
    taint: Literal["REMOTE_UNTRUSTED_DATA"] = GITHUB_REMOTE_TAINT

    @field_validator("default_branch", "requested_ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        if _REF.fullmatch(value) is None or ".." in value.split("/"):
            raise ValueError("GitHub ref is not canonical")
        return value

    @field_validator("observed_sha")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if _SHA.fullmatch(value) is None:
            raise ValueError("GitHub observed_sha is not a full lowercase commit SHA")
        return value


class IssueContext(NonZeroContract):
    """Bounded issue data that cannot carry policy or tool authority."""

    repository: GitHubRepositoryIdentity
    number: int = Field(gt=0)
    title: str = Field(max_length=512)
    body: str = Field(max_length=64 * 1024)
    state: Literal["OPEN", "CLOSED"]
    labels: tuple[str, ...] = Field(default=(), max_length=100)
    author: str | None = Field(default=None, max_length=256)
    url: str = Field(min_length=1, max_length=2048)
    observation: GitHubObservation
    taint: Literal["REMOTE_UNTRUSTED_DATA"] = GITHUB_REMOTE_TAINT

    @field_validator("labels")
    @classmethod
    def validate_labels(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if value != tuple(sorted(set(value))):
            raise ValueError("GitHub issue labels must be unique and sorted")
        return value


class IssueContextPage(NonZeroContract):
    repository: GitHubRepositoryIdentity
    issues: tuple[IssueContext, ...] = Field(max_length=100)
    observation: GitHubObservation


class PullRequestContext(NonZeroContract):
    """Bounded PR identity and CI summary; remote text remains tainted data."""

    repository: GitHubRepositoryIdentity
    number: int = Field(gt=0)
    title: str = Field(max_length=512)
    body: str = Field(max_length=64 * 1024)
    state: Literal["OPEN", "CLOSED", "MERGED"]
    base_ref: str
    base_sha: str
    head_ref: str
    head_sha: str
    changed_files: int | None = Field(default=None, ge=0)
    commits: int | None = Field(default=None, ge=0)
    checks_summary: str = Field(default="", max_length=8192)
    url: str = Field(min_length=1, max_length=2048)
    observation: GitHubObservation
    taint: Literal["REMOTE_UNTRUSTED_DATA"] = GITHUB_REMOTE_TAINT

    @field_validator("base_ref", "head_ref")
    @classmethod
    def validate_ref(cls, value: str) -> str:
        if _REF.fullmatch(value) is None or ".." in value.split("/"):
            raise ValueError("pull-request ref is not canonical")
        return value

    @field_validator("base_sha", "head_sha")
    @classmethod
    def validate_sha(cls, value: str) -> str:
        if _SHA.fullmatch(value) is None:
            raise ValueError("pull-request SHA is not canonical")
        return value


class PullRequestContextPage(NonZeroContract):
    repository: GitHubRepositoryIdentity
    pull_requests: tuple[PullRequestContext, ...] = Field(max_length=100)
    observation: GitHubObservation


class ActionsContext(NonZeroContract):
    """Bounded workflow/run context with explicit truncation and provenance."""

    repository: GitHubRepositoryIdentity
    workflow_id: str | None = Field(default=None, max_length=256)
    run_id: int | None = Field(default=None, gt=0)
    job_id: int | None = Field(default=None, gt=0)
    name: str = Field(default="", max_length=512)
    status: str = Field(default="UNKNOWN", max_length=64)
    conclusion: str | None = Field(default=None, max_length=64)
    head_branch: str | None = Field(default=None, max_length=256)
    head_sha: str | None = None
    url: str | None = Field(default=None, max_length=2048)
    log_context: str = Field(default="", max_length=64 * 1024)
    log_truncated: bool = False
    observation: GitHubObservation
    taint: Literal["REMOTE_UNTRUSTED_DATA"] = GITHUB_REMOTE_TAINT

    @field_validator("head_sha")
    @classmethod
    def validate_optional_sha(cls, value: str | None) -> str | None:
        if value is not None and _SHA.fullmatch(value) is None:
            raise ValueError("Actions head SHA is not canonical")
        return value


class ActionsContextPage(NonZeroContract):
    repository: GitHubRepositoryIdentity
    actions: tuple[ActionsContext, ...] = Field(max_length=100)
    observation: GitHubObservation
