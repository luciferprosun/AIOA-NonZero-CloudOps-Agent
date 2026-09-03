"""Typed boundary for the fixed repository-owned W4 runtime probe."""

from __future__ import annotations

from typing import Literal, Protocol

from aioa_cloudops_agent.nz.contracts import NonZeroContract

from .contracts import W2_VERIFICATION_PROFILE_ID


class TrustedRenderStartProfileFailure(RuntimeError):
    """A normalized profile failure that never contains token or host-private data."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class TrustedRenderStartProfileResult(NonZeroContract):
    """Bounded normalized proof returned by the fixed trusted probe."""

    verification_profile_id: Literal["render_start_contract_v1"] = (
        W2_VERIFICATION_PROFILE_ID
    )
    missing_token_fails_closed: Literal[True] = True
    token_mode_0600: Literal[True] = True
    bootstrap_secret_absent: Literal[True] = True
    child_argv_exact: Literal[True] = True
    health_passed: Literal[True] = True
    readiness_passed: Literal[True] = True
    external_egress_count: Literal[0] = 0
    aws_call_count: Literal[0] = 0
    workspace_code_executions: Literal[0] = 0
    arbitrary_command_executions: Literal[0] = 0
    process_executions: Literal[1] = 1


class TrustedRenderStartProfile(Protocol):
    """Server-selected profile dependency; its API takes no model-controlled values."""

    def run(self) -> TrustedRenderStartProfileResult: ...
