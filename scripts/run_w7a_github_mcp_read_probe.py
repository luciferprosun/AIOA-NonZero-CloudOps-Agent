#!/usr/bin/env python3
"""Run the W7A Phase 3 live GitHub MCP proof without remote mutation."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import cast

from pydantic import SecretStr

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = REPOSITORY_ROOT / "src"
if SOURCE_ROOT.as_posix() not in sys.path:
    sys.path.insert(0, SOURCE_ROOT.as_posix())

from aioa_cloudops_agent.github import (  # noqa: E402
    ActionsContextPage,
    GitHubMcpConfig,
    GitHubMcpProtocolError,
    GitHubMcpReadPlane,
    GitHubMcpStdioTransport,
    GitHubRepositoryIdentity,
    IssueContextPage,
    PullRequestContextPage,
    RepoContext,
)
from aioa_cloudops_agent.nz import ResultStatus, contains_sensitive_material  # noqa: E402

EXPECTED_READ_TOOLS = frozenset(
    {
        "actions_get",
        "actions_list",
        "get_commit",
        "get_file_contents",
        "get_job_logs",
        "get_label",
        "get_latest_release",
        "get_release_by_tag",
        "get_tag",
        "issue_read",
        "list_branches",
        "list_commits",
        "list_issue_types",
        "list_issues",
        "list_pull_requests",
        "list_releases",
        "list_repository_collaborators",
        "list_tags",
        "pull_request_read",
        "search_code",
        "search_issues",
        "search_pull_requests",
        "search_repositories",
    }
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary", required=True, type=Path)
    parser.add_argument("--owner", required=True)
    parser.add_argument("--repo", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--expected-sha", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=30.0)
    return parser.parse_args()


def _credential_from_gh() -> SecretStr:
    environment = {
        key: value
        for key, value in os.environ.items()
        if key in {"HOME", "PATH", "XDG_CONFIG_HOME", "XDG_RUNTIME_DIR"}
    }
    try:
        completed = subprocess.run(
            ("gh", "auth", "token", "--hostname", "github.com"),
            check=True,
            capture_output=True,
            env=environment,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("GITHUB_CREDENTIAL_PROVIDER_UNAVAILABLE") from error
    raw = completed.stdout.strip()
    del completed
    if len(raw) < 8:
        raise RuntimeError("GITHUB_CREDENTIAL_PROVIDER_EMPTY")
    protected = SecretStr(raw)
    raw = "destroyed"
    del raw
    return protected


def _must_succeed(result: object, label: str) -> object:
    status = getattr(result, "status", None)
    value = getattr(result, "value", None)
    if status is not ResultStatus.SUCCESS or value is None:
        raise RuntimeError(f"{label}_READ_FAILED")
    return value


def _evidence_key(value: object) -> str:
    observation = getattr(value, "observation", None)
    key = getattr(observation, "evidence_key", None)
    if not isinstance(key, str) or len(key) != 64:
        raise RuntimeError("GITHUB_OBSERVATION_IDENTITY_INVALID")
    return key


def main() -> int:
    arguments = _arguments()
    repository = GitHubRepositoryIdentity.create(arguments.owner, arguments.repo)
    config = GitHubMcpConfig(
        binary_path=arguments.binary.resolve(strict=True).as_posix(),
        repository=repository,
        request_timeout_seconds=arguments.timeout_seconds,
    )
    credential = _credential_from_gh()
    transport = GitHubMcpStdioTransport(config, credential)
    del credential
    plane = GitHubMcpReadPlane(config, transport)
    try:
        inventory = plane.start()
        inventory_names = frozenset(item.name for item in inventory.tools)
        if inventory_names != EXPECTED_READ_TOOLS or inventory.runtime_write_tools != 0:
            raise RuntimeError("GITHUB_MCP_EFFECTIVE_INVENTORY_MISMATCH")

        denied = False
        try:
            plane.assert_read_tool("create_issue")
        except GitHubMcpProtocolError:
            denied = True
        if not denied:
            raise RuntimeError("GITHUB_MCP_WRITE_DENIAL_FAILED")

        before = (
            cast(RepoContext, _must_succeed(plane.read_repository(arguments.ref), "REPOSITORY")),
            cast(IssueContextPage, _must_succeed(plane.read_issues(per_page=20), "ISSUES")),
            cast(
                PullRequestContextPage,
                _must_succeed(plane.read_pull_requests(per_page=20), "PULL_REQUESTS"),
            ),
            cast(ActionsContextPage, _must_succeed(plane.read_actions(per_page=20), "ACTIONS")),
        )
        after = (
            cast(RepoContext, _must_succeed(plane.read_repository(arguments.ref), "REPOSITORY")),
            cast(IssueContextPage, _must_succeed(plane.read_issues(per_page=20), "ISSUES")),
            cast(
                PullRequestContextPage,
                _must_succeed(plane.read_pull_requests(per_page=20), "PULL_REQUESTS"),
            ),
            cast(ActionsContextPage, _must_succeed(plane.read_actions(per_page=20), "ACTIONS")),
        )
        before_sha = getattr(before[0], "observed_sha", None)
        after_sha = getattr(after[0], "observed_sha", None)
        if before_sha != arguments.expected_sha or after_sha != arguments.expected_sha:
            raise RuntimeError("GITHUB_REMOTE_REF_IDENTITY_MISMATCH")
        if tuple(_evidence_key(item) for item in before) != tuple(
            _evidence_key(item) for item in after
        ):
            raise RuntimeError("GITHUB_REMOTE_CONTEXT_CHANGED_DURING_PROOF")
        diagnostics = transport.diagnostics()
        if contains_sensitive_material(diagnostics):
            raise RuntimeError("GITHUB_MCP_DIAGNOSTIC_SECRET_LEAK")

        issue_count = len(before[1].issues)
        pull_request_count = len(before[2].pull_requests)
        actions_count = len(before[3].actions)
        report = {
            "actions_context": "PASS" if actions_count else "NOT_APPLICABLE_NO_FIXTURE",
            "actions_count": actions_count,
            "aws_calls": 0,
            "effective_inventory_sha256": inventory.inventory_sha256,
            "effective_tool_count": len(inventory.tools),
            "github_mutations": 0,
            "issue_context": "PASS" if issue_count else "NOT_APPLICABLE_NO_FIXTURE",
            "issue_count": issue_count,
            "live_read_proof": "PASS",
            "pull_request_context": "PASS" if pull_request_count else "NOT_APPLICABLE_NO_FIXTURE",
            "pull_request_count": pull_request_count,
            "remote_context_stable": True,
            "remote_ref_sha": before_sha,
            "repository_context": "PASS",
            "runtime_write_tools": inventory.runtime_write_tools,
            "write_call_denial": "PASS",
        }
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    finally:
        plane.close()


if __name__ == "__main__":
    raise SystemExit(main())
