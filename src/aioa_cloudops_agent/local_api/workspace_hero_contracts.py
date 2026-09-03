"""Strict judge-safe contracts for the fixed W5 workspace hero scenario."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from aioa_cloudops_agent.nz import ApprovalDecision, contains_sensitive_material
from aioa_cloudops_agent.nz.contracts import NonZeroContract
from aioa_cloudops_agent.nz.identifiers import Sha256Digest, Uuid7Identifier
from aioa_cloudops_agent.workspace import WorkspaceAuthorityState

WORKSPACE_HERO_SCENARIO_ID = "FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1"
WORKSPACE_HERO_RESPONSE_MAX_BYTES = 65_536


class WorkspaceHeroStartRequest(NonZeroContract):
    """Start only the one server-owned W5 scenario."""

    scenario_id: Literal["FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1"] = (
        WORKSPACE_HERO_SCENARIO_ID
    )


class WorkspaceHeroDecisionRequest(NonZeroContract):
    """A human supplies no mutation material, only the current request binding."""

    request_fingerprint: Sha256Digest
    decision: ApprovalDecision


class WorkspaceHeroResumeRequest(NonZeroContract):
    """Keep the human decision and the separate effect gesture visibly distinct."""

    confirm_execution: Literal[True]


class WorkspaceHeroTimelineCategory(StrEnum):
    FACT = "FACT"
    AGENT_INFERENCE = "AGENT_INFERENCE"
    PATCH_PROPOSAL = "PATCH_PROPOSAL"
    POLICY_DECISION = "POLICY_DECISION"
    HUMAN_DECISION = "HUMAN_DECISION"
    ACTION = "ACTION"
    VERIFICATION = "VERIFICATION"
    RECOVERY_REPLAY = "RECOVERY/REPLAY"


class WorkspaceHeroTimelineStatus(StrEnum):
    COMPLETE = "COMPLETE"
    CURRENT = "CURRENT"
    PENDING = "PENDING"
    SAFE_STOP = "SAFE_STOP"


class WorkspaceHeroTimelineItem(NonZeroContract):
    stage: Literal[
        "OBSERVE",
        "EVIDENCE",
        "ROOT_CAUSE",
        "PATCH_PROPOSAL",
        "POLICY",
        "HUMAN_DECISION",
        "PATCH_EFFECT",
        "VERIFICATION",
        "RECEIPT",
        "RECOVERY_REPLAY",
    ]
    category: WorkspaceHeroTimelineCategory
    status: WorkspaceHeroTimelineStatus
    title: str = Field(min_length=1, max_length=96)
    summary: str = Field(min_length=1, max_length=320)
    authority_source: str = Field(min_length=1, max_length=96)
    evidence_fingerprint: Sha256Digest | None = None


class WorkspaceHeroApprovalCard(NonZeroContract):
    """Display-only facts derived exclusively from durable W2/W3 truth."""

    scenario: Literal["Failed deployment -> verified fix"] = (
        "Failed deployment -> verified fix"
    )
    target: Literal["render.yaml"] = "render.yaml"
    field_path: Literal["services[0].dockerCommand"] = "services[0].dockerCommand"
    proposed_change: Literal[
        "long inline bootstrap -> /usr/local/bin/aioa-render-start"
    ] = "long inline bootstrap -> /usr/local/bin/aioa-render-start"
    workspace_fingerprint: Sha256Digest
    proposal_fingerprint: Sha256Digest
    patch_fingerprint: Sha256Digest
    request_fingerprint: Sha256Digest | None = None
    evidence: tuple[
        Literal[
            "deployment.log",
            "render.yaml",
            "scripts/render_start.sh",
            "expected_runtime_contract.json",
        ],
        ...,
    ]
    expected_verification: tuple[str, ...] = Field(min_length=5, max_length=5)
    risk: Literal["PLAN_AND_CONFIRM"] = "PLAN_AND_CONFIRM"
    rollback: str = Field(min_length=1, max_length=512)
    warning: Literal[
        "This approval is valid only for this exact proposal, workspace, base state and patch."
    ] = "This approval is valid only for this exact proposal, workspace, base state and patch."

    @field_validator("evidence")
    @classmethod
    def validate_evidence_order(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        expected = (
            "deployment.log",
            "render.yaml",
            "scripts/render_start.sh",
            "expected_runtime_contract.json",
        )
        if value != expected:
            raise ValueError("approval evidence order must remain canonical")
        return value


class WorkspaceHeroBeforeProof(NonZeroContract):
    deployment_start_contract: Literal["FAIL"] = "FAIL"
    error: Literal["File name too long / exit 127"] = "File name too long / exit 127"


class WorkspaceHeroAfterProof(NonZeroContract):
    patch_scope: Literal["EXACT", "PENDING"]
    target_hash: Literal["MATCH", "PENDING"]
    startup_executable: Literal["FIXED", "PENDING"]
    token_mode: Literal["0600", "PENDING"]
    bootstrap_secret_in_child_env: Literal["ABSENT", "PENDING"]
    health: Literal["PASS", "PENDING"]
    ready: Literal["PASS", "PENDING"]
    external_egress: Literal[0]
    aws_calls: Literal[0]
    final: Literal["SUCCESS_WITH_EVIDENCE", "PENDING"]


class WorkspaceHeroVerificationView(NonZeroContract):
    profile_id: Literal["render_start_contract_v1"] = "render_start_contract_v1"
    disposition: Literal["VERIFIED"]
    report_fingerprint: Sha256Digest
    receipt_fingerprint: Sha256Digest
    proof_origin: Literal["APPLY_RECEIPT", "RECOVERY_READ_BACK"]
    checks_passed: int = Field(ge=1, le=32)
    checks_total: int = Field(ge=1, le=32)
    persisted_before_success: Literal[True] = True

    @model_validator(mode="after")
    def validate_all_checks_passed(self) -> Self:
        if self.checks_passed != self.checks_total:
            raise ValueError("verified projection requires every check to pass")
        return self


class WorkspaceHeroReplayView(NonZeroContract):
    status: Literal["AVAILABLE", "REPLAY_REJECTED_RECONCILED"]
    approval_already_consumed: bool
    patch_apply_count: int = Field(ge=0, le=1)
    additional_mutation_delta: Literal[0] = 0
    additional_profile_executions: Literal[0] = 0


class WorkspaceHeroRuntimeView(NonZeroContract):
    experience_mode: Literal["DEMO SANDBOX"] = "DEMO SANDBOX"
    provider_mode: Literal["PORTABLE / MOCK"] = "PORTABLE / MOCK"
    agent_framework: Literal["STRANDS"] = "STRANDS"
    authority: Literal["HUMAN AUTHORITY REQUIRED"] = "HUMAN AUTHORITY REQUIRED"
    aws_writes: Literal["NO LIVE AWS WRITES"] = "NO LIVE AWS WRITES"
    external_egress: Literal["NO EXTERNAL EGRESS"] = "NO EXTERNAL EGRESS"


class WorkspaceHeroProjection(NonZeroContract):
    """Bounded browser view; raw durable records and private paths never cross the API."""

    schema_version: Literal[1] = 1
    scenario_id: Literal["FAILED_RENDER_DEPLOYMENT_VERIFIED_FIX_V1"] = (
        WORKSPACE_HERO_SCENARIO_ID
    )
    scenario_title: Literal["Fix a Failed Deployment Safely"] = (
        "Fix a Failed Deployment Safely"
    )
    headline: Literal[
        "The model proposes. The human authorizes. Evidence decides."
    ] = "The model proposes. The human authorizes. Evidence decides."
    hero_sentence: Literal[
        "AIOA turns a failed deployment into one exact human-approved fix, executes it once, and independently proves the service can start."
    ] = "AIOA turns a failed deployment into one exact human-approved fix, executes it once, and independently proves the service can start."
    run_id: Uuid7Identifier
    state: WorkspaceAuthorityState
    success_with_evidence: bool
    model_output_is_authority: Literal[False] = False
    human_approval_is_success: Literal[False] = False
    patch_applied_is_success: Literal[False] = False
    runtime: WorkspaceHeroRuntimeView = Field(default_factory=WorkspaceHeroRuntimeView)
    incident_facts: tuple[str, ...] = Field(min_length=3, max_length=3)
    root_cause: str = Field(min_length=1, max_length=320)
    alternative_hypothesis: str = Field(min_length=1, max_length=240)
    approval_card: WorkspaceHeroApprovalCard
    patch_diff: str = Field(min_length=1, max_length=12_288)
    before: WorkspaceHeroBeforeProof = Field(default_factory=WorkspaceHeroBeforeProof)
    after: WorkspaceHeroAfterProof
    verification: WorkspaceHeroVerificationView | None = None
    human_decision: Literal["APPROVED", "DENIED", "PENDING"]
    workspace_mutation_count: int = Field(ge=0, le=1)
    executor_receipt_present: bool
    verification_receipt_present: bool
    replay: WorkspaceHeroReplayView | None = None
    recovery_badge: Literal["W4 RECOVERY / RECONCILIATION CERTIFIED"] = (
        "W4 RECOVERY / RECONCILIATION CERTIFIED"
    )
    timeline: tuple[WorkspaceHeroTimelineItem, ...] = Field(min_length=10, max_length=10)

    @model_validator(mode="after")
    def validate_public_truth(self) -> Self:
        terminal = self.state is WorkspaceAuthorityState.SUCCESS_WITH_EVIDENCE
        if self.success_with_evidence != terminal:
            raise ValueError("success flag must follow durable terminal state")
        if terminal != (self.verification is not None and self.verification_receipt_present):
            raise ValueError("success requires the visible persisted verification receipt")
        if self.workspace_mutation_count != int(self.executor_receipt_present):
            raise ValueError("mutation count must follow the exact executor receipt")
        payload = self.model_dump(mode="json")
        if contains_sensitive_material(payload):
            raise ValueError("workspace hero projection contains sensitive material")
        rendered = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(rendered) > WORKSPACE_HERO_RESPONSE_MAX_BYTES:
            raise ValueError("workspace hero projection exceeds its public response bound")
        return self
